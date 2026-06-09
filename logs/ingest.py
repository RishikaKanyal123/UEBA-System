# logs/ingest.py
import pandas as pd
import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.schema import (
    is_after_hours,
    EVENT_LOGON, EVENT_LOGOFF,
    EVENT_USB_CONNECT, EVENT_USB_DISCONNECT,
    EVENT_FILE, EVENT_EMAIL, EVENT_HTTP,
)
from logs.database import get_connection, create_tables

RAW_DIR = "data/raw/r4.2"
CHUNK_SIZE = 50_000   # rows per chunk for large files


# ── helpers ────────────────────────────────────────────────────────

def _dt_features(dt):
    return int(is_after_hours(dt)), dt.weekday(), dt.hour


def _insert_many(cursor, rows):
    cursor.executemany("""
        INSERT OR IGNORE INTO events (
            event_id, timestamp, user_id, pc, event_type,
            details, content,
            email_from, email_to, email_cc, email_bcc,
            email_size, email_attachments,
            is_after_hours, day_of_week, hour_of_day
        ) VALUES (
            ?,?,?,?,?,
            ?,?,
            ?,?,?,?,
            ?,?,
            ?,?,?
        )
    """, rows)


# ── logon.csv ──────────────────────────────────────────────────────

def ingest_logon(filepath):
    print(f"Ingesting: {filepath}")
    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date'])

    conn = get_connection()
    c = conn.cursor()
    rows = []

    for _, r in df.iterrows():
        dt = r['date']
        activity = str(r.get('activity', '')).strip().lower()
        etype = EVENT_LOGON if activity == 'logon' else EVENT_LOGOFF
        iah, dow, hod = _dt_features(dt)
        rows.append((
            str(r['id']), dt.strftime('%Y-%m-%d %H:%M:%S'),
            str(r['user']).upper(), str(r['pc']),
            etype,
            str(r.get('activity', '')), None,
            None, None, None, None, None, None,
            iah, dow, hod,
        ))

    _insert_many(c, rows)
    conn.commit()
    conn.close()
    print(f"  → {len(rows):,} logon rows inserted")


# ── device.csv ─────────────────────────────────────────────────────

def ingest_device(filepath):
    print(f"Ingesting: {filepath}")
    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date'])

    conn = get_connection()
    c = conn.cursor()
    rows = []

    for _, r in df.iterrows():
        dt = r['date']
        activity = str(r.get('activity', '')).strip().lower()
        etype = EVENT_USB_CONNECT if activity == 'connect' else EVENT_USB_DISCONNECT
        iah, dow, hod = _dt_features(dt)
        rows.append((
            str(r['id']), dt.strftime('%Y-%m-%d %H:%M:%S'),
            str(r['user']).upper(), str(r['pc']),
            etype,
            str(r.get('activity', '')), None,
            None, None, None, None, None, None,
            iah, dow, hod,
        ))

    _insert_many(c, rows)
    conn.commit()
    conn.close()
    print(f"  → {len(rows):,} device rows inserted")


# ── file.csv ───────────────────────────────────────────────────────

def ingest_file(filepath):
    print(f"Ingesting: {filepath}")
    df = pd.read_csv(filepath)
    df['date'] = pd.to_datetime(df['date'])

    conn = get_connection()
    c = conn.cursor()
    rows = []

    for _, r in df.iterrows():
        dt = r['date']
        iah, dow, hod = _dt_features(dt)
        rows.append((
            str(r['id']), dt.strftime('%Y-%m-%d %H:%M:%S'),
            str(r['user']).upper(), str(r['pc']),
            EVENT_FILE,
            str(r.get('filename', ''))[:300],
            str(r.get('content', ''))[:500] if pd.notna(r.get('content')) else None,
            None, None, None, None, None, None,
            iah, dow, hod,
        ))

    _insert_many(c, rows)
    conn.commit()
    conn.close()
    print(f"  → {len(rows):,} file rows inserted")


# ── email.csv (chunked — file is ~1.3 GB) ─────────────────────────

def ingest_email(filepath):
    print(f"Ingesting: {filepath}  (reading in chunks...)")
    conn = get_connection()
    c = conn.cursor()
    total = 0

    for chunk in pd.read_csv(filepath, chunksize=CHUNK_SIZE):
        chunk['date'] = pd.to_datetime(chunk['date'])
        rows = []
        for _, r in chunk.iterrows():
            dt = r['date']
            iah, dow, hod = _dt_features(dt)
            rows.append((
                str(r['id']), dt.strftime('%Y-%m-%d %H:%M:%S'),
                str(r['user']).upper(), str(r['pc']),
                EVENT_EMAIL,
                str(r.get('to', ''))[:300],
                str(r.get('content', ''))[:500] if pd.notna(r.get('content')) else None,
                str(r.get('from', '')) if pd.notna(r.get('from')) else None,
                str(r.get('to', ''))   if pd.notna(r.get('to'))   else None,
                str(r.get('cc', ''))   if pd.notna(r.get('cc'))   else None,
                str(r.get('bcc', ''))  if pd.notna(r.get('bcc'))  else None,
                int(r['size']) if pd.notna(r.get('size')) else None,
                int(r['attachments']) if pd.notna(r.get('attachments')) else None,
                iah, dow, hod,
            ))
        _insert_many(c, rows)
        conn.commit()
        total += len(rows)
        print(f"    {total:,} email rows so far...")

    conn.close()
    print(f"  → {total:,} email rows inserted total")


