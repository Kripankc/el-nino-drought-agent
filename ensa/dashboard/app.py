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

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

*{font-family:'Plus Jakarta Sans',-apple-system,sans-serif!important;}

/* ── App shell ────────────────────────────────── */
.stApp{
  background:radial-gradient(ellipse 90% 55% at 8% 0%,#061a0c 0%,#020905 52%,#010302 100%);
  color:#e2ede6;
}
#MainMenu,footer,.stDeployButton{display:none!important;}

/* ── Sidebar ────────────────────────────────────── */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#040e07 0%,#020803 100%)!important;
  border-right:1px solid rgba(52,211,153,.1)!important;
}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label{color:#6aab80!important;font-size:.84rem!important;}
[data-testid="stSidebar"] h2{color:#34d399!important;font-weight:800!important;}
[data-testid="stSidebar"] h3{color:#6ee7b7!important;font-size:.74rem!important;
  text-transform:uppercase!important;letter-spacing:.09em!important;}

/* ── Typography ─────────────────────────────────── */
h1,h2,h3,h4{color:#ecfdf5!important;font-weight:700!important;letter-spacing:-.025em!important;}
p,.stMarkdown p{color:#a7c4b0!important;}

/* ── Base card ───────────────────────────────────── */
.card{
  background:linear-gradient(135deg,rgba(10,38,20,.88) 0%,rgba(4,12,7,.94) 100%);
  border:1px solid rgba(52,211,153,.13);
  border-radius:18px;padding:22px 26px;margin-bottom:16px;
  box-shadow:0 2px 20px rgba(0,0,0,.5);
  transition:border-color .2s;
}
.card:hover{border-color:rgba(52,211,153,.24);}

/* ── Hero risk band ──────────────────────────────── */
.hero{border-radius:20px;padding:28px 32px;margin-bottom:20px;
  border:1px solid rgba(255,255,255,.08);position:relative;overflow:hidden;}
.hero-score{font-size:4.8rem;font-weight:800;line-height:1;letter-spacing:-.05em;}
.hero-level{font-size:1.25rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;}
.hero-summary{font-size:.97rem;line-height:1.7;color:rgba(255,255,255,.78);
  margin-top:10px;max-width:660px;}
.hero-glow{position:absolute;top:-60px;right:-60px;width:280px;height:280px;
  border-radius:50%;filter:blur(80px);opacity:.25;pointer-events:none;}

/* ── KPI grid ───────────────────────────────────── */
.kpi{background:rgba(8,30,16,.75);border:1px solid rgba(52,211,153,.12);
  border-radius:14px;padding:16px 18px;text-align:center;
  transition:border-color .2s,transform .15s;}
.kpi:hover{border-color:rgba(52,211,153,.28);transform:translateY(-2px);}
.kpi-icon{font-size:1.5rem;margin-bottom:5px;display:block;}
.kpi-lbl{font-size:.68rem;color:#52a874;text-transform:uppercase;
  letter-spacing:.08em;margin-bottom:3px;}
.kpi-val{font-size:1.6rem;font-weight:700;color:#ecfdf5;line-height:1.1;}
.kpi-sub{font-size:.76rem;color:#5a8a6e;margin-top:3px;}
.kpi-ok  {border-color:rgba(52,211,153,.28)!important;}
.kpi-warn{border-color:rgba(251,191,36,.28)!important;}
.kpi-bad {border-color:rgba(248,113,113,.28)!important;}

/* ── Recommendation card ────────────────────────── */
.rec{border-radius:12px;padding:13px 17px;margin-bottom:9px;
  border-left:3px solid;font-size:.91rem;line-height:1.65;}
.rec b{color:#ecfdf5;}
.rec-crit{border-left-color:#ef4444;background:rgba(239,68,68,.07);}
.rec-warn{border-left-color:#fbbf24;background:rgba(251,191,36,.07);}
.rec-info{border-left-color:#34d399;background:rgba(52,211,153,.07);}

/* ── Water satisfaction bar ─────────────────────── */
.sat-wrap{background:rgba(255,255,255,.07);border-radius:7px;
  height:14px;overflow:hidden;margin:6px 0 3px;}
.sat-fill{height:100%;border-radius:7px;}

/* ── Insight box ─────────────────────────────────── */
.insight{background:rgba(6,22,12,.7);border:1px solid rgba(52,211,153,.12);
  border-radius:14px;padding:18px 20px;font-size:.88rem;line-height:1.7;color:#8fbfa2;}
.insight b{color:#ecfdf5;}
.istat{font-size:1.7rem;font-weight:700;color:#34d399;line-height:1.1;display:block;}
.istat-lbl{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;
  color:#52a874;display:block;margin-bottom:8px;}

/* ── Tabs ────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"]{
  gap:3px;background:rgba(8,30,16,.6);border-radius:13px;
  padding:4px;border:1px solid rgba(52,211,153,.12);}
.stTabs [data-baseweb="tab"]{border-radius:9px;color:#52a874;
  font-weight:600;font-size:.86rem;padding:7px 18px;
  background:transparent!important;border:none!important;}
.stTabs [aria-selected="true"]{
  background:rgba(52,211,153,.14)!important;
  color:#34d399!important;border-bottom:none!important;}

/* ── Section heading ─────────────────────────────── */
.sec-head{font-size:.68rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.11em;color:#34d399;margin-bottom:8px;}

/* ── Inputs ─────────────────────────────────────── */
.stSelectbox>div>div,.stNumberInput input,.stDateInput input{
  background:rgba(8,30,16,.8)!important;
  border-color:rgba(52,211,153,.18)!important;
  color:#ecfdf5!important;border-radius:10px!important;}
.stButton button{
  background:linear-gradient(135deg,#065f34 0%,#047a43 100%)!important;
  color:#ecfdf5!important;border:1px solid rgba(52,211,153,.3)!important;
  border-radius:10px!important;font-weight:600!important;}
.stButton button:hover{background:linear-gradient(135deg,#047a43 0%,#059955 100%)!important;}
.stAlert{border-radius:12px!important;}

/* ── Scrollbar ────────────────────────────────────── */
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-track{background:#020803;}
::-webkit-scrollbar-thumb{background:rgba(52,211,153,.25);border-radius:3px;}
::-webkit-scrollbar-thumb:hover{background:rgba(52,211,153,.45);}

/* ── Caption / helper text ─────────────────────────── */
.stCaption{color:#466b57!important;font-size:.77rem!important;}
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


# ─────────────────────────────────────────────────────────────────────────────
# CROP CALENDARS  (literature-backed, no fallback values)
# daily_demand_mm = average FAO crop water requirement during active season
# optimal_temp    = (min, max) °C for healthy growth
# ─────────────────────────────────────────────────────────────────────────────
CROP_CALENDARS = {
    "Nepal": {
        "Kharif Rice": {
            "start":11,"end":5,"daily_demand_mm":6.0,"optimal_temp":(22,30),
            "stages":{6:"Nursery",7:"Transplanting",8:"Tillering",
                      9:"Flowering (Critical)",10:"Grain Filling",11:"Harvesting",
                      12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow",5:"Fallow"},
        },
        "Winter Wheat (Rabi)": {
            "start":11,"end":4,"daily_demand_mm":4.0,"optimal_temp":(10,22),
            "stages":{11:"Sowing",12:"Germination",1:"Tillering",
                      2:"Jointing",3:"Heading & Flowering (Critical)",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Spring Maize": {
            "start":3,"end":8,"daily_demand_mm":4.5,"optimal_temp":(18,26),
            "stages":{3:"Planting",4:"Emergence",5:"Vegetative",
                      6:"Tasseling (Critical)",7:"Grain Filling",8:"Harvesting",
                      9:"Fallow",10:"Fallow",11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow"},
        },
        "Finger Millet": {
            "start":6,"end":10,"daily_demand_mm":3.5,"optimal_temp":(20,30),
            "stages":{6:"Planting",7:"Vegetative",8:"Flowering (Critical)",
                      9:"Grain Filling",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow",5:"Fallow"},
        },
    },
    "India": {
        "Kharif Rice": {
            "start":6,"end":11,"daily_demand_mm":7.5,"optimal_temp":(25,33),
            "stages":{6:"Nursery & Transplanting",7:"Tillering",8:"Panicle Initiation",
                      9:"Flowering (Critical)",10:"Grain Filling",11:"Harvesting",
                      12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow",5:"Fallow"},
        },
        "Rabi Wheat": {
            "start":11,"end":4,"daily_demand_mm":4.2,"optimal_temp":(12,22),
            "stages":{11:"Sowing",12:"Crown Root Initiation",1:"Tillering",
                      2:"Jointing",3:"Heading & Flowering (Critical)",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Cotton (Kharif)": {
            "start":5,"end":12,"daily_demand_mm":5.5,"optimal_temp":(25,35),
            "stages":{5:"Sowing",6:"Seedling",7:"Squaring",8:"Flowering (Critical)",
                      9:"Boll Development (Critical)",10:"Boll Opening",11:"Picking",12:"Harvesting",
                      1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Sugarcane": {
            "start":2,"end":1,"daily_demand_mm":6.0,"optimal_temp":(24,32),
            "stages":{2:"Planting",3:"Germination",4:"Tillering",5:"Grand Growth",
                      6:"Grand Growth",7:"Grand Growth (Critical)",8:"Grand Growth (Critical)",
                      9:"Maturation",10:"Maturation",11:"Harvesting",12:"Harvesting",1:"Harvesting"},
        },
        "Groundnut (Kharif)": {
            "start":6,"end":10,"daily_demand_mm":4.0,"optimal_temp":(25,35),
            "stages":{6:"Sowing",7:"Vegetative",8:"Flowering & Pegging (Critical)",
                      9:"Pod Development (Critical)",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow",5:"Fallow"},
        },
    },
    "Pakistan": {
        "Kharif Cotton": {
            "start":5,"end":12,"daily_demand_mm":5.5,"optimal_temp":(26,36),
            "stages":{5:"Sowing",6:"Seedling",7:"Squaring",8:"Flowering (Critical)",
                      9:"Boll Development (Critical)",10:"Boll Opening",11:"Picking",12:"Harvesting",
                      1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Rabi Wheat": {
            "start":11,"end":4,"daily_demand_mm":4.0,"optimal_temp":(10,22),
            "stages":{11:"Sowing",12:"Germination",1:"Tillering",
                      2:"Jointing",3:"Heading & Flowering (Critical)",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Kharif Rice (Basmati)": {
            "start":6,"end":10,"daily_demand_mm":7.0,"optimal_temp":(24,32),
            "stages":{6:"Nursery",7:"Transplanting",8:"Vegetative",
                      9:"Flowering (Critical)",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow",5:"Fallow"},
        },
        "Sugarcane": {
            "start":3,"end":2,"daily_demand_mm":5.5,"optimal_temp":(22,32),
            "stages":{3:"Planting",4:"Germination",5:"Tillering",6:"Grand Growth",
                      7:"Grand Growth (Critical)",8:"Grand Growth (Critical)",9:"Maturation",
                      10:"Maturation",11:"Harvesting",12:"Harvesting",1:"Harvesting",2:"Harvesting"},
        },
    },
    "Bangladesh": {
        "Aman Rice (Wet season)": {
            "start":6,"end":11,"daily_demand_mm":7.0,"optimal_temp":(25,33),
            "stages":{6:"Nursery",7:"Transplanting",8:"Vegetative",
                      9:"Panicle Initiation",10:"Flowering (Critical)",11:"Harvesting",
                      12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow",5:"Fallow"},
        },
        "Boro Rice (Dry season)": {
            "start":12,"end":5,"daily_demand_mm":8.0,"optimal_temp":(20,30),
            "stages":{12:"Nursery",1:"Transplanting",2:"Vegetative",
                      3:"Panicle Initiation",4:"Flowering (Critical)",5:"Harvesting",
                      6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow",11:"Fallow"},
        },
        "Wheat (Rabi)": {
            "start":11,"end":4,"daily_demand_mm":3.8,"optimal_temp":(12,22),
            "stages":{11:"Sowing",12:"Germination",1:"Tillering",
                      2:"Jointing",3:"Heading & Flowering (Critical)",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Jute": {
            "start":3,"end":8,"daily_demand_mm":5.0,"optimal_temp":(24,35),
            "stages":{3:"Sowing",4:"Seedling",5:"Vegetative",6:"Vegetative",
                      7:"Flowering",8:"Harvesting",
                      9:"Fallow",10:"Fallow",11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow"},
        },
    },
    "Myanmar": {
        "Monsoon Rice": {
            "start":5,"end":10,"daily_demand_mm":7.0,"optimal_temp":(24,32),
            "stages":{5:"Nursery",6:"Transplanting",7:"Vegetative",8:"Panicle Initiation",
                      9:"Flowering (Critical)",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Summer Sesame": {
            "start":3,"end":7,"daily_demand_mm":3.8,"optimal_temp":(26,35),
            "stages":{3:"Sowing",4:"Seedling",5:"Vegetative",6:"Flowering (Critical)",7:"Harvesting",
                      8:"Fallow",9:"Fallow",10:"Fallow",11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow"},
        },
    },
    "Southeast Asia": {
        "Wet Season Rice": {
            "start":5,"end":11,"daily_demand_mm":7.0,"optimal_temp":(24,33),
            "stages":{5:"Nursery",6:"Transplanting",7:"Vegetative",8:"Vegetative",
                      9:"Flowering (Critical)",10:"Grain Filling",11:"Harvesting",
                      12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Cassava": {
            "start":3,"end":12,"daily_demand_mm":4.0,"optimal_temp":(25,35),
            "stages":{3:"Planting",4:"Establishment",5:"Vegetative",6:"Vegetative (Critical)",
                      7:"Tuber Bulking (Critical)",8:"Tuber Bulking",9:"Maturation",
                      10:"Maturation",11:"Harvest Ready",12:"Harvesting",
                      1:"Fallow",2:"Fallow"},
        },
        "Sugarcane": {
            "start":1,"end":12,"daily_demand_mm":5.5,"optimal_temp":(24,33),
            "stages":{1:"Grand Growth",2:"Grand Growth",3:"Grand Growth (Critical)",
                      4:"Maturation",5:"Harvesting",6:"Planting / Ratoon",
                      7:"Germination",8:"Tillering",9:"Grand Growth",
                      10:"Grand Growth (Critical)",11:"Maturation",12:"Harvesting"},
        },
    },
    "China": {
        "Double-Crop Rice (1st)": {
            "start":4,"end":8,"daily_demand_mm":6.5,"optimal_temp":(23,30),
            "stages":{4:"Transplanting",5:"Tillering",6:"Panicle Initiation",
                      7:"Flowering (Critical)",8:"Harvesting",
                      9:"Fallow",10:"Fallow",11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow"},
        },
        "Winter Wheat": {
            "start":10,"end":6,"daily_demand_mm":4.5,"optimal_temp":(10,22),
            "stages":{10:"Sowing",11:"Germination",12:"Overwintering",
                      1:"Overwintering",2:"Returning Green",3:"Jointing",
                      4:"Heading",5:"Flowering (Critical)",6:"Harvesting",
                      7:"Fallow",8:"Fallow",9:"Fallow"},
        },
        "Summer Maize": {
            "start":6,"end":9,"daily_demand_mm":5.0,"optimal_temp":(22,30),
            "stages":{6:"Planting",7:"Vegetative",8:"Tasseling & Silking (Critical)",
                      9:"Grain Fill & Harvest",
                      10:"Fallow",11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow",5:"Fallow"},
        },
    },
    "East Africa": {
        "Maize (Long Rains)": {
            "start":3,"end":9,"daily_demand_mm":4.8,"optimal_temp":(18,26),
            "stages":{3:"Planting",4:"Vegetative",5:"Vegetative",
                      6:"Tasseling & Silking (Critical)",7:"Grain Filling",8:"Maturity",9:"Harvesting",
                      10:"Fallow",11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow"},
        },
        "Maize (Short Rains)": {
            "start":10,"end":2,"daily_demand_mm":4.8,"optimal_temp":(18,26),
            "stages":{10:"Planting",11:"Vegetative",12:"Tasseling (Critical)",
                      1:"Grain Filling",2:"Harvesting",
                      3:"Fallow",4:"Fallow",5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow"},
        },
        "Sorghum": {
            "start":4,"end":10,"daily_demand_mm":3.5,"optimal_temp":(22,32),
            "stages":{4:"Planting",5:"Vegetative",6:"Vegetative",7:"Flowering (Critical)",
                      8:"Grain Filling",9:"Maturity",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow"},
        },
        "Tea": {
            "start":1,"end":12,"daily_demand_mm":4.5,"optimal_temp":(15,25),
            "stages":{1:"Dormant",2:"Bud Burst",3:"Flush (Critical)",4:"Flush (Critical)",
                      5:"Flush (Critical)",6:"Flush",7:"Flush",8:"Flush (Critical)",
                      9:"Flush",10:"Flush",11:"Semi-dormant",12:"Dormant"},
        },
        "Coffee (Arabica)": {
            "start":3,"end":11,"daily_demand_mm":4.0,"optimal_temp":(15,24),
            "stages":{3:"Vegetative",4:"Vegetative",5:"Flowering (Critical)",6:"Fruit Set",
                      7:"Fruit Development (Critical)",8:"Fruit Development",9:"Ripening",
                      10:"Harvesting",11:"Harvesting",12:"Fallow",1:"Fallow",2:"Fallow"},
        },
    },
    "West Africa": {
        "Pearl Millet": {
            "start":5,"end":10,"daily_demand_mm":3.8,"optimal_temp":(25,35),
            "stages":{5:"Planting",6:"Vegetative",7:"Vegetative",8:"Flowering (Critical)",
                      9:"Grain Filling",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Sorghum": {
            "start":5,"end":10,"daily_demand_mm":4.0,"optimal_temp":(25,35),
            "stages":{5:"Planting",6:"Vegetative",7:"Vegetative",8:"Flowering (Critical)",
                      9:"Grain Filling",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Groundnut": {
            "start":5,"end":10,"daily_demand_mm":3.5,"optimal_temp":(25,35),
            "stages":{5:"Sowing",6:"Vegetative",7:"Flowering & Pegging (Critical)",
                      8:"Pod Development (Critical)",9:"Maturation",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Cowpea": {
            "start":6,"end":10,"daily_demand_mm":3.0,"optimal_temp":(25,35),
            "stages":{6:"Planting",7:"Vegetative",8:"Flowering (Critical)",
                      9:"Pod Filling",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow",5:"Fallow"},
        },
    },
    "Southern Africa": {
        "White Maize": {
            "start":11,"end":5,"daily_demand_mm":5.0,"optimal_temp":(20,28),
            "stages":{11:"Planting",12:"Emergence",1:"Vegetative",2:"Vegetative",
                      3:"Flowering & Tasseling (Critical)",4:"Grain Fill",5:"Harvesting",
                      6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Sorghum / Millet": {
            "start":12,"end":6,"daily_demand_mm":3.8,"optimal_temp":(24,32),
            "stages":{12:"Planting",1:"Vegetative",2:"Vegetative",3:"Vegetative",
                      4:"Flowering (Critical)",5:"Maturity",6:"Harvesting",
                      7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow",11:"Fallow"},
        },
        "Groundnut": {
            "start":11,"end":4,"daily_demand_mm":4.0,"optimal_temp":(22,32),
            "stages":{11:"Sowing",12:"Vegetative",1:"Flowering & Pegging (Critical)",
                      2:"Pod Development (Critical)",3:"Maturation",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Soybean": {
            "start":11,"end":4,"daily_demand_mm":4.5,"optimal_temp":(20,30),
            "stages":{11:"Planting",12:"Emergence",1:"Vegetative",
                      2:"Flowering (Critical)",3:"Pod Fill (Critical)",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Cassava": {
            "start":11,"end":10,"daily_demand_mm":3.5,"optimal_temp":(22,32),
            "stages":{11:"Planting",12:"Establishment (Critical)",1:"Vegetative (Critical)",
                      2:"Tuber Initiation",3:"Tuber Bulking (Critical)",4:"Tuber Bulking",
                      5:"Maturation",6:"Maturation",7:"Maturation",8:"Maturation",
                      9:"Harvest Ready",10:"Harvesting"},
        },
        "Tobacco (Flue-cured)": {
            "start":10,"end":3,"daily_demand_mm":4.5,"optimal_temp":(20,28),
            "stages":{10:"Nursery",11:"Transplanting",12:"Establishment",
                      1:"Grand Growth (Critical)",2:"Maturation",3:"Harvesting",
                      4:"Fallow",5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow"},
        },
    },
    # Use Southern Africa calendars for plain "Zambia" region too
    "Zambia": {
        "White Maize": {
            "start":11,"end":5,"daily_demand_mm":5.0,"optimal_temp":(20,28),
            "stages":{11:"Planting",12:"Emergence",1:"Vegetative",2:"Vegetative",
                      3:"Flowering & Tasseling (Critical)",4:"Grain Fill",5:"Harvesting",
                      6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Sorghum / Millet": {
            "start":12,"end":6,"daily_demand_mm":3.8,"optimal_temp":(24,32),
            "stages":{12:"Planting",1:"Vegetative",2:"Vegetative",3:"Vegetative",
                      4:"Flowering (Critical)",5:"Maturity",6:"Harvesting",
                      7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow",11:"Fallow"},
        },
        "Groundnut": {
            "start":11,"end":4,"daily_demand_mm":4.0,"optimal_temp":(22,32),
            "stages":{11:"Sowing",12:"Vegetative",1:"Flowering & Pegging (Critical)",
                      2:"Pod Development (Critical)",3:"Maturation",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Soybean": {
            "start":11,"end":4,"daily_demand_mm":4.5,"optimal_temp":(20,30),
            "stages":{11:"Planting",12:"Emergence",1:"Vegetative",
                      2:"Flowering (Critical)",3:"Pod Fill (Critical)",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
    },
    "Australia": {
        "Winter Wheat": {
            "start":5,"end":11,"daily_demand_mm":3.8,"optimal_temp":(10,20),
            "stages":{5:"Sowing",6:"Tillering",7:"Jointing",8:"Booting",
                      9:"Heading & Flowering (Critical)",10:"Grain Fill",11:"Harvesting",
                      12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Barley": {
            "start":5,"end":10,"daily_demand_mm":3.6,"optimal_temp":(12,22),
            "stages":{5:"Sowing",6:"Tillering",7:"Jointing",8:"Flowering (Critical)",
                      9:"Grain Filling",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow",4:"Fallow"},
        },
        "Canola": {
            "start":4,"end":10,"daily_demand_mm":3.5,"optimal_temp":(10,22),
            "stages":{4:"Sowing",5:"Emergence",6:"Vegetative",7:"Flowering (Critical)",
                      8:"Pod Fill (Critical)",9:"Maturation",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow"},
        },
        "Summer Sorghum": {
            "start":10,"end":4,"daily_demand_mm":4.0,"optimal_temp":(22,35),
            "stages":{10:"Planting",11:"Vegetative",12:"Vegetative",1:"Flowering (Critical)",
                      2:"Grain Fill",3:"Maturity",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow"},
        },
    },
    "South America": {
        "Soybean (Summer)": {
            "start":10,"end":3,"daily_demand_mm":5.0,"optimal_temp":(22,32),
            "stages":{10:"Planting",11:"Emergence",12:"Vegetative",
                      1:"Flowering (Critical)",2:"Pod Fill (Critical)",3:"Harvesting",
                      4:"Fallow",5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow"},
        },
        "Maize (Summer)": {
            "start":10,"end":4,"daily_demand_mm":5.5,"optimal_temp":(20,30),
            "stages":{10:"Planting",11:"Emergence",12:"Vegetative",
                      1:"Tasseling (Critical)",2:"Grain Fill",3:"Maturity",4:"Harvesting",
                      5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow"},
        },
        "Coffee (Arabica)": {
            "start":1,"end":12,"daily_demand_mm":4.5,"optimal_temp":(15,24),
            "stages":{1:"Dormant",2:"Flowering (Critical)",3:"Fruit Set",4:"Fruit Development",
                      5:"Fruit Development (Critical)",6:"Ripening",7:"Harvesting",
                      8:"Harvesting",9:"Post-Harvest",10:"Vegetative",11:"Vegetative",12:"Dormant"},
        },
    },
    "North Africa": {
        "Winter Wheat": {
            "start":11,"end":6,"daily_demand_mm":4.0,"optimal_temp":(10,22),
            "stages":{11:"Sowing",12:"Germination",1:"Tillering",2:"Jointing",
                      3:"Heading",4:"Flowering (Critical)",5:"Grain Fill",6:"Harvesting",
                      7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Barley": {
            "start":11,"end":5,"daily_demand_mm":3.5,"optimal_temp":(8,22),
            "stages":{11:"Sowing",12:"Germination",1:"Tillering",2:"Jointing",
                      3:"Heading",4:"Flowering (Critical)",5:"Harvesting",
                      6:"Fallow",7:"Fallow",8:"Fallow",9:"Fallow",10:"Fallow"},
        },
        "Olive": {
            "start":1,"end":12,"daily_demand_mm":2.0,"optimal_temp":(10,30),
            "stages":{1:"Dormant",2:"Bud Swell",3:"Flowering (Critical)",4:"Fruit Set",
                      5:"Fruit Growth",6:"Pit Hardening",7:"Fruit Development (Critical)",
                      8:"Ripening",9:"Ripening",10:"Harvesting",11:"Harvesting",12:"Dormant"},
        },
    },
    "Central Asia": {
        "Cotton": {
            "start":4,"end":10,"daily_demand_mm":5.5,"optimal_temp":(25,35),
            "stages":{4:"Sowing",5:"Emergence",6:"Squaring",7:"Flowering (Critical)",
                      8:"Boll Development (Critical)",9:"Boll Opening",10:"Picking",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow"},
        },
        "Winter Wheat": {
            "start":10,"end":7,"daily_demand_mm":4.0,"optimal_temp":(8,20),
            "stages":{10:"Sowing",11:"Germination",12:"Overwintering",1:"Overwintering",
                      2:"Returning Green",3:"Jointing",4:"Heading",
                      5:"Flowering (Critical)",6:"Grain Fill",7:"Harvesting",
                      8:"Fallow",9:"Fallow"},
        },
    },
    "Europe": {
        "Winter Wheat": {
            "start":10,"end":7,"daily_demand_mm":3.5,"optimal_temp":(8,20),
            "stages":{10:"Sowing",11:"Germination",12:"Overwintering",1:"Overwintering",
                      2:"Returning Green",3:"Jointing",4:"Heading",
                      5:"Flowering (Critical)",6:"Grain Fill",7:"Harvesting",
                      8:"Fallow",9:"Fallow"},
        },
        "Sunflower": {
            "start":4,"end":9,"daily_demand_mm":4.0,"optimal_temp":(18,28),
            "stages":{4:"Sowing",5:"Emergence",6:"Vegetative",7:"Flowering (Critical)",
                      8:"Seed Fill (Critical)",9:"Harvesting",
                      10:"Fallow",11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow"},
        },
        "Maize (Summer)": {
            "start":4,"end":10,"daily_demand_mm":4.5,"optimal_temp":(18,28),
            "stages":{4:"Sowing",5:"Emergence",6:"Vegetative",7:"Tasseling (Critical)",
                      8:"Grain Fill (Critical)",9:"Maturation",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow"},
        },
    },
    "Global": {
        "Generic Cereal": {
            "start":4,"end":10,"daily_demand_mm":4.5,"optimal_temp":(15,28),
            "stages":{4:"Planting",5:"Emergence",6:"Vegetative",7:"Flowering (Critical)",
                      8:"Grain Fill",9:"Maturation",10:"Harvesting",
                      11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow"},
        },
    },
    "Sri Lanka": {
        "Maha Rice (Main)": {
            "start":9,"end":3,"daily_demand_mm":7.0,"optimal_temp":(24,32),
            "stages":{9:"Nursery",10:"Transplanting",11:"Vegetative",12:"Panicle Initiation",
                      1:"Flowering (Critical)",2:"Grain Fill",3:"Harvesting",
                      4:"Fallow",5:"Fallow",6:"Fallow",7:"Fallow",8:"Fallow"},
        },
        "Yala Rice (Secondary)": {
            "start":4,"end":8,"daily_demand_mm":7.0,"optimal_temp":(26,34),
            "stages":{4:"Nursery",5:"Transplanting",6:"Vegetative",
                      7:"Flowering (Critical)",8:"Harvesting",
                      9:"Fallow",10:"Fallow",11:"Fallow",12:"Fallow",1:"Fallow",2:"Fallow",3:"Fallow"},
        },
        "Tea": {
            "start":1,"end":12,"daily_demand_mm":4.5,"optimal_temp":(16,24),
            "stages":{1:"Dormant",2:"Bud Burst",3:"Flush (Critical)",4:"Flush (Critical)",
                      5:"Flush",6:"Flush",7:"Flush (Critical)",8:"Flush (Critical)",
                      9:"Flush",10:"Flush",11:"Semi-dormant",12:"Dormant"},
        },
    },
}

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
    "Custom Point":            {"coords": [-16.25,  27.65]},
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — charts
# ─────────────────────────────────────────────────────────────────────────────

def _gauge(score, color):
    """Premium half-donut risk gauge."""
    fig, ax = plt.subplots(figsize=(3.4, 2.1), facecolor="none")
    ax.set_facecolor("none")
    # Track
    θ = np.linspace(np.pi, 0, 300)
    ax.plot(np.cos(θ), np.sin(θ), color="#0d2a18", linewidth=24, solid_capstyle="round", zorder=1)
    # Value arc
    if score > 0:
        θv = np.linspace(np.pi, np.pi - (min(score, 100)/100)*np.pi, 300)
        ax.plot(np.cos(θv), np.sin(θv), color=color, linewidth=24,
                solid_capstyle="round", alpha=0.92, zorder=2)
    # Score text
    ax.text(0, 0.16, f"{score:.0f}", ha="center", va="center",
            fontsize=40, fontweight="800", color="#ecfdf5", zorder=3,
            fontfamily="Plus Jakarta Sans")
    ax.text(0, -0.26, "out of 100", ha="center", va="center",
            fontsize=8, color="#52a874", zorder=3)
    ax.set_xlim(-1.45, 1.45); ax.set_ylim(-0.52, 1.45); ax.axis("off")
    return fig


def _ax_style(ax, xlabel_rotation=30):
    """Consistent premium chart style."""
    ax.set_facecolor("none")
    ax.tick_params(colors="#52a874", labelsize=7.5)
    ax.spines[:].set_visible(False)
    ax.grid(axis="y", color="#34d399", alpha=0.04, linewidth=0.5)
    plt.xticks(rotation=xlabel_rotation, ha="right")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color("#52a874")


# ── HTML component helpers ────────────────────────────────────────────────────

def _hero_html(score, level, color, emoji, summary, crop, stage, location,
               satisfaction_pct, received_mm, needed_mm):
    """Full-width hero card: risk score + summary + water bar."""
    _bg = {
        "Extreme": "rgba(120,20,20,.55)",
        "Severe":  "rgba(110,50,10,.55)",
        "Warning": "rgba(110,85,5,.5)",
        "Watch":   "rgba(20,50,100,.5)",
        "Normal":  "rgba(5,50,25,.55)",
    }.get(level, "rgba(5,50,25,.55)")

    bar_col = "#ef4444" if satisfaction_pct < 50 else ("#fbbf24" if satisfaction_pct < 80 else "#34d399")
    bar_w   = min(100, max(0, satisfaction_pct))
    sat_line = (
        f"<div style='margin-top:18px'>"
        f"<div style='font-size:.72rem;color:rgba(255,255,255,.5);text-transform:uppercase;"
        f"letter-spacing:.09em;margin-bottom:6px'>Crop water needs met — last 90 days</div>"
        f"<div style='background:rgba(255,255,255,.08);border-radius:7px;height:12px;overflow:hidden;max-width:480px'>"
        f"<div style='width:{bar_w:.0f}%;height:100%;background:{bar_col};border-radius:7px'></div></div>"
        f"<div style='font-size:.8rem;color:rgba(255,255,255,.5);margin-top:5px'>"
        f"<b style='color:{bar_col}'>{satisfaction_pct:.0f}% met</b>"
        f" · {received_mm:.0f} mm received · {needed_mm:.0f} mm needed</div>"
        f"</div>"
    ) if satisfaction_pct is not None else ""

    return f"""
<div class='hero' style='background:linear-gradient(135deg,{_bg} 0%,rgba(4,12,7,.95) 100%)'>
  <div class='hero-glow' style='background:{color}'></div>
  <div style='display:flex;align-items:center;gap:10px;margin-bottom:6px'>
    <span style='font-size:.72rem;font-weight:700;text-transform:uppercase;
      letter-spacing:.12em;color:rgba(255,255,255,.5)'>Drought Risk Score</span>
    <span style='font-size:.72rem;font-weight:600;padding:2px 10px;border-radius:20px;
      background:rgba(255,255,255,.08);color:rgba(255,255,255,.6)'>{location}</span>
  </div>
  <div style='display:flex;align-items:baseline;gap:14px;flex-wrap:wrap'>
    <span class='hero-score' style='color:{color}'>{score:.0f}</span>
    <div>
      <div class='hero-level' style='color:{color}'>{emoji} {level} Risk</div>
      <div style='font-size:.84rem;color:rgba(255,255,255,.5);margin-top:2px'>
        {crop} &nbsp;·&nbsp; {stage}
      </div>
    </div>
  </div>
  <p class='hero-summary'>{summary}</p>
  {sat_line}
</div>"""


def _kpi_tile(icon, label, value, sub, status="ok"):
    return (f"<div class='kpi kpi-{status}'>"
            f"<span class='kpi-icon'>{icon}</span>"
            f"<div class='kpi-lbl'>{label}</div>"
            f"<div class='kpi-val'>{value}</div>"
            f"<div class='kpi-sub'>{sub}</div></div>")


def _rec_html(text, severity="info"):
    cls = {"critical": "rec-crit", "warning": "rec-warn", "info": "rec-info"}.get(severity, "rec-info")
    return f"<div class='rec {cls}'>{text}</div>"


def _insight_stats(*stats):
    """Render a row of (value, label) pairs inside an insight box."""
    items = "".join(
        f"<div style='text-align:center;padding:8px 14px'>"
        f"<span class='istat'>{v}</span>"
        f"<span class='istat-lbl'>{l}</span></div>"
        for v, l in stats
    )
    return f"<div style='display:flex;gap:4px;flex-wrap:wrap;margin-bottom:12px'>{items}</div>"


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
df_weather = df_forecast = None
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
    oni = _cached_enso()

data_ok = df_weather is not None and not df_weather.empty

# ─────────────────────────────────────────────────────────────────────────────
# PAGE HEADER  (lean — details live in the hero card below)
# ─────────────────────────────────────────────────────────────────────────────
oni_v = oni["value"]
live_tag = "🔴 LIVE" if "Offline" not in oni["source"] else "⚫ OFFLINE"

# Compact top-bar: wordmark + ENSO pill
if oni_v >= 1.5:   ep_bg, ep_col = "rgba(127,29,29,.7)","#fca5a5"
elif oni_v >= 0.5: ep_bg, ep_col = "rgba(120,53,15,.7)","#fcd34d"
elif oni_v <= -0.5:ep_bg, ep_col = "rgba(23,45,90,.7)", "#93c5fd"
else:              ep_bg, ep_col = "rgba(5,50,22,.7)",  "#6ee7b7"

st.markdown(
    "<div style='display:flex;align-items:center;justify-content:space-between;"
    "flex-wrap:wrap;gap:10px;margin-bottom:16px'>"
    "<div>"
    "<span style='font-size:1.45rem;font-weight:800;color:#ecfdf5;"
    "letter-spacing:-.03em'>ENSA</span>"
    "<span style='font-size:.82rem;color:#52a874;margin-left:10px;"
    "font-weight:500'>El Niño Sentinel Agent · Agricultural Drought Early-Warning</span>"
    "</div>"
    f"<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>"
    f"<span style='background:{ep_bg};color:{ep_col};font-size:.78rem;font-weight:700;"
    f"padding:5px 14px;border-radius:20px;border:1px solid rgba(255,255,255,.1)'>"
    f"NINO3.4 {oni_v:+.2f}°C &nbsp; {oni['phase']}</span>"
    f"<span style='font-size:.74rem;color:#466b57'>{live_tag} · {oni['month_name']} {oni['year']}</span>"
    "</div></div>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_status, tab_history, tab_fc, tab_about = st.tabs([
    "🌾 Farm Status", "📈 90-Day History", "🔮 14-Day Forecast", "📖 Methodology"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: FARM STATUS
# ═══════════════════════════════════════════════════════════════════════════
with tab_status:

    if not data_ok:
        st.error(
            f"**Could not load weather data.**  \n"
            f"Error: `{weather_error or 'empty API response'}`  \n"
            "Check your internet connection or try a different location.")
        st.stop()

    # ── Compute everything first ──────────────────────────────────────────
    a_dt = pd.Timestamp(assessment_date)
    if is_fc_mode and df_forecast is not None and not df_forecast.empty:
        df_all = pd.concat([df_weather, df_forecast], ignore_index=True)
    else:
        df_all = df_weather.copy()
    df_slice  = df_all[df_all["date"] <= a_dt]
    assessment = compute_drought_score(df_slice, oni_v, crop_stage, is_active)

    score = assessment["score"]
    level = assessment["alert_level"]
    color = assessment["alert_color"]
    emoji = assessment["alert_emoji"]

    tail90     = df_slice.tail(90)
    precip_90  = float(tail90["precip_mm"].sum())
    et0_90     = float(tail90["et0_mm"].sum())
    deficit_90 = max(0.0, et0_90 - precip_90)
    temp_90    = float(tail90["temp_c"].mean())
    opt_t_lo, opt_t_hi = cal["optimal_temp"]

    if is_active:
        needed           = cal["daily_demand_mm"] * len(tail90)
        satisfaction_pct = min(150.0, (precip_90 / (needed + 1e-6)) * 100)
    else:
        needed = 0; satisfaction_pct = None

    summary_text = generate_summary(
        assessment, crop_choice, crop_stage, oni["phase"], st.session_state.preset_name)

    # ── ROW 1: Hero card (full width) ────────────────────────────────────
    st.markdown(
        _hero_html(score, level, color, emoji, summary_text,
                   crop_choice, crop_stage, st.session_state.preset_name,
                   satisfaction_pct if satisfaction_pct is not None else 0,
                   precip_90, needed),
        unsafe_allow_html=True)

    # ── ROW 2: Map  |  Gauge  |  KPI grid ────────────────────────────────
    col_map, col_gauge, col_kpis = st.columns([3, 1.4, 2.6])

    with col_map:
        st.markdown("<div class='card' style='padding:14px 16px'>", unsafe_allow_html=True)
        st.markdown("<div class='sec-head'>📍 Farm Location</div>", unsafe_allow_html=True)
        st.caption("Click map to reposition")
        m_map = folium.Map(location=[lat, lon], zoom_start=7,
                           tiles="CartoDB dark_matter")
        folium.Marker([lat, lon], tooltip=f"{lat:.4f}°, {lon:.4f}°",
                      icon=folium.Icon(color="green", icon="leaf")).add_to(m_map)
        map_out = st_folium(m_map, height=270, use_container_width=True, key="main_map")
        if map_out and map_out.get("last_clicked"):
            clat = map_out["last_clicked"]["lat"]
            clon = map_out["last_clicked"]["lng"]
            if [round(clat,3), round(clon,3)] != [round(lat,3), round(lon,3)]:
                st.session_state.point = [clat, clon]
                st.session_state.preset_name = "Custom Point"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with col_gauge:
        st.markdown(
            f"<div class='card' style='text-align:center;padding:18px 12px'>",
            unsafe_allow_html=True)
        st.markdown("<div class='sec-head'>Risk Score</div>", unsafe_allow_html=True)
        st.pyplot(_gauge(score, color), use_container_width=True)
        st.markdown(
            f"<div style='color:{color};font-weight:700;font-size:.95rem;"
            f"text-align:center;margin-top:4px'>{emoji} {level}</div>"
            f"<div style='color:#466b57;font-size:.74rem;text-align:center;"
            f"margin-top:2px'>{active_region} · {assessment_date.strftime('%b %Y')}</div>",
            unsafe_allow_html=True)
        if is_fc_mode:
            st.markdown("<div style='color:#38bdf8;font-size:.76rem;text-align:center;margin-top:6px'>🔮 Forecast mode</div>", unsafe_allow_html=True)
        elif not is_active:
            st.markdown("<div style='color:#fbbf24;font-size:.76rem;text-align:center;margin-top:6px'>⚠️ Off-season</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_kpis:
        st.markdown("<div class='sec-head' style='margin-top:6px'>Key Indicators — last 90 days (ERA5)</div>", unsafe_allow_html=True)
        rain_ok  = precip_90 >= cal["daily_demand_mm"] * 90 * 0.7
        def_ok   = deficit_90 < 100
        temp_ok  = opt_t_lo <= temp_90 <= opt_t_hi + 2
        spi_ok   = assessment["spi3"] >= -1.0
        kpi_html = (
            "<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'>"
            + _kpi_tile("🌧️", "Rainfall 90d", f"{precip_90:.0f} mm",
                        f"Need {cal['daily_demand_mm']*90:.0f} mm", "ok" if rain_ok else "bad")
            + _kpi_tile("💧", "Water Deficit", f"{deficit_90:.0f} mm",
                        f"Evap demand {et0_90:.0f} mm", "ok" if def_ok else "bad")
            + _kpi_tile("🌡️", "Mean Temp", f"{temp_90:.1f}°C",
                        f"Optimal {opt_t_lo}–{opt_t_hi}°C", "ok" if temp_ok else "warn")
            + _kpi_tile("📊", "SPI-3", f"{assessment['spi3']:+.2f}",
                        "< –1.0 = drought onset", "ok" if spi_ok else "bad")
            + "</div>"
        )
        st.markdown(kpi_html, unsafe_allow_html=True)

    # ── ROW 3: Crop calendar (full width) ───────────────────────────────
    st.markdown("<div class='card' style='padding:16px 22px;margin-top:4px'>", unsafe_allow_html=True)
    st.markdown("<div class='sec-head'>📅 Crop Growth Calendar</div>", unsafe_allow_html=True)
    st.pyplot(_crop_calendar_strip(cal, a_month), use_container_width=True)
    st.caption("🟢 Growing  🔴 Critical water stage  🟡 Harvesting  ⬛ Fallow  — outlined = current month")
    st.markdown("</div>", unsafe_allow_html=True)

    # ── ROW 4: Recommendations  |  AI expander ───────────────────────────
    col_recs, col_ai = st.columns([3, 2])

    with col_recs:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec-head'>What to do now</div>", unsafe_allow_html=True)
        recs = generate_recommendations(assessment, crop_choice, crop_stage, oni_v)
        for r in recs:
            sev = "critical" if "🚿" in r or "🌊" in r or "🚨" in r else (
                  "warning"  if "💧" in r or "🐛" in r or "🌾" in r else "info")
            st.markdown(_rec_html(r, sev), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_ai:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec-head'>🤖 AI-Enhanced Analysis</div>", unsafe_allow_html=True)
        st.caption(
            "The core dashboard is 100% free. Optionally paste your "
            "Anthropic or OpenAI key in the sidebar for a richer AI-written assessment.")
        if ai_key:
            if st.button("Generate AI Analysis"):
                provider = "anthropic" if "anthropic" in ai_provider.lower() else "openai"
                with st.spinner("Asking AI…"):
                    txt = call_llm_narrative(
                        assessment, crop_choice, crop_stage, oni,
                        st.session_state.preset_name, ai_key, provider)
                st.markdown(txt)
        else:
            st.info("Add your API key in the sidebar (section 4) to enable AI analysis.")
        st.markdown("---")
        st.markdown("<div class='sec-head'>💾 Save Assessment</div>", unsafe_allow_html=True)
        if st.button("Save to local database"):
            try:
                init_db()
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("INSERT OR IGNORE INTO regional_targets "
                          "(region_name,country,crop_type,bbox_coords,is_scheduled) VALUES(?,?,?,?,?)",
                          (st.session_state.preset_name, active_region, crop_choice,
                           f"{lon},{lat}", 0))
                c.execute(
                    "INSERT INTO self_correction_journal "
                    "(journal_date,assessment_period,target_district,raw_pdsi_forecast,"
                    "observed_pdsi,forecast_rmse,agent_reasoning,parameter_adjustments)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (datetime.now().strftime("%Y-%m-%d"), "Manual",
                     st.session_state.preset_name, assessment["spi3"],
                     -deficit_90/100, abs(score-50), summary_text,
                     f'{{"score":{score},"level":"{level}","oni":{oni_v}}}'))
                conn.commit(); conn.close()
                st.success("Saved!")
            except Exception as e:
                st.error(f"Save failed: {e}")
        st.markdown("</div>", unsafe_allow_html=True)


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
# TAB 4: METHODOLOGY
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
