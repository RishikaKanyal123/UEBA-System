import sqlite3
import os

DB_PATH = "data/ueba.db"

def get_connection():
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Returns rows as dictionaries
    return conn

def create_tables():
    """Create all database tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Main events table — stores every log event
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id      TEXT PRIMARY KEY,
            timestamp     TEXT NOT NULL,
            user_id       TEXT NOT NULL,
            event_type    TEXT NOT NULL,
            source_ip     TEXT,
            hostname      TEXT,
            details       TEXT,
            is_after_hours INTEGER DEFAULT 0,
            day_of_week   INTEGER,
            hour_of_day   INTEGER,
            risk_score    REAL DEFAULT 0.0,
            is_anomaly    INTEGER DEFAULT 0
        )
    """)

    # User profiles table — one row per user, updated regularly
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id              TEXT PRIMARY KEY,
            avg_login_hour       REAL,
            std_login_hour       REAL,
            avg_daily_events     REAL,
            std_daily_events     REAL,
            known_ips            TEXT,   -- JSON list of known IPs
            known_hosts          TEXT,   -- JSON list of known machines
            after_hours_rate     REAL,   -- % of events after hours (baseline)
            total_events         INTEGER,
            last_updated         TEXT
        )
    """)

    # Alerts table — one row per alert generated
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id      TEXT PRIMARY KEY,
            timestamp     TEXT NOT NULL,
            user_id       TEXT NOT NULL,
            alert_type    TEXT NOT NULL,
            severity      TEXT NOT NULL,  -- LOW, MEDIUM, HIGH, CRITICAL
            description   TEXT NOT NULL,
            event_id      TEXT,           -- The event that triggered it
            is_resolved   INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print("Database tables created successfully.")

if __name__ == "__main__":
    create_tables()