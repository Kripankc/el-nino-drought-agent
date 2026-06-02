"""
ENSA â€” El NiÃ±o Sentinel Agent  v2.1
Farmer-facing drought early-warning dashboard.
Weather: Open-Meteo ERA5 (real, free, no key).
ENSO:    NOAA CPC NINO3.4 (real, free, no key).
LLM:     optional â€” user supplies their own Anthropic/OpenAI key.
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PAGE CONFIG
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.set_page_config(
    page_title="ENSA â€” Drought Early Warning",
    page_icon="ðŸ›°ï¸",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&display=swap');
*{font-family:'DM Sans',system-ui,-apple-system,sans-serif!important;}

/* â”€â”€ App â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.stApp{background:#0D1117!important;color:#E6EDF3!important;}
#MainMenu,footer,.stDeployButton{display:none!important;}

/* â”€â”€ Sidebar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
[data-testid="stSidebar"]{background:#0D1117!important;border-right:1px solid #21262D!important;}
[data-testid="stSidebar"] .stMarkdown,[data-testid="stSidebar"] label{color:#8B949E!important;font-size:.83rem!important;}
[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{color:#E6EDF3!important;font-weight:600!important;}

/* â”€â”€ Typography â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
h1,h2,h3,h4{color:#E6EDF3!important;font-weight:600!important;letter-spacing:-.015em!important;}
p,.stMarkdown p{color:#8B949E!important;}

/* â”€â”€ Card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.card{background:#161C22;border:1px solid #2D3741;border-radius:10px;padding:18px 22px;margin-bottom:12px;}

/* â”€â”€ Section label â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.sec{font-size:.66rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:#8B949E;margin-bottom:10px;}

/* â”€â”€ KPI tile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.kpi{background:#161C22;border:1px solid #2D3741;border-radius:10px;padding:14px 16px;}
.kpi-lbl{font-size:.66rem;font-weight:600;text-transform:uppercase;letter-spacing:.09em;color:#8B949E;margin-bottom:5px;}
.kpi-val{font-size:1.65rem;font-weight:600;color:#E6EDF3;line-height:1.1;letter-spacing:-.02em;}
.kpi-sub{font-size:.74rem;color:#484F58;margin-top:4px;}
.kpi-ok {border-top:2px solid #3FB950!important;}
.kpi-warn{border-top:2px solid #E3B341!important;}
.kpi-bad{border-top:2px solid #F0883E!important;}

/* â”€â”€ Insight box â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.insight{background:#161C22;border:1px solid #2D3741;border-radius:10px;padding:16px 18px;font-size:.88rem;line-height:1.7;color:#8B949E;}
.insight b{color:#E6EDF3!important;}

/* â”€â”€ Tabs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.stTabs [data-baseweb="tab-list"]{background:#161C22;border-radius:8px;padding:3px;gap:2px;border:1px solid #2D3741;}
.stTabs [data-baseweb="tab"]{border-radius:6px!important;color:#8B949E!important;font-weight:500!important;font-size:.86rem!important;padding:7px 18px!important;background:transparent!important;border:none!important;}
.stTabs [aria-selected="true"]{background:#21262D!important;color:#E6EDF3!important;border-bottom:none!important;}

/* â”€â”€ Inputs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.stSelectbox>div>div,[data-baseweb="select"]>div,.stNumberInput input,.stDateInput input{background:#21262D!important;border:1px solid #2D3741!important;border-radius:8px!important;color:#E6EDF3!important;}
.stButton button{background:#21262D!important;border:1px solid #2D3741!important;color:#8B949E!important;border-radius:7px!important;font-size:.82rem!important;font-weight:500!important;}
.stButton button:hover{background:#2D3741!important;color:#E6EDF3!important;}
.stAlert{border-radius:8px!important;}
.stCaption{color:#484F58!important;font-size:.76rem!important;}

/* â”€â”€ Scrollbar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-track{background:#0D1117;}
::-webkit-scrollbar-thumb{background:#2D3741;border-radius:3px;}
::-webkit-scrollbar-thumb:hover{background:#3D4F5C;}
</style>
""", unsafe_allow_html=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# REGION DETECTION â€” priority-ordered, most specific first
# (lat_min, lat_max, lon_min, lon_max)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CROP CALENDARS  (literature-backed, no fallback values)
# daily_demand_mm = average FAO crop water requirement during active season
# optimal_temp    = (min, max) Â°C for healthy growth
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PRESET LOCATIONS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
PRESETS = {
    "Mazabuka, Zambia":        {"coords": [-16.25,  27.65]},
    "Kathmandu Valley, Nepal": {"coords": [27.70,   85.30]},
    "Punjab, India":           {"coords": [30.90,   75.85]},
    "Eldoret, Kenya":          {"coords": [0.51,    35.26]},
    "Griffith, Australia":     {"coords": [-34.28, 146.04]},
    "Kano, Nigeria":           {"coords": [12.00,    8.52]},
    "Chiang Mai, Thailand":    {"coords": [18.79,   98.98]},
    "Lahore, Pakistan":        {"coords": [31.55,   74.34]},
    "SÃ£o Paulo State, Brazil": {"coords": [-22.90,  -47.06]},
    "Custom Point":            {"coords": [-16.25,  27.65]},
}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# HELPERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# â”€â”€ Risk colour map â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
RISK_COLORS = {
    "Normal":  "#3FB950",
    "Watch":   "#58A6FF",
    "Warning": "#E3B341",
    "Severe":  "#F0883E",
    "Extreme": "#FF7B72",
    "Unknown": "#8B949E",
}
RISK_BG = {
    "Normal":  "#0D2010",
    "Watch":   "#001A30",
    "Warning": "#2A1E00",
    "Severe":  "#2C1400",
    "Extreme": "#3D0000",
    "Unknown": "#161C22",
}

