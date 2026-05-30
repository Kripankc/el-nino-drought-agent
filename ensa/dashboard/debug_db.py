import sqlite3
import json
import os
import sys

# Append root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ensa.config import DB_PATH
from ensa.db.connection import get_db_connection

def run_db_diagnostic():
    print("=== [ENSA DB Diagnostic Script] ===")
    print(f"Active DB Path: {DB_PATH}")
    print(f"File Exists? {os.path.exists(DB_PATH)}")
    
    if not os.path.exists(DB_PATH):
        print("[Error] DB File does not exist!")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Inspect Tables
    print("\n1. Existing SQLite Tables:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(tables)
    
    # 2. Inspect Columns of forecast_history
    print("\n2. Columns in 'forecast_history' table:")
    try:
        cursor.execute("PRAGMA table_info(forecast_history)")
        columns = [f"{row[1]} ({row[2]})" for row in cursor.fetchall()]
        print(columns)
    except Exception as e:
        print(f"[Error] Failed to read columns: {e}")

    # 3. Inspect Rows of forecast_history
    print("\n3. Records in 'forecast_history':")
    try:
        cursor.execute("SELECT * FROM forecast_history")
        rows = [dict(row) for row in cursor.fetchall()]
        print(f"Total Rows: {len(rows)}")
        if rows:
            print("Latest Row Content:")
            print(json.dumps(rows[-1], indent=2))
    except Exception as e:
        print(f"[Error] Failed to read rows: {e}")
        
    conn.close()
    print("\n=== Diagnostic Completed ===")

if __name__ == "__main__":
    run_db_diagnostic()
