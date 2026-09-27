"""
Browser smoke test with every external request mocked.

The mock payloads below are SYNTHETIC and exist only to exercise the UI in an
offline sandbox (layout, charts, error paths). They are never deployed and say
nothing about real weather or crops.

Usage: npm run build && python tests/e2e/smoke.py [outdir]
"""
import json
import math
import random
import subprocess
import sys
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e"
PORT = 4173


def daily_payload(qs):
    start = date.fromisoformat(qs["start_date"][0])
    end = date.fromisoformat(qs["end_date"][0])
    vars_ = qs["daily"][0].split(",")
    days = [(start + timedelta(days=k)) for k in range((end - start).days + 1)]
    out = {"time": [d.isoformat() for d in days]}
    for v in vars_:
        col = []
        for d in days:
            rnd = random.Random(d.toordinal() * 31 + hash(v) % 1000)
            doy = d.timetuple().tm_yday
            wet = math.cos(2 * math.pi * (doy - 15) / 365)  # wet season around January
            if v == "precipitation_sum":
                col.append(round(max(0.0, rnd.gammavariate(0.6, 12) * max(0, wet)), 1) if rnd.random() < 0.55 * max(0.05, wet) else 0.0)
            elif v == "temperature_2m_max":
                col.append(round(29 + 4 * math.sin(2 * math.pi * (doy - 250) / 365) + rnd.gauss(0, 1.5) + 0.02 * (d.year - 1990), 1))
            elif v == "temperature_2m_min":
                col.append(round(16 + 4 * math.sin(2 * math.pi * (doy - 250) / 365) + rnd.gauss(0, 1.2), 1))
            elif v == "et0_fao_evapotranspiration":
                col.append(round(4.5 + 1.5 * math.sin(2 * math.pi * (doy - 250) / 365) + rnd.gauss(0, 0.3), 2))
            elif v == "relative_humidity_2m_mean":
                col.append(round(55 + 20 * wet + rnd.gauss(0, 5)))
            elif v == "soil_moisture_0_to_100cm_mean":
                col.append(round(0.22 + 0.08 * wet + rnd.gauss(0, 0.01), 3))
            else:
                col.append(None)
        out[v] = col
    return {"latitude": -16.25, "longitude": 27.75, "elevation": 1030, "daily": out}


def ensemble_payload():
    today = date.today()
    days = [(today + timedelta(days=k)) for k in range(15)]
    d = {"time": [x.isoformat() for x in days]}
    for base in ("precipitation_sum", "temperature_2m_max", "temperature_2m_min"):
        for m in range(51):
            key = base if m == 0 else f"{base}_member{m:02d}"
            rnd = random.Random(m)
            if base == "precipitation_sum":
                d[key] = [round(max(0, rnd.gauss(3, 4)), 1) for _ in days]
            elif base == "temperature_2m_max":
                d[key] = [round(31 + rnd.gauss(0, 1.5) + k * 0.1, 1) for k in range(15)]
            else:
                d[key] = [round(17 + rnd.gauss(0, 1), 1) for _ in days]
    return {"daily": d}


def seasonal_payload():
    t = date.today().replace(day=1)
    months = []
    for k in range(7):
        y, m = divmod(t.month - 1 + k, 12)
        months.append(f"{t.year + y}-{m + 1:02d}-01")
    return {"monthly": {
        "time": months,
        "precipitation_mean": [40, 90, 150, 180, 160, 120, 60],
        "precipitation_anomaly": [-5, -25, -40, -10, 20, 5, 0],
        "temperature_2m_mean": [25] * 7,
        "temperature_2m_anomaly": [0.4, 0.6, 0.8, 0.5, 0.2, 0.1, 0.0],
    }}


def enso_fixture():
    vals = []
    y, m = 1950, 1
    today = date.today()
    while (y, m) <= (today.year, today.month - 1):
        vals.append(round(1.2 * math.sin((y * 12 + m) / 21.0), 2))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return {
        "generated_utc": "fixture", "index": "RONI", "index_source": "fixture", "definition": "fixture",
        "start": "1950-01", "values": vals,
        "episodes": [
            {"type": "El Nino", "start": "1982-05", "end": "1983-06", "peak": 2.2},
            {"type": "El Nino", "start": "1991-05", "end": "1992-06", "peak": 1.7},
            {"type": "El Nino", "start": "1997-05", "end": "1998-05", "peak": 2.4},
            {"type": "El Nino", "start": "2002-06", "end": "2003-02", "peak": 1.3},
            {"type": "El Nino", "start": "2009-07", "end": "2010-03", "peak": 1.6},
            {"type": "El Nino", "start": "2015-03", "end": "2016-05", "peak": 2.6},
            {"type": "El Nino", "start": "2023-05", "end": "2024-04", "peak": 2.0},
            {"type": "La Nina", "start": "2010-06", "end": "2011-05", "peak": -1.6},
            {"type": "La Nina", "start": "1988-05", "end": "1989-05", "peak": -1.8},
        ],
        "run_in_progress": {"type": "El Nino", "seasons_so_far": 3},
        "latest": {"month": f"{today.year}-{today.month - 1:02d}", "value": 0.8},
        "seas5_nino34": {"source": "fixture", "description": "Fixture SEAS5 description.",
                         "months": ["2026-10", "2026-11", "2026-12"], "anomaly_c": [1.1, 1.3, 1.4], "n_points": [55, 55, 55]},
    }


