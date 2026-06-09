# logs/database.py
# ============================================================
# SQLite database setup for the UEBA system
# Designed specifically for CERT Insider Threat Dataset r4.2
# ============================================================

import sqlite3
import os

DB_PATH = "data/ueba.db"

# ------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database (row_factory enabled)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn


# ------------------------------------------------------------------
def create_tables():
    """Create all database tables (idempotent — safe to call repeatedly)."""
    conn = get_connection()
    c = conn.cursor()

    # ── 1. EVENTS ──────────────────────────────────────────────────
    # One row per raw log entry (logon, device, file, email, http).
    # Columns that don't apply to a given event type are stored NULL.
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            -- identity
            event_id          TEXT PRIMARY KEY,   -- original CSV `id`
            timestamp         TEXT NOT NULL,       -- ISO-8601 datetime string
            user_id           TEXT NOT NULL,       -- e.g. ACM2278
            pc                TEXT,                -- e.g. PC-7362

            -- classification
            event_type        TEXT NOT NULL,       -- LOGON / LOGOFF / USB_CONNECT /
                                                   -- USB_DISCONNECT / FILE_ACCESS /
                                                   -- EMAIL / WEB_VISIT

            -- general payload
            details           TEXT,                -- activity, filename, url, etc.
            content           TEXT,                -- raw content field (file/email/http)

            -- email-specific columns (NULL for non-email events)
            email_from        TEXT,
            email_to          TEXT,
            email_cc          TEXT,
            email_bcc         TEXT,
            email_size        INTEGER,
            email_attachments INTEGER,

            -- derived time features
            is_after_hours    INTEGER DEFAULT 0,   -- 1 = outside 08:00-18:00 Mon-Fri
            day_of_week       INTEGER,             -- 0=Mon … 6=Sun
            hour_of_day       INTEGER,             -- 0-23

            -- scoring (filled by detection / ML engine)
            risk_score        REAL    DEFAULT 0.0, -- 0-100
            is_anomaly        INTEGER DEFAULT 0    -- 1 = flagged
        )
    """)

    # Index for the most common query patterns
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_user   ON events (user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_type   ON events (event_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_ts     ON events (timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_anomaly ON events (is_anomaly)")

    # ── 2. PSYCHOMETRIC PROFILES ───────────────────────────────────
    # One row per employee — Big-Five personality scores from
    # psychometric.csv (employee | user_id | O | C | E | A | N)
    c.execute("""
        CREATE TABLE IF NOT EXISTS psychometric_profiles (
            user_id              TEXT PRIMARY KEY,
            employee_name        TEXT,
            openness             REAL,        -- O
            conscientiousness    REAL,        -- C
            extraversion         REAL,        -- E
            agreeableness        REAL,        -- A
            neuroticism          REAL         -- N
        )
    """)

    # ── 3. USER BEHAVIOURAL BASELINES ──────────────────────────────
    # Statistical baseline per user, recomputed periodically by
    # models/baseline.py.  No column from the original CSVs is stored
    # here — this is all derived.
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_baselines (
            user_id                  TEXT PRIMARY KEY,

            -- login timing
            avg_logon_hour           REAL,
            std_logon_hour           REAL,

            -- volume baselines
            avg_daily_events         REAL,
            std_daily_events         REAL,
            avg_daily_emails         REAL,
            avg_daily_http           REAL,
            avg_daily_file_accesses  REAL,
            avg_daily_usb_events     REAL,

            -- after-hours baseline (fraction of events)
            after_hours_rate         REAL,

            -- known machines (JSON array, e.g. '["PC-1042","PC-0998"]')
            known_pcs                TEXT,

            -- summary counts
            total_events             INTEGER,
            last_updated             TEXT     -- ISO-8601
        )
    """)

    # ── 4. LDAP / ORG STRUCTURE ────────────────────────────────────
    # Populated from the monthly LDAP CSVs in data/raw/r4.2/LDAP/
    # Each file is named YYYY-MM.csv.  We store the most-recent row
    # per employee; month is kept so historical lookups are possible.
    c.execute("""
        CREATE TABLE IF NOT EXISTS ldap_directory (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       TEXT NOT NULL,
            employee_name TEXT,
            email         TEXT,
            role          TEXT,
            projects      TEXT,    -- may be a semicolon-separated list
            team          TEXT,
            supervisor    TEXT,
            month         TEXT     -- YYYY-MM of the source file
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ldap_user ON ldap_directory (user_id)")

    # ── 5. INSIDER LABELS (ground truth) ───────────────────────────
    # From answers/insiders.csv:
    # dataset | scenario | details | user | start | end
    c.execute("""
        CREATE TABLE IF NOT EXISTS insider_labels (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset          TEXT,            -- e.g. "r4.2"
            scenario         TEXT,            -- scenario code
            scenario_details TEXT,            -- free-text description
            user_id          TEXT NOT NULL,   -- maps to events.user_id
            start_date       TEXT,            -- ISO-8601 date string
            end_date         TEXT             -- ISO-8601 date string
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_labels_user ON insider_labels (user_id)")

    # ── 6. ALERTS ──────────────────────────────────────────────────
    # One row per alert raised by the rule / ML engine.
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id      TEXT PRIMARY KEY,          -- e.g. ALT_000001
            timestamp     TEXT NOT NULL,
            user_id       TEXT NOT NULL,
            alert_type    TEXT NOT NULL,             -- e.g. AFTER_HOURS_USB
            severity      TEXT NOT NULL,             -- LOW / MEDIUM / HIGH / CRITICAL
            description   TEXT NOT NULL,
            event_id      TEXT,                      -- triggering event (FK → events)
            is_resolved   INTEGER DEFAULT 0
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_alerts_user     ON alerts (user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts (severity)")

    conn.commit()
    conn.close()
    print("✅  All database tables created / verified successfully.")
    print(f"    Database path: {os.path.abspath(DB_PATH)}")


# ------------------------------------------------------------------
def get_table_info():
    """Print a summary of every table and its row count."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in c.fetchall()]
    print(f"\n{'Table':<30} {'Rows':>8}")
    print("-" * 40)
    for tbl in tables:
        c.execute(f"SELECT COUNT(*) FROM {tbl}")
        print(f"{tbl:<30} {c.fetchone()[0]:>8,}")
    conn.close()


# ------------------------------------------------------------------
if __name__ == "__main__":
    create_tables()
    get_table_info()