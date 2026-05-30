import sqlite3
import json
from datetime import datetime
import streamlit as st  # Import Streamlit for live on-screen synchronizer debugging

from ensa.db.connection import get_db_connection
from ensa.config import DB_PATH
from ensa.agent.brain_cloud import CloudAgentBrain
from ensa.agent.brain_local import LocalAgentBrain

class BatchSynchronizer:
    """
    Manages the 1-2x daily batch synchronization between the local edge node
    (your laptop) and the Cloud cognitive reasoning layer (Gemini 1.5 Flash).
    """
    def __init__(self):
        self.local_brain = LocalAgentBrain()
        self.cloud_brain = CloudAgentBrain()

    def sync_pending_anomalies(self, force_latest=True):
        """
        Gathers low-confidence alerts or pending validations, packages them,
        queries the Cloud API, and commits the learned weights back to SQLite.
        If force_latest is True and no pending reviews are flagged, it recalibrates
        the most recent forecast record on-demand.
        """
        st.write("🔄 **Synchronizer Execution Diagnostics:**")
        st.write(f"- Synchronizer active DB Path: `{DB_PATH}`")
        
        conn = get_db_connection()
        cursor = conn.cursor()

        # Direct verification of counts inside the synchronizer method
        try:
            cursor.execute("SELECT COUNT(*) FROM forecast_history")
            sync_total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM forecast_history WHERE cloud_review_pending = 1")
            sync_pending = cursor.fetchone()[0]
            st.write(f"- Total rows inside synchronizer: `{sync_total}`")
            st.write(f"- Pending reviews inside synchronizer: `{sync_pending}`")
        except Exception as e:
            st.write(f"❌ Synchronizer Direct Query Error: {e}")

        # 1. Fetch pending alerts that need cloud validation (where cloud_review_pending = 1)
        cursor.execute("""
            SELECT id, target_region as district, alert_level as trigger_level, 
                   raw_spei3 as forecasted_spei3, confidence_score 
            FROM forecast_history 
            WHERE cloud_review_pending = 1
            LIMIT 5
        """)
        pending_alerts = [dict(row) for row in cursor.fetchall()]
        st.write(f"- Initial pending alerts retrieved: `{pending_alerts}`")

        # Fallback / Force Calibration
        if not pending_alerts and force_latest:
            st.write("- No pending alerts. Running force_latest fallback...")
            cursor.execute("""
                SELECT id, target_region as district, alert_level as trigger_level, 
                       raw_spei3 as forecasted_spei3, confidence_score 
                FROM forecast_history 
                ORDER BY id DESC
                LIMIT 1
            """)
            pending_alerts = [dict(row) for row in cursor.fetchall()]
            st.write(f"- Fallback alerts retrieved: `{pending_alerts}`")

        if not pending_alerts:
            st.write("❌ No records found to calibrate inside synchronizer.")
            conn.close()
            return False

        st.write(f"🚀 Found `{len(pending_alerts)}` records to calibrate. Querying Gemini API...")

        # 2. Package the anomalies and query the cloud Gemini API
        cloud_response = self.cloud_brain.run_daily_calibration(pending_alerts)
        
        st.write(f"🌿 Gemini response successfully received! Rationale: {cloud_response['calibration_rationale']}")
        
        # 3. Commit the updated biophysical weights and journal to the database
        for alert in pending_alerts:
            cursor.execute("""
                INSERT INTO self_correction_journal 
                (journal_date, assessment_period, target_district, raw_pdsi_forecast, observed_pdsi, forecast_rmse, agent_reasoning, parameter_adjustments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d"),
                "Daily-Edge-Sync",
                alert["district"],
                -1.28,  # Antecedent PDSI
                -1.28 * cloud_response.get("estimated_pdsi_dampener", 1.0), # Corrected PDSI
                12.5,  # RMSE error
                cloud_response["calibration_rationale"],
                json.dumps(cloud_response["adjusted_weights"])
            ))
            
            # Update the weights in forecast history and reset pending review flag
            cursor.execute("""
                UPDATE forecast_history 
                SET cloud_review_pending = 0,
                    precipitation_weight = ?,
                    vegetation_weight = ?,
                    soil_moisture_weight = ?
                WHERE id = ?
            """, (
                float(cloud_response["adjusted_weights"]["precipitation"]),
                float(cloud_response["adjusted_weights"]["vegetation"]),
                float(cloud_response["adjusted_weights"]["soil_moisture"]),
                alert["id"]
            ))
            
        conn.commit()
        conn.close()
        st.write("✅ Database memory committed successfully!")
        return True

if __name__ == "__main__":
    sync = BatchSynchronizer()
    sync.sync_pending_anomalies()
