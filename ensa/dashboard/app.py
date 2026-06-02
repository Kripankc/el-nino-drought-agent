"""
ENSA — El Niño Sentinel Agent
Farmer-facing drought early-warning dashboard.
All weather data: Open-Meteo (free, no key).
ENSO data: NOAA CPC (free, no key).
LLM narrative: optional — user supplies their own API key.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

from ensa.ingest.openmeteo import fetch_weather, fetch_forecast
from ensa.ingest.enso import fetch_current_oni
from ensa.agent.brain import (
    compute_drought_score,
    generate_summary,
    generate_recommendations,
    call_llm_narrative,
)
from ensa.db.connection import get_db_connection, init_db

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ENSA — Drought Early Warning",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS — dark glassmorphic theme, kept clean
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background: linear-gradient(135deg,#060913 0%,#020307 100%); color:#e2e8f0; }
  h1,h2,h3,h4 { color:#fff; font-weight:700; letter-spacing:-.025em; }
  .card {
    background:rgba(255,255,255,.03); border-radius:16px; padding:20px 24px;
    border:1px solid rgba(255,255,255,.08);
    box-shadow:0 8px 32px rgba(0,0,0,.45); margin-bottom:18px;
  }
  .risk-block {
    border-radius:14px; padding:22px 28px; margin-bottom:18px;
    border:1px solid rgba(255,255,255,.1);
  }
  .risk-score { font-size:3.6rem; font-weight:800; line-height:1; }
  .risk-label { font-size:1.4rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
  .risk-summary { font-size:1.05rem; line-height:1.65; color:#e2e8f0; margin-top:12px; }
  .rec-item { padding:10px 14px; border-radius:10px;
    background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.06);
    margin-bottom:8px; font-size:.97rem; line-height:1.5; }
  .stTabs [data-baseweb="tab-list"] { gap:20px; background:transparent; }
  .stTabs [data-baseweb="tab"] { background:transparent; color:#a0aec0; font-weight:600; }
  .stTabs [aria-selected="true"] { color:#38ef7d !important;
    border-bottom-color:#38ef7d !important; }
  .data-label { font-size:.75rem; color:#a0aec0; text-transform:uppercase;
    letter-spacing:.06em; margin-bottom:2px; }
  .data-value { font-size:1.6rem; font-weight:700; color:#fff; }
  .data-sub   { font-size:.83rem; color:#a0aec0; margin-top:1px; }
  .enso-chip {
    display:inline-block; padding:4px 12px; border-radius:20px;
    font-size:.82rem; font-weight:700; letter-spacing:.03em;
  }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
PRESETS = {
    "Mazabuka, Zambia":           {"coords": [-16.25, 27.65], "region": "Zambia"},
    "Punjab, India":              {"coords": [30.90,  75.85], "region": "India"},
    "Eldoret, Kenya":             {"coords": [0.51,   35.26], "region": "East Africa"},
    "Griffith, Australia":        {"coords": [-34.28, 146.04], "region": "Australia"},
    "Choma, Zambia":              {"coords": [-16.82, 26.98], "region": "Zambia"},
    "Custom Point":               {"coords": [-16.25, 27.65], "region": "Zambia"},
}

CROP_CALENDARS = {
    "Zambia": {
        "White Maize": {
            "start": 11, "end": 5, "daily_demand_mm": 5.0,
            "optimal_temp": (20, 28), "optimal_precip_mm_day": (4.5, 6.5),
            "stages": {
                11:"Planting & Emergence", 12:"Planting & Emergence",
                1:"Vegetative Growth", 2:"Vegetative Growth",
                3:"Flowering & Tasseling (Critical)", 4:"Grain Fill & Maturity",
                5:"Harvesting Phase",
                6:"Fallow", 7:"Fallow", 8:"Fallow", 9:"Fallow", 10:"Fallow",
            },
        },
        "Sorghum / Millet": {
            "start": 12, "end": 6, "daily_demand_mm": 3.8,
            "optimal_temp": (24, 32), "optimal_precip_mm_day": (3.0, 4.5),
            "stages": {
                12:"Planting & Emergence", 1:"Vegetative Growth", 2:"Vegetative Growth",
                3:"Vegetative Growth", 4:"Flowering Stage", 5:"Maturity",
                6:"Harvesting Phase",
                7:"Fallow", 8:"Fallow", 9:"Fallow", 10:"Fallow", 11:"Fallow",
            },
        },
    },
    "India": {
        "Kharif Rice": {
            "start": 6, "end": 11, "daily_demand_mm": 7.5,
            "optimal_temp": (25, 33), "optimal_precip_mm_day": (6.5, 9.5),
            "stages": {
                6:"Nursery & Transplanting", 7:"Tillering",
                8:"Panicle Initiation", 9:"Flowering (Critical)",
                10:"Grain Filling", 11:"Harvesting Phase",
                12:"Fallow", 1:"Fallow", 2:"Fallow", 3:"Fallow", 4:"Fallow", 5:"Fallow",
            },
        },
        "Rabi Wheat": {
            "start": 11, "end": 4, "daily_demand_mm": 4.2,
            "optimal_temp": (12, 22), "optimal_precip_mm_day": (2.0, 4.0),
            "stages": {
                11:"Sowing & Germination", 12:"Crown Root Initiation",
                1:"Tillering", 2:"Jointing",
                3:"Heading & Flowering (Critical)", 4:"Harvesting Phase",
                5:"Fallow", 6:"Fallow", 7:"Fallow", 8:"Fallow", 9:"Fallow", 10:"Fallow",
            },
        },
    },
    "East Africa": {
        "Maize (Long Rains)": {
            "start": 3, "end": 9, "daily_demand_mm": 4.8,
            "optimal_temp": (18, 26), "optimal_precip_mm_day": (4.0, 6.0),
            "stages": {
                3:"Planting & Emergence", 4:"Vegetative", 5:"Vegetative",
                6:"Tasseling & Silking (Critical)", 7:"Grain Filling",
                8:"Cob Maturity", 9:"Harvesting Phase",
                10:"Fallow", 11:"Fallow", 12:"Fallow", 1:"Fallow", 2:"Fallow",
            },
        },
        "Sorghum": {
            "start": 4, "end": 10, "daily_demand_mm": 3.5,
            "optimal_temp": (22, 30), "optimal_precip_mm_day": (2.5, 4.5),
            "stages": {
                4:"Planting", 5:"Vegetative", 6:"Vegetative",
                7:"Flowering", 8:"Grain Filling", 9:"Maturity",
                10:"Harvesting Phase",
                11:"Fallow", 12:"Fallow", 1:"Fallow", 2:"Fallow", 3:"Fallow",
            },
        },
    },
    "Australia": {
        "Winter Wheat": {
            "start": 5, "end": 11, "daily_demand_mm": 3.8,
            "optimal_temp": (10, 20), "optimal_precip_mm_day": (2.0, 4.0),
            "stages": {
                5:"Sowing & Emergence", 6:"Tillering", 7:"Jointing",
                8:"Booting", 9:"Heading & Flowering (Critical)",
                10:"Grain Fill", 11:"Harvesting Phase",
                12:"Fallow", 1:"Fallow", 2:"Fallow", 3:"Fallow", 4:"Fallow",
            },
        },
        "Barley": {
            "start": 5, "end": 10, "daily_demand_mm": 3.6,
            "optimal_temp": (12, 22), "optimal_precip_mm_day": (2.0, 4.0),
            "stages": {
                5:"Sowing & Emergence", 6:"Tillering", 7:"Jointing",
                8:"Flowering (Critical)", 9:"Grain Filling",
                10:"Harvesting Phase",
                11:"Fallow", 12:"Fallow", 1:"Fallow", 2:"Fallow", 3:"Fallow", 4:"Fallow",
            },
        },
    },
}


def _detect_region(lat: float, lon: float) -> str:
    if 65 < lon < 95 and 5 < lat < 38:
        return "India"
    if 110 < lon < 155 and -45 < lat < -10:
        return "Australia"
    if 30 < lon < 45 and -15 < lat < 15:
        return "East Africa"
    return "Zambia"


def _is_active_season(cal: dict, month: int) -> bool:
    s, e = cal["start"], cal["end"]
    if s <= e:
        return s <= month <= e
    return month >= s or month <= e


# ─────────────────────────────────────────────────────────────────────────────
# CACHED DATA FETCHERS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_weather(lat: float, lon: float) -> pd.DataFrame | None:
    try:
        return fetch_weather(lat, lon, days_back=400)
    except Exception as e:
        st.session_state["weather_error"] = str(e)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_forecast(lat: float, lon: float) -> pd.DataFrame | None:
    try:
        return fetch_forecast(lat, lon, days=14)
    except Exception as e:
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def _cached_enso() -> dict:
    return fetch_current_oni()


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "point" not in st.session_state:
    st.session_state.point = PRESETS["Mazabuka, Zambia"]["coords"]
if "preset_name" not in st.session_state:
    st.session_state.preset_name = "Mazabuka, Zambia"

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown(
    "<h2 style='text-align:center;margin-bottom:4px'>🌾 ENSA</h2>"
    "<p style='text-align:center;color:#a0aec0;font-size:.85rem;margin-top:0'>"
    "El Niño Sentinel Agent</p>",
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")

st.sidebar.subheader("1. Location")
preset_name = st.sidebar.selectbox(
    "Select preset location",
    list(PRESETS.keys()),
    index=list(PRESETS.keys()).index(st.session_state.preset_name),
)
if preset_name != st.session_state.preset_name:
    st.session_state.preset_name = preset_name
    if preset_name != "Custom Point":
        st.session_state.point = PRESETS[preset_name]["coords"]
    st.rerun()

c1, c2 = st.sidebar.columns(2)
with c1:
    lat_in = st.number_input("Latitude", value=float(st.session_state.point[0]), format="%.4f")
with c2:
    lon_in = st.number_input("Longitude", value=float(st.session_state.point[1]), format="%.4f")

if [lat_in, lon_in] != list(st.session_state.point):
    st.session_state.point = [lat_in, lon_in]
    st.session_state.preset_name = "Custom Point"
    st.rerun()

lat, lon = st.session_state.point
active_region = _detect_region(lat, lon)

st.sidebar.markdown("---")
st.sidebar.subheader("2. Crop")
available_crops = list(CROP_CALENDARS.get(active_region, CROP_CALENDARS["Zambia"]).keys())
crop_choice = st.sidebar.selectbox("Crop type", available_crops)
cal = CROP_CALENDARS[active_region][crop_choice]
today_month = datetime.now().month
crop_stage = cal["stages"][today_month]
is_active = _is_active_season(cal, today_month)

st.sidebar.markdown("---")
st.sidebar.subheader("3. AI Analysis (optional)")
st.sidebar.caption(
    "The core dashboard is 100% free. Optionally, paste your own API key "
    "below to unlock an AI-generated narrative for your farm."
)
ai_provider = st.sidebar.selectbox("AI Provider", ["Anthropic (Claude)", "OpenAI (GPT-4o-mini)"])
ai_key = st.sidebar.text_input("API Key", type="password", placeholder="sk-ant-... or sk-...")

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<div style='font-size:.78rem;color:#718096;text-align:center'>"
    "ENSA v2.0 · Weather: Open-Meteo · ENSO: NOAA CPC<br>"
    "Free & open-source</div>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
_lat_r = round(lat, 3)
_lon_r = round(lon, 3)

with st.spinner("Loading weather data for your location…"):
    df_weather = _cached_weather(_lat_r, _lon_r)
    df_forecast = _cached_forecast(_lat_r, _lon_r)
    oni = _cached_enso()

data_ok = df_weather is not None and not df_weather.empty

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='background:linear-gradient(90deg,#38ef7d,#11998e);"
    "-webkit-background-clip:text;-webkit-text-fill-color:transparent'>"
    "El Niño Sentinel Agent (ENSA)</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#a0aec0;font-size:1.05rem;margin-top:-8px'>"
    "Real-time agricultural drought early warning · Powered by Open-Meteo & NOAA</p>",
    unsafe_allow_html=True,
)

# ENSO STATUS STRIP
oni_v = oni["value"]
if oni_v >= 1.5:
    enso_bg, enso_txt = "#7f1d1d", "#fca5a5"
elif oni_v >= 0.5:
    enso_bg, enso_txt = "#78350f", "#fcd34d"
elif oni_v <= -0.5:
    enso_bg, enso_txt = "#1e3a5f", "#93c5fd"
else:
    enso_bg, enso_txt = "#14532d", "#86efac"

st.markdown(
    f"<div style='background:{enso_bg};border-radius:10px;padding:10px 18px;"
    f"margin-bottom:18px;display:flex;align-items:center;gap:16px'>"
    f"<span class='enso-chip' style='background:rgba(255,255,255,.15);color:{enso_txt}'>"
    f"NINO3.4: {oni_v:+.2f}°C</span>"
    f"<span style='color:{enso_txt};font-weight:600'>{oni['phase']}</span>"
    f"<span style='color:rgba(255,255,255,.55);font-size:.85rem'>"
    f"Source: {oni['source']} · {oni['month_name']} {oni['year']}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_farm, tab_trends, tab_forecast, tab_about = st.tabs([
    "🌾 Farm Status",
    "📈 90-Day Trends",
    "🔮 14-Day Outlook",
    "📖 About & Methods",
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: FARM STATUS
# ═════════════════════════════════════════════════════════════════════════════
with tab_farm:

    col_map, col_info = st.columns([3, 1])

    with col_map:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("📍 Farm Location")
        st.caption("Click anywhere on the map to select your farm location.")
        m = folium.Map(location=[lat, lon], zoom_start=7, tiles="OpenStreetMap")
        folium.Marker(
            location=[lat, lon],
            tooltip=f"{lat:.4f}°, {lon:.4f}°",
            icon=folium.Icon(color="green", icon="leaf"),
        ).add_to(m)
        map_out = st_folium(m, height=320, use_container_width=True, key="main_map")
        if map_out and map_out.get("last_clicked"):
            clat = map_out["last_clicked"]["lat"]
            clon = map_out["last_clicked"]["lng"]
            if [round(clat, 3), round(clon, 3)] != [round(lat, 3), round(lon, 3)]:
                st.session_state.point = [clat, clon]
                st.session_state.preset_name = "Custom Point"
                st.toast(f"📍 Location set to ({clat:.4f}°, {clon:.4f}°)")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_info:
        st.markdown("<div class='card' style='height:100%'>", unsafe_allow_html=True)
        st.subheader("Location")
        st.markdown(f"<div class='data-label'>Coordinates</div><div class='data-value' style='font-size:1rem'>{lat:.4f}°, {lon:.4f}°</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='data-label' style='margin-top:12px'>Region</div><div class='data-value' style='font-size:1.1rem'>{active_region}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='data-label' style='margin-top:12px'>Crop</div><div class='data-value' style='font-size:1.1rem'>{crop_choice}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='data-label' style='margin-top:12px'>Current Stage</div><div class='data-value' style='font-size:.95rem'>{crop_stage}</div>", unsafe_allow_html=True)
        if not is_active:
            st.warning("Off-season — crops are in fallow.")
        st.markdown("</div>", unsafe_allow_html=True)

    if not data_ok:
        st.error(
            "⚠️ Could not load weather data for this location. "
            "This may be a temporary network issue. "
            f"Error: {st.session_state.get('weather_error', 'Unknown')}"
        )
        st.stop()

    # ── RISK SCORE ──────────────────────────────────────────────────────────
    assessment = compute_drought_score(df_weather, oni_v, crop_stage, is_active)
    score = assessment["score"]
    level = assessment["alert_level"]
    color = assessment["alert_color"]
    emoji = assessment["alert_emoji"]

    summary_text = generate_summary(assessment, crop_choice, crop_stage, oni["phase"], st.session_state.preset_name)

    st.markdown(
        f"<div class='risk-block' style='background:linear-gradient(135deg,{color}18,{color}08);border-color:{color}55'>"
        f"<div style='display:flex;align-items:baseline;gap:16px'>"
        f"<span class='risk-score' style='color:{color}'>{score:.0f}</span>"
        f"<span style='color:{color};font-size:1.2rem'>/100</span>"
        f"<span class='risk-label' style='color:{color}'>{emoji} {level} Drought Risk</span>"
        f"</div>"
        f"<div class='risk-summary'>{summary_text}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 4 METRIC CARDS ──────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)

    tail90 = df_weather.tail(90)
    precip_90 = tail90["precip_mm"].sum()
    temp_90   = tail90["temp_c"].mean()
    et0_90    = tail90["et0_mm"].sum()
    deficit   = max(0, et0_90 - precip_90)

    opt_t_lo, opt_t_hi = cal["optimal_temp"]
    opt_p_lo, opt_p_hi = cal["optimal_precip_mm_day"]
    precip_daily_avg = precip_90 / 90

    with m1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        status_rain = "🔴 Below target" if precip_daily_avg < opt_p_lo else ("🟡 Low" if precip_daily_avg < opt_p_hi * 0.75 else "🟢 Adequate")
        st.markdown(
            f"<div class='data-label'>Rainfall (last 90 days)</div>"
            f"<div class='data-value'>{precip_90:.0f} mm</div>"
            f"<div class='data-sub'>{precip_daily_avg:.1f} mm/day · Target: {opt_p_lo}–{opt_p_hi} mm/day<br>{status_rain}</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with m2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        status_def = "🔴 Severe" if deficit > 200 else ("🟡 Moderate" if deficit > 80 else "🟢 Low")
        st.markdown(
            f"<div class='data-label'>Water Deficit (90 days)</div>"
            f"<div class='data-value'>{deficit:.0f} mm</div>"
            f"<div class='data-sub'>Evaporation demand: {et0_90:.0f} mm<br>{status_def}</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with m3:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        status_temp = "🔴 Heat stress" if temp_90 > opt_t_hi else ("🟡 Warm" if temp_90 > opt_t_hi - 2 else "🟢 Optimal")
        st.markdown(
            f"<div class='data-label'>Mean Temperature (90 days)</div>"
            f"<div class='data-value'>{temp_90:.1f} °C</div>"
            f"<div class='data-sub'>Optimal range: {opt_t_lo}–{opt_t_hi}°C<br>{status_temp}</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with m4:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        spi_label = "Severe drought" if assessment["spi3"] < -2 else (
            "Moderate drought" if assessment["spi3"] < -1 else (
            "Dry" if assessment["spi3"] < -0.5 else "Normal"))
        st.markdown(
            f"<div class='data-label'>SPI-3 (Precip Index)</div>"
            f"<div class='data-value'>{assessment['spi3']:+.2f}</div>"
            f"<div class='data-sub'>{spi_label}<br>Below –1.0 = drought onset</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # ── RECOMMENDATIONS ──────────────────────────────────────────────────────
    st.markdown("### What should you do?")
    recs = generate_recommendations(assessment, crop_choice, crop_stage, oni_v)
    for rec in recs:
        st.markdown(f"<div class='rec-item'>{rec}</div>", unsafe_allow_html=True)

    # ── AI ANALYSIS (optional) ───────────────────────────────────────────────
    with st.expander("🤖 AI-Enhanced Analysis (optional — requires your own API key)"):
        st.caption(
            "The AI uses the real data above to write a richer personalised assessment. "
            "Enter your Anthropic or OpenAI API key in the sidebar to enable this."
        )
        if st.button("Generate AI Analysis", disabled=not bool(ai_key)):
            if ai_key:
                provider = "anthropic" if "anthropic" in ai_provider.lower() else "openai"
                with st.spinner("Asking AI…"):
                    ai_text = call_llm_narrative(
                        assessment, crop_choice, crop_stage, oni,
                        st.session_state.preset_name, ai_key, provider,
                    )
                st.markdown(ai_text)
            else:
                st.info("Enter your API key in the sidebar first.")

    # ── LOG TO DB ────────────────────────────────────────────────────────────
    with st.expander("💾 Log this assessment to local database"):
        if st.button("Save assessment"):
            try:
                init_db()
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO regional_targets "
                    "(region_name, country, crop_type, bbox_coords, is_scheduled) "
                    "VALUES (?,?,?,?,?)",
                    (st.session_state.preset_name, active_region, crop_choice,
                     f"{lon},{lat}", 0),
                )
                cursor.execute(
                    "INSERT INTO self_correction_journal "
                    "(journal_date, assessment_period, target_district, "
                    "raw_pdsi_forecast, observed_pdsi, forecast_rmse, "
                    "agent_reasoning, parameter_adjustments) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        datetime.now().strftime("%Y-%m-%d"),
                        "Manual save",
                        st.session_state.preset_name,
                        assessment["spi3"],
                        -deficit / 100.0,
                        abs(score - 50),
                        summary_text,
                        f'{{"score":{score},"level":"{level}","oni":{oni_v}}}',
                    ),
                )
                conn.commit()
                conn.close()
                st.success("Saved!")
            except Exception as e:
                st.error(f"Could not save: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: 90-DAY TRENDS
# ═════════════════════════════════════════════════════════════════════════════
with tab_trends:
    if not data_ok:
        st.warning("Weather data unavailable.")
        st.stop()

    df_plot = df_weather.tail(90).copy()

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Rainfall — last 90 days")
    st.caption("Daily precipitation (bars) and 7-day rolling average (line).")
    fig, ax = plt.subplots(figsize=(10, 3.2), facecolor="none")
    ax.set_facecolor("none")
    ax.bar(df_plot["date"], df_plot["precip_mm"], color="#3b82f6", alpha=0.6, width=0.9, label="Daily rain (mm)")
    roll7 = df_plot["precip_mm"].rolling(7, min_periods=1).mean()
    ax.plot(df_plot["date"], roll7, color="#60a5fa", linewidth=2, label="7-day avg")
    daily_target = cal["optimal_precip_mm_day"][0]
    ax.axhline(daily_target, color="#38ef7d", linestyle="--", linewidth=1.2, alpha=0.7, label=f"Min crop need ({daily_target} mm/day)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=30, color="white", fontsize=8)
    ax.tick_params(colors="white")
    ax.spines[:].set_visible(False)
    ax.legend(facecolor="#1a1a2e", edgecolor="#333", labelcolor="white", fontsize=8)
    ax.set_ylabel("mm", color="white", fontsize=9)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
    st.markdown("</div>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Cumulative Water Balance")
        st.caption("Cumulative (rainfall − evaporation). Orange zone = water deficit.")
        fig2, ax2 = plt.subplots(figsize=(6, 3.2), facecolor="none")
        ax2.set_facecolor("none")
        cum_wb = df_plot["water_balance_mm"].cumsum()
        ax2.plot(df_plot["date"], cum_wb, color="#f97316", linewidth=2)
        ax2.fill_between(df_plot["date"], cum_wb, 0,
                         where=(cum_wb < 0), color="#f97316", alpha=0.18, label="Deficit")
        ax2.fill_between(df_plot["date"], cum_wb, 0,
                         where=(cum_wb >= 0), color="#38ef7d", alpha=0.18, label="Surplus")
        ax2.axhline(0, color="white", linewidth=0.7, alpha=0.4)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
        plt.xticks(rotation=30, color="white", fontsize=8)
        ax2.tick_params(colors="white")
        ax2.spines[:].set_visible(False)
        ax2.set_ylabel("mm cumulative", color="white", fontsize=9)
        ax2.legend(facecolor="#1a1a2e", edgecolor="#333", labelcolor="white", fontsize=8)
        st.pyplot(fig2, use_container_width=True)
        plt.close(fig2)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Temperature Trend")
        st.caption(f"Mean daily temperature with optimal range for {crop_choice}.")
        fig3, ax3 = plt.subplots(figsize=(6, 3.2), facecolor="none")
        ax3.set_facecolor("none")
        ax3.plot(df_plot["date"], df_plot["temp_c"], color="#ef4444", linewidth=1.8)
        t_lo, t_hi = cal["optimal_temp"]
        ax3.axhspan(t_lo, t_hi, alpha=0.12, color="#38ef7d", label=f"Optimal {t_lo}–{t_hi}°C")
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax3.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
        plt.xticks(rotation=30, color="white", fontsize=8)
        ax3.tick_params(colors="white")
        ax3.spines[:].set_visible(False)
        ax3.set_ylabel("°C", color="white", fontsize=9)
        ax3.legend(facecolor="#1a1a2e", edgecolor="#333", labelcolor="white", fontsize=8)
        st.pyplot(fig3, use_container_width=True)
        plt.close(fig3)
        st.markdown("</div>", unsafe_allow_html=True)

    # Monthly summary table
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Monthly Summary")
    df_month = df_plot.copy()
    df_month["month"] = df_month["date"].dt.to_period("M")
    monthly = df_month.groupby("month").agg(
        Rain_mm=("precip_mm", "sum"),
        Evap_mm=("et0_mm", "sum"),
        Deficit_mm=("water_balance_mm", lambda x: max(0, -x.sum())),
        Avg_Temp_C=("temp_c", "mean"),
    ).round(1)
    monthly.index = monthly.index.astype(str)
    st.dataframe(monthly, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: 14-DAY FORECAST
# ═════════════════════════════════════════════════════════════════════════════
with tab_forecast:
    if df_forecast is None or df_forecast.empty:
        st.warning("Forecast data unavailable. Check your internet connection.")
    else:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("14-Day Rainfall Forecast")
        st.caption("Open-Meteo weather model forecast. Updated daily.")
        fig4, ax4 = plt.subplots(figsize=(10, 3.2), facecolor="none")
        ax4.set_facecolor("none")
        ax4.bar(df_forecast["date"], df_forecast["precip_mm"],
                color="#818cf8", alpha=0.7, width=0.8, label="Forecast rain (mm)")
        ax4.axhline(cal["optimal_precip_mm_day"][0], color="#38ef7d",
                    linestyle="--", linewidth=1.2, alpha=0.7,
                    label=f"Min crop need ({cal['optimal_precip_mm_day'][0]} mm/day)")
        ax4.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        plt.xticks(rotation=30, color="white", fontsize=8)
        ax4.tick_params(colors="white")
        ax4.spines[:].set_visible(False)
        ax4.set_ylabel("mm", color="white", fontsize=9)
        ax4.legend(facecolor="#1a1a2e", edgecolor="#333", labelcolor="white", fontsize=8)
        st.pyplot(fig4, use_container_width=True)
        plt.close(fig4)

        total_fc = df_forecast["precip_mm"].sum()
        et0_fc = df_forecast["et0_mm"].sum()
        fc_deficit = max(0, et0_fc - total_fc)
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            st.metric("Total forecast rain (14d)", f"{total_fc:.0f} mm")
        with col_f2:
            st.metric("Expected evaporation (14d)", f"{et0_fc:.0f} mm")
        with col_f3:
            st.metric("Projected water deficit (14d)", f"{fc_deficit:.0f} mm",
                      delta="additional stress" if fc_deficit > 20 else "manageable",
                      delta_color="inverse" if fc_deficit > 20 else "normal")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("14-Day Temperature Forecast")
        fig5, ax5 = plt.subplots(figsize=(10, 2.8), facecolor="none")
        ax5.set_facecolor("none")
        ax5.plot(df_forecast["date"], df_forecast["temp_c"], color="#ef4444", linewidth=2)
        t_lo, t_hi = cal["optimal_temp"]
        ax5.axhspan(t_lo, t_hi, alpha=0.1, color="#38ef7d",
                    label=f"Optimal range {t_lo}–{t_hi}°C")
        ax5.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        plt.xticks(rotation=30, color="white", fontsize=8)
        ax5.tick_params(colors="white")
        ax5.spines[:].set_visible(False)
        ax5.set_ylabel("°C", color="white", fontsize=9)
        ax5.legend(facecolor="#1a1a2e", edgecolor="#333", labelcolor="white", fontsize=8)
        st.pyplot(fig5, use_container_width=True)
        plt.close(fig5)
        st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: ABOUT & METHODS
# ═════════════════════════════════════════════════════════════════════════════
with tab_about:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("How ENSA Works")
    st.markdown("""
