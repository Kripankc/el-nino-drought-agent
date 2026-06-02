"""
Open-Meteo weather ingestor.
Completely free, no API key required, global coverage back to 1940.
"""
import requests
import pandas as pd
from datetime import datetime, timedelta

_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_DAILY_VARS = "precipitation_sum,temperature_2m_mean,et0_fao_evapotranspiration"


def fetch_weather(lat: float, lon: float, days_back: int = 400) -> pd.DataFrame:
    """
    Fetches real daily weather from the Open-Meteo ERA5 archive.
    Fetches `days_back` days of history (archive has a ~5-day lag).
    Returns DataFrame: date, precip_mm, temp_c, et0_mm, water_balance_mm.
    Raises requests.HTTPError on API failure.
    """
    end = datetime.utcnow() - timedelta(days=5)
    start = end - timedelta(days=days_back)
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "daily": _DAILY_VARS,
        "timezone": "auto",
    }
    r = requests.get(_ARCHIVE_URL, params=params, timeout=25)
    r.raise_for_status()
    return _parse_daily(r.json()["daily"])


def fetch_forecast(lat: float, lon: float, days: int = 14) -> pd.DataFrame:
    """
    Fetches a 14-day weather forecast from Open-Meteo.
    No API key required.
    Returns DataFrame: date, precip_mm, temp_c, et0_mm, water_balance_mm.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": _DAILY_VARS,
        "forecast_days": days,
        "timezone": "auto",
    }
    r = requests.get(_FORECAST_URL, params=params, timeout=25)
    r.raise_for_status()
    return _parse_daily(r.json()["daily"])


def _parse_daily(daily: dict) -> pd.DataFrame:
    df = pd.DataFrame({
        "date": pd.to_datetime(daily["time"]),
        "precip_mm": daily["precipitation_sum"],
        "temp_c": daily["temperature_2m_mean"],
        "et0_mm": daily["et0_fao_evapotranspiration"],
    })
    df["precip_mm"] = pd.to_numeric(df["precip_mm"], errors="coerce").fillna(0.0)
    df["temp_c"]    = pd.to_numeric(df["temp_c"],    errors="coerce")
    df["et0_mm"]    = pd.to_numeric(df["et0_mm"],    errors="coerce").fillna(0.0)
    df.dropna(subset=["temp_c"], inplace=True)
    # Strip timezone so date comparisons work cleanly everywhere
    df["date"] = df["date"].dt.tz_localize(None)
    df["water_balance_mm"] = df["precip_mm"] - df["et0_mm"]
    return df.reset_index(drop=True)
