"""
NOAA NINO3.4 SST anomaly ingestor.
Fetches the Oceanic Niño Index (ONI) from NOAA CPC — free, no API key.
"""
import requests
from datetime import datetime

_NINO34_URL = (
    "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/"
    "ensostuff/detrend.nino34.ascii.txt"
)

_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def fetch_current_oni() -> dict:
    """
    Returns the latest available NINO3.4 SST anomaly from NOAA.
    Dict keys: value (float), phase (str), year (int), month (int), source (str).
    Falls back to a neutral estimate if the fetch fails.
    """
    try:
        r = requests.get(_NINO34_URL, timeout=15)
        r.raise_for_status()
        records = _parse_nino34(r.text)
        if not records:
            return _fallback()
        latest = max(records, key=lambda x: (x[0], x[1]))
        value = round(latest[2], 2)
        return {
            "value": value,
            "phase": _classify(value),
            "year": latest[0],
            "month": latest[1],
            "month_name": _MONTH_NAMES.get(latest[1], ""),
            "source": "NOAA CPC NINO3.4",
        }
    except Exception as e:
        print(f"[ENSO] Failed to fetch ONI: {e}")
        return _fallback()


def fetch_oni_history() -> dict:
    """
    Returns the full NINO3.4 monthly anomaly record from NOAA CPC.
    Result: { (year, month): anomaly_float, ... }  plus key "_source".
    Empty dict (with _source flag) on failure.
    """
    try:
        r = requests.get(_NINO34_URL, timeout=20)
        r.raise_for_status()
        records = _parse_nino34(r.text)
        hist = {(y, m): a for (y, m, a) in records}
        hist["_source"] = "NOAA CPC NINO3.4"
        return hist
    except Exception as e:
        print(f"[ENSO] Failed to fetch ONI history: {e}")
        return {"_source": "offline"}


def classify_oni(oni: float) -> str:
    """Public classifier: returns 'El Nino' | 'La Nina' | 'Neutral'."""
    if oni >= 0.5:
        return "El Nino"
    if oni <= -0.5:
        return "La Nina"
    return "Neutral"


def _parse_nino34(text: str) -> list:
    records = []
    for line in text.strip().splitlines():
        parts = line.split()
        # Expected columns: Year Month Total CLIM ANOM ...
        if len(parts) >= 5 and parts[0].isdigit():
            try:
                year, month, anom = int(parts[0]), int(parts[1]), float(parts[4])
                records.append((year, month, anom))
            except ValueError:
                continue
    return records


def _classify(oni: float) -> str:
    if oni >= 2.0:
        return "Super El Niño"
    if oni >= 1.5:
        return "Strong El Niño"
    if oni >= 1.0:
        return "Moderate El Niño"
    if oni >= 0.5:
        return "Weak El Niño"
    if oni <= -1.5:
        return "Strong La Niña"
    if oni <= -0.5:
        return "La Niña"
    return "Neutral ENSO"


def _fallback() -> dict:
    now = datetime.now()
    return {
        "value": 0.0,
        "phase": "Neutral (offline estimate)",
        "year": now.year,
        "month": now.month,
        "month_name": _MONTH_NAMES.get(now.month, ""),
        "source": "Offline fallback",
    }