ENSA calculates a **0–100 drought risk score** from three real data sources, all free:

| Source | What it provides | Cost |
|--------|-----------------|------|
| **Open-Meteo ERA5 archive** | Daily rainfall, temperature, reference evapotranspiration (FAO-56) for any point on Earth back to 1940 | Free · No key |
| **Open-Meteo forecast** | 14-day weather model forecast | Free · No key |
| **NOAA CPC NINO3.4** | Monthly El Niño / La Niña SST anomaly (ONI) | Free · No key |

### Scoring Logic
The risk score combines four components:

1. **SPI-3** (McKee et al. 1993) — Standardised Precipitation Index over 90 days. Fits the historical precipitation series to a Gamma distribution; values below –1.0 indicate drought, below –2.0 indicate severe drought. *Weight: up to 40 pts.*

2. **Cumulative water deficit** (P − ET₀) — Total rainfall minus reference evapotranspiration over 90 days using the FAO-56 Penman-Monteith method. A large negative balance means crops cannot replace the water they lose. *Weight: up to 40 pts.*

3. **Temperature stress** — Mean temperature above 25°C drives additional evaporation. *Weight: up to 20 pts.*

4. **ENSO amplification** — If NINO3.4 ≥ +0.5°C (El Niño), the score is multiplied up to 1.5× because southern Africa rainfall is systematically suppressed during El Niño events (Ropelewski & Halpert 1987).