CROP_INDEX = {"area_res": 0.25, "cal_res": 0.5, "tile_deg": 10, "min_cell_ha": 50, "top_n": 10,
              "crops": [{"id": 0, "name": "maize", "param": "maize", "ggcmi": ["mai"], "global_ha": 1},
                        {"id": 1, "name": "soybean", "param": "soybean", "ggcmi": ["soy"], "global_ha": 1},
                        {"id": 2, "name": "tobacco", "param": None, "ggcmi": [], "global_ha": 1},
                        {"id": 3, "name": "wheat", "param": "wheat", "ggcmi": ["swh", "wwh"], "global_ha": 1}],
              "calendar_keys": [], "sources": {"area": "fixture", "calendar": "fixture"}}
CROP_TILE = {"a": {"295_830": [21000.0, [[0, 12000.0], [1, 4000.0], [2, 3000.0], [3, 2000.0]]]},
             "c": {"147_415": {"mai_rf": [320, 120], "soy_rf": [330, 100], "wwh_ir": [130, 260]}}}


def handler(route):
    url = route.request.url
    u = urlparse(url)
    qs = parse_qs(u.query)
    body = None
    if "archive-api.open-meteo.com" in u.netloc:
        body = daily_payload(qs)
    elif "ensemble-api.open-meteo.com" in u.netloc:
        body = ensemble_payload()
    elif "seasonal-api.open-meteo.com" in u.netloc:
        body = seasonal_payload()
    elif "nominatim.openstreetmap.org" in u.netloc:
        body = {"address": {"town": "Mazabuka", "state": "Southern Province", "country": "Zambia"}} if "reverse" in u.path \
            else [{"display_name": "Mazabuka, Southern Province, Zambia", "lat": "-15.86", "lon": "27.76"}]
    elif "tile.openstreetmap.org" in u.netloc:
        return route.fulfill(status=204, body="")
    elif u.path.endswith("/data/enso.json"):
        body = enso_fixture()
    elif u.path.endswith("/data/crops/index.json"):
        body = CROP_INDEX
    elif "/data/crops/" in u.path:
        if u.path.endswith("/7_20.json"):
            body = CROP_TILE
        else:
            return route.fulfill(status=404, body="")
    if body is not None:
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body),
                             headers={"access-control-allow-origin": "*"})
    return route.continue_()


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    srv = subprocess.Popen(["npx", "vite", "preview", "--port", str(PORT), "--strictPort"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    errors = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for name, query, width in [
                ("current-desktop", "?lat=-16.25&lon=27.65", 1100),
                ("current-mobile", "?lat=-16.25&lon=27.65", 390),
                ("past-2016", "?lat=-16.25&lon=27.65&date=2016-01-20&cmp=2023", 1100),
                ("no-cropland", "?lat=60.5&lon=100.5", 1100),
            ]:
                ctx = b.new_context(viewport={"width": width, "height": 900})
                pg = ctx.new_page()
                pg.on("console", lambda m, n=name: errors.append(f"[{n}] {m.type}: {m.text}") if m.type in ("error",) else None)
                pg.on("pageerror", lambda e, n=name: errors.append(f"[{n}] pageerror: {e}"))
                pg.route("**/*", handler)
                pg.goto(f"http://localhost:{PORT}/{query}")
                pg.wait_for_function("document.getElementById('status').textContent.startsWith('Done') || document.getElementById('status').classList.contains('error')", timeout=60000)
                btn = pg.get_by_text("Show past El Niño seasons here")
                if btn.count():
                    btn.click()
                    pg.wait_for_function("!document.body.innerText.includes('Loading 75 years')", timeout=60000)
                    pg.wait_for_timeout(500)
                print(name, "status:", pg.inner_text("#status"))
                pg.screenshot(path=f"{OUT}/{name}.png", full_page=True)
                ctx.close()
            b.close()
    finally:
        srv.terminate()
    print("\n".join(errors) if errors else "no console errors")


if __name__ == "__main__":
    main()
