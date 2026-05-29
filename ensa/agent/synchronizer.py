import sqlite3
import json
from datetime import datetime
from ensa.db.connection import get_db_connection
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

    def sync_pending_anomalies(self):
        """
        Gathers low-confidence alerts or pending validations, packages them,
        queries the Cloud API, and commits the learned weights back to SQLite.
        """
        print("\n=== [Edge Node Sync] Starting Daily Cloud Sync Loop ===")
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Fetch pending alerts that need cloud validation or have low confidence
        # For demonstration, we select active alerts in our database
        try:
            cursor.execute("""
                SELECT id, district, trigger_level, forecasted_spei3, trigger_rationale 
                FROM alert_triggers 
                LIMIT 5
            """)
            pending_alerts = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            # Fallback if table structure is being initialized
            pending_alerts = []

        if not pending_alerts:
            print("[Edge Node Sync] No pending alerts found in SQLite DB requiring cloud calibration.")
            conn.close()
            return False

        print(f"[Edge Node Sync] Found {len(pending_alerts)} records requiring biophysical cloud validation.")

        # 2. Package the anomalies and query the cloud
        cloud_response = self.cloud_brain.run_daily_calibration(pending_alerts)
        
        print("\n=== [Cloud Response Received] ===")
        print(f"Calibration Rationale: {cloud_response['calibration_rationale']}")
        print(f"Adjusted Weights: {json.dumps(cloud_response['adjusted_weights'])}")
        
        # 3. Commit the updated biophysical weights and journal to the database
        for alert in pending_alerts:
            cursor.execute("""
                INSERT INTO self_correction_journal 
                (journal_date, assessment_period, target_district, predicted_drought_severity, observed_drought_severity, error_metric, agent_reasoning, parameter_adjustments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d"),
                "Daily-Edge-Sync",
                alert["district"],
                70.0,  # Mock forecasted
                70.0 * cloud_response.get("estimated_pdsi_dampener", 1.0), # Corrected
                10.0,  # Delta
                cloud_response["calibration_rationale"],
                json.dumps(cloud_response["adjusted_weights"])
            ))
            
        conn.commit()
        conn.close()
        print("\n[Edge Node Sync] Local database memory successfully updated with dynamic weights!")
        return True

if __name__ == "__main__":
    sync = BatchSynchronizer()
    sync.sync_pending_anomalies()
