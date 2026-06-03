"""
El Nino vs normal-year climatology comparison.

For a given location and crop calendar, aggregates each growing-season cycle's
rainfall and temperature, classifies the cycle by the NOAA ONI averaged over the
same season, and contrasts El Nino / Neutral / La Nina years.

All inputs are real (Open-Meteo ERA5 archive + NOAA CPC ONI). No simulated values.
"""
import numpy as np
import pandas as pd


def _active_months(cal: dict) -> set:
    """Set of calendar months in which the crop is actively growing."""
    s, e = cal["start"], cal["end"]
    months = range(1, 13)
    if s <= e:
        return {m for m in months if s <= m <= e}
    return {m for m in months if m >= s or m <= e}


def _season_year(cal: dict, year: int, month: int) -> int:
    """
    Map a (year, month) to the season-cycle it belongs to.
    For wrap-around seasons (e.g. Nov-May) the cycle is labelled by the year it
    STARTS: months >= start_month -> that year; months <= end_month -> prior year.
    """
    s, e = cal["start"], cal["end"]
    if s <= e:
        return year
    return year if month >= s else year - 1


def seasonal_elnino_comparison(df_clim: pd.DataFrame, oni_hist: dict, cal: dict) -> dict:
    """
    df_clim : DataFrame with columns date, precip_mm, temp_c (multi-decade).
    oni_hist: { (year, month): anomaly } from enso.fetch_oni_history().
    cal     : crop calendar dict (needs 'start', 'end').

    Returns a dict summarising rainfall under each ENSO phase for the crop's
    growing season, or {"ok": False, ...} when there isn't enough data.
    """
    if df_clim is None or df_clim.empty:
        return {"ok": False, "reason": "no climatology data"}

    active = _active_months(cal)
    df = df_clim.copy()
    df["year"]  = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df = df[df["month"].isin(active)]
    if df.empty:
        return {"ok": False, "reason": "no active-season data"}

    df["season_year"] = [
        _season_year(cal, y, m) for y, m in zip(df["year"], df["month"])
    ]

    # Per-cycle rainfall total and mean temperature
    grp = df.groupby("season_year").agg(
        precip_mm=("precip_mm", "sum"),
        temp_c=("temp_c", "mean"),
        n_days=("precip_mm", "count"),
    ).reset_index()

    # Require near-complete seasons (drop partial first/last cycles)
    full_len = grp["n_days"].median()
    grp = grp[grp["n_days"] >= full_len * 0.8]
    if len(grp) < 6:
        return {"ok": False, "reason": "not enough complete seasons"}

    # Mean ONI over each cycle's active months
    def _cycle_oni(season_year: int):
        vals = []
        for m in active:
            # month m belongs to season_year per the wrap rule
            yr = season_year if (cal["start"] <= cal["end"] or m >= cal["start"]) else season_year + 1
            v = oni_hist.get((yr, m))
            if v is not None:
                vals.append(v)
        return float(np.mean(vals)) if vals else np.nan

    grp["oni"] = grp["season_year"].apply(_cycle_oni)
    grp = grp.dropna(subset=["oni"])
    if len(grp) < 6:
        return {"ok": False, "reason": "ONI history incomplete"}

    def _phase(o):
        return "El Nino" if o >= 0.5 else ("La Nina" if o <= -0.5 else "Neutral")

    grp["phase"] = grp["oni"].apply(_phase)

    phases = {}
    for ph in ("El Nino", "Neutral", "La Nina"):
        sub = grp[grp["phase"] == ph]
        if not sub.empty:
            phases[ph] = {
                "mean_precip": round(float(sub["precip_mm"].mean()), 1),
                "mean_temp":   round(float(sub["temp_c"].mean()), 1),
                "n_years":     int(len(sub)),
                "years":       sorted(int(y) for y in sub["season_year"]),
            }

    neutral_precip = phases.get("Neutral", {}).get("mean_precip")
    elnino_precip  = phases.get("El Nino", {}).get("mean_precip")

    departure_pct = None
    if neutral_precip and elnino_precip is not None and neutral_precip > 0:
        departure_pct = round((elnino_precip - neutral_precip) / neutral_precip * 100, 1)

    # Per-year series for plotting (sorted)
    grp_sorted = grp.sort_values("season_year")
    series = [
        {"year": int(r.season_year), "precip": round(float(r.precip_mm), 1),
         "phase": r.phase, "oni": round(float(r.oni), 2)}
        for r in grp_sorted.itertuples()
    ]

    return {
        "ok": True,
        "phases": phases,
        "neutral_precip_mm": neutral_precip,
        "elnino_precip_mm": elnino_precip,
        "elnino_departure_pct": departure_pct,
        "series": series,
        "n_seasons": len(grp),
        "first_year": int(grp_sorted["season_year"].min()),
        "last_year": int(grp_sorted["season_year"].max()),
        "active_months": sorted(active),
    }
