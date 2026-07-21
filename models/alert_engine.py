import pandas as pd, os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.database import get_connection
from logs.schema import RISK_SCORES_CSV, ML_PREDICTIONS_CSV, PROCESSED_DIR

PSYCH_MODIFIERS_CSV = os.path.join(PROCESSED_DIR, "psychometric_modifiers.csv")

# Same severity thresholds as the project doc, Section 7.3.
SEVERITY_THRESHOLDS = [(90, 'CRITICAL'), (70, 'HIGH'), (50, 'MEDIUM'), (30, 'LOW')]

# A day is escalated to an alert only if BOTH of these hold:
#   1. Detection flagged it: risk_score OR ml_score >= this threshold
#      (using the continuous ml_score rather than the binary ml_anomaly
#      flag, since Isolation Forest's per-user 5% quota can miss a real,
#      elevated signal that isn't among that specific user's most
#      extreme days - confirmed against 5 real Scenario 3 misses where
#      ml_score was 34-58 but ml_anomaly never fired)
#   2. The scenario classifier confidently assigned a real scenario (not Normal)
# This combination was validated at 83.8% precision on the confidence
# check (Findings doc, Section 7). Lowered from 50 to 30 (LOW floor)
# after diagnosing that several real insiders had real but moderate
# elevated scores that a MEDIUM-only gate discarded.
DETECTION_THRESHOLD = 30


def severity_for(score):
    for threshold, label in SEVERITY_THRESHOLDS:
        if score >= threshold:
            return label
    return None  # below LOW - no alert


def build_alerts():
    risk = pd.read_csv(RISK_SCORES_CSV)
    ml = pd.read_csv(ML_PREDICTIONS_CSV)

    if not os.path.exists(PSYCH_MODIFIERS_CSV):
        print("No psychometric_modifiers.csv found - run models/psychometric.py first.")
        return None
    psych = pd.read_csv(PSYCH_MODIFIERS_CSV)

    # Merge Z-score and Isolation Forest results on user_id + date
    merged = risk.merge(
        ml[['user_id', 'date', 'ml_anomaly', 'ml_score', 'scenario', 'scenario_name', 'scenario_confidence']],
        on=['user_id', 'date'], how='outer'
    )
    merged['risk_score'] = merged['risk_score'].fillna(0)
    merged['ml_score'] = merged['ml_score'].fillna(0)
    merged['ml_anomaly'] = merged['ml_anomaly'].fillna(0)
    merged['scenario'] = merged['scenario'].fillna(0)

    # Gate 1: was this day flagged by EITHER detection method, using the
    # continuous scores rather than the binary ml_anomaly quota flag?
    detected = (merged['risk_score'] >= DETECTION_THRESHOLD) | (merged['ml_score'] >= DETECTION_THRESHOLD)

    # Gate 2: did the scenario classifier confidently say this isn't Normal?
    scenario_confirmed = merged['scenario'] != 0

    candidates = merged[detected & scenario_confirmed].copy()
    print(f"Days flagged by detection (risk_score or ml_score >= {DETECTION_THRESHOLD}): {detected.sum()}")
    print(f"Of those, confirmed by scenario classifier (not Normal): {len(candidates)}")

    if candidates.empty:
        print("No alerts to generate.")
        return candidates

    # Base behavioural score: best of the two detection methods, per the
    # validated finding that max(risk_score, ml_score) covers every known
    # scenario's insiders without leaving any uncovered.
    candidates['base_score'] = candidates[['risk_score', 'ml_score']].max(axis=1)

    # Apply psychometric modifier - adjusts an ALREADY-raised score, never
    # creates a flag on its own (personality data is never the sole trigger).
    candidates = candidates.merge(psych, on='user_id', how='left')
    candidates['modifier'] = candidates['modifier'].fillna(1.0)  # no profile = neutral
    candidates['fused_score'] = (candidates['base_score'] * candidates['modifier']).clip(0, 100).round(2)

    candidates['severity'] = candidates['fused_score'].apply(severity_for)
    candidates = candidates[candidates['severity'].notna()]

    # Human-readable description, e.g.
    # "USB activity 4.2 standard deviations above this user's baseline"
    def describe(row):
        reason = row['top_reason'].replace('_', ' ') if pd.notna(row.get('top_reason')) else 'behavioural pattern'
        z = row.get('top_zscore', None)
        z_part = f" ({z:.1f} std devs above baseline)" if pd.notna(z) else ""
        scenario_part = f" Matches {row['scenario_name']}" if pd.notna(row.get('scenario_name')) else ""
        conf_part = f" (confidence {row['scenario_confidence']:.2f})" if pd.notna(row.get('scenario_confidence')) else ""
        return f"Elevated {reason}{z_part}.{scenario_part}{conf_part}"

    candidates['description'] = candidates.apply(describe, axis=1)
    candidates['alert_id'] = candidates.apply(lambda r: f"ALT_{r['user_id']}_{r['date']}", axis=1)
    candidates['timestamp'] = pd.to_datetime(candidates['date']).astype(str)

    return candidates[[
        'alert_id', 'timestamp', 'user_id', 'scenario_name', 'severity',
        'description', 'fused_score', 'base_score', 'modifier'
    ]]


def write_to_db(alerts_df):
    if alerts_df is None or alerts_df.empty:
        print("Nothing to write.")
        return

    conn = get_connection()
    c = conn.cursor()
    rows = [
        (
            r['alert_id'], r['timestamp'], r['user_id'],
            r['scenario_name'] if pd.notna(r['scenario_name']) else 'Unknown',
            r['severity'], r['description'], None, float(r['fused_score']), 0,
        )
        for _, r in alerts_df.iterrows()
    ]
    c.executemany("""
        INSERT OR REPLACE INTO alerts
        (alert_id, timestamp, user_id, alert_type, severity, description, event_id, risk_score, is_resolved)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, rows)
    conn.commit()
    conn.close()
    print(f"{len(rows)} alerts written to the alerts table.")


def show_summary(alerts_df):
    if alerts_df is None or alerts_df.empty:
        return
    print("\nSeverity breakdown:")
    print(alerts_df['severity'].value_counts())
    print("\nTop 10 alerts by fused_score:")
    print(alerts_df.sort_values('fused_score', ascending=False).head(10)[
        ['user_id', 'severity', 'fused_score', 'scenario_name']
    ].to_string(index=False))


if __name__ == '__main__':
    alerts = build_alerts()
    write_to_db(alerts)
    show_summary(alerts)