# â”€â”€ Chart style helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _ax(ax, xrot=30):
    ax.set_facecolor("none")
    ax.tick_params(colors="#484F58", labelsize=7.5)
    ax.spines[:].set_visible(False)
    ax.grid(axis="y", color="#21262D", linewidth=0.6)
    plt.xticks(rotation=xrot, ha="right")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color("#484F58")


# â”€â”€ HTML helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _mini_cal(cal, current_month):
    """12-month compact strip with current month outlined."""
    html = "<div style='display:flex;gap:2px;flex-wrap:wrap'>"
    for m in range(1, 13):
        stage = cal["stages"][m]
        is_now = (m == current_month)
        if "Critical" in stage or "Flowering" in stage or "Silking" in stage or "Tasseling" in stage:
            bg, tc = "#2C1400", "#F0883E"
        elif "Fallow" in stage or "Dormant" in stage or "Overwintering" in stage:
            bg, tc = "#0D1117", "#3D444D"
        elif "Harvest" in stage:
            bg, tc = "#201800", "#E3B341"
        else:
            bg, tc = "#0D2010", "#3FB950"
        if is_now:
            bg = "#2D3741"
        outline = f"outline:2px solid {tc};outline-offset:1px;" if is_now else ""
        fw = "700" if is_now else "400"
        html += (f"<div style='background:{bg};border-radius:3px;padding:3px 5px;"
                 f"font-size:10px;color:{tc};font-weight:{fw};{outline}'>"
                 f"{calendar.month_abbr[m]}</div>")
    html += "</div>"
    stage_now = cal["stages"][current_month]
    if "Critical" in stage_now or "Flowering" in stage_now:
        sc, si = "#F0883E", "ðŸ”´"
    elif "Fallow" in stage_now or "Dormant" in stage_now:
        sc, si = "#484F58", "â€”"
    elif "Harvest" in stage_now:
        sc, si = "#E3B341", "ðŸŸ¡"
    else:
        sc, si = "#3FB950", "ðŸŸ¢"
    html += f"<div style='font-size:11px;color:{sc};margin-top:5px;font-weight:500'>{si} {stage_now}</div>"
    return html


def _ticker(assessment, crop, location):
    level = assessment["alert_level"]
    bg   = RISK_BG.get(level, "#161C22")
    tc   = RISK_COLORS.get(level, "#8B949E")
    msgs = {
        "Extreme": f"Emergency drought conditions at {location}. Immediate crop loss risk â€” act now.",
        "Severe":  f"Severe dry spell detected at {location}. High yield risk for {crop} if untreated.",
        "Warning": f"Below-normal rainfall with rising evaporation stress for {crop} at {location}.",
        "Watch":   f"Conditions slightly below normal for {crop} at {location}. Monitor weekly.",
        "Normal":  f"Conditions are within the normal range for {crop} at {location}.",
    }
    labels = {"Extreme":"ðŸš¨ EMERGENCY","Severe":"ðŸš¨ ALERT","Warning":"âš ï¸ WARNING",
              "Watch":"ðŸ‘ WATCH","Normal":"âœ… NORMAL"}
    return (f"<div style='background:{bg};border:1px solid {tc}44;border-radius:8px;"
            f"padding:9px 18px;margin:8px 0 14px;display:flex;align-items:center;gap:14px'>"
            f"<span style='color:{tc};font-size:.78rem;font-weight:700;white-space:nowrap;"
            f"letter-spacing:.04em'>{labels.get(level,'')}</span>"
            f"<span style='color:#C9D1D9;font-size:.86rem'>{msgs.get(level,'')}</span>"
            f"</div>")


def _score_card(score, level, spi3):
    tc = RISK_COLORS.get(level, "#8B949E")
    spi_desc = ("Extreme drought" if spi3 < -2 else "Severe drought" if spi3 < -1.5
                else "Moderate drought" if spi3 < -1 else "Dry conditions" if spi3 < -0.5
                else "Normal range")
    return (f"<div class='card'>"
            f"<div class='sec'>Drought Stress Score</div>"
            f"<div style='display:flex;align-items:baseline;gap:8px'>"
            f"<span style='font-size:4.2rem;font-weight:700;color:{tc};"
            f"line-height:1;letter-spacing:-.04em'>{score:.0f}</span>"
            f"<span style='font-size:1.1rem;color:#3D444D'>/&thinsp;100</span></div>"
            f"<div style='margin-top:10px'>"
            f"<span style='background:{tc}18;color:{tc};border:1px solid {tc}44;"
            f"border-radius:6px;padding:3px 10px;font-size:.8rem;font-weight:600'>"
            f"{level.upper()} RISK</span></div>"
            f"<div style='margin-top:12px;font-size:.8rem;color:#8B949E'>"
            f"SPI-3 <span style='color:{tc};font-weight:600'>{spi3:+.2f}</span>"
            f"&emsp;{spi_desc}</div></div>")


def _deficit_card(sat_pct, received, needed, deficit):
    if sat_pct is None:
        return ("<div class='card'><div class='sec'>Moisture Deficit</div>"
                "<div style='color:#484F58;font-size:.88rem'>Off-season â€” crop not actively growing.</div></div>")
    pct = min(100, max(0, sat_pct))
    bc  = "#3FB950" if pct >= 80 else ("#E3B341" if pct >= 50 else "#F0883E")
    return (f"<div class='card'>"
            f"<div class='sec'>Moisture Deficit</div>"
            f"<div style='font-size:2rem;font-weight:700;color:{bc};line-height:1'>{pct:.0f}%</div>"
            f"<div style='font-size:.8rem;color:#8B949E;margin-top:2px'>Water Needs Met (90 days)</div>"
            f"<div style='background:#21262D;border-radius:5px;height:10px;"
            f"overflow:hidden;margin:10px 0'>"
            f"<div style='width:{pct:.0f}%;height:100%;background:{bc};border-radius:5px'></div></div>"
            f"<div style='font-size:.8rem;color:#8B949E'>"
            f"<span style='color:#E6EDF3'>{received:.0f} mm</span> received"
            f" &nbsp;Â·&nbsp; <span style='color:#E6EDF3'>{needed:.0f} mm</span> needed"
            f" &nbsp;Â·&nbsp; Deficit: <span style='color:#F0883E;font-weight:600'>â€“{deficit:.0f} mm</span>"
            f"</div></div>")


