# ENSOwatch AI

> **Agricultural drought early-warning, powered by free open data.**
> Any farm, any date, any crop — no API keys, no sign-up.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ensa-kripan.streamlit.app/)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)
[![Data: ERA5 · NOAA](https://img.shields.io/badge/data-ERA5%20%C2%B7%20NOAA%20CPC-orange.svg)](#data-sources)

🔗 **Live app: [ensa-kripan.streamlit.app](https://ensa-kripan.streamlit.app/)**

---

## What it does

ENSOwatch AI monitors any farm on Earth for **drought risk driven by El Niño / La Niña / Southern Oscillation (ENSO)**. Click a point on the world map, pick a crop, and you get:

| Tab | What you see |
|-----|--------------|
| **Farm Status** | A 0–100 drought risk score, plain-English summary, 5 key indicators (rainfall, water deficit, SPI-3, soil moisture, temperature) and prioritised actions for this week |
| **90-Day History** | Monthly rainfall vs crop water requirement, cumulative water balance, soil-moisture trend, temperature trend — each chart paired with a written analysis column |
| **14-Day Forecast** | Day-by-day rainfall outlook, projected water deficit, two-week balance trajectory |
| **El Niño Impact** | For this exact location, how growing-season rainfall differs between past El Niño years vs Neutral vs La Niña years (1985–present) |
| **Historical Analysis** | Pick any past date and see what was observed vs what the climatology baseline predicted vs what an ENSO-aware forecast would have predicted — a hindsight skill assessment |
| **Methodology** | Full scoring methodology with citations |

When the user picks a date older than 7 days, the dashboard automatically switches to **historical analysis mode** — past tense narrative, no irrigation advice, observations only, with a model-vs-observed comparison panel.

---

## Why this matters

The 2023–24 El Niño wiped out roughly 40–50% of the maize harvest across Southern Africa. Punjab's monsoon was suppressed by ~25%. Smallholder farmers had no localised early warning. Commercial agtech platforms exist but cost money and require sign-ups.

ENSOwatch AI is **free, location-aware, browser-based, and works on any phone**. It's built end-to-end on free public data — no subscriptions, no API keys for the core functionality, no usage limits we can hit.

---

## Data sources

| Source | What it provides | Cost |
|--------|------------------|------|
| **[Open-Meteo ERA5 archive](https://open-meteo.com/)** | Daily rainfall, temperature, FAO-56 reference evapotranspiration, volumetric soil moisture (0–7 cm and 7–28 cm), back to 1940 | Free · No key |
| **[Open-Meteo Forecast](https://open-meteo.com/)** | 14-day weather forecast (precipitation, temperature, ET₀) for any lat/lon | Free · No key |
| **[NOAA CPC NINO3.4](https://www.cpc.ncep.noaa.gov/)** | Monthly Oceanic Niño Index (ONI) — the global El Niño / La Niña indicator | Free · No key |
| **[FAO Crop Calendar](https://cropcalendar.apps.fao.org/)** + USDA IPAD + IRRI Rice Knowledge Bank | Region-specific crop growing windows, water requirements, critical stages | Static (literature-grounded) |

**No simulated or fallback values are shown.** If a data source is offline the dashboard surfaces the error and stops; it never invents data.

---

## Methodology

ENSOwatch AI computes a **0–100 drought risk score** from five components:

1. **SPI-3** *(McKee et al. 1993)* — Standardised Precipitation Index over 90 days, fitted to a two-parameter Gamma distribution from the full ERA5 daily history. SPI-3 < −1.0 indicates drought onset; < −2.0 indicates severe drought. **Up to 40 points.**
2. **Cumulative water deficit (P − ET₀)** *(FAO-56)* — Total ERA5 rainfall minus FAO-56 Penman-Monteith reference evapotranspiration over 90 days. **Up to 40 points.**
3. **Temperature stress** — Mean temperature above 25 °C accelerates evaporation and crop transpiration demand. **Up to 20 points.**
4. **ENSO amplification** *(Ropelewski & Halpert 1987)* — If NINO3.4 ≥ +0.5 °C (El Niño developing), the score is multiplied up to ×1.5, reflecting the documented teleconnection between Pacific SST anomalies and rainfall in Southern Africa, South Asia, and Australia.
5. **Crop stage weighting** — Flowering, tasseling, panicle initiation, and grain-filling stages are amplified ×1.35, because water stress during pollination causes irreversible yield loss.

Off-season months apply a ×0.25 dampener — dry conditions during fallow are expected, not a crop emergency.

The full methodology is also available in the **Methodology** tab of the app itself.

---

## Crops & regions

**18 regions** with FAO/USDA-grounded crop calendars and water requirements:

| Region | Main crops |
|---|---|
| North America (Corn Belt + Prairies) | Maize · Soybean · Spring Wheat · Winter Wheat |
| South America (Brazil/Argentina) | Soybean · Maize · Winter Wheat · Sugarcane · Coffee |
| Europe | Wheat · Maize · Sunflower |
| North Africa | Wheat · Barley · Olive |
| West Africa | Maize · Millet · Sorghum · Groundnut · Cowpea |
| East Africa (Kenya, Ethiopia, Uganda) | Maize (Long & Short Rains) · Sorghum · Tea · Coffee |
| Southern Africa (Zambia, Zimbabwe, etc.) | Maize · Sorghum/Millet · Groundnut · Soybean · Cassava · Tobacco |
| Central Asia | Cotton · Wheat |
| Nepal · India · Pakistan · Bangladesh | Rice · Wheat · Cotton · Sugarcane · Groundnut · Millet · Jute |
| Myanmar · SE Asia · China · Sri Lanka | Rice · Maize · Cotton · Tea · Cassava |
| Australia | Wheat · Barley · Canola · Sorghum |

The region and crop calendar are auto-detected from the dropped pin — no setup required.

---

## Project structure

```
ensa/
├── ingest/
│   ├── openmeteo.py        # ERA5 weather + 14-day forecast + soil moisture + climatology + window
│   └── enso.py             # NOAA CPC NINO3.4 monthly history & ENSO classifier
├── analysis/
│   ├── crop_calendars.py   # FAO/USDA-grounded calendars for 18 regions
│   ├── elnino.py           # El Niño vs Neutral vs La Niña seasonal comparison
│   └── hindsight.py        # Model-vs-observed comparison for past dates
├── agent/
│   └── brain.py            # Drought scoring + plain-English summaries + optional AI narrative
├── math/
│   ├── meteorology.py      # SPI-3 (Gamma fit), SPEI
│   └── pdsi.py             # Palmer Drought Severity Index
└── dashboard/
    └── app.py              # Streamlit dashboard (entry point)
```

---

## Run locally

```bash
git clone https://github.com/Kripankc/el-nino-drought-agent.git
cd el-nino-drought-agent
pip install -r requirements.txt
streamlit run ensa/dashboard/app.py
```

Opens at `http://localhost:8501`. No API keys, no environment variables, no setup.

### Optional: AI-enhanced narrative
The core dashboard works without any keys. If you want an AI-generated paragraph for each farm, paste an Anthropic or OpenAI API key in the sidebar. The key stays in your session — it is never logged or stored.

---

## Deploy your own copy

ENSOwatch AI is designed for free hosting on [**Streamlit Community Cloud**](https://share.streamlit.io):

1. Fork this repo to your GitHub
2. Go to share.streamlit.io and connect your repo
3. Set main file path to `ensa/dashboard/app.py`
4. Choose Python 3.11
5. Click Deploy

Free hosting forever. Every push to `main` redeploys automatically.

---

## Citations & references

- **McKee, T. B., Doesken, N. J., & Kleist, J.** (1993). *The relationship of drought frequency and duration to time scales.* Proceedings of the 8th Conference on Applied Climatology.
- **Vicente-Serrano, S. M., Beguería, S., & López-Moreno, J. I.** (2010). *A multiscalar drought index sensitive to global warming: the standardized precipitation evapotranspiration index.* Journal of Climate, 23(7), 1696–1718.
- **Palmer, W. C.** (1965). *Meteorological drought.* US Weather Bureau Research Paper No. 45.
- **Ropelewski, C. F., & Halpert, M. S.** (1987). *Global and regional scale precipitation patterns associated with the El Niño/Southern Oscillation.* Monthly Weather Review, 115(8), 1606–1626.
- **Allen, R. G., Pereira, L. S., Raes, D., & Smith, M.** (1998). *Crop evapotranspiration — Guidelines for computing crop water requirements.* FAO Irrigation and Drainage Paper No. 56.
- **Kogan, F. N.** (1995). *Application of vegetation index and brightness temperature for drought detection.* Advances in Space Research, 15(11), 91–100.

---

## Roadmap

- [ ] Sentinel-2 NDVI satellite layer (STAC + Microsoft Planetary Computer) — *not yet integrated*
- [ ] IRI/CPC seasonal ENSO forecast plume
- [ ] Multi-language farmer-facing summaries
- [ ] Email/SMS push for high-risk locations
- [ ] Custom field polygon upload (GeoJSON)

Contributions welcome — open an issue or a pull request.

---

## A note on the name

The original codebase was called *El Niño Sentinel Agent* (ENSA). The current name **ENSOwatch AI** reflects that the dashboard covers **the full ENSO cycle** — El Niño *and* La Niña *and* Neutral phases — rather than only El Niño events. The "AI" suffix refers to the optional AI-enhanced narrative feature; the core analytical pipeline is deterministic and reproducible.

This dashboard does **not** currently use Sentinel-2 satellite imagery. All vegetation and soil-moisture indicators come from ERA5 reanalysis (which itself assimilates satellite radiances). Sentinel-2 NDVI integration is on the roadmap.

---

## License

MIT — see [LICENSE](LICENSE) for full text. Free to use, modify, and redistribute. Attribution appreciated but not required.

---

## Author

**Kripan K C**
M.Sc. Environmental Engineering, Technical University of Munich (TUM)
Student Research Assistant, German Aerospace Center (DLR)

📧 [Kripankc3@gmail.com](mailto:Kripankc3@gmail.com)

---

## Acknowledgments

Built on top of open data from **Open-Meteo**, **NOAA Climate Prediction Center**, the **FAO Crop Calendar**, **USDA IPAD**, and **IRRI Rice Knowledge Bank**. None of these organisations endorse this project — but ENSOwatch AI would not exist without their free public APIs and datasets.

Built with [Streamlit](https://streamlit.io), [folium](https://python-visualization.github.io/folium/), and Python.
