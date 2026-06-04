"""
ENSOwatch AI — Agricultural Drought Early-Warning
Farmer-facing dashboard built on free public climate data.

Data sources:
  Weather:        Open-Meteo ERA5 archive + 14-day forecast (free, no key)
  ENSO state:     NOAA CPC NINO3.4 (free, no key)
  Soil moisture:  ERA5 volumetric (free, no key)
  Crop calendars: FAO / USDA / IRRI (literature-grounded)

Optional AI narrative: user supplies their own Anthropic or OpenAI key.
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
    fetch_weather, fetch_forecast, fetch_climatology, fetch_soil_moisture, fetch_window,
)
from ensa.ingest.enso import fetch_current_oni, fetch_oni_history
from ensa.analysis.elnino import seasonal_elnino_comparison
from ensa.analysis.crop_calendars import CROP_CALENDARS
from ensa.analysis.hindsight import hindsight_compare
from ensa.agent.brain import (
    compute_drought_score,
    generate_summary,
    generate_summary_past,
    generate_recommendations,
    generate_observations_past,
    call_llm_narrative,
)
from ensa.db.connection import get_db_connection, init_db

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ENSOwatch AI — Agricultural Drought Early-Warning",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Institutional Light theme — inspired by FAO GIEWS / World Bank CKP / WFP HungerMap
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Serif:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

/* ---- App shell ----------------------------------------------------- */
html, body, [class*="stApp"] {
    background: #FAFAF7 !important;
    color: #1F2937 !important;
    font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
.stApp { background: #FAFAF7 !important; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 4rem !important; max-width: 1400px; }

/* ---- Typography ---------------------------------------------------- */
h1, h2, h3, h4, h5 {
    font-family: 'IBM Plex Serif', Georgia, serif !important;
    color: #111827 !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
}
h1 { font-size: 2rem !important; }
h2 { font-size: 1.5rem !important; }
/* Subheaders become section dividers automatically -- replaces card wrappers */
h3 {
    font-size: 1.15rem !important;
    margin: 32px 0 12px 0 !important;
    padding-top: 16px !important;
    border-top: 1px solid #E5E7EB !important;
}
/* First subheader in each tab shouldn't have a top rule */
[data-testid="stTabContent"] > div > div:first-child h3,
[data-testid="stTabContent"] > div > div:first-child + div h3 {
    border-top: none !important;
    padding-top: 0 !important;
    margin-top: 8px !important;
}
h4 { font-size: 1rem !important; margin-top: 18px !important; }
/* Markdown headings emitted via st.markdown("### ...") */
.stMarkdown h3 {
    border-top: 1px solid #E5E7EB !important;
    padding-top: 16px !important;
    margin-top: 28px !important;
}
p, .stMarkdown p, label, span { color: #374151 !important; }
.stMarkdown code, .data-mono { font-family: 'IBM Plex Mono', monospace !important; }

/* ---- Cards (white surface, hairline border, no shadow) ------------- */
.card {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 24px 28px;
    margin-bottom: 16px;
}

/* ---- Section labels ----------------------------------------------- */
.kpi-label, .sec-label {
    font-size: 0.7rem !important;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #6B7280 !important;
    margin-bottom: 6px;
}
.kpi-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.7rem;
    font-weight: 600;
    color: #111827 !important;
    line-height: 1.1;
}
.kpi-sub {
    font-size: 0.8rem;
    color: #6B7280 !important;
    margin-top: 4px;
    line-height: 1.4;
}

/* ---- Recommendation / observation rows ----------------------------- */
.rec-item {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-left: 3px solid #003D5C;
    border-radius: 4px;
    padding: 14px 18px;
    margin-bottom: 8px;
    font-size: 0.92rem;
    line-height: 1.55;
    color: #1F2937;
}

/* ---- Tabs (clean, institutional) ----------------------------------- */
.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 1px solid #E5E7EB;
    gap: 0;
    padding-left: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #6B7280 !important;
    font-weight: 500 !important;
    font-size: 0.92rem !important;
    padding: 8px 18px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -1px !important;
}
.stTabs [aria-selected="true"] {
    color: #003D5C !important;
    border-bottom-color: #003D5C !important;
    background: transparent !important;
    font-weight: 600 !important;
}

/* ---- Sidebar -------------------------------------------------------- */
[data-testid="stSidebar"] {
    background: #F3F4F6 !important;
    border-right: 1px solid #E5E7EB !important;
}
[data-testid="stSidebar"] * { color: #374151 !important; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #111827 !important; }
[data-testid="stSidebar"] hr { border-color: #E5E7EB !important; }

/* ---- Buttons -------------------------------------------------------- */
.stButton > button {
    background: #003D5C !important;
    color: #FFFFFF !important;
    border: 1px solid #003D5C !important;
    border-radius: 4px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    transition: background 0.15s ease;
}
.stButton > button:hover {
    background: #002A40 !important;
    border-color: #002A40 !important;
}

/* ---- Inputs --------------------------------------------------------- */
input, .stSelectbox > div > div, [data-baseweb="select"] {
    background: #FFFFFF !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 4px !important;
    color: #1F2937 !important;
}

/* ---- Saturation bar (water needs met) ----------------------------- */
.sat-bar-wrap {
    background: #F3F4F6;
    border: 1px solid #E5E7EB;
    border-radius: 4px;
    height: 14px;
    overflow: hidden;
    margin: 6px 0 4px;
}
.sat-bar-fill { height: 100%; border-radius: 3px; }

/* ---- ENSO chip / general chip ------------------------------------- */
.enso-chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 3px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}

/* ---- Top header bar (wordmark) ------------------------------------ */
.app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    padding: 6px 0 16px;
    margin-bottom: 18px;
    border-bottom: 1px solid #E5E7EB;
}
.brand-wordmark {
    font-family: 'IBM Plex Serif', Georgia, serif;
    font-size: 1.5rem;
    font-weight: 600;
    color: #111827;
    letter-spacing: -0.01em;
}
.brand-wordmark .accent { color: #003D5C; }
.brand-tagline {
    font-size: 0.85rem;
    color: #6B7280;
    margin-left: 14px;
    border-left: 1px solid #E5E7EB;
    padding-left: 14px;
}

/* ---- Streamlit defaults to suppress ------------------------------- */
#MainMenu, footer, .stDeployButton { display: none !important; }
.stCaption, .caption { color: #9CA3AF !important; font-size: 0.78rem !important; }

/* ---- Alerts -------------------------------------------------------- */
[data-testid="stAlert"] { border-radius: 4px; }
.stAlert > div { font-family: 'IBM Plex Sans', sans-serif !important; }

/* ---- Past-mode banner (lighter slate, less shouty) ---------------- */
.past-banner {
    background: #EFF6FF;
    border-left: 3px solid #003D5C;
    border-radius: 4px;
    padding: 12px 18px;
    margin-bottom: 18px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}

/* ---- NO global container styling -- we don't want nested borders. ----
   Cards are now sections separated by whitespace + .sec-label dividers
   (FAO GIEWS / World Bank Climate Knowledge Portal aesthetic). */

/* ---- Hide Streamlit's native top header bar (the black strip) ----- */
header[data-testid="stHeader"] { background: transparent !important;
    height: 0 !important; visibility: hidden !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {
    display: none !important;
}

/* ---- Number input stepper buttons ---------------------------------- */
.stNumberInput button {
    background: #FFFFFF !important; color: #003D5C !important;
    border: 1px solid #D1D5DB !important; border-radius: 4px !important;
}
.stNumberInput button:hover {
    background: #F3F4F6 !important; border-color: #003D5C !important;
}
.stNumberInput button svg { fill: #003D5C !important; color: #003D5C !important; }
.stNumberInput input {
    background: #FFFFFF !important; color: #1F2937 !important;
    border: 1px solid #D1D5DB !important;
}

/* ---- Date input (target every nested wrapper Streamlit emits) ---- */
.stDateInput, .stDateInput * { background-color: transparent !important; }
.stDateInput [data-baseweb="input"],
.stDateInput [data-baseweb="input"] > div {
    background: #FFFFFF !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 4px !important;
}
.stDateInput input { color: #1F2937 !important; background: #FFFFFF !important; }
.stDateInput [data-baseweb="input"] svg { fill: #6B7280 !important; }

/* ---- Text input (API key field + eye icon) ----------------------- */
.stTextInput [data-baseweb="input"],
.stTextInput [data-baseweb="input"] > div {
    background: #FFFFFF !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 4px !important;
}
.stTextInput input { background: #FFFFFF !important; color: #1F2937 !important; }
/* Eye icon (password visibility toggle) — kill dark background */
.stTextInput button { background: #FFFFFF !important; border: none !important; }
.stTextInput button:hover { background: #F3F4F6 !important; }
.stTextInput button svg { fill: #6B7280 !important; color: #6B7280 !important; }

/* ---- Sidebar select / inputs -------------------------------------- */
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #FFFFFF !important; border-color: #D1D5DB !important; color: #1F2937 !important;
}
/* Tighten the sidebar -- less vertical padding, custom labels */
[data-testid="stSidebar"] .block-container { padding-top: 1.5rem !important; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
    color: #475569 !important; font-size: 0.78rem !important;
    text-transform: uppercase !important; letter-spacing: 0.05em !important;
    margin-bottom: 4px !important;
}
.sb-section {
    font-family: 'IBM Plex Serif', Georgia, serif;
    font-size: 0.95rem; font-weight: 600;
    color: #003D5C;
    margin: 18px 0 6px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid #E5E7EB;
}
.sb-section:first-of-type { margin-top: 6px; }

/* ---- Brand tagline wrapping --------------------------------------- */
.brand-tagline { white-space: nowrap; min-width: 0; }
@media (max-width: 980px) {
    .brand-tagline { display: none; }
    .app-header { padding-bottom: 10px; }
}
.brand-wordmark { white-space: nowrap; }

/* ---- SECTION LABEL (publication-style heading row) ---------------- */
.sec-label {
    font-family: 'IBM Plex Serif', Georgia, serif;
    font-size: 1.15rem;
    font-weight: 600;
    color: #111827;
    margin: 32px 0 12px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #E5E7EB;
    letter-spacing: -0.005em;
}
.sec-label.subtle {
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #475569;
    border-bottom: none;
    margin: 24px 0 8px 0;
    padding-bottom: 0;
}
.sec-label:first-of-type { margin-top: 8px; }

/* ---- KPI label / value / sub colors ------------------------------- */
.kpi-label { color: #475569 !important; }
.kpi-value { color: #0F172A !important; }
.kpi-sub   { color: #475569 !important; }

/* ---- KPI tile (used inline in El Nino tab) ------------------------ */
/* No heavy border -- just a coloured top accent rule + padding */
.kpi-tile {
    background: #FFFFFF;
    border-top: 3px solid #E5E7EB;
    padding: 14px 4px 6px 4px;
    margin-bottom: 10px;
}
.kpi-tile.ok   { border-top-color: #15803D; }
.kpi-tile.warn { border-top-color: #B45309; }
.kpi-tile.bad  { border-top-color: #B91C1C; }

/* ---- st.metric ---------------------------------------------------- */
[data-testid="stMetricValue"] { color: #0F172A !important; font-family: 'IBM Plex Mono', monospace !important; }
[data-testid="stMetricLabel"] { color: #475569 !important; }
[data-testid="stMetricDelta"] { color: #475569 !important; }

/* ---- Captions ----------------------------------------------------- */
[data-testid="stCaptionContainer"], .stCaption {
    color: #6B7280 !important; font-size: 0.82rem !important;
}

/* ---- Recommendation/observation rows ------------------------------ */
.rec-item {
    background: #FFFFFF;
    border-left: 3px solid #003D5C;
    border-radius: 0;
    padding: 12px 18px;
    margin-bottom: 6px;
    font-size: 0.92rem;
    line-height: 1.55;
    color: #1F2937;
}

/* ---- Risk score block (KEPT as visual highlight) ------------------ */
.risk-block {
    background: #F8FAFC;
    border-left: 4px solid #003D5C;
    border-radius: 4px;
    padding: 20px 24px;
    margin: 16px 0;
}
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
    ("Pakistan",        23.0, 37.5,  60.0,  75.0),
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

# Institutional Light chart palette (matches CSS theme)
_LIGHT_BG       = "#FFFFFF"
_LIGHT_BORDER   = "#E5E7EB"
_LIGHT_GRID     = "#F3F4F6"
_LIGHT_AXIS     = "#6B7280"
_LIGHT_TEXT     = "#1F2937"
_LIGHT_TEXT_DIM = "#9CA3AF"
_ACCENT_NAVY    = "#003D5C"
_ACCENT_GREEN   = "#15803D"
_RISK_NORMAL    = "#15803D"
_RISK_WATCH     = "#1E40AF"
_RISK_WARNING   = "#B45309"
_RISK_SEVERE    = "#C2410C"
_RISK_EXTREME   = "#B91C1C"
_OFF_SEASON     = "#D1D5DB"


def _gauge(score, color):
    """Half-donut risk gauge — light theme."""
    fig, ax = plt.subplots(figsize=(3.6, 2.2), facecolor=_LIGHT_BG)
    ax.set_facecolor(_LIGHT_BG)
    track_θ = np.linspace(np.pi, 0, 300)
    ax.plot(np.cos(track_θ), np.sin(track_θ), color=_LIGHT_GRID,
            linewidth=22, solid_capstyle="round", zorder=1)
    if score > 0:
        value_θ = np.linspace(np.pi, np.pi - (min(score, 100) / 100) * np.pi, 300)
        ax.plot(np.cos(value_θ), np.sin(value_θ), color=color,
                linewidth=22, solid_capstyle="round", zorder=2)
    ax.text(0, 0.18, f"{score:.0f}", ha="center", va="center",
            fontsize=38, fontweight="600", color=_LIGHT_TEXT,
            family="IBM Plex Mono", zorder=3)
    ax.text(0, -0.22, "out of 100", ha="center", va="center",
            fontsize=8.5, color=_LIGHT_AXIS, zorder=3)
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-0.55, 1.4)
    ax.axis("off")
    return fig


def _ax_style(ax, xlabel_rotation=30):
    """Consistent light-theme chart style — sober UN/WB look."""
    ax.set_facecolor(_LIGHT_BG)
    ax.tick_params(colors=_LIGHT_AXIS, labelsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["left"].set_visible(True)
    ax.spines["bottom"].set_visible(True)
    ax.spines["left"].set_color(_LIGHT_BORDER)
    ax.spines["bottom"].set_color(_LIGHT_BORDER)
    ax.grid(axis="y", color=_LIGHT_GRID, linewidth=1, zorder=0)
    plt.xticks(rotation=xlabel_rotation, ha="right")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(_LIGHT_AXIS)


def _legend(ax, **kw):
    """Consistent legend styling."""
    leg = ax.legend(facecolor=_LIGHT_BG, edgecolor=_LIGHT_BORDER,
                    labelcolor=_LIGHT_TEXT, fontsize=7, framealpha=1, **kw)
    return leg


def _monthly_bar_chart(df_hist, daily_demand_mm, cal):
    """Monthly rainfall vs crop need — adequacy-coloured bars + dashed need line."""
    df = df_hist.copy()
    df["ym"] = df["date"].dt.to_period("M")
    monthly = df.groupby("ym").agg(
        precip_mm=("precip_mm", "sum"),
        n_days=("precip_mm", "count"),
    ).reset_index()
    monthly["needed_mm"] = monthly.apply(
        lambda r: daily_demand_mm * r["n_days"] if _is_active(cal, r["ym"].month) else 0,
        axis=1,
    )
    monthly["label"] = monthly["ym"].dt.strftime("%b '%y")

    def _bar_color(row):
        if row["needed_mm"] == 0:                                return _OFF_SEASON
        if row["precip_mm"] >= row["needed_mm"] * 0.9:           return _RISK_NORMAL
        if row["precip_mm"] >= row["needed_mm"] * 0.6:           return _RISK_WARNING
        return _RISK_SEVERE

    colors = monthly.apply(_bar_color, axis=1)
    fig, ax = plt.subplots(figsize=(8, 2.8), facecolor=_LIGHT_BG)
    ax.bar(range(len(monthly)), monthly["precip_mm"], color=colors,
           alpha=0.92, width=0.65, zorder=2)
    ax.plot(range(len(monthly)), monthly["needed_mm"], color=_ACCENT_NAVY,
            linewidth=1.6, linestyle="--", marker="o", markersize=3.5,
            label="Crop water need", zorder=3)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels(monthly["label"])
    _ax_style(ax)
    ax.set_ylabel("mm", color=_LIGHT_AXIS, fontsize=8)

    from matplotlib.patches import Patch
    legend_els = [
        Patch(facecolor=_RISK_NORMAL,  alpha=0.92, label="Adequate (≥ 90%)"),
        Patch(facecolor=_RISK_WARNING, alpha=0.92, label="Below optimal (60–90%)"),
        Patch(facecolor=_RISK_SEVERE,  alpha=0.92, label="Critical deficit (< 60%)"),
        Patch(facecolor=_OFF_SEASON,   alpha=0.92, label="Off-season"),
        plt.Line2D([0], [0], color=_ACCENT_NAVY, linewidth=1.5,
                   linestyle="--", label="Crop water need"),
    ]
    ax.legend(handles=legend_els, facecolor=_LIGHT_BG, edgecolor=_LIGHT_BORDER,
              labelcolor=_LIGHT_TEXT, fontsize=7, ncol=2, loc="upper right",
              framealpha=1)
    return fig


def _forecast_chart(df_fc, daily_demand_mm):
    """Forecast bars coloured by daily-need adequacy."""
    colors = [_RISK_NORMAL if r >= daily_demand_mm else
              (_RISK_WARNING if r >= daily_demand_mm * 0.5 else _RISK_SEVERE)
              for r in df_fc["precip_mm"]]
    fig, ax = plt.subplots(figsize=(8, 2.6), facecolor=_LIGHT_BG)
    ax.bar(df_fc["date"], df_fc["precip_mm"], color=colors,
           alpha=0.92, width=0.8, zorder=2)
    ax.axhline(daily_demand_mm, color=_ACCENT_NAVY, linestyle="--",
               linewidth=1.4, label=f"Daily crop need ({daily_demand_mm} mm)",
               zorder=3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    _ax_style(ax)
    ax.set_ylabel("mm/day", color=_LIGHT_AXIS, fontsize=8)
    _legend(ax)
    return fig


def _water_balance_chart(df_hist):
    """Cumulative P − ET₀ over last 90 days — light theme."""
    df = df_hist.tail(90).copy()
    cum = df["water_balance_mm"].cumsum()
    fig, ax = plt.subplots(figsize=(8, 2.5), facecolor=_LIGHT_BG)
    ax.plot(df["date"], cum, color=_LIGHT_TEXT, linewidth=1.6, zorder=3)
    ax.fill_between(df["date"], cum, 0, where=(cum < 0),
                    color=_RISK_SEVERE, alpha=0.18, label="Deficit", zorder=2)
    ax.fill_between(df["date"], cum, 0, where=(cum >= 0),
                    color=_RISK_NORMAL, alpha=0.16, label="Surplus", zorder=2)
    ax.axhline(0, color=_LIGHT_BORDER, linewidth=1, zorder=1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    _ax_style(ax)
    ax.set_ylabel("mm", color=_LIGHT_AXIS, fontsize=8)
    _legend(ax)
    return fig


def _crop_calendar_strip(cal, current_month):
    """Horizontal 12-month crop calendar with current month marked — light theme."""
    months = list(range(1, 13))
    colors = []
    for m in months:
        stage = cal["stages"][m]
        if "Critical" in stage:
            colors.append(_RISK_SEVERE)
        elif "Fallow" in stage or "Dormant" in stage or "Overwintering" in stage:
            colors.append(_OFF_SEASON)
        elif "Harvesting" in stage:
            colors.append(_RISK_WARNING)
        else:
            colors.append(_RISK_NORMAL)

    fig, ax = plt.subplots(figsize=(10, 1.1), facecolor="none")
    ax.set_facecolor("none")
    for i, (m, c) in enumerate(zip(months, colors)):
        rect = mpatches.FancyBboxPatch((i, 0), 0.88, 0.9, boxstyle="round,pad=0.04",
                                       facecolor=c, edgecolor="none", alpha=0.85)
        ax.add_patch(rect)
        label = calendar.month_abbr[m]
        ax.text(i + 0.44, 0.45, label, ha="center", va="center",
                color="white", fontsize=8.5, fontweight="600")
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
        ax.text(x_pos+0.25, -0.14, label, color="#6B7280", fontsize=6.5, va="center")
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


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_window(lat, lon, end_date_iso, days_back=120):
    """Cached ERA5 archive window ending on a specific past date."""
    return fetch_window(lat, lon, end_date_iso, days_back=days_back)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "point"       not in st.session_state: st.session_state.point = PRESETS["Mazabuka, Zambia"]["coords"]
if "preset_name" not in st.session_state: st.session_state.preset_name = "Mazabuka, Zambia"

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown(
    "<div style='text-align:center;padding:8px 0 4px'>"
    "<div style='font-family:IBM Plex Serif,Georgia,serif;font-size:1.4rem;"
    "font-weight:600;color:#111827;letter-spacing:-.01em'>"
    "ENSO<span style='color:#003D5C'>watch</span>"
    " <span style='font-size:.7em;color:#6B7280;font-weight:500'>AI</span>"
    "</div>"
    "<div style='color:#6B7280;font-size:.78rem;margin-top:2px'>"
    "Agricultural Drought Early-Warning</div>"
    "</div>",
    unsafe_allow_html=True)
st.sidebar.markdown(
    "<div style='border-top:1px solid #E5E7EB;margin:8px 0 4px'></div>",
    unsafe_allow_html=True)

# ── Location ────────────────────────────────────────────────────────────────
st.sidebar.markdown('<div class="sb-section">Location</div>', unsafe_allow_html=True)
preset_name = st.sidebar.selectbox(
    "Preset", list(PRESETS.keys()),
    index=list(PRESETS.keys()).index(st.session_state.preset_name),
    label_visibility="collapsed")
if preset_name != st.session_state.preset_name:
    st.session_state.preset_name = preset_name
    if preset_name != "Custom Point":
        st.session_state.point = PRESETS[preset_name]["coords"]
    st.rerun()

c1, c2 = st.sidebar.columns(2)
with c1: lat_in = st.number_input("Lat",  value=float(st.session_state.point[0]), format="%.4f")
with c2: lon_in = st.number_input("Lon",  value=float(st.session_state.point[1]), format="%.4f")
if [lat_in, lon_in] != list(st.session_state.point):
    st.session_state.point = [lat_in, lon_in]
    st.session_state.preset_name = "Custom Point"
    st.rerun()

lat, lon = st.session_state.point
active_region = _detect_region(lat, lon)
cal_region = CROP_CALENDARS.get(active_region, CROP_CALENDARS["Global"])

# ── Crop ────────────────────────────────────────────────────────────────────
st.sidebar.markdown('<div class="sb-section">Crop</div>', unsafe_allow_html=True)
crop_choice = st.sidebar.selectbox("Type", list(cal_region.keys()), label_visibility="collapsed")
cal = cal_region[crop_choice]

# ── Date ────────────────────────────────────────────────────────────────────
st.sidebar.markdown('<div class="sb-section">Assessment Date</div>', unsafe_allow_html=True)
assessment_date = st.sidebar.date_input(
    "Date", value=datetime.now().date(),
    min_value=datetime(2000,1,1).date(),
    max_value=(datetime.now()+timedelta(days=14)).date(),
    label_visibility="collapsed",
    help="Pick any past date to analyse historical conditions")
a_month = assessment_date.month
crop_stage = cal["stages"][a_month]
is_active  = _is_active(cal, a_month)
is_fc_mode    = assessment_date > (datetime.now() - timedelta(days=5)).date()
# Hindsight mode: any date older than ~395 days isn't in the standard df_weather
# window, so we fetch a dedicated archive window centered on that date.
days_ago      = (datetime.now().date() - assessment_date).days
is_hindsight  = (not is_fc_mode) and days_ago > 395
# "Recent past" hindsight: within df_weather range but >7 days old still gets the
# climatology comparison shown -- it's the model-vs-truth story the user asked for.
is_past_mode  = (not is_fc_mode) and days_ago > 7

# ── AI (optional) ───────────────────────────────────────────────────────────
st.sidebar.markdown('<div class="sb-section">AI Analysis · optional</div>', unsafe_allow_html=True)
ai_provider = st.sidebar.selectbox("Provider", ["Anthropic (Claude)", "OpenAI (GPT-4o-mini)"],
                                   label_visibility="collapsed")
ai_key = st.sidebar.text_input("API Key", type="password", placeholder="sk-ant-... or sk-...",
                               label_visibility="collapsed")

st.sidebar.markdown(
    "<div style='font-size:.72rem;color:#9CA3AF;text-align:center;"
    "margin-top:18px;line-height:1.5;border-top:1px solid #E5E7EB;padding-top:12px'>"
    "Weather: Open-Meteo ERA5<br>ENSO: NOAA CPC<br>"
    "<span style='color:#6B7280'>All data is real — no simulations.</span></div>",
    unsafe_allow_html=True)

# ── Author / attribution block ─────────────────────────────────────────────
st.sidebar.markdown(
    "<div style='font-size:.72rem;color:#475569;text-align:center;"
    "margin-top:14px;line-height:1.55;border-top:1px solid #E5E7EB;padding-top:12px'>"
    "<div style='font-weight:600;color:#111827;font-size:.78rem;"
    "font-family:IBM Plex Serif,Georgia,serif'>Kripan K C</div>"
    "<div style='margin-top:2px'>M.Sc. Environmental Engineering, TUM</div>"
    "<div>Student Research Assistant, DLR</div>"
    "<a href='mailto:Kripankc3@gmail.com' "
    "style='color:#003D5C;text-decoration:none;font-weight:500;"
    "margin-top:4px;display:inline-block'>Kripankc3@gmail.com</a>"
    "</div>",
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
oni_v = oni["value"]

# Institutional ENSO chip colors (light theme)
if   oni_v >= 1.5: enso_bg, enso_border, enso_txt = "#FEE2E2", "#FCA5A5", "#991B1B"
elif oni_v >= 0.5: enso_bg, enso_border, enso_txt = "#FEF3C7", "#FCD34D", "#92400E"
elif oni_v <= -0.5:enso_bg, enso_border, enso_txt = "#DBEAFE", "#93C5FD", "#1E40AF"
else:              enso_bg, enso_border, enso_txt = "#D1FAE5", "#86EFAC", "#065F46"

live_dot = "●" if "Offline" not in oni["source"] else "○"

st.markdown(
    f"<div class='app-header'>"
    f"  <div style='display:flex;align-items:center;gap:0;flex-wrap:wrap'>"
    f"    <span class='brand-wordmark'>ENSO<span class='accent'>watch</span> "
    f"<span style='font-size:.65em;color:#6B7280;font-weight:500;letter-spacing:.05em'>AI</span></span>"
    f"    <span class='brand-tagline'>Agricultural drought early-warning · {active_region}</span>"
    f"  </div>"
    f"  <div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>"
    f"    <span class='enso-chip' style='background:{enso_bg};border:1px solid {enso_border};color:{enso_txt}'>"
    f"      NINO3.4&nbsp;&nbsp;<b>{oni_v:+.2f}°C</b>&nbsp;&nbsp;·&nbsp;&nbsp;{oni['phase']}"
    f"    </span>"
    f"    <span style='color:#9CA3AF;font-size:.78rem;font-family:IBM Plex Mono,monospace'>"
    f"      {live_dot} {oni['month_name']} {oni['year']} · NOAA CPC"
    f"    </span>"
    f"  </div>"
    f"</div>",
    unsafe_allow_html=True
)

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
    # Banner at top when user is analysing a historical date.
    if is_past_mode:
        st.markdown(
            f"<div class='past-banner'>"
            f"<span style='font-size:1.2rem'>🕰</span>"
            f"<span style='color:#003D5C;font-weight:600;font-size:.78rem;"
            f"text-transform:uppercase;letter-spacing:.08em'>Historical Analysis Mode</span>"
            f"<span style='color:#374151;font-size:.92rem'>"
            f"Analysing conditions on <b style='color:#111827'>{assessment_date.strftime('%d %B %Y')}</b>"
            f" ({days_ago} days ago) — past observations only, no live actions.</span>"
            f"</div>", unsafe_allow_html=True)

    col_map, col_info = st.columns([3,1])

    with col_map:
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

    with col_info:
        st.markdown(f"<div class='kpi-label'>Detected Region</div><div class='kpi-value' style='font-size:1.1rem'>{active_region}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-label' style='margin-top:10px'>Crop</div><div class='kpi-value' style='font-size:1.05rem'>{crop_choice}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-label' style='margin-top:10px'>Stage · {assessment_date.strftime('%b %Y')}</div><div class='kpi-value' style='font-size:.92rem'>{crop_stage}</div>", unsafe_allow_html=True)
        if is_fc_mode:    st.info("🔮 Forecast mode")
        elif not is_active: st.warning("Off-season / Fallow")

    if not data_ok:
        st.error(f"**Could not load weather data.**\n\nError: `{weather_error or 'empty API response'}`\n\nCheck your internet connection, or try a different location.")
        st.stop()

    # Slice to assessment date.
    # Three branches:
    #   forecast mode  -> df_weather + df_forecast
    #   hindsight mode -> dedicated archive window ending on the past date
    #   present mode   -> df_weather as-is
    a_dt = pd.Timestamp(assessment_date)
    hindsight_error = None
    if is_fc_mode and df_forecast is not None and not df_forecast.empty:
        df_all = pd.concat([df_weather, df_forecast], ignore_index=True)
        df_slice = df_all[df_all["date"] <= a_dt]
    elif is_hindsight:
        with st.spinner(f"Loading ERA5 archive for {assessment_date}…"):
            try:
                df_slice = _cached_window(_lat_r, _lon_r,
                                          a_dt.strftime("%Y-%m-%d"), 120)
            except Exception as e:
                hindsight_error = str(e)
                df_slice = df_weather[df_weather["date"] <= a_dt]   # graceful fallback
    else:
        df_slice = df_weather[df_weather["date"] <= a_dt]

    # In past-date mode, score amplification & summary should use the ENSO state
    # at THAT TIME, not today's. Look up the historical ONI for the picked month.
    score_oni_v = oni_v
    score_oni   = oni
    if is_past_mode:
        try:
            _oni_hist_for_past = _cached_oni_history()
            _past_oni = _oni_hist_for_past.get((a_dt.year, a_dt.month))
            if _past_oni is None:
                # try previous month if very early in current month
                _past_oni = _oni_hist_for_past.get((a_dt.year, max(1, a_dt.month - 1)))
            if _past_oni is not None:
                from ensa.ingest.enso import classify_oni
                score_oni_v = float(round(_past_oni, 2))
                score_oni = {
                    "value": score_oni_v,
                    "phase": classify_oni(_past_oni),
                    "year": a_dt.year, "month": a_dt.month,
                    "month_name": a_dt.strftime("%B"),
                    "source": "NOAA CPC NINO3.4 (historical)",
                }
        except Exception:
            pass

    assessment = compute_drought_score(df_slice, score_oni_v, crop_stage, is_active)
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
        st.pyplot(_gauge(score, color), use_container_width=True)
        st.markdown(f"<div style='text-align:center;color:{color};font-weight:700;font-size:1.1rem'>{emoji} {level}</div>", unsafe_allow_html=True)

    with col_summary:
        if is_past_mode:
            summary_text = generate_summary_past(
                assessment, crop_choice, crop_stage, score_oni["phase"],
                st.session_state.preset_name,
                assessment_date.strftime("%d %B %Y"))
            if score_oni is not oni:
                st.caption(
                    f"📅 ENSO state at the time: "
                    f"NINO3.4 was {score_oni['value']:+.2f}°C ({score_oni['phase']})."
                )
        else:
            summary_text = generate_summary(
                assessment, crop_choice, crop_stage, score_oni["phase"],
                st.session_state.preset_name)
        st.markdown(f"<p style='font-size:1.05rem;line-height:1.7;color:#1F2937'>{summary_text}</p>",
                    unsafe_allow_html=True)

        if satisfaction_pct is not None:
            bar_color = "#ef4444" if satisfaction_pct < 50 else ("#f59e0b" if satisfaction_pct < 80 else "#22c55e")
            bar_w = min(100, satisfaction_pct)
            sat_label = ("Crop Water Needs Met (90 days ending the picked date)"
                         if is_past_mode else "Crop Water Needs Met (last 90 days)")
            verb_recv = "Rain that fell" if is_past_mode else "Rain received"
            verb_need = "Crop needed"
            verb_met  = "% met"
            st.markdown(
                f"<div style='margin-top:14px'>"
                f"<div class='kpi-label'>{sat_label}</div>"
                f"<div class='sat-bar-wrap'><div class='sat-bar-fill' style='width:{bar_w:.0f}%;background:{bar_color}'></div></div>"
                f"<div style='font-size:.85rem;color:#6B7280'>"
                f"{verb_recv}: <b style='color:#111827'>{precip_90:.0f} mm</b> · "
                f"{verb_need}: <b style='color:#111827'>{needed:.0f} mm</b> · "
                f"<b style='color:{bar_color}'>{satisfaction_pct:.0f}{verb_met}</b></div>"
                f"</div>", unsafe_allow_html=True)

    # ── CROP CALENDAR STRIP ──────────────────────────────────────────────
    st.subheader("📅 Crop Growth Calendar")
    st.caption("Green = growing · Red = critical water stage · Orange = harvesting · Dark = fallow. Border = current month.")
    st.pyplot(_crop_calendar_strip(cal, a_month), use_container_width=True)

    # ── HINDSIGHT PANEL  (only when user picks a past date > 7 days ago) ─
    if is_past_mode:
        if hindsight_error:
            st.warning(f"Could not fetch the historical archive window: "
                       f"{hindsight_error}. Showing best-effort comparison below.")
        st.subheader(f"🕰️ Hindsight: {assessment_date.strftime('%d %b %Y')} at "
                     f"{st.session_state.preset_name}")
        st.caption(
            "Comparing what the **observed weather** (ERA5 reanalysis) "
            "actually recorded around that date against two baselines: the "
            "**climatology** (40-year average for the same calendar window) "
            "and the **ENSO-conditional baseline** (mean of past seasons whose "
            "ENSO phase matched the one in effect on that date).")

        try:
            df_clim_hist = _cached_climatology(_lat_r, _lon_r)
            oni_hist     = _cached_oni_history()
            hs = hindsight_compare(df_clim_hist, df_slice, oni_hist, a_dt, window_days=90)
        except Exception as e:
            hs = {"ok": False, "reason": str(e)}

        if not hs.get("ok"):
            st.warning(f"Hindsight comparison unavailable: {hs.get('reason', 'unknown')}")
        else:
            enso_then = hs["enso_then"]
            phase     = enso_then["phase"]
            ph_color  = {"El Nino": "#F0883E", "La Nina": "#58A6FF",
                         "Neutral": "#8B949E", "Unknown": "#8B949E"}.get(phase, "#8B949E")

            # ENSO state on that date
            st.markdown(
                f"<div style='display:flex;gap:10px;align-items:center;margin-bottom:14px'>"
                f"<span style='font-size:.74rem;color:#8B949E;"
                f"text-transform:uppercase;letter-spacing:.1em'>ENSO state on that date</span>"
                f"<span style='background:{ph_color}22;color:{ph_color};"
                f"border:1px solid {ph_color}55;padding:3px 10px;border-radius:6px;"
                f"font-size:.82rem;font-weight:700'>"
                f"{phase} · NINO3.4 "
                f"{enso_then['value']:+.2f}°C</span>"
                f"</div>", unsafe_allow_html=True)

            # 3 stat tiles: observed / climatology / ENSO-conditional
            cA, cB, cC = st.columns(3)
            with cA:
                st.markdown(
                    f"<div class='kpi-tile' style='border-top-color:#15803D'>"
                    f"<div class='kpi-label' style='color:#3FB950'>OBSERVED (ERA5)</div>"
                    f"<div class='kpi-value' style='color:#3FB950'>"
                    f"{hs['observed_precip']:.0f} mm</div>"
                    f"<div class='kpi-sub'>over 90 days ending {hs['target_date']}</div>"
                    f"</div>", unsafe_allow_html=True)
            with cB:
                d = hs["delta_vs_clim"]
                d_col = "#F0883E" if d < -20 else ("#3FB950" if d > 20 else "#8B949E")
                st.markdown(
                    f"<div class='kpi-tile' style='border-top-color:#15803D'>"
                    f"<div class='kpi-label'>CLIMATOLOGY (naive forecast)</div>"
                    f"<div class='kpi-value'>{hs['climatology_precip']:.0f} mm</div>"
                    f"<div class='kpi-sub'>40-yr avg for same window · "
                    f"<span style='color:{d_col}'>"
                    f"observed was {d:+.0f} mm vs this</span></div>"
                    f"</div>", unsafe_allow_html=True)
            with cC:
                if hs["enso_conditional_precip"] is not None:
                    e_d = hs["delta_vs_enso"]
                    e_col = "#F0883E" if e_d < -20 else ("#3FB950" if e_d > 20 else "#8B949E")
                    st.markdown(
                        f"<div class='kpi-tile' style='border-top-color:{ph_color}'>"
                        f"<div class='kpi-label' style='color:{ph_color}'>"
                        f"ENSO-AWARE FORECAST</div>"
                        f"<div class='kpi-value'>{hs['enso_conditional_precip']:.0f} mm</div>"
                        f"<div class='kpi-sub'>avg of past {phase} years · "
                        f"<span style='color:{e_col}'>"
                        f"observed was {e_d:+.0f} mm vs this</span></div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    st.markdown(
                        f"<div class='kpi-tile' style='opacity:.55'>"
                        f"<div class='kpi-label'>ENSO-AWARE FORECAST</div>"
                        f"<div class='kpi-value' style='font-size:.95rem;color:#484F58'>"
                        f"Insufficient data</div>"
                        f"<div class='kpi-sub'>not enough {phase} years in record</div>"
                        f"</div>", unsafe_allow_html=True)

            # Verdict
            skill = hs.get("enso_skill_pct")
            verdict_md = ""
            if skill is None:
                verdict_md = (
                    f"For this 90-day window ending **{hs['target_date']}**, ERA5 recorded "
                    f"**{hs['observed_precip']:.0f} mm** of rain. "
                    f"The long-term climatology for the same calendar window is "
                    f"**{hs['climatology_precip']:.0f} mm** "
                    f"({hs['delta_vs_clim']:+.0f} mm difference). "
                    f"ENSO phase at the time was **{phase}**."
                )
            elif skill > 20:
                verdict_md = (
                    f"**Knowing it was {phase} would have helped.** "
                    f"The ENSO-aware forecast (**{hs['enso_conditional_precip']:.0f} mm**) "
                    f"was {abs(skill):.0f}% closer to what actually happened "
                    f"(**{hs['observed_precip']:.0f} mm**) than the naive climatology "
                    f"(**{hs['climatology_precip']:.0f} mm**)."
                )
            elif skill < -20:
                verdict_md = (
                    f"**ENSO didn't help much here.** Despite {phase} conditions, the actual "
                    f"observed rainfall was closer to the long-term climatology than to "
                    f"the typical {phase} signal. Other factors dominated this season."
                )
            else:
                verdict_md = (
                    f"**ENSO had marginal predictive value** for this season. "
                    f"The ENSO-aware forecast was within ~{abs(skill):.0f}% skill of "
                    f"the naive climatology baseline."
                )
            st.markdown(
                f"<div class='insight' style='margin-top:14px;font-size:.93rem'>{verdict_md}</div>",
                unsafe_allow_html=True)


    # ── 5 METRIC CARDS ──────────────────────────────────────────────────
    opt_t_lo, opt_t_hi = cal["optimal_temp"]
    kpi_label_period = (f"around {assessment_date.strftime('%d %b %Y')}"
                        if is_past_mode else "last 90 days")
    st.markdown(f"### Key Indicators ({kpi_label_period} — real ERA5 data)")
    m1, m2, m3, m4, m5 = st.columns(5)

    def _kpi(col, label, val, sub, ok):
        dot = "🟢" if ok else "🔴"
        col.markdown(f"<div class='kpi-tile'><div class='kpi-label'>{label}</div>"
                     f"<div class='kpi-value'>{val}</div>"
                     f"<div class='kpi-sub'>{dot} {sub}</div></div>", unsafe_allow_html=True)

    _kpi(m1, "Rainfall (90d)", f"{precip_90:.0f} mm",
         f"Need over 90 days: {cal['daily_demand_mm']*90:.0f} mm",
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
            "<div class='kpi-tile' style='opacity:.55'>"
            "<div class='kpi-label'>Soil Moisture</div>"
            "<div class='kpi-value' style='font-size:.95rem;color:#484F58'>Unavailable</div>"
            "<div class='kpi-sub'>ERA5 soil layer fetch failed</div></div>",
            unsafe_allow_html=True)

    # ── RECOMMENDATIONS / OBSERVATIONS ──────────────────────────────────
    if is_past_mode:
        st.markdown(f"### 📋 What was observed on {assessment_date.strftime('%d %b %Y')}")
        st.caption("Evidence-based observations of what likely happened to the "
                   "crop during this 90-day window. No live action items — this "
                   "is a historical analysis.")
        for obs in generate_observations_past(
                assessment, crop_choice, crop_stage, score_oni_v,
                assessment_date.strftime("%d %B %Y")):
            st.markdown(f"<div class='rec-item'>{obs}</div>", unsafe_allow_html=True)
    else:
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
                           generate_summary(assessment, crop_choice, crop_stage, score_oni["phase"],
                                            st.session_state.preset_name),
                           f'{{"score":{score},"level":"{level}","oni":{score_oni_v}}}'))
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
        # Historical analysis mode: anchor charts on the user's picked date
        # using the previously computed df_slice (which is either df_weather
        # or a dedicated archive window for older dates).
        if is_past_mode:
            st.markdown(
                f"<div style='background:#FFFFFF;border-left:3px solid #58A6FF;"
                f"padding:10px 16px;border-radius:6px;margin-bottom:14px;"
                f"font-size:.88rem;color:#374151'>"
                f"🕰️ Showing the 90 days ending on "
                f"<b style='color:#111827'>{assessment_date.strftime('%d %B %Y')}</b>"
                f" (historical analysis).</div>",
                unsafe_allow_html=True)
            df_hist_source = df_slice
        else:
            df_hist_source = df_weather

        df90 = df_hist_source.tail(90)
        t_lo, t_hi = cal["optimal_temp"]

        # ── Pre-compute insights ─────────────────────────────────────────
        df_m = df_hist_source.tail(180).copy() if len(df_hist_source) >= 180 else df_hist_source.copy()
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
        st.subheader("Monthly Rainfall vs Crop Water Requirement")
        c_chart, c_insight = st.columns([3, 2])
        with c_chart:
            fig_m = _monthly_bar_chart(df_m, cal["daily_demand_mm"], cal)
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

        # ── SECTION 2: Water balance ─────────────────────────────────────
        st.subheader("Cumulative Water Balance — Last 90 Days")
        c_chart2, c_insight2 = st.columns([3, 2])
        with c_chart2:
            fig_wb = _water_balance_chart(df_hist_source)
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

        # ── SECTION 3: Temperature + Rain side-by-side ───────────────────
        col_t_chart, col_r_chart = st.columns(2)

        with col_t_chart:
            st.subheader("Temperature — 90 Days")
            fig_t, ax_t = plt.subplots(figsize=(5, 2.4), facecolor="none")
            ax_t.plot(df90["date"], df90["temp_c"], color="#C2410C", linewidth=1.5, zorder=3)
            ax_t.axhspan(t_lo, t_hi, alpha=0.10, color="#15803D",
                         label=f"Optimal {t_lo}–{t_hi}°C", zorder=2)
            ax_t.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_t.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
            _ax_style(ax_t)
            ax_t.set_ylabel("°C", color="#6B7280", fontsize=8)
            ax_t.legend(facecolor="#FFFFFF", edgecolor="#E5E7EB", labelcolor="#1F2937", fontsize=7)
            st.pyplot(fig_t, use_container_width=True); plt.close(fig_t)
            heat_note = (f"🌡️ **{days_above_opt} days** above the {t_hi}°C optimum — "
                         f"elevated evaporation stress." if days_above_opt > 5 else
                         f"Temperature has stayed mostly within the optimal range for {crop_choice}.")
            st.caption(heat_note)

        with col_r_chart:
            st.subheader("Daily Rain — 90 Days")
            fig_r, ax_r = plt.subplots(figsize=(5, 2.4), facecolor="none")
            ax_r.bar(df90["date"], df90["precip_mm"], color="#1E40AF", alpha=0.78, width=0.9, zorder=2)
            ax_r.axhline(cal["daily_demand_mm"], color="#003D5C", linestyle="--",
                         linewidth=1.3, label=f"Daily need ({cal['daily_demand_mm']} mm)", zorder=3)
            ax_r.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_r.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
            _ax_style(ax_r)
            ax_r.set_ylabel("mm", color="#6B7280", fontsize=8)
            ax_r.legend(facecolor="#FFFFFF", edgecolor="#E5E7EB", labelcolor="#1F2937", fontsize=7)
            st.pyplot(fig_r, use_container_width=True); plt.close(fig_r)
            st.caption(f"**{dry_days_90}** days with less than 1 mm of rain in the last 90 days.")

        # ── Soil moisture section ───────────────────────────────────────
        if df_soil is not None and not df_soil.empty:
            st.subheader("Soil Moisture — last 120 days (ERA5 volumetric)")
            c_sm_chart, c_sm_txt = st.columns([3, 2])

            with c_sm_chart:
                fig_sm, ax_sm = plt.subplots(figsize=(8, 2.6), facecolor="none")
                ax_sm.plot(df_soil["date"], df_soil["soil_surface"] * 100,
                           color="#B45309", linewidth=1.5, label="Surface 0–7 cm", zorder=2)
                ax_sm.plot(df_soil["date"], df_soil["soil_root"] * 100,
                           color="#1E40AF", linewidth=1.7, label="Root-zone 7–28 cm", zorder=3)
                # Reference threshold band — below ~18% root-zone moisture is dryland stress
                ax_sm.axhspan(0, 18, alpha=0.10, color="#C2410C",
                              label="Root-zone stress (< 18%)")
                ax_sm.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
                ax_sm.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
                _ax_style(ax_sm)
                ax_sm.set_ylabel("% volumetric", color="#6B7280", fontsize=8)
                ax_sm.legend(facecolor="#FFFFFF", edgecolor="#E5E7EB",
                             labelcolor="#1F2937", fontsize=7, loc="upper right")
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


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: 14-DAY FORECAST
# ═══════════════════════════════════════════════════════════════════════════
with tab_fc:
    if is_past_mode:
        st.markdown(
            f"<div style='background:#FFFFFF;border:1px solid #E5E7EB;"
            f"border-radius:10px;padding:30px;text-align:center;margin-top:20px'>"
            f"<div style='font-size:2.5rem;margin-bottom:10px'>🚫</div>"
            f"<div style='color:#374151;font-size:1.05rem;margin-bottom:6px'>"
            f"<b>Forecast not applicable for historical dates</b></div>"
            f"<div style='color:#6B7280;font-size:.92rem;line-height:1.5;max-width:520px;"
            f"margin:0 auto'>"
            f"You are analysing <b style='color:#111827'>{assessment_date.strftime('%d %B %Y')}</b>"
            f" — a past date. A 14-day forecast only makes sense from today forward.<br><br>"
            f"To see the live 14-day forecast for your farm location, set the Assessment "
            f"Date back to today.</div></div>",
            unsafe_allow_html=True)
    elif df_forecast is None or df_forecast.empty:
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

        # ── Cumulative balance + analysis ─────────────────────────────────
        st.subheader("Cumulative Water Balance — Next 14 Days")
        c_cum, c_cum_txt = st.columns([3, 2])
        with c_cum:
            fig_cumfc, ax_cumfc = plt.subplots(figsize=(6, 2.4), facecolor="none")
            ax_cumfc.plot(df_forecast["date"], cum_fc, color="#1F2937", linewidth=1.6, zorder=3)
            ax_cumfc.fill_between(df_forecast["date"], cum_fc, 0,
                                  where=(cum_fc < 0), color="#C2410C", alpha=0.18, label="Deficit", zorder=2)
            ax_cumfc.fill_between(df_forecast["date"], cum_fc, 0,
                                  where=(cum_fc >= 0), color="#15803D", alpha=0.16, label="Surplus", zorder=2)
            ax_cumfc.axhline(0, color="#E5E7EB", linewidth=1)
            ax_cumfc.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_cumfc.xaxis.set_major_locator(mdates.DayLocator(interval=3))
            _ax_style(ax_cumfc)
            ax_cumfc.set_ylabel("mm", color="#6B7280", fontsize=8)
            ax_cumfc.legend(facecolor="#FFFFFF", edgecolor="#E5E7EB", labelcolor="#1F2937", fontsize=7)
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


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: EL NIÑO IMPACT — this location's history, El Niño vs Neutral years
# ═══════════════════════════════════════════════════════════════════════════
with tab_elnino:
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
                f"<div style='background:#FFFFFF;border:1px solid {hl_col};border-radius:6px;"
                f"padding:14px 20px;margin:10px 0'>"
                f"<div style='font-size:.66rem;color:#475569;text-transform:uppercase;"
                f"letter-spacing:.1em;margin-bottom:6px;font-weight:600'>Climatological Signal</div>"
                f"<div style='font-size:1rem;color:#0F172A;line-height:1.6'>{hl_emoji} {hl_msg}</div>"
                f"<div style='font-size:.78rem;color:#6B7280;margin-top:6px'>"
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
                        f"<div class='kpi-tile'>"
                        f"<div style='font-size:.66rem;text-transform:uppercase;letter-spacing:.1em;"
                        f"color:{color};font-weight:600;margin-bottom:6px'>{ph_key} Years</div>"
                        f"<div style='font-size:1.7rem;font-weight:700;color:#0F172A;line-height:1'>"
                        f"{ph['mean_precip']:.0f} mm</div>"
                        f"<div style='font-size:.77rem;color:#475569;margin-top:4px'>"
                        f"Avg season rainfall · {ph['n_years']} years · {ph['mean_temp']:.1f}°C</div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    col.markdown(
                        f"<div class='kpi-tile' style='opacity:.5'>"
                        f"<div style='font-size:.66rem;text-transform:uppercase;letter-spacing:.1em;"
                        f"color:#475569;font-weight:600;margin-bottom:6px'>{ph_key} Years</div>"
                        f"<div style='color:#6B7280;font-size:.85rem'>No years in record</div>"
                        f"</div>", unsafe_allow_html=True)

        # ── Per-year chart ──────────────────────────────────────────────
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
        ], facecolor="#FFFFFF", edgecolor="#E5E7EB", labelcolor="#1F2937",
           fontsize=7, ncol=4, loc="upper right")
        st.pyplot(fig_y, use_container_width=True); plt.close(fig_y)

        # ── What this means for this season ─────────────────────────────
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


    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 5: METHODOLOGY
    # ═══════════════════════════════════════════════════════════════════════════
    with tab_about:
        st.subheader("Data Sources — All Real, All Free")
        st.markdown("""
        | Source | Variable | Update |
        |--------|----------|--------|
        | **Open-Meteo ERA5 archive** | Daily rainfall (mm), mean temperature (°C), FAO-56 reference evapotranspiration ET₀ (mm), volumetric soil moisture (0–7 cm and 7–28 cm) | Daily, 5-day lag |
        | **Open-Meteo Forecast** | 14-day precipitation, temperature, ET₀ | Daily |
        | **NOAA CPC NINO3.4** | Monthly Oceanic Niño Index (SST anomaly) | Monthly |
        | **FAO / USDA / IRRI crop calendars** | Region-specific growing windows, water requirements, critical stages | Static (literature-grounded) |

        All four sources are free and require no registration or API key.
        No simulated or fallback values are shown — if a data source is offline the dashboard shows an error.

        > **A note on "Sentinel":** The name *El Niño **Sentinel** Agent* uses "Sentinel" in the
        > classical sense of *watcher / early-warning guard*. **This dashboard does not currently
        > use Sentinel-2 satellite imagery.** Real-time NDVI from the Sentinel-2 / Microsoft
        > Planetary Computer STAC is on the roadmap for a future release.
        """)

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
