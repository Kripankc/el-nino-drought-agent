"""
Build the crop layers served under public/data/crops/.

Sources
-------
* CROPGRIDS v1.08 (Tang et al. 2024, Scientific Data 11:413), harvested area
  of 173 crops circa 2020 at 0.05 deg. figshare DOI 10.6084/m9.figshare.22491997
  License: CC BY 4.0.
* GGCMI Phase 3 crop calendar (Jaegermeyr et al. 2021, Nature Food 2:873-885),
  planting and maturity day-of-year for 18 crops, rainfed and irrigated, at
  0.5 deg. Zenodo DOI 10.5281/zenodo.5062513. License: CC BY 4.0.

Output
------
crops/index.json            crop list, grid definitions, source citations
crops/<ti>_<tj>.json        one 10x10 deg tile:
    "a": {"<i>_<j>": [total_ha_all_crops, [[crop_id, hectares], ...]]}   0.25 deg cells, top 10 crops
    "c": {"<i>_<j>": {"mai_rf": [plant_doy, maturity_doy], ...}}  0.5 deg cells

Cell indices are global: i = floor((lat + 90) / res), j = floor((lon + 180) / res).

Run:  python pipeline/crops.py --work /tmp/cropwork --out public/data/crops
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from collections import defaultdict

import numpy as np
import requests

AREA_RES = 0.25
CAL_RES = 0.5
TILE_DEG = 10
TOP_N = 10
MIN_CELL_HA = 50.0  # below this a 0.25 deg cell is reported as "no cropland recorded"

FIGSHARE_API = "https://api.figshare.com/v2/articles/22491997"
ZENODO_API = "https://zenodo.org/api/records/5062513"
UA = {"User-Agent": "ENSOwatch data pipeline (github.com/Kripankc/el-nino-drought-agent)"}

# CROPGRIDS crop name -> (parameter key used by the web app, GGCMI codes)
# Matching is on the lower-cased crop name taken from the file name.
CROP_MAP: list[tuple[str, str, list[str]]] = [
    (r"^maize$", "maize", ["mai"]),
    (r"^rice$", "rice", ["ri1", "ri2"]),
    (r"^wheat$", "wheat", ["swh", "wwh"]),
    (r"^soybeans?$", "soybean", ["soy"]),
    (r"^sorghum$", "sorghum", ["sor"]),
    (r"^millet$", "millet", ["mil"]),
    (r"^barley$", "barley", ["bar"]),
    (r"^cassava", "cassava", ["cas"]),
    (r"^potatoe?s?$", "potato", ["pot"]),
    (r"^groundnuts?", "groundnut", ["nut"]),
    (r"cotton", "cotton", ["cot"]),
    (r"^sugar ?cane$", "sugarcane", ["sgc"]),
    (r"^sugar ?beets?$", "sugarbeet", ["sgb"]),
    (r"^sunflower", "sunflower", ["sun"]),
    (r"^rapeseed", "rapeseed", ["rap"]),
    (r"^beans?(,? ?dry)?$", "beans", ["bea"]),
    (r"^peas?(,? ?dry)?$", "peas", ["pea"]),
    (r"^rye$", "rye", ["rye"]),
]


# --------------------------------------------------------------------------
# Pure functions (unit-tested)
# --------------------------------------------------------------------------
def map_crop(name: str) -> tuple[str | None, list[str]]:
    n = name.lower().replace("_", " ").strip()
    for pat, key, codes in CROP_MAP:
        if re.search(pat, n):
            return key, codes
    return None, []


def pick_var(names: list[str], *needles: str) -> str:
    for needle in needles:
        for n in names:
            if needle in n.lower():
                return n
    raise KeyError(f"none of {needles} in variables {names}")


def cell_index(lat: np.ndarray, lon: np.ndarray, res: float) -> tuple[np.ndarray, np.ndarray]:
    i = np.floor((lat + 90.0) / res + 1e-9).astype(int)
    j = np.floor((((lon + 180.0) % 360.0)) / res + 1e-9).astype(int)
    ni, nj = int(round(180 / res)), int(round(360 / res))
    return np.clip(i, 0, ni - 1), np.clip(j, 0, nj - 1)


def aggregate_sum(values: np.ndarray, lats: np.ndarray, lons: np.ndarray, res: float) -> np.ndarray:
    """Sum a (lat, lon) field of hectares onto a coarser global grid."""
    ni, nj = int(round(180 / res)), int(round(360 / res))
    out = np.zeros((ni, nj), dtype=np.float64)
    v = np.asarray(values, dtype=np.float64)
    v = np.where(np.isfinite(v) & (v > 0), v, 0.0)
    r, c = np.nonzero(v)
    if r.size == 0:
        return out
    ii, jj = cell_index(lats[r], lons[c], res)
    np.add.at(out, (ii, jj), v[r, c])
    return out


def tile_of(i: int, j: int, res: float) -> str:
    per = int(round(TILE_DEG / res))
    return f"{i // per}_{j // per}"


def top_crops(stack: dict[int, np.ndarray], top_n: int = TOP_N,
              min_cell_ha: float = MIN_CELL_HA) -> dict[str, dict[str, list]]:
    """stack: crop_id -> (ni, nj) hectares. Returns {tile: {"i_j": [total_ha, [[id, ha], ...]]}}"""
    ids = sorted(stack)
    cube = np.stack([stack[k] for k in ids])            # (n_crops, ni, nj)
    total = cube.sum(axis=0)
    tiles: dict[str, dict[str, list]] = defaultdict(dict)
    for i, j in zip(*np.nonzero(total >= min_cell_ha)):
        col = cube[:, i, j]
        order = np.argsort(col)[::-1][:top_n]
        entries = [[ids[k], round(float(col[k]), 1)] for k in order if col[k] > 0]
        tiles[tile_of(int(i), int(j), AREA_RES)][f"{i}_{j}"] = [round(float(total[i, j]), 1), entries]
    return tiles


def calendar_cells(cal: dict[str, tuple[np.ndarray, np.ndarray]],
                   lats: np.ndarray, lons: np.ndarray) -> dict[str, dict[str, dict]]:
    """cal: 'mai_rf' -> (plant_doy grid, maturity_doy grid) on (lats, lons)."""
    tiles: dict[str, dict[str, dict]] = defaultdict(dict)
    for key, (pd_, md_) in cal.items():
        ok = np.isfinite(pd_) & np.isfinite(md_) & (pd_ >= 1) & (pd_ <= 366) & (md_ >= 1) & (md_ <= 366)
        for r, c in zip(*np.nonzero(ok)):
            ii, jj = cell_index(np.array([lats[r]]), np.array([lons[c]]), CAL_RES)
            i, j = int(ii[0]), int(jj[0])
            tiles[tile_of(i, j, CAL_RES)].setdefault(f"{i}_{j}", {})[key] = [
                int(round(float(pd_[r, c]))), int(round(float(md_[r, c])))]
    return tiles


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------
def download(url: str, dest: str) -> str:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    with requests.get(url, stream=True, timeout=600, headers=UA) as r:
        r.raise_for_status()
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        os.replace(tmp, dest)
    return dest


def load_cropgrids(work: str) -> tuple[list[dict], dict[int, np.ndarray]]:
    import xarray as xr

    meta = requests.get(FIGSHARE_API, timeout=60, headers=UA).json()
    files = meta["files"]
    print("CROPGRIDS files:", [f["name"] for f in files])
    nc_zip = next((f for f in files if "nc" in f["name"].lower() and f["name"].lower().endswith(".zip")
                   and "map" in f["name"].lower()), None)
    if nc_zip is None:
        raise RuntimeError("Could not identify the CROPGRIDS NetCDF maps archive")
    zpath = download(nc_zip["download_url"], os.path.join(work, nc_zip["name"]))
    outdir = os.path.join(work, "cropgrids")
    os.makedirs(outdir, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(outdir)

    crops: list[dict] = []
    stack: dict[int, np.ndarray] = {}
    for root, _, fnames in os.walk(outdir):
        for fn in sorted(fnames):
            if not fn.lower().endswith(".nc"):
                continue
            m = re.match(r"CROPGRIDSv[\d.]+_(.+)\.nc$", fn, re.I)
            if not m:
                continue
            name = m.group(1).replace("_", " ")
            with xr.open_dataset(os.path.join(root, fn)) as ds:
                try:
                    var = pick_var(list(ds.data_vars), "harvarea", "harv")
                except KeyError:
                    print(f"skip {fn}: no harvested-area variable ({list(ds.data_vars)})")
                    continue
                latn = pick_var(list(ds.coords) + list(ds.dims), "lat")
                lonn = pick_var(list(ds.coords) + list(ds.dims), "lon")
                da = ds[var].squeeze().transpose(latn, lonn)
                agg = aggregate_sum(da.values, ds[latn].values, ds[lonn].values, AREA_RES)
                units = ds[var].attrs.get("units", "")
            if agg.sum() <= 0:
                continue
            cid = len(crops)
            key, codes = map_crop(name)
            crops.append({"id": cid, "name": name, "param": key, "ggcmi": codes,
                          "global_ha": round(float(agg.sum()))})
            stack[cid] = agg
            print(f"  {name:30s} var={var} units={units!r} total={agg.sum():,.0f} -> {key}")
    if not crops:
        raise RuntimeError("No CROPGRIDS crops were read")
    return crops, stack


def load_ggcmi(work: str) -> tuple[dict, np.ndarray, np.ndarray]:
    import xarray as xr

    rec = requests.get(ZENODO_API, timeout=60, headers=UA).json()
    cal: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    lats = lons = None
    for f in rec["files"]:
        name = f["key"]
        m = re.match(r"([a-z0-9]{3})_(ir|rf)_ggcmi_crop_calendar_phase3_v[\d.]+\.nc4$", name)
        if not m:
            continue
        path = download(f["links"]["self"], os.path.join(work, name))
        with xr.open_dataset(path, decode_times=False) as ds:
            names = list(ds.data_vars)
            pv = pick_var(names, "planting_day", "plant")
            mv = pick_var(names, "maturity_day", "matur")
            latn = pick_var(list(ds.coords) + list(ds.dims), "lat")
            lonn = pick_var(list(ds.coords) + list(ds.dims), "lon")
            p = ds[pv].squeeze().transpose(latn, lonn).values.astype(float)
            q = ds[mv].squeeze().transpose(latn, lonn).values.astype(float)
            lats, lons = ds[latn].values, ds[lonn].values
        cal[f"{m.group(1)}_{m.group(2)}"] = (p, q)
        print(f"  GGCMI {name}: {pv}/{mv}, valid cells {int(np.isfinite(p).sum())}")
    if not cal:
        raise RuntimeError("No GGCMI calendar files were read")
    return cal, lats, lons


def build(work: str, out: str) -> None:
    os.makedirs(work, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    crops, stack = load_cropgrids(work)
    area_tiles = top_crops(stack)
    cal, clat, clon = load_ggcmi(work)
    cal_tiles = calendar_cells(cal, clat, clon)

    for t in sorted(set(area_tiles) | set(cal_tiles)):
        with open(os.path.join(out, f"{t}.json"), "w") as f:
            json.dump({"a": area_tiles.get(t, {}), "c": cal_tiles.get(t, {})}, f,
                      separators=(",", ":"))
    index = {
        "area_res": AREA_RES, "cal_res": CAL_RES, "tile_deg": TILE_DEG,
        "min_cell_ha": MIN_CELL_HA, "top_n": TOP_N,
        "crops": crops,
        "calendar_keys": sorted(cal),
        "sources": {
            "area": "Tang, F.H.M. et al. (2024) CROPGRIDS: a global geo-referenced dataset of 173 "
                    "crops. Scientific Data 11, 413. doi:10.1038/s41597-024-03247-7 "
                    "(data: doi:10.6084/m9.figshare.22491997). CC BY 4.0.",
            "calendar": "Jaegermeyr, J. et al. (2021) Climate impacts on global agriculture emerge "
                        "earlier in new generation of climate and crop models. Nature Food 2, "
                        "873-885 (data: doi:10.5281/zenodo.5062513). CC BY 4.0.",
        },
    }
    with open(os.path.join(out, "index.json"), "w") as f:
        json.dump(index, f, separators=(",", ":"))
    print(f"Wrote {len(set(area_tiles) | set(cal_tiles))} tiles and index.json to {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/tmp/cropwork")
    ap.add_argument("--out", default="public/data/crops")
    a = ap.parse_args()
    try:
        build(a.work, a.out)
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {e}", file=sys.stderr)
        raise