def _kpi(icon, label, value, sub, status_text, tc):
    cls = "kpi-ok" if "ok" in tc.lower() or tc == "#3FB950" else (
          "kpi-warn" if tc == "#E3B341" else "kpi-bad")
    return (f"<div class='kpi {cls}'>"
            f"<div class='kpi-lbl'>{icon} {label}</div>"
            f"<div class='kpi-val'>{value}</div>"
            f"<div style='font-size:.75rem;color:{tc};font-weight:500;margin-top:3px'>{status_text}</div>"
            f"<div class='kpi-sub'>{sub}</div></div>")


def _actions(recs, level):
    scheme = {
        "Extreme": [("#FF7B72","HIGH"),("#FF7B72","HIGH"),("#E3B341","MEDIUM"),("#E3B341","MEDIUM"),("#3FB950","LOW")],
        "Severe":  [("#F0883E","HIGH"),("#F0883E","HIGH"),("#E3B341","MEDIUM"),("#E3B341","MEDIUM"),("#3FB950","LOW")],
        "Warning": [("#E3B341","MEDIUM"),("#E3B341","MEDIUM"),("#3FB950","LOW"),("#3FB950","LOW")],
        "Watch":   [("#58A6FF","LOW")] * 4,
        "Normal":  [("#3FB950","LOW")] * 4,
    }
    priorities = scheme.get(level, scheme["Normal"])
    html = ("<div class='card' style='padding:0;overflow:hidden'>"
            "<div style='background:#1C2128;padding:10px 18px;border-bottom:1px solid #2D3741;"
            "font-size:.66rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:#8B949E'>"
            "ðŸ“‹ REQUIRED AGRONOMIC ACTIONS</div>")
    for i, rec in enumerate(recs):
        tc, pri = priorities[min(i, len(priorities)-1)]
        sep = "" if i == len(recs)-1 else "border-bottom:1px solid #21262D;"
        html += (f"<div style='display:flex;align-items:flex-start;gap:12px;"
                 f"padding:11px 18px;border-left:3px solid {tc};{sep}'>"
                 f"<span style='background:{tc}20;color:{tc};border:1px solid {tc}44;"
                 f"font-size:.6rem;font-weight:700;padding:2px 7px;border-radius:4px;"
                 f"white-space:nowrap;margin-top:1px'>{pri}</span>"
                 f"<span style='font-size:.87rem;color:#C9D1D9;line-height:1.55'>{rec}</span></div>")
    html += "</div>"
    return html


# â”€â”€ Chart functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _gauge(score, color):
    """Half-donut risk gauge â€” clean dark slate style."""
    fig, ax = plt.subplots(figsize=(3.2, 2.0), facecolor="none")
    ax.set_facecolor("none")
    Î¸ = np.linspace(np.pi, 0, 300)
    ax.plot(np.cos(Î¸), np.sin(Î¸), color="#21262D", linewidth=22, solid_capstyle="round", zorder=1)
    if score > 0:
        Î¸v = np.linspace(np.pi, np.pi - (min(score,100)/100)*np.pi, 300)
        ax.plot(np.cos(Î¸v), np.sin(Î¸v), color=color, linewidth=22, solid_capstyle="round", zorder=2)
    ax.text(0, 0.14, f"{score:.0f}", ha="center", va="center",
            fontsize=38, fontweight="700", color="#E6EDF3", zorder=3)
    ax.text(0, -0.28, "out of 100", ha="center", va="center",
            fontsize=7.5, color="#484F58", zorder=3)
    ax.set_xlim(-1.4, 1.4); ax.set_ylim(-0.52, 1.4); ax.axis("off")
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


# â”€â”€ HTML component helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        f"letter-spacing:.09em;margin-bottom:6px'>Crop water needs met â€” last 90 days</div>"
        f"<div style='background:rgba(255,255,255,.08);border-radius:7px;height:12px;overflow:hidden;max-width:480px'>"
        f"<div style='width:{bar_w:.0f}%;height:100%;background:{bar_col};border-radius:7px'></div></div>"
        f"<div style='font-size:.8rem;color:rgba(255,255,255,.5);margin-top:5px'>"
        f"<b style='color:{bar_col}'>{satisfaction_pct:.0f}% met</b>"
        f" Â· {received_mm:.0f} mm received Â· {needed_mm:.0f} mm needed</div>"
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
        {crop} &nbsp;Â·&nbsp; {stage}
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
        if row["needed_mm"] == 0: return "#21262D"
        if row["precip_mm"] >= row["needed_mm"] * 0.9: return "#3FB950"
        if row["precip_mm"] >= row["needed_mm"] * 0.6: return "#E3B341"
        return "#F0883E"

    colors = monthly.apply(_bar_color, axis=1)

    fig, ax = plt.subplots(figsize=(8, 2.8), facecolor="none")
    ax.bar(range(len(monthly)), monthly["precip_mm"], color=colors, alpha=0.88, width=0.62, zorder=2)
    ax.plot(range(len(monthly)), monthly["needed_mm"], color="#58A6FF",
            linewidth=1.5, linestyle="--", marker="o", markersize=3, label="Crop water need", zorder=3)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels(monthly["label"])
    _ax(ax)
    ax.set_ylabel("mm", color="#484F58", fontsize=8)
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(facecolor="#3FB950", alpha=0.88, label="Adequate"),
        Patch(facecolor="#E3B341", alpha=0.88, label="Below optimal"),
        Patch(facecolor="#F0883E", alpha=0.88, label="Critical deficit"),
        Patch(facecolor="#21262D", alpha=0.88, label="Off-season"),
        plt.Line2D([0],[0], color="#58A6FF", linewidth=1.5, linestyle="--", label="Crop need"),
    ], facecolor="#161C22", edgecolor="#21262D", labelcolor="#8B949E", fontsize=7, ncol=3)
    return fig


