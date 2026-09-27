"""Offline tests for the data pipeline. Inputs are small hand-built arrays and
text snippets that mimic the source formats; nothing here is shipped as data."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crops  # noqa: E402
import enso   # noqa: E402


# ---------------------------------------------------------------- ENSO
ONI_SNIPPET = """SEAS  YR   TOTAL   ANOM
  DJF 1950   24.72   -1.53
  JFM 1950   25.17   -1.34
  NDJ 1950   25.00    0.10
"""


def test_parse_ascii_takes_last_column_and_centre_month():
    v = enso.parse_ascii(ONI_SNIPPET)
    assert v[(1950, 1)] == -1.53      # DJF -> January
    assert v[(1950, 2)] == -1.34      # JFM -> February
    assert v[(1950, 12)] == 0.10      # NDJ -> December
    assert len(v) == 3


def test_parse_ascii_skips_missing_sentinel():
    v = enso.parse_ascii("DJF 2030 -99.90 -99.90\nJFM 2030 26.0 0.4")
    assert (2030, 1) not in v and v[(2030, 2)] == 0.4


def test_parse_html_table():
    html = """<table><tr><td>Year</td><td>DJF</td><td>JFM</td><td>FMA</td></tr>
              <tr><td>1997</td><td>-0.5</td><td>-0.4</td><td>-0.1</td></tr>
              <tr><td>Year</td><td>DJF</td><td>JFM</td><td>FMA</td></tr>
              <tr><td>1998</td><td>2.2</td><td>1.9</td><td>1.4</td></tr></table>"""
    v = enso.parse_html_table(html)
    assert v[(1997, 1)] == -0.5 and v[(1998, 3)] == 1.4 and len(v) == 6


def test_episode_needs_five_consecutive_seasons():
    s = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.2, 0.5, 0.5, 0.5, 0.5, 0.1]
    ep = enso.find_episodes(s)
    assert ep == [{"type": "El Nino", "start": 1, "end": 5, "peak": 0.9}]


def test_la_nina_and_gap_breaks_run():
    s = [-0.5, -0.6, None, -0.7, -0.8, -0.9, -1.0, -1.1]
    ep = enso.find_episodes(s)
    assert ep == [{"type": "La Nina", "start": 3, "end": 7, "peak": -1.1}]


def test_run_in_progress():
    assert enso.episode_open_at_end([0.0, 0.6, 0.7]) == {"type": "El Nino", "seasons_so_far": 2}
    assert enso.episode_open_at_end([0.0, 0.1]) is None


def test_to_series_is_dense():
    y0, m0, s = enso.to_series({(2000, 11): 1.0, (2001, 2): 2.0})
    assert (y0, m0) == (2000, 11) and s == [1.0, None, None, 2.0]


# ---------------------------------------------------------------- crops
def test_map_crop():
    assert crops.map_crop("maize") == ("maize", ["mai"])
    assert crops.map_crop("sugar cane")[0] == "sugarcane"
    assert crops.map_crop("sweet potato")[0] is None      # must not match potato
    assert crops.map_crop("seedcotton")[0] == "cotton"
    assert crops.map_crop("tea")[0] is None


def test_aggregate_sum_conserves_area_and_bins_correctly():
    # 0.05 deg grid covering 0..0.5N, 10..10.5E, north-to-south like most products
    lats = np.arange(0.475, 0.0, -0.05)
    lons = np.arange(10.025, 10.5, 0.05)
    field = np.ones((lats.size, lons.size))
    field[0, 0] = np.nan                     # missing values ignored
    out = crops.aggregate_sum(field, lats, lons, 0.25)
    assert out.sum() == field.size - 1
    i0 = int((0 + 90) / 0.25)
    j0 = int((10 + 180) / 0.25)
    assert out[i0:i0 + 2, j0:j0 + 2].sum() == out.sum()
    assert out[i0 + 1, j0] == 24             # the NaN sits in the NW quarter


def test_top_crops_threshold_and_order():
    ni, nj = 720, 1440
    a = np.zeros((ni, nj)); b = np.zeros((ni, nj))
    a[400, 800] = 30; b[400, 800] = 100      # cell above threshold
    a[10, 10] = 20                            # below 50 ha -> dropped
    t = crops.top_crops({0: a, 1: b})
    tile = crops.tile_of(400, 800, 0.25)
    assert t[tile]["400_800"] == [130.0, [[1, 100.0], [0, 30.0]]]
    assert all("10_10" not in cells for cells in t.values())


def test_calendar_cells_filters_invalid():
    lats = np.array([0.25]); lons = np.array([10.25])
    cal = {"mai_rf": (np.array([[120.0]]), np.array([[250.0]])),
           "soy_rf": (np.array([[np.nan]]), np.array([[200.0]]))}
    t = crops.calendar_cells(cal, lats, lons)
    (tile, cells), = t.items()
    assert cells == {"180_380": {"mai_rf": [120, 250]}}
