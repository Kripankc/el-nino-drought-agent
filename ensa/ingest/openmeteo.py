"""
Open-Meteo weather ingestor.
Completely free, no API key required, global coverage back to 1940.
"""
import requests
import pandas as pd
from datetime import datetime, timedelta

_ARCHIVE_URL  = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_DAILY_VARS   = "precipitation_sum,temperature_2m_mean,et0_fao_evapotranspiration"


def fetch_weather(lat: float, lon: float, days_back: int = 400) -> pd.DataFrame:
    """
    Fetches real daily weather from the Open-Meteo ERA5 archive.
    Returns DataFrame: date, precip_mm, temp_c, et0_mm, water_balance_mm.
    """
    end   = datetime.utcnow() - timedelta(days=5)
    start = end - timedelta(days=days_back)
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date":   end.strftime("%Y-%m-%d"),
        "daily":      _DAILY_VARS,
        "timezone":   "UTC",
    }
    r = requests.get(_ARCHIVE_URL, params=params, timeout=25)
    r.raise_for_status()
    return _parse(r.json()["daily"])


def fetch_forecast(lat: float, lon: float, days: int = 14) -> pd.DataFrame:
    """
    Fetches a 14-day weather forecast from Open-Meteo.
    """
    params = {
        "latitude":      lat,
        "longitude":     lon,
        "daily":         _DAILY_VARS,
        "forecast_days": days,
        "timezone":      "UTC",
    }
    r = requests.get(_FORECAST_URL, params=params, timeout=25)
    r.raise_for_status()
    return _parse(r.json()["daily"])


def fetch_climatology(lat: float, lon: float, start_year: int = 1985) -> pd.DataFrame:
    """
    Fetches a multi-decade daily archive (rainfall + mean temperature) for
    El Nino vs normal-year comparison. Lean payload — no ET0.
    Returns DataFrame: date, precip_mm, temp_c.
    """
    end = datetime.utcnow() - timedelta(days=5)
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": f"{start_year}-01-01",
        "end_date":   end.strftime("%Y-%m-%d"),
        "daily":      "precipitation_sum,temperature_2m_mean",
        "timezone":   "UTC",
    }
    r = requests.get(_ARCHIVE_URL, params=params, timeout=60)
    r.raise_for_status()
    d = r.json()["daily"]
    df = pd.DataFrame({
        "date":      pd.to_datetime(d["time"]).tz_localize(None),
        "precip_mm": pd.Series(d["precipitation_sum"], dtype=float).fillna(0.0).values,
        "temp_c":    pd.Series(d["temperature_2m_mean"], dtype=float).values,
    })
    df.dropna(subset=["temp_c"], inplace=True)
    return df.reset_index(drop=True)


def _parse(daily: dict) -> pd.DataFrame:
    """Convert Open-Meteo daily JSON to a clean DataFrame."""
    # Use pd.Series() explicitly so we always get a Series, never a numpy array.
    dates    = pd.to_datetime(daily["time"]).tz_localize(None)
    precip   = pd.Series(daily["precipitation_sum"],         dtype=float).fillna(0.0)
    temp     = pd.Series(daily["temperature_2m_mean"],       dtype=float)
    et0      = pd.Series(daily["et0_fao_evapotranspiration"], dtype=float).fillna(0.0)

    df = pd.DataFrame({
        "date":             dates,
        "precip_mm":        precip.values,
        "temp_c":           temp.values,
        "et0_mm":           et0.values,
        "water_balance_mm": (precip - et0).values,
    })
    df.dropna(subset=["temp_c"], inplace=True)
    return df.reset_index(drop=True)