def _forecast_chart(df_fc, daily_demand_mm):
    """Forecast bars coloured by whether they meet daily crop need."""
    colors = ["#3FB950" if r >= daily_demand_mm else
              ("#E3B341" if r >= daily_demand_mm * 0.5 else "#F0883E")
              for r in df_fc["precip_mm"]]
    fig, ax = plt.subplots(figsize=(8, 2.6), facecolor="none")
    ax.bar(df_fc["date"], df_fc["precip_mm"], color=colors, alpha=0.88, width=0.8, zorder=2)
    ax.axhline(daily_demand_mm, color="#58A6FF", linestyle="--",
               linewidth=1.4, label=f"Daily crop need ({daily_demand_mm} mm)", zorder=3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    _ax(ax)
    ax.set_ylabel("mm/day", color="#484F58", fontsize=8)
    ax.legend(facecolor="#161C22", edgecolor="#21262D", labelcolor="#8B949E", fontsize=7)
    return fig


def _water_balance_chart(df_hist):
    """Cumulative P âˆ’ ETâ‚€ over last 90 days."""
    df = df_hist.tail(90).copy()
    cum = df["water_balance_mm"].cumsum()
    fig, ax = plt.subplots(figsize=(8, 2.5), facecolor="none")
    ax.plot(df["date"], cum, color="#8B949E", linewidth=1.5, zorder=3)
    ax.fill_between(df["date"], cum, 0, where=(cum < 0),
                    color="#F0883E", alpha=0.2, label="Deficit", zorder=2)
    ax.fill_between(df["date"], cum, 0, where=(cum >= 0),
                    color="#3FB950", alpha=0.15, label="Surplus", zorder=2)
    ax.axhline(0, color="#2D3741", linewidth=1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    _ax(ax)
    ax.set_ylabel("mm", color="#484F58", fontsize=8)
    ax.legend(facecolor="#161C22", edgecolor="#21262D", labelcolor="#8B949E", fontsize=7)
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


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CACHED DATA FETCHERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_weather(lat, lon):
    return fetch_weather(lat, lon, days_back=400)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_forecast(lat, lon):
    return fetch_forecast(lat, lon, days=14)


@st.cache_data(ttl=21600, show_spinner=False)
def _cached_enso():
    return fetch_current_oni()


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SESSION STATE
if "point"       not in st.session_state: st.session_state.point = PRESETS["Mazabuka, Zambia"]["coords"]
if "preset_name" not in st.session_state: st.session_state.preset_name = "Mazabuka, Zambia"

# Sidebar â€” minimal: only AI key
with st.sidebar:
    st.markdown("### ðŸ›°ï¸ ENSA")
    st.caption("El NiÃ±o Sentinel Agent")
    st.markdown("---")
    st.markdown("**AI Analysis** *(optional)*")
    st.caption("Core dashboard is 100% free. Paste your own key for AI narrative.")
    ai_provider = st.selectbox("Provider", ["Anthropic (Claude)", "OpenAI (GPT-4o-mini)"],
                               label_visibility="collapsed")
    ai_key = st.text_input("API Key", type="password", placeholder="sk-ant-... or sk-...",
                           label_visibility="collapsed")
    st.markdown("---")
    st.caption("Weather: Open-Meteo ERA5\nENSO: NOAA CPC\nAll data is real â€” no simulations.")

# Derive region early (needed for crop selector)
lat, lon = st.session_state.point
active_region = _detect_region(lat, lon)
cal_region    = CROP_CALENDARS.get(active_region, CROP_CALENDARS["Global"])

# Load data (cached)
_lat_r, _lon_r = round(lat, 3), round(lon, 3)
df_weather = df_forecast = None
weather_error = None
with st.spinner("Loading weather dataâ€¦"):
    try:    df_weather  = _cached_weather(_lat_r, _lon_r)
    except Exception as e: weather_error = str(e)
    try:    df_forecast = _cached_forecast(_lat_r, _lon_r)
    except Exception: pass
    oni = _cached_enso()
data_ok = df_weather is not None and not df_weather.empty

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# HEADER BAR
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
oni_v = oni["value"]
if oni_v >= 1.5:    ep_bg, ep_tc = "#6E1C1C", "#FF7B72"
elif oni_v >= 0.5:  ep_bg, ep_tc = "#5C3700", "#E3B341"
elif oni_v <= -0.5: ep_bg, ep_tc = "#0D2A4A", "#58A6FF"
else:               ep_bg, ep_tc = "#1A3020", "#3FB950"

live = "â—" if "Offline" not in oni["source"] else "â—‹"
st.markdown(
    f"<div style='background:#161C22;border-bottom:1px solid #21262D;"
    f"padding:10px 0;margin-bottom:16px;"
    f"display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px'>"
    f"<div style='display:flex;align-items:center;gap:14px'>"
    f"<span style='font-size:1.1rem;font-weight:700;color:#E6EDF3;letter-spacing:-.02em'>"
    f"ðŸ›°ï¸ ENSA</span>"
    f"<span style='font-size:.76rem;color:#484F58;border-left:1px solid #2D3741;"
    f"padding-left:12px'>Drought Early-Warning</span></div>"
    f"<div style='display:flex;align-items:center;gap:10px'>"
    f"<span style='background:{ep_bg};color:{ep_tc};border:1px solid {ep_tc}44;"
    f"padding:4px 12px;border-radius:6px;font-size:.76rem;font-weight:600'>"
    f"ðŸŒ¡ï¸ {oni['phase']}: NINO3.4 {oni_v:+.2f}Â°C</span>"
    f"<span style='font-size:.72rem;color:#484F58'>{live} NOAA {oni['month_name']} {oni['year']}</span>"
    f"</div></div>",
    unsafe_allow_html=True,
)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROW 1: MAP (left)  +  LOCATION & CROP CONTROLS (right)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
col_map, col_ctrl = st.columns([3, 2])

with col_map:
    st.markdown("<div class='card' style='padding:14px 16px'>", unsafe_allow_html=True)
    st.markdown("<div class='sec'>ðŸ“ Select your farm location</div>", unsafe_allow_html=True)
    st.caption("Click anywhere on the map to drop a pin on your farm.")
    m_map = folium.Map(location=[lat, lon], zoom_start=7, tiles="OpenStreetMap")
    folium.Marker(
        [lat, lon], tooltip=f"{lat:.4f}Â°, {lon:.4f}Â°",
        icon=folium.Icon(color="green", icon="leaf", prefix="fa"),
    ).add_to(m_map)
    map_out = st_folium(m_map, height=270, use_container_width=True, key="farm_map")
    if map_out and map_out.get("last_clicked"):
        clat = map_out["last_clicked"]["lat"]
        clon = map_out["last_clicked"]["lng"]
        if [round(clat, 3), round(clon, 3)] != [round(lat, 3), round(lon, 3)]:
            st.session_state.point = [clat, clon]
            st.session_state.preset_name = "Custom Point"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

with col_ctrl:
    st.markdown("<div class='card' style='padding:16px 18px'>", unsafe_allow_html=True)
    st.markdown("<div class='sec'>ðŸ“ Location & Crop</div>", unsafe_allow_html=True)

    # Derived location name
    st.markdown(
        f"<div style='font-size:.88rem;color:#E6EDF3;font-weight:600;margin-bottom:4px'>"
        f"{st.session_state.preset_name}</div>"
        f"<div style='font-size:.76rem;color:#484F58;margin-bottom:12px'>"
        f"Lat {lat:.4f}Â° &nbsp;Â·&nbsp; Lon {lon:.4f}Â° &nbsp;Â·&nbsp; {active_region}</div>",
        unsafe_allow_html=True)

    crop_choice     = st.selectbox("Crop", list(cal_region.keys()), label_visibility="collapsed",
                                   key="crop_sel")
    cal             = cal_region[crop_choice]
    assessment_date = st.date_input("Date", value=datetime.now().date(),
                                    min_value=datetime(2000,1,1).date(),
                                    max_value=(datetime.now()+timedelta(days=14)).date(),
                                    label_visibility="collapsed", key="date_sel")

    a_month    = assessment_date.month
    crop_stage = cal["stages"][a_month]
    is_active  = _is_active(cal, a_month)
    is_fc_mode = assessment_date > (datetime.now()-timedelta(days=5)).date()

    # Mini crop calendar
    st.markdown("<div class='sec' style='margin-top:14px'>ðŸ“… Crop Timeline & Stage</div>",
                unsafe_allow_html=True)
    st.markdown(_mini_cal(cal, a_month), unsafe_allow_html=True)

    # Quick presets
    st.markdown("<div class='sec' style='margin-top:14px'>âœ¨ Quick Presets</div>",
                unsafe_allow_html=True)
    preset_keys = [k for k in PRESETS if k != "Custom Point"]
    pc = st.columns(min(4, len(preset_keys)))
    for i, pk in enumerate(preset_keys[:4]):
        with pc[i]:
            short = pk.split(",")[0]
            if st.button(short, key=f"p_{i}", use_container_width=True):
                st.session_state.point = PRESETS[pk]["coords"]
                st.session_state.preset_name = pk
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# FAIL-FAST: show error and stop if no weather data
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if not data_ok:
    st.markdown(
        f"<div style='background:#3D0000;border:1px solid #FF7B7244;border-radius:8px;"
        f"padding:14px 18px;margin:10px 0'>"
        f"<b style='color:#FF7B72'>Could not load weather data</b><br>"
        f"<span style='color:#C9D1D9;font-size:.88rem'>"
        f"Error: {weather_error or 'empty API response'}<br>"
        f"Check your internet connection or try a different location.</span></div>",
        unsafe_allow_html=True)
    st.stop()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# COMPUTE ASSESSMENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
a_dt = pd.Timestamp(assessment_date)
if is_fc_mode and df_forecast is not None and not df_forecast.empty:
    df_all = pd.concat([df_weather, df_forecast], ignore_index=True)
else:
    df_all = df_weather.copy()
df_slice   = df_all[df_all["date"] <= a_dt]
assessment = compute_drought_score(df_slice, oni_v, crop_stage, is_active)

score = assessment["score"]
level = assessment["alert_level"]
color = RISK_COLORS.get(level, "#8B949E")

tail90     = df_slice.tail(90)
precip_90  = float(tail90["precip_mm"].sum())
et0_90     = float(tail90["et0_mm"].sum())
deficit_90 = max(0.0, et0_90 - precip_90)
temp_90    = float(tail90["temp_c"].mean())

if is_active:
    needed           = cal["daily_demand_mm"] * len(tail90)
    satisfaction_pct = min(150.0, (precip_90 / (needed + 1e-6)) * 100)
else:
    needed = 0; satisfaction_pct = None

summary_text = generate_summary(
    assessment, crop_choice, crop_stage, oni["phase"], st.session_state.preset_name)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ALERT TICKER
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown(_ticker(assessment, crop_choice, st.session_state.preset_name),
            unsafe_allow_html=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROW 2: SCORE CARD  +  DEFICIT CARD
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
col_score, col_deficit = st.columns(2)
with col_score:
    st.markdown(_score_card(score, level, assessment["spi3"]), unsafe_allow_html=True)
with col_deficit:
    st.markdown(_deficit_card(satisfaction_pct, precip_90, needed, deficit_90),
                unsafe_allow_html=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROW 3: 4 KPI TILES
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
opt_t_lo, opt_t_hi = cal["optimal_temp"]
rain_ok   = precip_90 >= cal["daily_demand_mm"] * 90 * 0.7
temp_ok   = opt_t_lo <= temp_90 <= opt_t_hi + 2
spi_ok    = assessment["spi3"] >= -1.0

k1, k2, k3, k4 = st.columns(4)
with k1:
    rain_st = "Adequate" if rain_ok else "Below target"
    st.markdown(
        _kpi("ðŸŒ§ï¸","90-Day Rain", f"{precip_90:.0f} mm",
             f"Target â‰¥ {cal['daily_demand_mm']*90*0.7:.0f} mm",
             rain_st, "#3FB950" if rain_ok else "#F0883E"),
        unsafe_allow_html=True)
with k2:
    spi_desc = ("Extreme dry" if assessment["spi3"] < -2 else
                "Severe dry"  if assessment["spi3"] < -1.5 else
                "Moderate dry"if assessment["spi3"] < -1 else
                "Dry watch"   if assessment["spi3"] < -0.5 else "Normal")
    st.markdown(
        _kpi("ðŸ“Š","SPI-3", f"{assessment['spi3']:+.2f}",
             "< â€“1.0 = drought onset",
             spi_desc, "#3FB950" if spi_ok else "#F0883E"),
        unsafe_allow_html=True)
with k3:
    temp_st = "Optimal" if temp_ok else ("Heat stress" if temp_90 > opt_t_hi else "Cool")
    st.markdown(
        _kpi("ðŸŒ¡ï¸","Avg Temp", f"{temp_90:.1f} Â°C",
             f"Optimal {opt_t_lo}â€“{opt_t_hi}Â°C",
             temp_st, "#3FB950" if temp_ok else "#E3B341"),
        unsafe_allow_html=True)
with k4:
    if df_forecast is not None and not df_forecast.empty:
        best_idx  = df_forecast["precip_mm"].idxmax()
        best_date = df_forecast.loc[best_idx, "date"].strftime("%b %d")
        best_mm   = float(df_forecast.loc[best_idx, "precip_mm"])
        fc_total  = float(df_forecast["precip_mm"].sum())
        fc_st     = f"Best: {best_mm:.1f} mm on {best_date}"
        fc_sub    = f"Total forecast: {fc_total:.0f} mm"
    else:
        fc_st, fc_sub = "Unavailable", "Check connection"
    st.markdown(
        _kpi("ðŸ”®","14-Day Forecast", f"{fc_total:.0f} mm" if df_forecast is not None and not df_forecast.empty else "â€”",
             fc_sub, fc_st, "#58A6FF"),
        unsafe_allow_html=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ROW 4: ACTIONS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
recs = generate_recommendations(assessment, crop_choice, crop_stage, oni_v)
st.markdown(_actions(recs, level), unsafe_allow_html=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# BOTTOM ACTIONS ROW
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ba1, ba2, ba3, ba4 = st.columns(4)
with ba1:
    if st.button("ðŸ“ˆ View Historical Analytics", use_container_width=True):
        st.session_state["active_tab"] = "history"
        st.rerun()
with ba2:
    if st.button("ðŸ”® 14-Day Forecast", use_container_width=True):
        st.session_state["active_tab"] = "forecast"
        st.rerun()
with ba3:
    if st.button("ðŸ“‘ Export Report", use_container_width=True):
        report = (f"ENSA Drought Report\n{'='*40}\n"
                  f"Location: {st.session_state.preset_name}\n"
                  f"Date: {assessment_date}\nCrop: {crop_choice}\n"
                  f"Stage: {crop_stage}\nRisk Score: {score:.0f}/100 ({level})\n"
                  f"SPI-3: {assessment['spi3']:+.2f}\n"
                  f"90-day Rain: {precip_90:.0f} mm\n"
                  f"Water Deficit: {deficit_90:.0f} mm\n"
                  f"ENSO: {oni['phase']} ({oni_v:+.2f}Â°C)\n\n"
                  f"Summary:\n{summary_text}\n\nRecommendations:\n" +
                  "\n".join(f"- {r}" for r in recs))
        st.download_button("Download .txt", report,
                           f"ensa_{assessment_date}_{crop_choice.replace(' ','_')}.txt",
                           "text/plain", use_container_width=True)
with ba4:
    with st.expander("ðŸ¤– AI Analysis"):
        if ai_key:
            if st.button("Generate", key="ai_gen"):
                prov = "anthropic" if "anthropic" in ai_provider.lower() else "openai"
                with st.spinner("Asking AIâ€¦"):
                    txt = call_llm_narrative(
                        assessment, crop_choice, crop_stage, oni,
                        st.session_state.preset_name, ai_key, prov)
                st.markdown(txt)
        else:
            st.caption("Add your API key in the sidebar to enable.")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# DEEP-DIVE TABS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
tab_history, tab_fc, tab_about = st.tabs(["ðŸ“ˆ Historical Analytics", "ðŸ”® 14-Day Forecast", "ðŸ“– Methodology"])

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 1: 90-DAY HISTORY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab_history:
    if not data_ok:
        st.warning(f"No data. {weather_error or ''}")
    else:
        df90 = df_weather.tail(90)
        t_lo, t_hi = cal["optimal_temp"]

        # Pre-compute insights
        df_m = df_weather.tail(180).copy()
        df_m["ym"] = df_m["date"].dt.to_period("M")
        monthly_sum = df_m.groupby("ym").agg(
            rain=("precip_mm","sum"), n=("precip_mm","count")).reset_index()
        monthly_sum["need"] = monthly_sum.apply(
            lambda r: cal["daily_demand_mm"]*r["n"] if _is_active(cal, r["ym"].month) else 0, axis=1)
        active_months = monthly_sum[monthly_sum["need"] > 0]

        dry_days  = int((df90["precip_mm"] < 1.0).sum())
        hot_days  = int((df90["temp_c"] > t_hi).sum())
        cum_wb    = df90["water_balance_mm"].cumsum()
        trend     = "worsening ðŸ“‰" if float(cum_wb.iloc[-1]) < float(cum_wb.iloc[len(cum_wb)//2]) else "stabilising ðŸ“Š"
        deficit_months = int((active_months["rain"] < active_months["need"]*0.8).sum()) if not active_months.empty else 0

        # â”€â”€ Monthly chart â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec'>Monthly Rainfall vs Crop Water Requirement</div>", unsafe_allow_html=True)
        c1, c2 = st.columns([3, 2])
        with c1:
            fig_m = _monthly_bar_chart(df_weather.tail(180), cal["daily_demand_mm"], cal)
            st.pyplot(fig_m, use_container_width=True); plt.close(fig_m)
            st.caption("ðŸŸ¢ Adequate Â· ðŸŸ¡ Below optimal Â· ðŸ”´ Critical Â· â¬› Off-season  â•Œ Dashed = crop water need")
        with c2:
            st.markdown("<div class='insight'>", unsafe_allow_html=True)
            st.markdown(
                f"Over the last 6 months, **{deficit_months}** active growing "
                f"month{'s' if deficit_months != 1 else ''} received less than 80% of "
                f"what **{crop_choice}** required.\n\n"
                f"A bar touching or exceeding the dashed blue line means that "
                f"month was adequate. Bars well below it represent water stress periods.")
            if deficit_months >= 2:
                st.error(f"âš ï¸ {deficit_months} months below normal â€” cumulative stress is high.")
            elif deficit_months == 1:
                st.warning("One below-normal month detected.")
            else:
                st.success("Rainfall broadly adequate across recent months.")
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # â”€â”€ Water balance chart â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec'>Cumulative Water Balance â€” last 90 days (Rain âˆ’ Evaporation)</div>", unsafe_allow_html=True)
        c3, c4 = st.columns([3, 2])
        with c3:
            fig_wb = _water_balance_chart(df_weather)
            st.pyplot(fig_wb, use_container_width=True); plt.close(fig_wb)
            st.caption("ERA5 Penman-Monteith ETâ‚€. Orange shading = moisture deficit zone.")
        with c4:
            st.markdown("<div class='insight'>", unsafe_allow_html=True)
            st.markdown(
                f"**{precip_90:.0f} mm** rain fell over 90 days.  \n"
                f"Evaporation demanded **{et0_90:.0f} mm**.  \n"
                f"Net deficit: **{deficit_90:.0f} mm**  \n\n"
                f"Balance trend: **{trend}**. "
                f"The line moving downward means more water is leaving than arriving.")
            if deficit_90 > 150: st.error("Severe deficit. Irrigation critical.")
            elif deficit_90 > 60: st.warning("Moderate deficit building.")
            else: st.success("Balance within manageable range.")
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # â”€â”€ Temperature + Rain â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        ct, cr = st.columns(2)
        with ct:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='sec'>Temperature â€” 90 days</div>", unsafe_allow_html=True)
            fig_t, ax_t = plt.subplots(figsize=(5, 2.4), facecolor="none")
            ax_t.plot(df90["date"], df90["temp_c"], color="#F0883E", linewidth=1.5, zorder=3)
            ax_t.axhspan(t_lo, t_hi, alpha=0.1, color="#3FB950", label=f"Optimal {t_lo}â€“{t_hi}Â°C", zorder=2)
            ax_t.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_t.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
            _ax(ax_t)
            ax_t.set_ylabel("Â°C", color="#484F58", fontsize=8)
            ax_t.legend(facecolor="#161C22", edgecolor="#21262D", labelcolor="#8B949E", fontsize=7)
            st.pyplot(fig_t, use_container_width=True); plt.close(fig_t)
            st.caption(f"**{hot_days}** days above the {t_hi}Â°C optimum." if hot_days > 5
                       else "Temperature stayed mostly within optimal range.")
            st.markdown("</div>", unsafe_allow_html=True)
        with cr:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='sec'>Daily Rainfall â€” 90 days</div>", unsafe_allow_html=True)
            fig_r, ax_r = plt.subplots(figsize=(5, 2.4), facecolor="none")
            ax_r.bar(df90["date"], df90["precip_mm"], color="#58A6FF", alpha=0.75, width=0.9, zorder=2)
            ax_r.axhline(cal["daily_demand_mm"], color="#3FB950", linestyle="--",
                         linewidth=1.3, label=f"Daily need ({cal['daily_demand_mm']} mm)", zorder=3)
            ax_r.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_r.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3))
            _ax(ax_r)
            ax_r.set_ylabel("mm", color="#484F58", fontsize=8)
            ax_r.legend(facecolor="#161C22", edgecolor="#21262D", labelcolor="#8B949E", fontsize=7)
            st.pyplot(fig_r, use_container_width=True); plt.close(fig_r)
            st.caption(f"**{dry_days}** days with less than 1 mm of rain in the last 90 days.")
            st.markdown("</div>", unsafe_allow_html=True)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 2: 14-DAY FORECAST
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab_fc:
    if df_forecast is None or df_forecast.empty:
        st.warning("Forecast data unavailable. Check internet connection.")
    else:
        fc_precip  = float(df_forecast["precip_mm"].sum())
        fc_et0     = float(df_forecast["et0_mm"].sum())
        fc_deficit = max(0.0, fc_et0 - fc_precip)
        fc_needed  = cal["daily_demand_mm"] * len(df_forecast)
        fc_pct     = min(150, (fc_precip / (fc_needed + 1e-6)) * 100)
        good_days  = int((df_forecast["precip_mm"] >= cal["daily_demand_mm"]).sum())
        ok_days    = int(((df_forecast["precip_mm"] >= cal["daily_demand_mm"]*0.5) &
                          (df_forecast["precip_mm"] < cal["daily_demand_mm"])).sum())
        bad_days   = len(df_forecast) - good_days - ok_days
        cum_fc     = df_forecast["water_balance_mm"].cumsum()
        fc_trend   = ("improving ðŸ“ˆ" if float(cum_fc.iloc[-1]) > float(cum_fc.iloc[len(cum_fc)//2])
                      else "worsening ðŸ“‰")

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec'>14-Day Rainfall Forecast</div>", unsafe_allow_html=True)
        cf1, cf2 = st.columns([3, 2])
        with cf1:
            st.pyplot(_forecast_chart(df_forecast, cal["daily_demand_mm"]),
                      use_container_width=True)
            st.caption("ðŸŸ¢ Meets daily need Â· ðŸŸ¡ Partial Â· ðŸ”´ Near-dry  â•Œ Dashed = daily crop need")
        with cf2:
            st.markdown("<div class='insight'>", unsafe_allow_html=True)
            pct_c = "#3FB950" if fc_pct >= 80 else ("#E3B341" if fc_pct >= 50 else "#F0883E")
            st.markdown(
                f"Forecast rain: **{fc_precip:.0f} mm**  \n"
                f"Crop water need: **{fc_needed:.0f} mm**  \n"
                f"<span style='color:{pct_c};font-weight:600'>Needs covered: {fc_pct:.0f}%</span>\n\n"
                f"ðŸŸ¢ **{good_days}** adequate days  \n"
                f"ðŸŸ¡ **{ok_days}** partial days  \n"
                f"ðŸ”´ **{bad_days}** near-dry days  \n\n"
                f"Balance trend: **{fc_trend}**",
                unsafe_allow_html=True)
            if fc_pct < 50: st.error("Forecast does not cover crop needs. Arrange irrigation.")
            elif fc_pct < 80: st.warning("Partial coverage expected.")
            else: st.success("Forecast broadly meets crop water requirements.")
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec'>Cumulative Water Balance â€” Next 14 Days</div>", unsafe_allow_html=True)
        cc1, cc2 = st.columns([3, 2])
        with cc1:
            fig_cfc, ax_cfc = plt.subplots(figsize=(6, 2.4), facecolor="none")
            ax_cfc.plot(df_forecast["date"], cum_fc, color="#8B949E", linewidth=1.5, zorder=3)
            ax_cfc.fill_between(df_forecast["date"], cum_fc, 0,
                                where=(cum_fc < 0), color="#F0883E", alpha=0.2, label="Deficit", zorder=2)
            ax_cfc.fill_between(df_forecast["date"], cum_fc, 0,
                                where=(cum_fc >= 0), color="#3FB950", alpha=0.15, label="Surplus", zorder=2)
            ax_cfc.axhline(0, color="#2D3741", linewidth=1)
            ax_cfc.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax_cfc.xaxis.set_major_locator(mdates.DayLocator(interval=3))
            _ax(ax_cfc)
            ax_cfc.set_ylabel("mm", color="#484F58", fontsize=8)
            ax_cfc.legend(facecolor="#161C22", edgecolor="#21262D", labelcolor="#8B949E", fontsize=7)
            st.pyplot(fig_cfc, use_container_width=True); plt.close(fig_cfc)
        with cc2:
            st.markdown("<div class='insight'>", unsafe_allow_html=True)
            final = float(cum_fc.iloc[-1])
            st.markdown(f"By day 14, net water balance: **{final:+.0f} mm**")
            if final < -80:
                st.markdown(f"The forecast **adds more drought stress**. Without irrigation, {crop_choice} yield will continue to deteriorate.")
            elif final < 0:
                st.markdown("Evaporation outpaces rainfall but the deficit is modest.")
            else:
                st.markdown("Forecast conditions offer **some relief** â€” incoming rain should partially replenish soil moisture.")
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TAB 3: METHODOLOGY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
with tab_about:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Data Sources")
    st.markdown("""
| Source | Variables | Cost |
|--------|-----------|------|
| **Open-Meteo ERA5 archive** | Daily rainfall, mean temperature, FAO-56 ETâ‚€ | Free, no key |
| **Open-Meteo Forecast** | 14-day precipitation, temperature, ETâ‚€ | Free, no key |
| **NOAA CPC NINO3.4** | Monthly Oceanic NiÃ±o Index (El NiÃ±o intensity) | Free, no key |

No simulations anywhere â€” if a source is offline the dashboard shows an error.
""")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Risk Score Methodology")
    st.markdown(r"""
The **0â€“100 drought risk score** combines four real-data components:

**1. SPI-3** (McKee et al. 1993) â€” Standardised Precipitation Index computed from the full ERA5 daily rainfall history. SPI-3 < â€“1.0 = drought; < â€“2.0 = severe. *Up to 40 pts.*

**2. Cumulative Water Deficit P âˆ’ ETâ‚€** â€” Total ERA5 rainfall minus FAO-56 Penman-Monteith evapotranspiration over 90 days. A large negative balance = crops have depleted available soil water. *Up to 40 pts.*

**3. Temperature stress** â€” Mean temperature above 25 Â°C accelerates evaporation. *Up to 20 pts.*

**4. ENSO amplification** (Ropelewski & Halpert 1987) â€” El NiÃ±o (NINO3.4 â‰¥ +0.5 Â°C) multiplies the score up to Ã—1.5, reflecting the known teleconnection between Pacific SST and suppressed rainfall in Southern Africa, South Asia, and Australia.

**5. Crop stage weighting** â€” Flowering, tasseling, panicle initiation, and grain-filling stages are multiplied Ã—1.35, because water stress during pollination causes irreversible yield loss.
""")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("ðŸ““ Saved Assessments")
    try:
        init_db()
        conn = get_db_connection()
        df_j = pd.read_sql_query(
            "SELECT journal_date, target_district, agent_reasoning "
            "FROM self_correction_journal ORDER BY id DESC LIMIT 20", conn)
        conn.close()
        if df_j.empty:
            st.info("No saved assessments yet. Use the Export Report button.")
        else:
            for _, row in df_j.iterrows():
                st.markdown(f"**{row['journal_date']} â€” {row['target_district']}**")
                st.caption(row["agent_reasoning"])
                st.markdown("---")
    except Exception as e:
        st.info(f"Database not yet initialised: {e}")
    st.markdown("</div>", unsafe_allow_html=True)
