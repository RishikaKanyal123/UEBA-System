import pandas as pd, numpy as np, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.database import get_connection
from logs.schema import PROCESSED_DIR

EVALUATION_CSV = os.path.join(PROCESSED_DIR, "evaluation_report.csv")


def load_ground_truth():
    conn = get_connection()
    insiders = pd.read_sql('SELECT DISTINCT user_id FROM insider_labels', conn)
    conn.close()
    return set(insiders['user_id'])


def evaluate_by_severity():
    """The correct way to evaluate a TIERED alert system: report precision
    and recall PER SEVERITY TIER, not one blended number across all tiers.
    Blending LOW/MEDIUM (explicitly documented as 'log for trend analysis'
    / 'worth a review', not confirmed threats) with HIGH/CRITICAL into a
    single precision figure understates how the system is actually meant
    to be used and read."""
    conn = get_connection()
    alerts = pd.read_sql('SELECT user_id, severity, risk_score FROM alerts', conn)
    conn.close()
    insider_set = load_ground_truth()
    total_insiders = len(insider_set)

    print("=== Precision and Recall by Severity Tier ===\n")
    rows = []
    for sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
        tier_users = set(alerts[alerts['severity'] == sev]['user_id'])
        if not tier_users:
            continue
        hits = tier_users & insider_set
        precision = len(hits) / len(tier_users) * 100
        print(f"{sev:9s}: {len(tier_users):4d} users alerted | {len(hits):3d} real insiders | precision {precision:5.1f}%")
        rows.append({'severity': sev, 'users_alerted': len(tier_users), 'real_insiders': len(hits), 'precision_pct': round(precision, 1)})

    print("\n=== Cumulative Recall (insiders reaching AT LEAST this severity) ===\n")
    severity_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
    cumulative_users = set()
    for sev in severity_order:
        tier_users = set(alerts[alerts['severity'] == sev]['user_id'])
        cumulative_users |= tier_users
        hits = cumulative_users & insider_set
        recall = len(hits) / total_insiders * 100
        precision = len(hits) / len(cumulative_users) * 100 if cumulative_users else 0
        print(f"At least {sev:9s}: recall {recall:5.1f}% ({len(hits)}/{total_insiders}) | precision at this cutoff {precision:5.1f}%")
        rows.append({'severity': f'at_least_{sev}', 'users_alerted': len(cumulative_users), 'real_insiders': len(hits), 'precision_pct': round(precision, 1), 'recall_pct': round(recall, 1)})

    return pd.DataFrame(rows)


def threshold_sweep():
    """Precision/recall/F1 at a range of fused_score cutoffs - standard ML
    evaluation practice, and useful evidence that the deployed threshold
    (50, matching the MEDIUM severity floor) was a deliberate choice, not
    an arbitrary one."""
    conn = get_connection()
    alerts = pd.read_sql('SELECT user_id, risk_score FROM alerts', conn)
    conn.close()
    insider_set = load_ground_truth()
    total_insiders = len(insider_set)

    print("\n=== Threshold Sweep (fused_score cutoff -> precision/recall/F1) ===\n")
    print(f"{'Cutoff':>7} {'Users':>7} {'TP':>5} {'Precision':>10} {'Recall':>8} {'F1':>6}")
    rows = []
    for cutoff in [30, 40, 50, 60, 70, 80, 90]:
        users = set(alerts[alerts['risk_score'] >= cutoff]['user_id'])
        hits = users & insider_set
        precision = len(hits) / len(users) if users else 0
        recall = len(hits) / total_insiders
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(f"{cutoff:>7} {len(users):>7} {len(hits):>5} {precision*100:>9.1f}% {recall*100:>7.1f}% {f1:>6.3f}")
        rows.append({'cutoff': cutoff, 'users_alerted': len(users), 'true_positives': len(hits),
                      'precision': round(precision, 3), 'recall': round(recall, 3), 'f1': round(f1, 3)})

    return pd.DataFrame(rows)


def missed_insiders_report():
    conn = get_connection()
    alerts = pd.read_sql('SELECT DISTINCT user_id FROM alerts', conn)
    insiders = pd.read_sql('SELECT user_id, scenario, start_date, end_date FROM insider_labels', conn)
    conn.close()

    missed = insiders[~insiders['user_id'].isin(set(alerts['user_id']))]
    print(f"\n=== Insiders Never Alerted ({len(missed)}) ===\n")
    if len(missed):
        print(missed.to_string(index=False))
    return missed


if __name__ == '__main__':
    severity_df = evaluate_by_severity()
    sweep_df = threshold_sweep()
    missed_df = missed_insiders_report()

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    severity_df.to_csv(EVALUATION_CSV, index=False)
    sweep_df.to_csv(EVALUATION_CSV.replace('.csv', '_threshold_sweep.csv'), index=False)
    print(f"\nSaved: {EVALUATION_CSV}")
    print(f"Saved: {EVALUATION_CSV.replace('.csv', '_threshold_sweep.csv')}")