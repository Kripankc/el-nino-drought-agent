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
# Hourly ERA5 soil moisture (volumetric, 0-1) for two root zones
_HOURLY_SOIL  = "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm"


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


def fetch_window(lat: float, lon: float, end_date, days_back: int = 120) -> pd.DataFrame:
    """
    Fetches a historical ERA5 archive window ending on a SPECIFIC past date.
    Used for hindsight analysis ("what actually happened on 2023-01-15?").
    Returns DataFrame: date, precip_mm, temp_c, et0_mm, water_balance_mm.
    """
    end = pd.Timestamp(end_date)
    # Allow a small look-ahead so we can also show what came AFTER the selected date
    look_ahead = min(14, (datetime.utcnow().date() - end.date()).days)
    look_ahead = max(0, look_ahead - 5)  # archive has ~5 day lag
    end_with_buffer = end + pd.Timedelta(days=look_ahead)
    start = end - pd.Timedelta(days=days_back)
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date":   end_with_buffer.strftime("%Y-%m-%d"),
        "daily":      _DAILY_VARS,
        "timezone":   "UTC",
    }
    r = requests.get(_ARCHIVE_URL, params=params, timeout=30)
    r.raise_for_status()
    return _parse(r.json()["daily"])


def fetch_soil_moisture(lat: float, lon: float, days_back: int = 120) -> pd.DataFrame:
    """
    Fetches real ERA5 volumetric soil moisture (0-1) for two depth layers
    and returns daily means. Surface = 0-7 cm, Root-zone = 7-28 cm.
    Returns DataFrame: date, soil_surface, soil_root.
    """
    end   = datetime.utcnow() - timedelta(days=5)
    start = end - timedelta(days=days_back)
    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date":   end.strftime("%Y-%m-%d"),
        "hourly":     _HOURLY_SOIL,
        "timezone":   "UTC",
    }
    r = requests.get(_ARCHIVE_URL, params=params, timeout=30)
    r.raise_for_status()
    h = r.json()["hourly"]
    df = pd.DataFrame({
        "datetime":     pd.to_datetime(h["time"]).tz_localize(None),
        "soil_surface": pd.Series(h["soil_moisture_0_to_7cm"], dtype=float).values,
        "soil_root":    pd.Series(h["soil_moisture_7_to_28cm"], dtype=float).values,
    })
    df["date"] = df["datetime"].dt.normalize()
    daily = df.groupby("date").agg(
        soil_surface=("soil_surface", "mean"),
        soil_root=("soil_root", "mean"),
    ).reset_index()
    return daily


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
