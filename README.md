# ENSOwatch AI

> **Agricultural drought early-warning powered by AI.**
> Free, open-data, no API keys, no sign-up. Any farm on Earth.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ensa-kripan.streamlit.app/)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)
[![Data: ERA5 · NOAA](https://img.shields.io/badge/data-ERA5%20%C2%B7%20NOAA%20CPC-orange.svg)](#data-sources)

---

## What ENSOwatch AI does

ENSOwatch AI monitors any farm location on Earth for **ENSO-driven drought risk** (El Niño *and* La Niña phases) and gives the farmer a clear, actionable verdict in plain language.

Click anywhere on the world map, pick a crop, and the dashboard shows:

| | |
|---|---|
| **🌾 Farm Status** | A 0–100 drought risk score, plain-English summary, key indicators (rainfall, water deficit, SPI-3, soil moisture, temperature), and a prioritised action list. |
| **📈 90-Day History** | Monthly rainfall vs crop water requirement, cumulative water balance, soil moisture trend, side-by-side analysis. |
| **🔮 14-Day Forecast** | Day-by-day rainfall outlook, projected water deficit, model-narrative verdict for the next two weeks. |
| **🌊 El Niño Impact** | For the picked location, contrasts past El Niño years vs Neutral vs La Niña years (1985–present), with per-year bar chart and current-season verdict. |
| **🕰️ Hindsight** | Pick any past date and compare what was observed vs the climatology baseline vs the ENSO-aware forecast — tells you whether knowing the ENSO state would have improved the seasonal forecast. |
| **📖 Methodology** | Full scoring methodology with citations. |

---

## Live demo

🔗 **[ensa-kripan.streamlit.app](https://ensa-kripan.streamlit.app/)**

Works on desktop and mobile. No login. Free.

---

## Why this matters

The 2023–24 El Niño was among the strongest on record. Southern Africa's 2024 maize harvest collapsed by roughly 40–50% across Zambia, Zimbabwe, and Malawi. Punjab's monsoon was suppressed. Drought-driven food-security crises hit several regions where farmers had no localised early warning.

Commercial agtech platforms exist, but they cost money, require sign-ups, and many smallholder farmers can't access them. **ENSA is a free, location-aware drought dashboard that runs in any browser — designed for the people who actually need it.**

Built end-to-end on free, public data sources, hosted free on Streamlit Cloud, with no API keys or hidden costs.

---

## Data sources

| Source | What it provides | Cost |
|--------|-----------------|------|
| **[Open-Meteo ERA5 archive](https://open-meteo.com/)** | Daily rainfall, mean temperature, FAO-56 reference evapotranspiration (ET₀), volumetric soil moisture (0–7 cm and 7–28 cm), back to 1940. | Free · No key |
| **[Open-Meteo Forecast](https://open-meteo.com/)** | 14-day weather forecast (rainfall, temperature, ET₀) for any lat/lon. | Free · No key |
| **[NOAA CPC NINO3.4](https://www.cpc.ncep.noaa.gov/)** | Monthly Oceanic Niño Index (ONI) — the global El Niño / La Niña indicator. | Free · No key |
| **[FAO Crop Calendars](https://cropcalendar.apps.fao.org/)** + USDA IPAD + IRRI Rice Knowledge Bank | Region-specific crop growth windows and water requirements (cited in source). | Free · No key |

**No simulated or fallback values are ever shown.** If a data source is offline the dashboard surfaces an error.

---

## Methodology

ENSA computes a **0–100 drought risk score** from five components:

1. **SPI-3** (McKee et al. 1993) — Standardised Precipitation Index over 90 days, fitted to a Gamma distribution from the full ERA5 daily history. SPI-3 < −1.0 indicates drought onset. *Up to 40 points.*

2. **Cumulative water deficit** — Total ERA5 rainfall minus FAO-56 Penman-Monteith evapotranspiration over 90 days. *Up to 40 points.*

3. **Temperature stress** — Mean temperature above 25 °C accelerates evaporation and crop transpiration demand. *Up to 20 points.*

4. **ENSO amplification** (Ropelewski & Halpert 1987) — If NINO3.4 ≥ +0.5 °C (El Niño developing), the score is multiplied up to ×1.5, reflecting the well-documented teleconnection between Pacific SST anomalies and rainfall in Southern Africa, South Asia, and Australia.

5. **Crop stage weighting** — Flowering, tasseling, panicle initiation, and grain-filling stages are amplified ×1.35 because water stress during pollination causes irreversible yield loss.

Off-season months apply a ×0.25 dampener — dry conditions during fallow are expected, not a crop emergency.

Detailed methodology, equations, and references are in-app under the **Methodology** tab.

---

## Crops & regions covered

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

Crop and region are auto-detected from the dropped pin — no setup required.

---

## Project structure

```
ensa/
├── ingest/
│   ├── openmeteo.py        # ERA5 weather + 14-day forecast + soil moisture
│   └── enso.py             # NOAA CPC NINO3.4 monthly history & classifier
├── analysis/
│   ├── crop_calendars.py   # FAO/USDA-grounded calendars for 18 regions
│   ├── elnino.py           # El Niño vs Neutral seasonal comparison
│   └── hindsight.py        # Model-vs-observed comparison for past dates
├── agent/
│   └── brain.py            # Drought scoring + plain-English summaries + optional LLM
├── math/
│   ├── meteorology.py      # SPI-3 (Gamma fit), SPEI
│   └── pdsi.py             # Palmer Drought Severity Index
├── core/
│   └── gatekeeper.py       # Pearson correlation, confidence scoring
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

That's it — no API keys, no environment variables, no setup. Opens at `http://localhost:8501`.

### Optional: AI-enhanced narrative
The core dashboard works without any keys. If you want an AI-generated paragraph for each location, paste an **Anthropic** or **OpenAI** API key in the sidebar. The key stays in your session — it's never logged or stored.

---

## Deploy your own copy

ENSA is designed for free hosting on [**Streamlit Community Cloud**](https://share.streamlit.io):

1. Fork this repo to your GitHub
2. Go to share.streamlit.io and connect your repo
3. Set the main file path to `ensa/dashboard/app.py`
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

## A note on satellites

ENSOwatch AI does **not currently use Sentinel-2 satellite imagery.** All vegetation and soil moisture indicators come from the ERA5 reanalysis (which itself ingests satellite radiances). Adding real-time NDVI maps from the Sentinel-2 STAC catalog is on the roadmap below.

---

## Roadmap

- [ ] Sentinel-2 NDVI satellite layer (STAC + Planetary Computer) — *not yet integrated*
- [ ] IRI/CPC seasonal ENSO forecast plume
- [ ] Multi-language farmer-facing summaries
- [ ] Email/SMS push for high-risk locations
- [ ] Custom field polygon upload (GeoJSON)

Contributions welcome — open an issue or PR.

---

## License

MIT — see [LICENSE](LICENSE) for full text.

You may freely use, modify, and redistribute. Attribution appreciated but not required.

---

## Acknowledgments

Built on top of open data from **Open-Meteo**, **NOAA Climate Prediction Center**, the **FAO Crop Calendar**, **USDA IPAD**, and **IRRI Rice Knowledge Bank**. None of these organisations endorse this project — but ENSA wouldn't exist without their free public APIs and datasets.

Built with [Streamlit](https://streamlit.io), [folium](https://python-visualization.github.io/folium/), and Python.