# ── http.csv (chunked — file is over 1 GB) ────────────────────────

def ingest_http(filepath):
    print(f"Ingesting: {filepath}  (reading in chunks...)")
    conn = get_connection()
    c = conn.cursor()
    total = 0

    for chunk in pd.read_csv(filepath, chunksize=CHUNK_SIZE):
        chunk['date'] = pd.to_datetime(chunk['date'])
        rows = []
        for _, r in chunk.iterrows():
            dt = r['date']
            iah, dow, hod = _dt_features(dt)
            rows.append((
                str(r['id']), dt.strftime('%Y-%m-%d %H:%M:%S'),
                str(r['user']).upper(), str(r['pc']),
                EVENT_HTTP,
                str(r.get('url', ''))[:500],
                str(r.get('content', ''))[:500] if pd.notna(r.get('content')) else None,
                None, None, None, None, None, None,
                iah, dow, hod,
            ))
        _insert_many(c, rows)
        conn.commit()
        total += len(rows)
        print(f"    {total:,} http rows so far...")

    conn.close()
    print(f"  → {total:,} http rows inserted total")


# ── psychometric.csv ──────────────────────────────────────────────

def ingest_psychometric(filepath):
    print(f"Ingesting: {filepath}")
    df = pd.read_csv(filepath)
    conn = get_connection()
    c = conn.cursor()

    rows = []
    for _, r in df.iterrows():
        rows.append((
            str(r['user_id']).upper(),
            str(r.get('employee', '')),
            float(r['O']) if pd.notna(r.get('O')) else None,
            float(r['C']) if pd.notna(r.get('C')) else None,
            float(r['E']) if pd.notna(r.get('E')) else None,
            float(r['A']) if pd.notna(r.get('A')) else None,
            float(r['N']) if pd.notna(r.get('N')) else None,
        ))

    c.executemany("""
        INSERT OR REPLACE INTO psychometric_profiles
        (user_id, employee_name, openness, conscientiousness,
         extraversion, agreeableness, neuroticism)
        VALUES (?,?,?,?,?,?,?)
    """, rows)
    conn.commit()
    conn.close()
    print(f"  → {len(rows):,} psychometric rows inserted")


# ── LDAP directory ────────────────────────────────────────────────

def ingest_ldap(ldap_dir):
    print(f"Ingesting LDAP files from: {ldap_dir}")
    conn = get_connection()
    c = conn.cursor()
    total = 0

    for fname in sorted(os.listdir(ldap_dir)):
        if not fname.endswith('.csv'):
            continue
        month = fname.replace('.csv', '')
        df = pd.read_csv(os.path.join(ldap_dir, fname))
        rows = []
        for _, r in df.iterrows():
            # LDAP column names vary slightly — use .get() safely
            rows.append((
                str(r.get('user_id', r.get('userId', ''))).upper(),
                str(r.get('employee_name', r.get('name', ''))),
                str(r.get('email', '')),
                str(r.get('role', '')),
                str(r.get('projects', '')),
                str(r.get('team', '')),
                str(r.get('supervisor', '')),
                month,
            ))
        c.executemany("""
            INSERT INTO ldap_directory
            (user_id, employee_name, email, role, projects, team, supervisor, month)
            VALUES (?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()
        total += len(rows)

    conn.close()
    print(f"  → {total:,} LDAP rows inserted")


# ── answers/insiders.csv ──────────────────────────────────────────

def ingest_insiders(filepath):
    print(f"Ingesting: {filepath}")
    df = pd.read_csv(filepath)
    # Keep only r4.2 rows
    df = df[df['dataset'].str.contains('r4.2', na=False)]

    conn = get_connection()
    c = conn.cursor()
    rows = []
    for _, r in df.iterrows():
        rows.append((
            str(r.get('dataset', '')),
            str(r.get('scenario', '')),
            str(r.get('details', '')),
            str(r['user']).upper(),
            str(r.get('start', '')),
            str(r.get('end', '')),
        ))

    c.executemany("""
        INSERT OR IGNORE INTO insider_labels
        (dataset, scenario, scenario_details, user_id, start_date, end_date)
        VALUES (?,?,?,?,?,?)
    """, rows)
    conn.commit()
    conn.close()
    print(f"  → {len(rows):,} insider label rows inserted")


# ── run all ───────────────────────────────────────────────────────

def run_full_ingestion():
    create_tables()
    print("\n=== Starting full ingestion ===\n")

    files = {
        f"{RAW_DIR}/logon.csv":        ingest_logon,
        f"{RAW_DIR}/device.csv":       ingest_device,
        f"{RAW_DIR}/file.csv":         ingest_file,
        f"{RAW_DIR}/email.csv":        ingest_email,
        f"{RAW_DIR}/http.csv":         ingest_http,
        f"{RAW_DIR}/psychometric.csv": ingest_psychometric,
    }

    for path, func in files.items():
        if os.path.exists(path):
            func(path)
        else:
            print(f"WARNING: {path} not found, skipping.")

    ldap_dir = f"{RAW_DIR}/LDAP"
    if os.path.isdir(ldap_dir):
        ingest_ldap(ldap_dir)

    insiders_path = "data/raw/answers/insiders.csv"
    if os.path.exists(insiders_path):
        ingest_insiders(insiders_path)

    print("\n=== Ingestion complete ===")
    from logs.database import get_table_info
    get_table_info()


if __name__ == "__main__":
    run_full_ingestion()