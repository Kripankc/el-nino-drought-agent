"""
ENSA — El Niño Sentinel Agent  v2.1
Farmer-facing drought early-warning dashboard.
Weather: Open-Meteo ERA5 (real, free, no key).
ENSO:    NOAA CPC NINO3.4 (real, free, no key).
LLM:     optional — user supplies their own Anthropic/OpenAI key.
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import calendar

from ensa.ingest.openmeteo import (
    fetch_weather, fetch_forecast, fetch_climatology, fetch_soil_moisture,
)
from ensa.ingest.enso import fetch_current_oni, fetch_oni_history
from ensa.analysis.elnino import seasonal_elnino_comparison
from ensa.analysis.crop_calendars import CROP_CALENDARS
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

st.markdown("""
<style>
  .stApp{background:linear-gradient(135deg,#060913 0%,#020307 100%);color:#e2e8f0;}
  h1,h2,h3,h4{color:#fff;font-weight:700;letter-spacing:-.025em;}
  .card{background:rgba(255,255,255,.03);border-radius:16px;padding:20px 24px;
    border:1px solid rgba(255,255,255,.08);box-shadow:0 8px 32px rgba(0,0,0,.45);margin-bottom:18px;}
  .rec-item{padding:10px 14px;border-radius:10px;background:rgba(255,255,255,.04);
    border:1px solid rgba(255,255,255,.06);margin-bottom:8px;font-size:.97rem;line-height:1.55;}
  .stTabs [data-baseweb="tab-list"]{gap:20px;background:transparent;}
  .stTabs [data-baseweb="tab"]{background:transparent;color:#a0aec0;font-weight:600;}
  .stTabs [aria-selected="true"]{color:#38ef7d !important;border-bottom-color:#38ef7d !important;}
  .kpi-label{font-size:.72rem;color:#a0aec0;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px;}
  .kpi-value{font-size:1.55rem;font-weight:700;color:#fff;}
  .kpi-sub{font-size:.82rem;color:#a0aec0;margin-top:1px;}
  .enso-chip{display:inline-block;padding:4px 12px;border-radius:20px;font-size:.82rem;font-weight:700;}
  .sat-bar-wrap{background:#1a1a2e;border-radius:8px;height:22px;overflow:hidden;margin:6px 0 2px;}
  .sat-bar-fill{height:100%;border-radius:8px;transition:width .4s;}
  .stage-pill{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.8rem;font-weight:600;margin:2px 3px;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# REGION DETECTION — priority-ordered, most specific first
# (lat_min, lat_max, lon_min, lon_max)
# ─────────────────────────────────────────────────────────────────────────────
_REGION_BOXES = [
    ("Nepal",           26.0, 30.5,  80.0,  88.5),
    ("Bangladesh",      20.5, 26.7,  88.0,  92.7),
    ("Sri Lanka",        5.9,  9.9,  79.5,  82.0),
    ("Pakistan",        23.0, 37.5,  60.0,  77.5),
    ("Myanmar",          9.5, 28.5,  92.0, 101.0),
    ("Southeast Asia", -10.0, 28.0,  95.0, 141.0),
    ("India",            8.0, 37.0,  68.0,  97.0),
    ("China",           18.0, 53.0,  73.0, 135.0),
    ("East Africa",    -12.0, 12.0,  28.0,  42.0),
    ("West Africa",      4.0, 18.0, -18.0,  16.0),
    ("Southern Africa",-35.0,-10.0,  10.0,  40.0),
    ("Australia",      -44.0,-10.0, 112.0, 154.0),
    ("South America",  -55.0, 12.0, -82.0, -34.0),
    ("North America",   24.0, 60.0,-125.0, -60.0),
    ("North Africa",    15.0, 38.0, -18.0,  40.0),
    ("Central Asia",    36.0, 56.0,  45.0,  90.0),
    ("Europe",          36.0, 72.0, -12.0,  45.0),
]

def _detect_region(lat, lon):
    for name, la, lb, loa, lob in _REGION_BOXES:
        if la <= lat <= lb and loa <= lon <= lob:
            return name
    return "Global"


def _is_active(cal, month):
    s, e = cal["start"], cal["end"]
    return (s <= month <= e) if s <= e else (month >= s or month <= e)
# CROP_CALENDARS is imported from ensa.analysis.crop_calendars


# ─────────────────────────────────────────────────────────────────────────────
# PRESET LOCATIONS
# ─────────────────────────────────────────────────────────────────────────────
PRESETS = {
    "Mazabuka, Zambia":        {"coords": [-16.25,  27.65]},
    "Kathmandu Valley, Nepal": {"coords": [27.70,   85.30]},
    "Punjab, India":           {"coords": [30.90,   75.85]},
    "Eldoret, Kenya":          {"coords": [0.51,    35.26]},
    "Griffith, Australia":     {"coords": [-34.28, 146.04]},
    "Kano, Nigeria":           {"coords": [12.00,    8.52]},
    "Chiang Mai, Thailand":    {"coords": [18.79,   98.98]},
    "Lahore, Pakistan":        {"coords": [31.55,   74.34]},
    "São Paulo State, Brazil": {"coords": [-22.90,  -47.06]},
    "Iowa, USA (Corn Belt)":   {"coords": [41.88,   -93.10]},
    "Saskatchewan, Canada":    {"coords": [50.45,  -104.61]},
    "Custom Point":            {"coords": [-16.25,  27.65]},
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — charts
# ─────────────────────────────────────────────────────────────────────────────

def _gauge(score, color):
    """Half-donut risk gauge."""
    fig, ax = plt.subplots(figsize=(3.6, 2.2), facecolor="none")
    ax.set_facecolor("none")
    θ = np.linspace(np.pi, 0, 300)
    ax.plot(np.cos(θ), np.sin(θ), color="#1e2535", linewidth=22, solid_capstyle="round", zorder=1)
    if score > 0:
        θv = np.linspace(np.pi, np.pi - (min(score,100)/100)*np.pi, 300)
        ax.plot(np.cos(θv), np.sin(θv), color=color, linewidth=22, solid_capstyle="round", zorder=2)
    ax.text(0, 0.18, f"{score:.0f}", ha="center", va="center",
            fontsize=38, fontweight="bold", color="white", zorder=3)
    ax.text(0, -0.22, "/ 100  drought risk", ha="center", va="center",
            fontsize=8.5, color="#a0aec0", zorder=3)
    ax.set_xlim(-1.4, 1.4); ax.set_ylim(-0.55, 1.4); ax.axis("off")
    return fig


def _ax_style(ax, xlabel_rotation=30):
    """Consistent dark-theme chart style."""
    ax.set_facecolor("none")
    ax.tick_params(colors="#94a3b8", labelsize=8)
    ax.spines[:].set_visible(False)
    ax.grid(axis="y", color="white", alpha=0.05, linewidth=0.6)
    plt.xticks(rotation=xlabel_rotation, ha="right")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color("#94a3b8")


def _monthly_bar_chart(df_hist, daily_demand_mm, cal):
    """Single-bar chart coloured by adequacy + dashed need line."""
    df = df_hist.copy()
    df["ym"] = df["date"].dt.to_period("M")
    monthly = df.groupby("ym").agg(
        precip_mm=("precip_mm","sum"),
        n_days=("precip_mm","count"),
    ).reset_index()
    monthly["needed_mm"] = monthly.apply(
        lambda r: daily_demand_mm * r["n_days"] if _is_active(cal, r["ym"].month) else 0, axis=1
    )
    monthly["label"] = monthly["ym"].dt.strftime("%b '%y")

    def _bar_color(row):
        if row["needed_mm"] == 0: return "#334155"          # off-season, slate
        if row["precip_mm"] >= row["needed_mm"] * 0.9: return "#22c55e"   # met
        if row["precip_mm"] >= row["needed_mm"] * 0.6: return "#f59e0b"   # borderline
        return "#ef4444"                                      # deficit

    colors = monthly.apply(_bar_color, axis=1)

    fig, ax = plt.subplots(figsize=(8, 2.8), facecolor="none")
    ax.bar(range(len(monthly)), monthly["precip_mm"], color=colors, alpha=0.85, width=0.65, zorder=2)
    ax.plot(range(len(monthly)), monthly["needed_mm"], color="#38ef7d",
            linewidth=1.6, linestyle="--", marker="o", markersize=3.5,
            label="Crop water need", zorder=3)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels(monthly["label"])
    _ax_style(ax)
    ax.set_ylabel("mm", color="#94a3b8", fontsize=8)

    from matplotlib.patches import Patch
    legend_els = [
        Patch(facecolor="#22c55e", alpha=0.85, label="Adequate (≥ 90% of need)"),
        Patch(facecolor="#f59e0b", alpha=0.85, label="Below optimal (60–90%)"),
        Patch(facecolor="#ef4444", alpha=0.85, label="Critical deficit (< 60%)"),
        Patch(facecolor="#334155", alpha=0.85, label="Off-season"),
        plt.Line2D([0],[0], color="#38ef7d", linewidth=1.5, linestyle="--", label="Crop water need"),
    ]
    ax.legend(handles=legend_els, facecolor="#0d1117", edgecolor="#1e293b",
              labelcolor="#cbd5e1", fontsize=7, ncol=2, loc="upper right")
    return fig


def _forecast_chart(df_fc, daily_demand_mm):
    """Forecast bars coloured by whether they meet crop daily need."""
    colors = ["#22c55e" if r >= daily_demand_mm else
              ("#f59e0b" if r >= daily_demand_mm * 0.5 else "#ef4444")
              for r in df_fc["precip_mm"]]
    fig, ax = plt.subplots(figsize=(8, 2.6), facecolor="none")
    ax.bar(df_fc["date"], df_fc["precip_mm"], color=colors, alpha=0.85, width=0.8, zorder=2)
    ax.axhline(daily_demand_mm, color="#38ef7d", linestyle="--",
               linewidth=1.4, label=f"Daily crop need ({daily_demand_mm} mm)", zorder=3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    _ax_style(ax)
    ax.set_ylabel("mm/day", color="#94a3b8", fontsize=8)
    ax.legend(facecolor="#0d1117", edgecolor="#1e293b", labelcolor="#cbd5e1", fontsize=7)
    return fig


def _water_balance_chart(df_hist):
    """Cumulative P − ET₀ over last 90 days."""
    df = df_hist.tail(90).copy()
    cum = df["water_balance_mm"].cumsum()
    fig, ax = plt.subplots(figsize=(8, 2.5), facecolor="none")
    ax.plot(df["date"], cum, color="#94a3b8", linewidth=1.6, zorder=3)
    ax.fill_between(df["date"], cum, 0, where=(cum < 0),
                    color="#ef4444", alpha=0.22, label="Deficit", zorder=2)
    ax.fill_between(df["date"], cum, 0, where=(cum >= 0),
                    color="#22c55e", alpha=0.15, label="Surplus", zorder=2)
    ax.axhline(0, color="white", linewidth=0.5, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    _ax_style(ax)
    ax.set_ylabel("mm", color="#94a3b8", fontsize=8)
    ax.legend(facecolor="#0d1117", edgecolor="#1e293b", labelcolor="#cbd5e1", fontsize=7)
    return fig


def _crop_calendar_strip(cal, current_month):
    """Horizontal 12-month crop calendar with current month marked."""
    months = list(range(1, 13))
    colors = []
    for m in months:
        stage = cal["stages"][m]
        if "Critical" in stage:
            colors.append("#ef4444")
        elif "Fallow" in stage or "Dormant" in stage or "Overwintering" in stage:
            colors.append("#1e2535")
        elif "Harvesting" in stage:
            colors.append("#f59e0b")
        else:
            colors.append("#22c55e")

    fig, ax = plt.subplots(figsize=(10, 1.1), facecolor="none")
    ax.set_facecolor("none")
    for i, (m, c) in enumerate(zip(months, colors)):
        rect = mpatches.FancyBboxPatch((i, 0), 0.88, 0.9, boxstyle="round,pad=0.04",
                                       facecolor=c, edgecolor="none", alpha=0.85)
        ax.add_patch(rect)
        label = calendar.month_abbr[m]
        ax.text(i + 0.44, 0.45, label, ha="center", va="center",
                color="white", fontsize=8, fontweight="bold")
        if m == current_month:
            ax.add_patch(mpatches.FancyBboxPatch((i-0.05, -0.1), 0.98, 1.1,
                boxstyle="round,pad=0.04", facecolor="none",
                edgecolor="#38ef7d", linewidth=2.5))
    ax.set_xlim(-0.1, 12.1); ax.set_ylim(-0.25, 1.2); ax.axis("off")
    # Legend
    for x_pos, label, col in [(0, "Fallow", "#1e2535"),
                               (3, "Growing", "#22c55e"),
                               (6, "Critical / Flowering", "#ef4444"),
                               (9.2, "Harvesting", "#f59e0b")]:
        ax.add_patch(mpatches.Rectangle((x_pos-0.1, -0.22), 0.3, 0.18, color=col))
        ax.text(x_pos+0.25, -0.14, label, color="#a0aec0", fontsize=6.5, va="center")
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# CACHED DATA FETCHERS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_weather(lat, lon):
    return fetch_weather(lat, lon, days_back=400)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_forecast(lat, lon):
    return fetch_forecast(lat, lon, days=14)


@st.cache_data(ttl=21600, show_spinner=False)
def _cached_enso():
    return fetch_current_oni()


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_climatology(lat, lon):
    return fetch_climatology(lat, lon, start_year=1985)


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_oni_history():
    return fetch_oni_history()


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_soil(lat, lon):
    return fetch_soil_moisture(lat, lon, days_back=120)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "point"       not in st.session_state: st.session_state.point = PRESETS["Mazabuka, Zambia"]["coords"]
if "preset_name" not in st.session_state: st.session_state.preset_name = "Mazabuka, Zambia"

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown(
    "<h2 style='text-align:center;margin-bottom:4px'>🌾 ENSA</h2>"
    "<p style='text-align:center;color:#a0aec0;font-size:.85rem;margin-top:0'>"
    "El Niño Sentinel Agent</p>", unsafe_allow_html=True)
st.sidebar.markdown("---")

st.sidebar.subheader("1. Location")
preset_name = st.sidebar.selectbox("Preset location", list(PRESETS.keys()),
    index=list(PRESETS.keys()).index(st.session_state.preset_name))
if preset_name != st.session_state.preset_name:
    st.session_state.preset_name = preset_name
    if preset_name != "Custom Point":
        st.session_state.point = PRESETS[preset_name]["coords"]
    st.rerun()

c1, c2 = st.sidebar.columns(2)
with c1: lat_in = st.number_input("Latitude",  value=float(st.session_state.point[0]), format="%.4f")
with c2: lon_in = st.number_input("Longitude", value=float(st.session_state.point[1]), format="%.4f")
if [lat_in, lon_in] != list(st.session_state.point):
    st.session_state.point = [lat_in, lon_in]
    st.session_state.preset_name = "Custom Point"
    st.rerun()

lat, lon = st.session_state.point
active_region = _detect_region(lat, lon)
cal_region = CROP_CALENDARS.get(active_region, CROP_CALENDARS["Global"])

st.sidebar.markdown("---")
st.sidebar.subheader("2. Crop")
crop_choice = st.sidebar.selectbox("Crop type", list(cal_region.keys()))
cal = cal_region[crop_choice]

st.sidebar.markdown("---")
st.sidebar.subheader("3. Assessment Date")
st.sidebar.caption("Pick any past date to analyse historical conditions.")
assessment_date = st.sidebar.date_input("Date",
    value=datetime.now().date(),
    min_value=datetime(2000,1,1).date(),
    max_value=(datetime.now()+timedelta(days=14)).date())
a_month = assessment_date.month
crop_stage = cal["stages"][a_month]
is_active  = _is_active(cal, a_month)
is_fc_mode = assessment_date > (datetime.now()-timedelta(days=5)).date()

st.sidebar.markdown("---")
st.sidebar.subheader("4. AI Analysis (optional)")
st.sidebar.caption("Core dashboard is 100% free. Paste your own API key for an AI-written narrative.")
ai_provider = st.sidebar.selectbox("Provider", ["Anthropic (Claude)", "OpenAI (GPT-4o-mini)"])
ai_key = st.sidebar.text_input("API Key", type="password", placeholder="sk-ant-... or sk-...")

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<div style='font-size:.75rem;color:#718096;text-align:center'>"
    "Weather: Open-Meteo ERA5 · ENSO: NOAA CPC<br>All data is real — no simulations.</div>",
    unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
_lat_r, _lon_r = round(lat, 3), round(lon, 3)
df_weather = df_forecast = df_soil = None
weather_error = None

with st.spinner("Fetching real weather data from Open-Meteo ERA5…"):
    try:
        df_weather = _cached_weather(_lat_r, _lon_r)
    except Exception as e:
        weather_error = str(e)
    try:
        df_forecast = _cached_forecast(_lat_r, _lon_r)
    except Exception:
        pass
    try:
        df_soil = _cached_soil(_lat_r, _lon_r)
    except Exception:
        df_soil = None
    oni = _cached_enso()

data_ok = df_weather is not None and not df_weather.empty

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='background:linear-gradient(90deg,#38ef7d,#11998e);"
    "-webkit-background-clip:text;-webkit-text-fill-color:transparent'>"
    "El Niño Sentinel Agent (ENSA)</h1>", unsafe_allow_html=True)
st.markdown(
    f"<p style='color:#a0aec0;font-size:1.0rem;margin-top:-8px'>"
    f"Agricultural drought early-warning · {active_region} · "
    f"All data live from Open-Meteo ERA5 & NOAA CPC</p>", unsafe_allow_html=True)

# ENSO BANNER
oni_v = oni["value"]
if oni_v >= 1.5:   enso_bg, enso_txt = "#7f1d1d","#fca5a5"
elif oni_v >= 0.5: enso_bg, enso_txt = "#78350f","#fcd34d"
elif oni_v <= -0.5:enso_bg, enso_txt = "#1e3a5f","#93c5fd"
else:              enso_bg, enso_txt = "#14532d","#86efac"

live_tag = "🔴 LIVE" if "Offline" not in oni["source"] else "⚫ OFFLINE"
st.markdown(
    f"<div style='background:{enso_bg};border-radius:10px;padding:10px 18px;"
    f"margin-bottom:18px;display:flex;align-items:center;gap:16px;flex-wrap:wrap'>"
    f"<span class='enso-chip' style='background:rgba(255,255,255,.15);color:{enso_txt}'>"
    f"NINO3.4: {oni_v:+.2f}°C</span>"
    f"<span style='color:{enso_txt};font-weight:700'>{oni['phase']}</span>"
    f"<span style='color:rgba(255,255,255,.55);font-size:.83rem'>"
    f"{live_tag} · {oni['month_name']} {oni['year']} · {oni['source']}</span>"
    f"</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_status, tab_history, tab_fc, tab_elnino, tab_about = st.tabs([
    "🌾 Farm Status", "📈 90-Day History", "🔮 14-Day Forecast",
    "🌊 El Niño Impact", "📖 Methodology"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: FARM STATUS
# ═══════════════════════════════════════════════════════════════════════════
with tab_status:
    col_map, col_info = st.columns([3,1])

    with col_map:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("📍 Select Your Farm")
        st.caption("Click the map to move the pin to your farm location.")
        m = folium.Map(location=[lat, lon], zoom_start=7, tiles="OpenStreetMap")
        folium.Marker([lat, lon], tooltip=f"{lat:.4f}°, {lon:.4f}°",
                      icon=folium.Icon(color="green", icon="leaf")).add_to(m)
        map_out = st_folium(m, height=300, use_container_width=True, key="main_map")
        if map_out and map_out.get("last_clicked"):
            clat = map_out["last_clicked"]["lat"]
            clon = map_out["last_clicked"]["lng"]
            if [round(clat,3), round(clon,3)] != [round(lat,3), round(lon,3)]:
                st.session_state.point = [clat, clon]
                st.session_state.preset_name = "Custom Point"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_info:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-label'>Detected Region</div><div class='kpi-value' style='font-size:1.1rem'>{active_region}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-label' style='margin-top:10px'>Crop</div><div class='kpi-value' style='font-size:1.05rem'>{crop_choice}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-label' style='margin-top:10px'>Stage · {assessment_date.strftime('%b %Y')}</div><div class='kpi-value' style='font-size:.92rem'>{crop_stage}</div>", unsafe_allow_html=True)
        if is_fc_mode:    st.info("🔮 Forecast mode")
        elif not is_active: st.warning("Off-season / Fallow")
        st.markdown("</div>", unsafe_allow_html=True)

    if not data_ok:
        st.error(f"**Could not load weather data.**\n\nError: `{weather_error or 'empty API response'}`\n\nCheck your internet connection, or try a different location.")
        st.stop()

    # Slice to assessment date
    a_dt = pd.Timestamp(assessment_date)
    if is_fc_mode and df_forecast is not None and not df_forecast.empty:
        df_all = pd.concat([df_weather, df_forecast], ignore_index=True)
    else:
        df_all = df_weather.copy()
    df_slice = df_all[df_all["date"] <= a_dt]

    assessment = compute_drought_score(df_slice, oni_v, crop_stage, is_active)
    score  = assessment["score"]
    level  = assessment["alert_level"]
    color  = assessment["alert_color"]
    emoji  = assessment["alert_emoji"]

    tail90 = df_slice.tail(90)
    precip_90  = float(tail90["precip_mm"].sum())
    et0_90     = float(tail90["et0_mm"].sum())
    deficit_90 = max(0.0, et0_90 - precip_90)
    temp_90    = float(tail90["temp_c"].mean())

    # Water satisfaction (how much of crop need was met by rain)
    if is_active:
        needed = cal["daily_demand_mm"] * len(tail90)
        satisfaction_pct = min(150.0, (precip_90 / (needed + 1e-6)) * 100)
    else:
        needed = 0; satisfaction_pct = None

    # ── RISK GAUGE + SUMMARY ─────────────────────────────────────────────
    col_gauge, col_summary = st.columns([1, 3])
    with col_gauge:
        st.markdown("<div class='card' style='text-align:center'>", unsafe_allow_html=True)
        st.pyplot(_gauge(score, color), use_container_width=True)
        st.markdown(f"<div style='text-align:center;color:{color};font-weight:700;font-size:1.1rem'>{emoji} {level}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_summary:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        summary_text = generate_summary(assessment, crop_choice, crop_stage, oni["phase"],
                                        st.session_state.preset_name)
        st.markdown(f"<p style='font-size:1.05rem;line-height:1.7;color:#e2e8f0'>{summary_text}</p>",
                    unsafe_allow_html=True)

        if satisfaction_pct is not None:
            bar_color = "#ef4444" if satisfaction_pct < 50 else ("#f59e0b" if satisfaction_pct < 80 else "#22c55e")
            bar_w = min(100, satisfaction_pct)
            st.markdown(
                f"<div style='margin-top:14px'>"
                f"<div class='kpi-label'>Crop Water Needs Met (last 90 days)</div>"
                f"<div class='sat-bar-wrap'><div class='sat-bar-fill' style='width:{bar_w:.0f}%;background:{bar_color}'></div></div>"
                f"<div style='font-size:.85rem;color:#a0aec0'>"
                f"Rain received: <b style='color:#fff'>{precip_90:.0f} mm</b> · "
                f"Crop needed: <b style='color:#fff'>{needed:.0f} mm</b> · "
                f"<b style='color:{bar_color}'>{satisfaction_pct:.0f}% met</b></div>"
                f"</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── CROP CALENDAR STRIP ──────────────────────────────────────────────
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("📅 Crop Growth Calendar")
    st.caption("Green = growing · Red = critical water stage · Orange = harvesting · Dark = fallow. Border = current month.")
    st.pyplot(_crop_calendar_strip(cal, a_month), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── 5 METRIC CARDS ──────────────────────────────────────────────────
    opt_t_lo, opt_t_hi = cal["optimal_temp"]
    st.markdown("### Key Indicators (last 90 days — real ERA5 data)")
    m1, m2, m3, m4, m5 = st.columns(5)

    def _kpi(col, label, val, sub, ok):
        dot = "🟢" if ok else "🔴"
        col.markdown(f"<div class='card'><div class='kpi-label'>{label}</div>"
                     f"<div class='kpi-value'>{val}</div>"
                     f"<div class='kpi-sub'>{dot} {sub}</div></div>", unsafe_allow_html=True)

    _kpi(m1, "Rainfall (90d)", f"{precip_90:.0f} mm",
         f"Need: {cal['daily_demand_mm']*90:.0f} mm for full season",
         precip_90 >= cal["daily_demand_mm"] * 90 * 0.7)
    _kpi(m2, "Water Deficit (90d)", f"{deficit_90:.0f} mm",
         f"Evaporation demand: {et0_90:.0f} mm",
         deficit_90 < 100)
    _kpi(m3, "Mean Temperature", f"{temp_90:.1f} °C",
         f"Optimal: {opt_t_lo}–{opt_t_hi}°C",
         opt_t_lo <= temp_90 <= opt_t_hi + 2)
    _kpi(m4, "SPI-3 Index", f"{assessment['spi3']:+.2f}",
         "< –1.0 = drought · < –2.0 = severe",
         assessment["spi3"] >= -1.0)

    # Soil moisture KPI — uses real ERA5 if available, otherwise a friendly skip
    if df_soil is not None and not df_soil.empty:
        sm_recent = df_soil.tail(7)
        sm_root_recent = float(sm_recent["soil_root"].mean())
        # historical median for this layer over the full 120-day window for context
        sm_root_hist_med = float(df_soil["soil_root"].median())
        sm_delta_pct = ((sm_root_recent - sm_root_hist_med) / (sm_root_hist_med + 1e-6)) * 100
        sm_ok = sm_root_recent >= 0.18    # rough root-zone threshold (volumetric)
        _kpi(m5, "Soil Moisture (7-day)", f"{sm_root_recent*100:.0f}%",
             f"Root-zone 7-28 cm · {sm_delta_pct:+.0f}% vs 120-day median",
             sm_ok)
    else:
        m5.markdown(
            "<div class='card' style='opacity:.55'>"
            "<div class='kpi-label'>Soil Moisture</div>"
            "<div class='kpi-value' style='font-size:.95rem;color:#484F58'>Unavailable</div>"
            "<div class='kpi-sub'>ERA5 soil layer fetch failed</div></div>",
            unsafe_allow_html=True)

    # ── RECOMMENDATIONS ──────────────────────────────────────────────────
    st.markdown("### What to do")
    for rec in generate_recommendations(assessment, crop_choice, crop_stage, oni_v):
        st.markdown(f"<div class='rec-item'>{rec}</div>", unsafe_allow_html=True)

    # ── AI ANALYSIS ──────────────────────────────────────────────────────
    with st.expander("🤖 AI-Enhanced Analysis (optional)"):
        st.caption("Paste your Anthropic or OpenAI key in the sidebar to unlock.")
        if st.button("Generate AI Analysis", disabled=not bool(ai_key)):
            provider = "anthropic" if "anthropic" in ai_provider.lower() else "openai"
            with st.spinner("Asking AI…"):
                txt = call_llm_narrative(assessment, crop_choice, crop_stage, oni,
                                         st.session_state.preset_name, ai_key, provider)
            st.markdown(txt)

    # ── SAVE ────────────────────────────────────────────────────────────
    with st.expander("💾 Save this assessment"):
        if st.button("Save to local database"):
            try:
                init_db()
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO regional_targets "
                          "(region_name,country,crop_type,bbox_coords,is_scheduled) VALUES(?,?,?,?,?)",
                          (st.session_state.preset_name, active_region, crop_choice, f"{lon},{lat}", 0))
                c.execute("INSERT INTO self_correction_journal "
                          "(journal_date,assessment_period,target_district,raw_pdsi_forecast,"
                          "observed_pdsi,forecast_rmse,agent_reasoning,parameter_adjustments)"
                          " VALUES(?,?,?,?,?,?,?,?)",
                          (datetime.now().strftime("%Y-%m-%d"), "Manual",
                           st.session_state.preset_name, assessment["spi3"],
                           -deficit_90/100, abs(score-50),
                           generate_summary(assessment, crop_choice, crop_stage, oni["phase"],
                                            st.session_state.preset_name),
                           f'{{"score":{score},"level":"{level}","oni":{oni_v}}}'))
                conn.commit(); conn.close()
                st.success("Saved!")
            except Exception as e:
                st.error(f"Save failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: 90-DAY HISTORY
# ═══════════════════════════════════════════════════════════════════════════
with tab_history:
    if not data_ok:
        st.warning(f"No data. {weather_error or ''}")
    else:
        df90 = df_weather.tail(90)
        t_lo, t_hi = cal["optimal_temp"]

        # ── Pre-compute insights ─────────────────────────────────────────
        df_m = df_weather.tail(180).copy()
        df_m["ym"] = df_m["date"].dt.to_period("M")
        monthly_sum = df_m.groupby("ym").agg(
            rain=("precip_mm","sum"), n=("precip_mm","count")).reset_index()
        monthly_sum["need"] = monthly_sum.apply(
            lambda r: cal["daily_demand_mm"]*r["n"] if _is_active(cal, r["ym"].month) else 0, axis=1)
        active_months = monthly_sum[monthly_sum["need"] > 0]

        total_rain_90  = float(df90["precip_mm"].sum())
        total_et0_90   = float(df90["et0_mm"].sum())
        total_need_90  = cal["daily_demand_mm"] * len(df90)
        cum_deficit_90 = max(0.0, total_et0_90 - total_rain_90)
        avg_temp_90    = float(df90["temp_c"].mean())
        days_above_opt = int((df90["temp_c"] > t_hi).sum())
        dry_days_90    = int((df90["precip_mm"] < 1.0).sum())

        if not active_months.empty:
            worst_row = active_months.loc[active_months["rain"].idxmin()]
            worst_month_name = worst_row["ym"].strftime("%B %Y")
            worst_pct = min(100, (worst_row["rain"] / (worst_row["need"]+1e-6)) * 100)
            deficit_months = int((active_months["rain"] < active_months["need"] * 0.8).sum())
        else:
            worst_month_name, worst_pct, deficit_months = "—", 0, 0

        # cumulative balance trend
        cum_series = df90["water_balance_mm"].cumsum()
        trend_dir  = "worsening 📉" if cum_series.iloc[-1] < cum_series.iloc[len(cum_series)//2] else "stabilising 📊"

        # ── SECTION 1: Monthly rainfall ──────────────────────────────────
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Monthly Rainfall vs Crop Water Requirement")
        c_chart, c_insight = st.columns([3, 2])
        with c_chart:
            fig_m = _monthly_bar_chart(df_weather.tail(180), cal["daily_demand_mm"], cal)
            st.pyplot(fig_m, use_container_width=True); plt.close(fig_m)
            st.caption("🟢 Adequate · 🟡 Below optimal · 🔴 Critical deficit · ⬛ Off-season  ╌╌  Dashed line = crop water need")
        with c_insight:
            st.markdown("**What this tells you**")
            st.markdown(
                f"Over the last 6 months, **{deficit_months}** active growing "
                f"{'month' if deficit_months == 1 else 'months'} received less than 80% of "
                f"what your **{crop_choice}** needed.\n\n"
                f"The worst month was **{worst_month_name}**, which delivered only "
                f"**{worst_pct:.0f}%** of the required rainfall.\n\n"
                f"A bar touching or crossing the dashed green line means that month's rainfall "
                f"was sufficient. Bars well below it represent water stress periods your crop had to endure."
            )
            if deficit_months >= 2:
                st.error(f"⚠️ {deficit_months} months of deficit — cumulative stress is high.")
            elif deficit_months == 1:
                st.warning("One below-normal month detected. Watch the next rainfall closely.")
            else:
                st.success("Rainfall has been broadly adequate across recent months.")
        st.markdown("</div>", unsafe_allow_html=True)

        # ── SECTION 2: Water balance ─────────────────────────────────────
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Cumulative Water Balance — Last 90 Days")
        c_chart2, c_insight2 = st.columns([3, 2])
        with c_chart2:
            fig_wb = _water_balance_chart(df_weather)
            st.pyplot(fig_wb, use_container_width=True); plt.close(fig_wb)
            st.caption("Daily rainfall minus evaporation (ERA5 Penman-Monteith ET₀), cumulated over 90 days.")
        with c_insight2:
            st.markdown("**Reading the balance**")
            st.markdown(
                f"Total rainfall over 90 days: **{total_rain_90:.0f} mm**  \n"
                f"Total evaporation demand: **{total_et0_90:.0f} mm**  \n"
                f"Net moisture deficit: **{cum_deficit_90:.0f} mm**\n\n"
                f"The balance is currently **{trend_dir}** — "
                f"the line moving downward means more water is leaving the soil than arriving. "
                f"A balance consistently below zero means your crop's roots have less water available "
                f"each week."
            )
            if cum_deficit_90 > 150:
                st.error("Severe moisture deficit. Irrigation is critical.")
            elif cum_deficit_90 > 60:
                st.warning("Moderate deficit building. Consider supplementary water.")
            else:
                st.success("Water balance is within manageable range.")
        st.markdown("</div>", unsafe_allow_html=True)

        # ── SECTION 3: Temperature + Rain side-by-side ───────────────────
        col_t_chart, col_r_chart = st.columns(2)

        with col_t_chart:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("Temperature — 90 Days")
            fig_t, ax_t = plt.subplots(figsize=(5, 2.4), facecolor="none")
            ax_t.plot(df90["date"], df90["temp_c"], color="#f87171", linewidth=1.5, zorder=3)
            ax_t.axhspan(t_lo, t_hi, alpha=0.10, color="#38ef7d",
                         label=f"Optimal {t_lo}–{t_hi}°C", zorder=2)
            ax_t.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_t.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
            _ax_style(ax_t)
            ax_t.set_ylabel("°C", color="#94a3b8", fontsize=8)
            ax_t.legend(facecolor="#0d1117", edgecolor="#1e293b", labelcolor="#cbd5e1", fontsize=7)
            st.pyplot(fig_t, use_container_width=True); plt.close(fig_t)
            heat_note = (f"🌡️ **{days_above_opt} days** above the {t_hi}°C optimum — "
                         f"elevated evaporation stress." if days_above_opt > 5 else
                         f"Temperature has stayed mostly within the optimal range for {crop_choice}.")
            st.caption(heat_note)
            st.markdown("</div>", unsafe_allow_html=True)

        with col_r_chart:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("Daily Rain — 90 Days")
            fig_r, ax_r = plt.subplots(figsize=(5, 2.4), facecolor="none")
            ax_r.bar(df90["date"], df90["precip_mm"], color="#3b82f6", alpha=0.72, width=0.9, zorder=2)
            ax_r.axhline(cal["daily_demand_mm"], color="#38ef7d", linestyle="--",
                         linewidth=1.3, label=f"Daily need ({cal['daily_demand_mm']} mm)", zorder=3)
            ax_r.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_r.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
            _ax_style(ax_r)
            ax_r.set_ylabel("mm", color="#94a3b8", fontsize=8)
            ax_r.legend(facecolor="#0d1117", edgecolor="#1e293b", labelcolor="#cbd5e1", fontsize=7)
            st.pyplot(fig_r, use_container_width=True); plt.close(fig_r)
            st.caption(f"**{dry_days_90}** days with less than 1 mm of rain in the last 90 days.")
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Soil moisture section ───────────────────────────────────────
        if df_soil is not None and not df_soil.empty:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.subheader("Soil Moisture — last 120 days (ERA5 volumetric)")
            c_sm_chart, c_sm_txt = st.columns([3, 2])

            with c_sm_chart:
                fig_sm, ax_sm = plt.subplots(figsize=(8, 2.6), facecolor="none")
                ax_sm.plot(df_soil["date"], df_soil["soil_surface"] * 100,
                           color="#fbbf24", linewidth=1.5, label="Surface 0–7 cm", zorder=2)
                ax_sm.plot(df_soil["date"], df_soil["soil_root"] * 100,
                           color="#38bdf8", linewidth=1.7, label="Root-zone 7–28 cm", zorder=3)
                # Reference threshold band — below ~18% root-zone moisture is dryland stress
                ax_sm.axhspan(0, 18, alpha=0.07, color="#ef4444",
                              label="Root-zone stress (< 18%)")
                ax_sm.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
                ax_sm.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
                _ax_style(ax_sm)
                ax_sm.set_ylabel("% volumetric", color="#94a3b8", fontsize=8)
                ax_sm.legend(facecolor="#0d1117", edgecolor="#1e293b",
                             labelcolor="#cbd5e1", fontsize=7, loc="upper right")
                st.pyplot(fig_sm, use_container_width=True); plt.close(fig_sm)
                st.caption(
                    "ERA5 volumetric soil moisture (fraction of pore space filled with water). "
                    "Below 18% in the root zone is generally moisture-stress territory.")

            with c_sm_txt:
                sm_recent_7d = float(df_soil.tail(7)["soil_root"].mean())
                sm_recent_30d = float(df_soil.tail(30)["soil_root"].mean())
                sm_med_120d = float(df_soil["soil_root"].median())
                trend = "drying 📉" if sm_recent_7d < sm_recent_30d else "wetting 📈"
                stress_days = int((df_soil["soil_root"] < 0.18).sum())
                st.markdown("<div class='insight'>", unsafe_allow_html=True)
                st.markdown(
                    f"**Root-zone (7–28 cm) — the layer your crop drinks from**  \n"
                    f"7-day average:  **{sm_recent_7d*100:.0f}%**  \n"
                    f"30-day average: **{sm_recent_30d*100:.0f}%**  \n"
                    f"120-day median: **{sm_med_120d*100:.0f}%**  \n\n"
                    f"Trend over last week: **{trend}**  \n"
                    f"**{stress_days}** days were below the 18% stress threshold "
                    f"in the last 120 days."
                )
                if sm_recent_7d < 0.15:
                    st.error("Root zone is severely depleted. Crop is at wilting point.")
                elif sm_recent_7d < 0.18:
                    st.warning("Root zone is approaching stress threshold.")
                else:
                    st.success("Root-zone moisture is adequate for crop uptake.")
                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: 14-DAY FORECAST
# ═══════════════════════════════════════════════════════════════════════════
with tab_fc:
    if df_forecast is None or df_forecast.empty:
        st.warning("Forecast data unavailable. Check internet connection.")
    else:
        fc_precip = float(df_forecast["precip_mm"].sum())
        fc_et0    = float(df_forecast["et0_mm"].sum())
        fc_deficit = max(0.0, fc_et0 - fc_precip)
        fc_needed  = cal["daily_demand_mm"] * len(df_forecast)
        fc_pct     = min(150, (fc_precip / (fc_needed + 1e-6)) * 100)

        # ── Pre-compute forecast insights ────────────────────────────────
        good_days  = int((df_forecast["precip_mm"] >= cal["daily_demand_mm"]).sum())
        ok_days    = int(((df_forecast["precip_mm"] >= cal["daily_demand_mm"]*0.5) &
                          (df_forecast["precip_mm"] < cal["daily_demand_mm"])).sum())
        bad_days   = len(df_forecast) - good_days - ok_days
        best_idx   = df_forecast["precip_mm"].idxmax()
        best_day   = df_forecast.loc[best_idx, "date"].strftime("%b %d")
        best_rain  = float(df_forecast.loc[best_idx, "precip_mm"])
        cum_fc     = df_forecast["water_balance_mm"].cumsum()
        fc_trend   = ("improving 📈" if float(cum_fc.iloc[-1]) > float(cum_fc.iloc[len(cum_fc)//2])
                      else "worsening 📉")

        # ── Day-by-day chart + analysis ───────────────────────────────────
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("14-Day Rainfall Forecast")
        c_fc, c_fc_txt = st.columns([3, 2])
        with c_fc:
            st.pyplot(_forecast_chart(df_forecast, cal["daily_demand_mm"]),
                      use_container_width=True)
            st.caption("🟢 Meets daily crop need · 🟡 Partial (50–100%) · 🔴 Near-zero rain  ╌╌  Dashed = daily crop need")
        with c_fc_txt:
            st.markdown("**Forecast summary**")
            pct_col = "#22c55e" if fc_pct >= 80 else ("#f59e0b" if fc_pct >= 50 else "#ef4444")
            st.markdown(
                f"Forecast rain: **{fc_precip:.0f} mm**  \n"
                f"Crop water need: **{fc_needed:.0f} mm**  \n"
                f"Needs covered: <span style='color:{pct_col};font-weight:700'>{fc_pct:.0f}%</span>",
                unsafe_allow_html=True)
            st.markdown("---")
            st.markdown(
                f"🟢 **{good_days}** adequate rain days  \n"
                f"🟡 **{ok_days}** partial rain days  \n"
                f"🔴 **{bad_days}** near-dry days  \n\n"
                f"Best day: **{best_day}** ({best_rain:.1f} mm)  \n"
                f"Balance trend: **{fc_trend}**")
            if fc_pct < 50:
                st.error("Forecast does not cover crop needs. Arrange irrigation.")
            elif fc_pct < 80:
                st.warning("Partial coverage. Monitor soil moisture closely.")
            else:
                st.success("Forecast should broadly meet crop water requirements.")
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Cumulative balance + analysis ─────────────────────────────────
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Cumulative Water Balance — Next 14 Days")
        c_cum, c_cum_txt = st.columns([3, 2])
        with c_cum:
            fig_cumfc, ax_cumfc = plt.subplots(figsize=(6, 2.4), facecolor="none")
            ax_cumfc.plot(df_forecast["date"], cum_fc, color="#94a3b8", linewidth=1.6, zorder=3)
            ax_cumfc.fill_between(df_forecast["date"], cum_fc, 0,
                                  where=(cum_fc < 0), color="#ef4444", alpha=0.22, label="Deficit", zorder=2)
            ax_cumfc.fill_between(df_forecast["date"], cum_fc, 0,
                                  where=(cum_fc >= 0), color="#22c55e", alpha=0.15, label="Surplus", zorder=2)
            ax_cumfc.axhline(0, color="white", linewidth=0.5, alpha=0.3)
            ax_cumfc.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_cumfc.xaxis.set_major_locator(mdates.DayLocator(interval=3))
            _ax_style(ax_cumfc)
            ax_cumfc.set_ylabel("mm", color="#94a3b8", fontsize=8)
            ax_cumfc.legend(facecolor="#0d1117", edgecolor="#1e293b", labelcolor="#cbd5e1", fontsize=7)
            st.pyplot(fig_cumfc, use_container_width=True); plt.close(fig_cumfc)
            st.caption("Cumulative (rain − evaporation) over the forecast window.")
        with c_cum_txt:
            st.markdown("**What this means**")
            final_bal = float(cum_fc.iloc[-1])
            st.markdown(
                f"By day 14 the forecast adds a net water balance of **{final_bal:+.0f} mm**.\n\n")
            if final_bal < -80:
                st.markdown(
                    f"The outlook **adds more drought stress**. Without irrigation, "
                    f"**{crop_choice}** yield potential will continue to deteriorate.")
            elif final_bal < 0:
                st.markdown(
                    "Evaporation outpaces rainfall but the deficit is modest. "
                    "Soil reserves may buffer the impact short-term.")
            else:
                st.markdown(
                    "Forecast conditions offer **some relief** — incoming rain should "
                    "partially replenish soil moisture.")
        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: EL NIÑO IMPACT — this location's history, El Niño vs Neutral years
# ═══════════════════════════════════════════════════════════════════════════
with tab_elnino:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader(f"🌊 El Niño Impact on {crop_choice} at {st.session_state.preset_name}")
    st.caption("Comparing rainfall during the crop's growing season across "
               "all El Niño years vs Neutral years vs La Niña years since 1985. "
               "Real ERA5 history. Real NOAA ONI classification. No simulations.")

    with st.spinner("Loading 40 years of climatology…"):
        try:
            df_clim   = _cached_climatology(_lat_r, _lon_r)
            oni_hist  = _cached_oni_history()
            elnino    = seasonal_elnino_comparison(df_clim, oni_hist, cal)
        except Exception as e:
            elnino = {"ok": False, "reason": str(e)}

    if not elnino.get("ok"):
        st.warning(
            f"Could not build El Niño comparison: {elnino.get('reason', 'unknown')}.  \n"
            f"This view needs at least 6 complete growing seasons with valid ONI data. "
            f"Try a different location or crop.")
    else:
        phases   = elnino["phases"]
        dep_pct  = elnino["elnino_departure_pct"]
        ph_en    = phases.get("El Nino")
        ph_neu   = phases.get("Neutral")
        ph_la    = phases.get("La Nina")

        # ── Headline stat ────────────────────────────────────────────────
        if dep_pct is not None:
            hl_col   = "#F0883E" if dep_pct < -10 else ("#E3B341" if dep_pct < 0 else "#3FB950")
            hl_emoji = "⚠️" if dep_pct < -10 else ("🔻" if dep_pct < 0 else "↗")
            hl_msg   = (
                f"In **El Niño years**, the growing season at this location received "
                f"<span style='color:{hl_col};font-weight:700'>{dep_pct:+.0f}%</span> "
                f"rainfall vs Neutral years."
            )
            if dep_pct < -20:
                hl_msg += " That is a **substantial dry signal** — expect drought-style stress."
            elif dep_pct < -5:
                hl_msg += " That is a **mild dry signal**."
            elif dep_pct > 5:
                hl_msg += " Interestingly, El Niño actually brings MORE rain here."
            else:
                hl_msg += " Little ENSO sensitivity at this location."
            st.markdown(
                f"<div style='background:#161C22;border:1px solid {hl_col}44;border-radius:8px;"
                f"padding:14px 20px;margin:10px 0'>"
                f"<div style='font-size:.66rem;color:#8B949E;text-transform:uppercase;"
                f"letter-spacing:.1em;margin-bottom:6px'>Climatological Signal</div>"
                f"<div style='font-size:1rem;color:#E6EDF3;line-height:1.6'>{hl_emoji} {hl_msg}</div>"
                f"<div style='font-size:.78rem;color:#484F58;margin-top:6px'>"
                f"Based on {elnino['n_seasons']} growing seasons from "
                f"{elnino['first_year']} to {elnino['last_year']}.</div></div>",
                unsafe_allow_html=True)

        # ── KPI strip ────────────────────────────────────────────────────
        c1, c2, c3 = st.columns(3)
        for col, ph_key, color in [(c1, "El Nino", "#F0883E"),
                                    (c2, "Neutral", "#8B949E"),
                                    (c3, "La Nina", "#58A6FF")]:
            with col:
                ph = phases.get(ph_key)
                if ph:
                    col.markdown(
                        f"<div class='card'>"
                        f"<div style='font-size:.66rem;text-transform:uppercase;letter-spacing:.1em;"
                        f"color:{color};font-weight:600;margin-bottom:6px'>{ph_key} Years</div>"
                        f"<div style='font-size:1.7rem;font-weight:700;color:#E6EDF3;line-height:1'>"
                        f"{ph['mean_precip']:.0f} mm</div>"
                        f"<div style='font-size:.77rem;color:#8B949E;margin-top:4px'>"
                        f"Avg season rainfall · {ph['n_years']} years · {ph['mean_temp']:.1f}°C</div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    col.markdown(
                        f"<div class='card' style='opacity:.5'>"
                        f"<div style='font-size:.66rem;text-transform:uppercase;letter-spacing:.1em;"
                        f"color:#8B949E;font-weight:600;margin-bottom:6px'>{ph_key} Years</div>"
                        f"<div style='color:#484F58;font-size:.85rem'>No years in record</div>"
                        f"</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Per-year chart ──────────────────────────────────────────────
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Year-by-year growing-season rainfall")
        st.caption("Each bar = one growing season. Coloured by the ENSO phase that "
                   "year. Dashed line = Neutral-year average.")

        series = elnino["series"]
        years   = [s["year"]   for s in series]
        precips = [s["precip"] for s in series]
        phs     = [s["phase"]  for s in series]
        ph_color = {"El Nino": "#F0883E", "Neutral": "#8B949E", "La Nina": "#58A6FF"}
        colors   = [ph_color[p] for p in phs]

        fig_y, ax_y = plt.subplots(figsize=(10, 3.0), facecolor="none")
        ax_y.bar(years, precips, color=colors, alpha=0.88, width=0.7, zorder=2)
        if ph_neu:
            ax_y.axhline(ph_neu["mean_precip"], color="#8B949E", linestyle="--",
                         linewidth=1.4, alpha=0.7,
                         label=f"Neutral-year avg ({ph_neu['mean_precip']:.0f} mm)", zorder=3)
        ax_y.set_xticks(years)
        ax_y.set_xticklabels([str(y) for y in years], rotation=45, ha="right", fontsize=7)
        _ax_style(ax_y, xlabel_rotation=45)
        ax_y.set_ylabel("mm per season", color="#484F58", fontsize=8)
        from matplotlib.patches import Patch
        ax_y.legend(handles=[
            Patch(facecolor="#F0883E", alpha=0.88, label="El Niño year"),
            Patch(facecolor="#8B949E", alpha=0.88, label="Neutral year"),
            Patch(facecolor="#58A6FF", alpha=0.88, label="La Niña year"),
            plt.Line2D([0],[0], color="#8B949E", linestyle="--", linewidth=1.4, label="Neutral avg"),
        ], facecolor="#161C22", edgecolor="#21262D", labelcolor="#8B949E",
           fontsize=7, ncol=4, loc="upper right")
        st.pyplot(fig_y, use_container_width=True); plt.close(fig_y)
        st.markdown("</div>", unsafe_allow_html=True)

        # ── What this means for this season ─────────────────────────────
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("What this means for your current season")

        # Always lead with the LOCATION sensitivity (the part that varies per farm).
        # ENSO classification thresholds (NOAA): El Nino >= +0.5, La Nina <= -0.5,
        # else Neutral. ONI is a single global number, so the *current phase* is
        # the same everywhere — what changes per location is the *response*.

        if dep_pct is not None and ph_en and ph_neu:
            sens_word = ("highly sensitive" if abs(dep_pct) > 20 else
                         "moderately sensitive" if abs(dep_pct) > 10 else
                         "weakly sensitive")
            dep_dir = "drier" if dep_pct < 0 else "wetter"
            st.markdown(
                f"**At this location, the growing season is {sens_word} to El Niño.**  \n"
                f"In past El Niño seasons, rainfall was **{abs(dep_pct):.0f}% {dep_dir}** "
                f"than Neutral years ({ph_neu['mean_precip']:.0f} mm → "
                f"{ph_en['mean_precip']:.0f} mm).")
            st.markdown(
                f"<div style='font-size:.84rem;color:#8B949E;margin-top:6px'>"
                f"Current global ENSO: <b style='color:#E6EDF3'>NINO3.4 = {oni_v:+.2f}°C</b>"
                f" · NOAA classifies this as <b style='color:#E6EDF3'>"
                f"{'El Niño' if oni_v >= 0.5 else ('La Niña' if oni_v <= -0.5 else 'Neutral')}</b>."
                f" Thresholds: El Niño ≥ +0.5°C · La Niña ≤ –0.5°C · between = Neutral."
                f"</div>",
                unsafe_allow_html=True)

            # Action banner driven by actual current phase + location sensitivity
            if oni_v >= 0.5 and dep_pct < -15:
                st.error(
                    f"⚠️ El Niño is active AND this location is highly sensitive — "
                    f"plan supplementary irrigation early. Expected season rainfall "
                    f"~{ph_en['mean_precip']:.0f} mm vs typical {ph_neu['mean_precip']:.0f} mm.")
            elif oni_v >= 0.5 and dep_pct < -5:
                st.warning(f"El Niño is active and this location historically gets "
                           f"{abs(dep_pct):.0f}% less rain in such years.")
            elif oni_v >= 0.3 and dep_pct < -10:
                st.warning(f"ONI is climbing toward the El Niño threshold "
                           f"(+0.5°C). At this location, El Niño years are "
                           f"{abs(dep_pct):.0f}% drier — start contingency planning now.")
            elif oni_v <= -0.5 and ph_la:
                st.success(
                    f"La Niña is active. At this location, La Niña years averaged "
                    f"**{ph_la['mean_precip']:.0f} mm** vs **{ph_neu['mean_precip']:.0f} mm** "
                    f"in Neutral years — generally wetter than normal.")
            else:
                st.info(
                    f"ENSO is currently Neutral. Most likely outcome: a season "
                    f"close to the typical **{ph_neu['mean_precip']:.0f} mm**. "
                    f"Monitor monthly — the ONI is only {abs(oni_v):.2f}°C from "
                    f"the {'El Niño' if oni_v >= 0 else 'La Niña'} threshold.")
        else:
            st.info("Not enough phase data to build a current-season verdict.")
        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 5: METHODOLOGY
# ═══════════════════════════════════════════════════════════════════════════
with tab_about:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Data Sources — All Real, All Free")
    st.markdown("""
| Source | Variable | Update |
|--------|----------|--------|
| **Open-Meteo ERA5 archive** | Daily rainfall (mm), mean temperature (°C), FAO-56 reference evapotranspiration ET₀ (mm) | Daily, 5-day lag |
| **Open-Meteo Forecast** | 14-day precipitation, temperature, ET₀ | Daily |
| **NOAA CPC NINO3.4** | Monthly SST anomaly (El Niño / La Niña intensity) | Monthly |

All three sources are free and require no registration or API key.
No simulated or fallback values are shown — if a data source is offline the dashboard shows an error.
""")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Risk Score Methodology")
    st.markdown(r"""
The 0–100 drought risk score combines four components:

**1. SPI-3 — Standardised Precipitation Index (McKee et al. 1993)**
Fits the full historical daily precipitation series to a two-parameter Gamma distribution,
then converts to standard normal probabilities. SPI-3 < –1.0 = drought onset; < –2.0 = severe drought.
*Contributes up to 40 points.*

**2. Cumulative Water Deficit P − ET₀ (FAO-56)**
Total rainfall minus reference evapotranspiration over the last 90 days.
ET₀ is computed by Open-Meteo using the Penman-Monteith equation from ERA5 radiation,
wind, humidity, and temperature — no approximations.
*Contributes up to 40 points.*

**3. Temperature stress**
Mean temperature above 25 °C accelerates soil drying and increases crop transpiration demand.
*Contributes up to 20 points.*

**4. ENSO amplification (Ropelewski & Halpert 1987)**
If NINO3.4 ≥ +0.5 °C (El Niño developing), the score is multiplied up to ×1.5,
reflecting the teleconnection between Pacific SST anomalies and suppressed monsoon rainfall
over Southern Africa, South Asia, and Australia.

**5. Crop stage weighting**
Flowering, tasseling, panicle initiation, and grain-filling stages are amplified ×1.35,
because water stress during pollination causes irreversible yield loss.

**6. Off-season dampener**
During fallow/dormant months the score is reduced ×0.25 — dry conditions are expected
and do not represent crop stress.
""")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("📓 Saved Assessments")
    try:
        init_db()
        conn = get_db_connection()
        df_j = pd.read_sql_query(
            "SELECT journal_date, target_district, agent_reasoning "
            "FROM self_correction_journal ORDER BY id DESC LIMIT 20", conn)
        conn.close()
        if df_j.empty:
            st.info("No saved assessments yet. Use the 'Save' button in Farm Status.")
        else:
            for _, row in df_j.iterrows():
                st.markdown(f"**{row['journal_date']} — {row['target_district']}**")
                st.caption(row["agent_reasoning"])
                st.markdown("---")
    except Exception as e:
        st.info(f"Database not yet initialised: {e}")
    st.markdown("</div>", unsafe_allow_html=True)
