# ENSA (El Niño Sentinel Agent) 🛰️🌾
> **Drought Early Warning & Earth Observation Monitoring System**

ENSA is an autonomous, agentic AI system designed to sit on top of Copernicus GDO, ECMWF, and CDSE STAC services to predict, monitor, and assess agricultural drought impacts at a local field scale during the **El Niño 2026** season in Southern Africa.

---

## 🚀 Getting Started

### 1. Set as Active Workspace
To begin developing and running this project, **set this directory as your active workspace in your IDE**.
- Workspace path: `C:\Users\USER\.gemini\antigravity\scratch\el_nino_drought_agent`

### 2. Install Dependencies
Make sure you have a Python environment ready (Python 3.10+ recommended). Run the following to install the core libraries:
```bash
pip install -r requirements.txt
```

### 3. API Key Setup
You will need credentials for the following services:
- **Copernicus CDS (Climate Data Store)**: Register a free account at [cds.climate.copernicus.eu](https://cds.climate.copernicus.eu/) and place your `.cdsapirc` file in your home directory.
- **CDSE (Copernicus Data Space Ecosystem)**: Register a free account at [dataspace.copernicus.eu](https://dataspace.copernicus.eu/) for STAC queries and Sentinel-2 downloads.
- **OpenAI / Anthropic (LLM Layer)**: Provide API credentials in your environment variables.

---

## 📂 Project Structure

- `ensa/system_design.md`: Core system architecture, database schema, and data flows.
- `ensa/ingest/`: Python scripts to ingest ECMWF forecasts, GDO WCS indicators, and ENSO SST indices.
- `ensa/eo/`: STAC searcher and raster processing (NDVI, VCI, NDWI) with `xarray` and `rioxarray`.
- `ensa/agent/`: The LLM agentic core, containing prompt templates and tools for evaluating seasonal risks.
- `ensa/dashboard/`: MVP dashboard built using Streamlit and Folium maps.
- `run_worker.py`: 24/7 background scheduler loop.

---

## 🤖 Leverage Agentic Workflows

We recommend using the following slash commands in the IDE:
- `/goal`: To initiate long-running autonomous development tasks (e.g., *"Set up the entire ingestion pipeline and write automated tests for it"*).
- `/schedule`: To schedule periodic data ingestion runs or agent evaluations.
- `/browser`: To query the STAC catalogs visually or inspect CDS documentation pages.
