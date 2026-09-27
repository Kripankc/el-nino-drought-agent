"""
Contract check for the live APIs the web app calls from the browser.
Fails (exit 1) if an endpoint, parameter or variable name the app relies on
has changed, or returns no data. Run weekly in CI and before releases.
"""
import sys
from datetime import date, timedelta

import requests

LAT, LON = -16.25, 27.75
problems: list[str] = []


def get(url, params):
    r = requests.get(url, params=params, timeout=60)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not r.ok or body.get("error"):
        problems.append(f"{url}: HTTP {r.status_code} {body.get('reason', '')}")
        return None
    return body


def non_null(name, arr):
    vals = [v for v in (arr or []) if v is not None]
    if not vals:
        problems.append(f"{name}: no values")
    return vals


# ERA5 archive: every daily variable the app requests, with models=era5
end = date.today() - timedelta(days=10)
daily = ["precipitation_sum", "temperature_2m_max", "temperature_2m_min",
         "et0_fao_evapotranspiration", "relative_humidity_2m_mean", "soil_moisture_0_to_100cm_mean"]
j = get("https://archive-api.open-meteo.com/v1/archive", {
    "latitude": LAT, "longitude": LON, "start_date": (end - timedelta(days=30)).isoformat(),
    "end_date": end.isoformat(), "daily": ",".join(daily), "models": "era5", "timezone": "GMT"})
if j:
    for v in daily:
        non_null(f"archive {v}", j["daily"].get(v))
    # 1950 must be available for the ENSO composites
    j2 = get("https://archive-api.open-meteo.com/v1/archive", {
        "latitude": LAT, "longitude": LON, "start_date": "1950-01-01", "end_date": "1950-01-31",
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min", "models": "era5", "timezone": "GMT"})
    if j2:
        non_null("archive 1950 precipitation", j2["daily"].get("precipitation_sum"))

# Ensemble: members present
j = get("https://ensemble-api.open-meteo.com/v1/ensemble", {
    "latitude": LAT, "longitude": LON, "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
    "models": "ecmwf_ifs025_ensemble", "forecast_days": 15, "timezone": "GMT"})
if j:
    members = [k for k in j["daily"] if k.startswith("precipitation_sum")]
    if len(members) < 20:
        problems.append(f"ensemble: only {len(members)} precipitation members ({members[:3]})")

# Seasonal monthly fields
j = get("https://seasonal-api.open-meteo.com/v1/seasonal", {
    "latitude": LAT, "longitude": LON,
    "monthly": "precipitation_mean,precipitation_anomaly,temperature_2m_mean,temperature_2m_anomaly"})
if j:
    m = j.get("monthly", {})
    for p in ("precipitation_mean", "precipitation_anomaly", "temperature_2m_anomaly"):
        key = next((k for k in m if k == p or k.startswith(p + "_")), None)
        if key is None:
            problems.append(f"seasonal: missing {p}; keys = {list(m)}")
        else:
            non_null(f"seasonal {key}", m[key])

if problems:
    print("API contract check FAILED:\n  " + "\n  ".join(problems))
    sys.exit(1)
print("API contract check passed.")
