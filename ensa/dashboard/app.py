import sys
import os
# Append the repository root to Python path to ensure clean imports on Streamlit Cloud
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import folium
from streamlit_folium import folium_static
import json
import sqlite3
import pandas as pd
from datetime import datetime

# Import ENSA modules
from ensa.config import DB_PATH, ZAMBIA_BBOX
from ensa.db.connection import get_db_connection
from ensa.agent.synchronizer import BatchSynchronizer

# ----------------- PAGE CONFIG -----------------
st.set_page_config(
    page_title="ENSA — El Niño Sentinel Agent",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium Glassmorphic Styles
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #070b19 0%, #03050c 100%);
        color: #e2e8f0;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3, h4 {
        color: #ffffff;
        font-weight: 700;
        letter-spacing: -0.025em;
    }
    .glass-card {
        background: rgba(255, 255, 255, 0.02);
        border-radius: 16px;
        padding: 24px;
        border: 1px solid rgba(255, 255, 255, 0.07);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(10px);
        margin-bottom: 22px;
    }
    .badge {
        border-radius: 8px;
        padding: 4px 10px;
        font-weight: bold;
        font-size: 0.8rem;
        display: inline-block;
    }
    .badge-extreme {
        background: linear-gradient(135deg, #ff4b4b 0%, #9e0b0b 100%);
        color: white;
        box-shadow: 0 4px 12px rgba(255, 75, 75, 0.35);
    }
    .badge-severe {
        background: linear-gradient(135deg, #f7931e 0%, #b85b00 100%);
        color: white;
        box-shadow: 0 4px 12px rgba(247, 147, 30, 0.35);
    }
    .badge-moderate {
        background: linear-gradient(135deg, #fbb03b 0%, #a16b00 100%);
        color: white;
        box-shadow: 0 4px 12px rgba(251, 176, 59, 0.35);
    }
    .badge-normal {
        background: linear-gradient(135deg, #39b54a 0%, #1c6b24 100%);
        color: white;
        box-shadow: 0 4px 12px rgba(57, 181, 74, 0.35);
    }
</style>
""", unsafe_allow_html=True)

# ----------------- SIDEBAR -----------------
st.sidebar.markdown("<h2 style='text-align: center;'>🛰️ ENSA Edge Control</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

st.sidebar.subheader("Edge LLM (Local)")
st.sidebar.code("Ollama: Qwen-2.5-1.5B\nStatus: RUNNING (Cold)", language="text")

st.sidebar.subheader("Cloud Sync API Credentials")
openai_key = st.sidebar.text_input("Gemini API Key", type="password")

st.sidebar.markdown("---")
# Trigger Cloud Calibration Batch Sync
st.sidebar.subheader("Daily Cognitive Sync")
if st.sidebar.button("🔄 Sync Uncertainties with Cloud", use_container_width=True):
    with st.spinner("Batching low-confidence alerts for Cloud AI analysis..."):
        # Temporarily set key in env if provided
        if openai_key:
            import os
            os.environ["GEMINI_API_KEY"] = openai_key
            
        synchronizer = BatchSynchronizer()
        status = synchronizer.sync_pending_anomalies()
        if status:
            st.sidebar.success("Database memory calibrated successfully!")
        else:
            st.sidebar.info("No uncertainties pending cloud review.")

st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style='font-size: 0.8rem; opacity: 0.65; text-align: center;'>
    ENSA v1.1.0 — Biophysically Calibrated<br/>
    Drought Forecasting Engine
</div>
""", unsafe_allow_html=True)

# ----------------- MAIN UI -----------------
st.markdown("<h1 style='background: linear-gradient(90deg, #38ef7d 0%, #11998e 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>El Niño Sentinel Agent (ENSA)</h1>", unsafe_allow_html=True)
st.markdown("<p style='font-size: 1.15rem; color: #a0aec0;'>Local-Cloud Edge-Node Biophysical Calibration & Forecasting Loop</p>", unsafe_allow_html=True)

# Pull latest SQLite forecast data
conn = get_db_connection()
try:
    df_history = pd.read_sql_query("""
        SELECT * FROM forecast_history 
        ORDER BY id DESC LIMIT 1
    """, conn)
    
    df_journal = pd.read_sql_query("""
        SELECT * FROM self_correction_journal 
        ORDER BY id DESC LIMIT 5
    """, conn)
except Exception:
    df_history = pd.DataFrame()
    df_journal = pd.DataFrame()
conn.close()

if df_history.empty:
    st.warning("⚠️ No localized forecast logs found in SQLite database. Please run the ingestor pipeline first.")
else:
    latest = df_history.iloc[0]
    
    # ----------------- LAYOUT -----------------
    col_left, col_right = st.columns([3, 2])
    
    with col_left:
        # 1. Map Card
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.subheader(f"Target Boundary: {latest['target_region']}, Southern Zambia")
        
        map_center = [-16.2, 27.7] # Southern Province center
        m = folium.Map(location=map_center, zoom_start=9, tiles="CartoDB dark_matter")
        # Draw search bounding box
        folium.Rectangle(
            bounds=[[-18.0, 22.0], [-8.0, 33.5]],
            color="#11998e",
            fill=True,
            fill_opacity=0.04,
            weight=1.5,
            popup="Zambia Footprint"
        ).add_to(m)
        folium_static(m, width=650, height=350)
        st.markdown("</div>", unsafe_allow_html=True)
        
        # 2. Scientific Indicators Matrix
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.subheader("Ingested Biophysical Indicators")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Sentinel-2 VCI", f"{latest['observed_vci']:.1f}%", delta="Kogan 1995")
        with c2:
            st.metric("Sentinel-2 NDWI", f"{latest['observed_ndwi']:.3f}", delta="McFeeters 1996")
        with c3:
            st.metric("ERA5-Land LST", f"{latest['observed_lst']:.1f}°C", delta="Sobrino 2004")
        with c4:
            st.metric("Forecast SPEI-3", f"{latest['raw_spei3']:.2f}", delta="Vicente-Serrano")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        # 3. Palmer Alert Card
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.subheader("Calibrated Early Warning")
        
        pdsi = latest["projected_pdsi"]
        alert = latest["alert_level"]
        
        badge_style = "badge-extreme" if "Extreme" in alert else ("badge-severe" if "Severe" in alert else ("badge-moderate" if "Moderate" in alert else "badge-normal"))
        
        st.markdown(f"<h4>Projected PDSI: <span class='badge {badge_style}'>{pdsi:.2f} ({alert})</span></h4>", unsafe_allow_html=True)
        
        citations = json.loads(latest["literature_citations"])
        st.caption(f"Calculated using **Palmer 1965** moisture anomaly index normalization.")
        
        # Recommendations derived dynamically
        st.markdown("---")
        st.markdown("**Actionable Intervention Recommendation:**")
        if pdsi < -2.0:
            st.warning(f"🚨 {pdsi:.2f}: Restrict irrigation draws, implement dynamic water-shaving schedules, and prepare emergency regional food supply lines.")
        else:
            st.info(f"ℹ️ {pdsi:.2f}: Localized watch status. Proceed with weekly high-res NDWI water shrinkage tracking on smallholder wards.")
            
        st.markdown("</div>", unsafe_allow_html=True)
        
        # 4. Correlation & Weight Fusion Card
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.subheader("Dynamic Correlation Weighting")
        st.write(f"**Fusion Type**: `{latest['fusion_type']}`")
        st.write(f"**Pearson Correlation (r)**: `{latest['pearson_r']:.3f}`")
        
        st.markdown("---")
        st.write(f"🌧️ **Precipitation Weight ($w_1$)**: `{latest['precipitation_weight']:.2f}`")
        st.write(f"🌿 **Vegetation VCI Weight ($w_2$)**: `{latest['vegetation_weight']:.2f}`")
        st.write(f"💧 **Soil Moisture Weight ($w_3$)**: `{latest['soil_moisture_weight']:.2f}`")
        st.markdown("</div>", unsafe_allow_html=True)

# ----------------- JOURNAL SECTION -----------------
st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
st.subheader("🔄 Edge Node Calibration & Self-Correction Journal")
if df_journal.empty:
    st.info("No cloud self-correction logs recorded. Perform your first Cloud Sync in the sidebar to populate the journal!")
else:
    for idx, row in df_journal.iterrows():
        st.markdown(f"**📅 Journal Date: {row['journal_date']} | Period: {row['assessment_period']}**")
        st.markdown(f"*Target district: `{row['target_district']}` | Predictive RMSE calibration error: `{row['forecast_rmse']:.1f}%`*")
        st.info(row["agent_reasoning"])
        st.markdown("---")
st.markdown("</div>", unsafe_allow_html=True)
