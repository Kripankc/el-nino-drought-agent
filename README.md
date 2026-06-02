# ENSA — El Niño Sentinel Agent 🌾🛰️
> **Free agricultural drought early-warning system for smallholder farmers**

ENSA monitors any farm location on Earth for El Niño-driven drought risk. It combines real weather data, evapotranspiration calculations, and ENSO index tracking to produce a simple risk score with plain-language recommendations.

**Everything is free.** No satellites subscription, no paid API keys, no cloud bill. Just open data.

---

## Data Sources (all free, no registration)

| Source | What it provides |
|--------|-----------------|
| [Open-Meteo](https://open-meteo.com/) | Daily rainfall, temperature, and FAO-56 evapotranspiration for any lat/lon, back to 1940 |
| [Open-Meteo Forecast](https://open-meteo.com/) | 14-day weather forecast, globally |
| [NOAA CPC NINO3.4](https://www.cpc.ncep.noaa.gov/) | Monthly Oceanic Niño Index (El Niño / La Niña intensity) |

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the dashboard
```bash
streamlit run ensa/dashboard/app.py
```

### 3. (Optional) API key for AI narrative
Create a `.env` file from the template:
```bash
cp .env.example .env
# edit .env and add ANTHROPIC_API_KEY or OPENAI_API_KEY
```
The dashboard works fully without this. The AI feature only adds a richer narrative paragraph.

---

## Project Structure

```
ensa/
  ingest/
    openmeteo.py     # Real weather data from Open-Meteo (free)
    enso.py          # NINO3.4 SST anomaly from NOAA CPC (free)
  agent/
    brain.py         # Drought scoring + optional LLM narrative
  math/
    meteorology.py   # SPI-3, SPEI calculations
    pdsi.py          # Palmer Drought Severity Index
    indices.py       # NDVI, NDWI, VCI (for satellite path)
  core/
    gatekeeper.py    # Pearson correlation & confidence scoring
  dashboard/
    app.py           # Streamlit farmer-facing dashboard
  db/
    schema.sql       # SQLite schema for saved assessments
```

---

## Risk Score Methodology

ENSA computes a **0–100 drought risk score** from:

1. **SPI-3** (McKee et al. 1993) — Standardised Precipitation Index from real rainfall history
2. **Cumulative Water Deficit** (P − ET₀) — Rainfall minus crop evaporation demand (FAO-56 Penman-Monteith)
3. **Temperature stress** — Heat above the crop's optimal range increases evaporation
4. **ENSO amplification** — El Niño phases (NINO3.4 ≥ +0.5°C) multiply the score up to ×1.5
5. **Crop stage weighting** — Flowering and grain-fill stages carry ×1.35 weight (most sensitive to water stress)

---

## Hosting (free)

Deploy for free on [Streamlit Community Cloud](https://streamlit.io/cloud):
1. Push this repo to GitHub
2. Connect to Streamlit Cloud
3. Set `STREAMLIT_SHARING_MODE=1` in Secrets
4. Optionally add `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` to Secrets for the AI feature

The background worker (`run_worker.py`) can run weekly via GitHub Actions (free tier).