5. **Crop stage weighting** — Flowering, tasseling, and grain-filling stages amplify the score ×1.35 because water stress during pollination causes irreversible yield loss.

### References
- McKee et al. (1993) — SPI definition
- Vicente-Serrano et al. (2010) — SPEI / Penman-Monteith PET
- Palmer (1965) — PDSI drought severity framework
- Kogan (1995) — Vegetation Condition Index
- Ropelewski & Halpert (1987) — ENSO–Southern Africa rainfall teleconnections
""")
    st.markdown("</div>", unsafe_allow_html=True)

    # Saved journal
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("📓 Saved Assessments")
    try:
        init_db()
        conn = get_db_connection()
        df_j = pd.read_sql_query(
            "SELECT journal_date, target_district, agent_reasoning, parameter_adjustments "
            "FROM self_correction_journal ORDER BY id DESC LIMIT 20",
            conn,
        )
        conn.close()
        if df_j.empty:
            st.info("No saved assessments yet. Use the 'Save assessment' button in Farm Status.")
        else:
            for _, row in df_j.iterrows():
                st.markdown(f"**{row['journal_date']} — {row['target_district']}**")
                st.caption(row["agent_reasoning"])
                st.markdown("---")
    except Exception as e:
        st.info(f"Database not yet initialised: {e}")
    st.markdown("</div>", unsafe_allow_html=True)
