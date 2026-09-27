# ENSOwatch

A static web tool for farmers and extension officers. Search a place or click the map to see:

- which crops are grown there, and when they are sown and harvested;
- this season's rainfall, compared with the crop's water need and the 1991–2020 normal range;
- temperature, humidity, reference evapotranspiration and soil moisture, each with its normal range;
- a 15-day ensemble forecast and a 7-month seasonal outlook;
- what happened at that place in past El Niño and La Niña seasons, with a significance test;
- rule-based guidance. Each item shows the data that triggered it and a source.

Pick a past date to see the season around it and what followed. Pick a comparison season, such as the last El Niño, to overlay it. The URL stores location, date, crop and comparison, so a view can be shared as a link.

Methods, sources and limitations are on the site's [methods page](methods.html).

## Data

| Layer | Source | How it reaches the page |
|---|---|---|
| Daily weather 1950–present | ERA5 (`models=era5`), Open-Meteo Historical API | Browser, cached in IndexedDB |
| 15-day forecast | ECMWF IFS 0.25° ensemble, Open-Meteo Ensemble API | Browser |
| 7-month outlook | ECMWF SEAS5, Open-Meteo Seasonal API | Browser |
| ENSO index and episodes | NOAA CPC RONI (ONI as a fallback) | `pipeline/enso.py`, daily GitHub Action |
| Crop harvested area | CROPGRIDS v1.08 (Tang et al. 2024) | `pipeline/crops.py`, manual GitHub Action |
| Crop calendars | GGCMI Phase 3 (Jägermeyr et al. 2021) | `pipeline/crops.py` |
| Kc, stage lengths, heat thresholds | FAO-56 Tables 11–12; Schlenker & Roberts 2009; Yoshida 1981; Lobell et al. 2012 | `public/data/crop_params.json` (check against the originals before citing) |

The app never substitutes placeholder values. If a source fails, the section says so.

## Build the data

Both data jobs run on GitHub's runners. Neither needs an API key.

1. Actions → **Build crop data** → Run workflow. This downloads CROPGRIDS (~0.8 GB) and the GGCMI calendars, then commits `public/data/crops/`.
2. Actions → **Update ENSO data** → Run workflow. After that it runs daily.
3. Actions → **API contract check** checks that every Open-Meteo field the app uses still exists.

Locally:

```bash
pip install -r pipeline/requirements.txt
python pipeline/enso.py --out public/data/enso.json
python pipeline/crops.py --work /tmp/cropwork --out public/data/crops
pytest -q pipeline/tests
```

## Run the site

```bash
npm ci
npm run dev        # http://localhost:5173
npm test           # unit tests for the calculations
npm run build      # static site in dist/
python tests/e2e/smoke.py   # browser smoke test with mocked (synthetic) API responses
```

Deployment: set Settings → Pages → Source to **GitHub Actions**. Every push to `main` and every data update redeploys.

## Layout

```
index.html, methods.html   pages
src/calc/                  season, FAO-56 water balance, climatology, ENSO composites, guidance rules (unit-tested)
src/api/                   Open-Meteo, Nominatim and static-data loaders
src/ui/                    sections and charts (Observable Plot)
pipeline/                  data builders, API contract check, tests
public/data/               generated data + crop_params.json
```

## Licence and attribution

Code: MIT. Weather data by Open-Meteo.com (non-commercial free tier), from Copernicus/ECMWF. ENSO: NOAA CPC. CROPGRIDS and GGCMI data: CC BY 4.0. Map data © OpenStreetMap contributors.

Author: Kripan K C
