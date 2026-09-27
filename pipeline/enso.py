"""
Build public/data/enso.json.

Sources
-------
* NOAA CPC Relative Oceanic Nino Index (RONI), operational at CPC since
  February 2026. 3-month running mean of relative Nino-3.4 SST anomalies.
  https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/
* Fallback: NOAA CPC Oceanic Nino Index (ONI, ERSSTv5), used only if RONI
  cannot be retrieved. The output records which index was used.
  https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
* ECMWF SEAS5 monthly sea-surface-temperature anomaly (ensemble mean, relative
  to SEAS5 model climatology) via the Open-Meteo Seasonal API, averaged over a
  regular grid of points inside the Nino-3.4 box (5S-5N, 170W-120W).

Episode definition (CPC): at least five consecutive overlapping 3-month
seasons at or above +0.5 C (El Nino) or at or below -0.5 C (La Nina).

Run:  python pipeline/enso.py --out public/data/enso.json
The script exits non-zero if no ENSO index can be retrieved. It never
writes placeholder values.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import datetime, timezone

import requests

SEASONS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ",
           "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
# Centre month of each 3-month season (DJF -> January, ..., NDJ -> December)
SEASON_CENTRE = {s: i + 1 for i, s in enumerate(SEASONS)}

RONI_PAGE = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/"
RONI_ASCII_CANDIDATES = [
    "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt",
    "https://www.cpc.ncep.noaa.gov/data/indices/roni.ascii.txt",
]
ONI_ASCII = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
SEASONAL_API = "https://seasonal-api.open-meteo.com/v1/seasonal"

UA = {"User-Agent": "ENSOwatch data pipeline (github.com/Kripankc/el-nino-drought-agent)"}


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def parse_ascii(text: str) -> dict[tuple[int, int], float]:
    """
    Parse CPC-style ascii tables:  SEAS  YR  [TOTAL]  ANOM
    The anomaly is taken as the LAST numeric column on each data row.
    Returns {(year, centre_month): value}.
    """
    out: dict[tuple[int, int], float] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0].upper() not in SEASON_CENTRE:
            continue
        try:
            year = int(parts[1])
            val = float(parts[-1])
        except ValueError:
            continue
        if val <= -90:  # CPC missing-value sentinel (-99.9)
            continue
        out[(year, SEASON_CENTRE[parts[0].upper()])] = val
    return out


def parse_html_table(html: str) -> dict[tuple[int, int], float]:
    """
    Parse the CPC HTML table layout: one row per year, columns Year, DJF..NDJ.
    """
    import pandas as pd

    tables = pd.read_html(io.StringIO(html))
    out: dict[tuple[int, int], float] = {}
    for t in tables:
        # Header may be the first row instead of the column index
        cols = [str(c).strip().upper() for c in t.columns]
        if "DJF" not in cols:
            first = [str(v).strip().upper() for v in t.iloc[0].tolist()]
            if "DJF" in first:
                t = t.iloc[1:].copy()
                t.columns = first
                cols = first
            else:
                continue
        year_col = next((c for c in t.columns if str(c).strip().upper() in ("YEAR", "YR")), None)
        if year_col is None:
            continue
        colmap = {c: str(c).strip().upper() for c in t.columns}
        for _, row in t.iterrows():
            try:
                year = int(str(row[year_col]).strip())
            except ValueError:
                continue  # repeated header rows inside the table
            for c, name in colmap.items():
                if name in SEASON_CENTRE:
                    try:
                        v = float(str(row[c]).strip())
                    except ValueError:
                        continue
                    if v > -90:
                        out[(year, SEASON_CENTRE[name])] = v
    return out


# --------------------------------------------------------------------------
# Episodes
# --------------------------------------------------------------------------
def to_series(values: dict[tuple[int, int], float]) -> tuple[int, int, list[float | None]]:
    """Dense monthly list from the first to the last available season."""
    keys = sorted(values)
    (y0, m0), (y1, m1) = keys[0], keys[-1]
    series: list[float | None] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        series.append(values.get((y, m)))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return y0, m0, series


def find_episodes(series: list[float | None], min_len: int = 5, thr: float = 0.5) -> list[dict]:
    """
    CPC definition: >= min_len consecutive overlapping seasons with
    value >= +thr (El Nino) or <= -thr (La Nina). Indices refer to `series`.
    A missing value breaks a run.
    """
    episodes = []
    for kind, test in (("El Nino", lambda v: v >= thr), ("La Nina", lambda v: v <= -thr)):
        start = None
        for i, v in enumerate(series + [None]):
            ok = v is not None and test(v)
            if ok and start is None:
                start = i
            elif not ok and start is not None:
                if i - start >= min_len:
                    seg = series[start:i]
                    peak = max(seg) if kind == "El Nino" else min(seg)
                    episodes.append({"type": kind, "start": start, "end": i - 1, "peak": peak})
                start = None
    return sorted(episodes, key=lambda e: e["start"])


def episode_open_at_end(series: list[float | None], thr: float = 0.5) -> dict | None:
    """Report a run still in progress at the end of the record (not yet a
    confirmed episode because fewer than 5 seasons may have elapsed)."""
    for kind, test in (("El Nino", lambda v: v >= thr), ("La Nina", lambda v: v <= -thr)):
        n = 0
        for v in reversed(series):
            if v is not None and test(v):
                n += 1
            else:
                break
        if n:
            return {"type": kind, "seasons_so_far": n}
    return None


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------
def fetch_index() -> tuple[str, str, dict[tuple[int, int], float]]:
    errors = []
    for url in RONI_ASCII_CANDIDATES:
        try:
            r = requests.get(url, timeout=30, headers=UA)
            if r.ok:
                vals = parse_ascii(r.text)
                if len(vals) > 600:
                    return "RONI", url, vals
            errors.append(f"{url}: HTTP {r.status_code}")
        except requests.RequestException as e:
            errors.append(f"{url}: {e}")
    try:
        r = requests.get(RONI_PAGE, timeout=30, headers=UA)
        r.raise_for_status()
        vals = parse_html_table(r.text)
        if len(vals) > 600:
            return "RONI", RONI_PAGE, vals
        errors.append(f"{RONI_PAGE}: parsed only {len(vals)} values")
    except Exception as e:  # noqa: BLE001 - report every failure mode
        errors.append(f"{RONI_PAGE}: {e}")
    print("RONI unavailable, falling back to ONI:\n  " + "\n  ".join(errors), file=sys.stderr)
    r = requests.get(ONI_ASCII, timeout=30, headers=UA)
    r.raise_for_status()
    vals = parse_ascii(r.text)
    if len(vals) < 600:
        raise RuntimeError("ONI table could not be parsed")
    return "ONI", ONI_ASCII, vals


def fetch_seas5_nino34() -> dict | None:
    lats = [-5.0, -2.5, 0.0, 2.5, 5.0]
    lons = [float(x) for x in range(-170, -119, 5)]
    pts = [(la, lo) for la in lats for lo in lons]
    params = {
        "latitude": ",".join(str(p[0]) for p in pts),
        "longitude": ",".join(str(p[1]) for p in pts),
        "monthly": "sea_surface_temperature_anomaly",
        "models": "ecmwf_seas5",
    }
    try:
        r = requests.get(SEASONAL_API, params=params, timeout=90, headers=UA)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"SEAS5 Nino-3.4 fetch failed: {e}", file=sys.stderr)
        return None
    data = r.json()
    if isinstance(data, dict):
        data = [data]
    months: list[str] | None = None
    sums: list[float] = []
    counts: list[int] = []
    for loc in data:
        mo = loc.get("monthly") or {}
        key = next((k for k in mo if k.startswith("sea_surface_temperature_anomaly")), None)
        if key is None:
            continue
        if months is None:
            months = mo["time"]
            sums = [0.0] * len(months)
            counts = [0] * len(months)
        for i, v in enumerate(mo[key]):
            if v is not None:
                sums[i] += v
                counts[i] += 1
    if not months:
        print("SEAS5 response had no sea_surface_temperature_anomaly", file=sys.stderr)
        return None
    return {
        "source": "ECMWF SEAS5 via Open-Meteo Seasonal API",
        "description": ("Ensemble-mean SST anomaly relative to SEAS5 model climatology, "
                        f"averaged over {len(pts)} grid points in the Nino-3.4 box "
                        "(5S-5N, 170W-120W). Not the relative index; an indicator only."),
        "months": [m[:7] for m in months],
        "anomaly_c": [round(s / c, 2) if c else None for s, c in zip(sums, counts)],
        "n_points": [c for c in counts],
    }


def build(out_path: str) -> None:
    name, url, values = fetch_index()
    y0, m0, series = to_series(values)
    episodes = find_episodes(series)
    open_run = episode_open_at_end(series)

    def ym(i: int) -> str:
        y, m = divmod((m0 - 1) + i, 12)
        return f"{y0 + y:04d}-{m + 1:02d}"

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "index": name,
        "index_source": url,
        "definition": ("3-month running mean; value stored at the centre month "
                       "(DJF -> Jan). Episode: >=5 consecutive overlapping seasons "
                       ">= +0.5 C (El Nino) or <= -0.5 C (La Nina), per NOAA CPC."),
        "start": ym(0),
        "values": series,
        "episodes": [
            {"type": e["type"], "start": ym(e["start"]), "end": ym(e["end"]), "peak": e["peak"]}
            for e in episodes
        ],
        "run_in_progress": open_run,
        "latest": {"month": ym(len(series) - 1), "value": series[-1]},
        "seas5_nino34": fetch_seas5_nino34(),
    }
    try:
        with open(out_path) as f:
            old = json.load(f)
        if {k: v for k, v in old.items() if k != "generated_utc"} == \
                {k: v for k, v in json.loads(json.dumps(payload)).items() if k != "generated_utc"}:
            print("No change in ENSO data; file left untouched.")
            return
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    with open(out_path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {out_path}: {name}, {len(series)} months, {len(episodes)} episodes, "
          f"latest {payload['latest']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="public/data/enso.json")
    build(ap.parse_args().out)
