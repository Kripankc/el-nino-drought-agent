import os
import sqlite3
from ensa.config import DB_PATH, BASE_DIR

def get_db_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(force_recreate=False):
    """Initializes the database using the schema.sql file. Recreates if force_recreate is True."""
    schema_path = os.path.join(BASE_DIR, "ensa", "db", "schema.sql")
    
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found at {schema_path}")
        
    if force_recreate and os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("[Database] Cleaned old database to avoid structural conflicts.")
        except Exception as e:
            print(f"[Database Warning] Could not remove old database file: {e}")

    conn = get_db_connection()
    try:
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        conn.commit()
        print(f"Database successfully initialized at {DB_PATH}")
    except sqlite3.Error as e:
        print(f"An error occurred while initializing the database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db(force_recreate=True)
