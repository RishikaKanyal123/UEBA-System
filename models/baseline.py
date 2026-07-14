import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.schema import FEATURES_CSV, BASELINES_CSV, RISK_SCORES_CSV, PROCESSED_DIR

FEATURE_COLS = ['total_events', 'login_count', 'after_hours_count',
    'after_hours_rate', 'unique_pcs', 'usb_events', 'file_events',
    'email_events', 'http_events', 'avg_hour', 'std_hour', 'weekend_activity']

FEATURE_WEIGHTS = {
    'usb_events':        3.0,
    'after_hours_count': 2.5,
    'after_hours_rate':  2.5,
    'file_events':       2.0,
    'unique_pcs':        2.0,
    'weekend_activity':  1.5,
    'email_events':      1.5,
    'http_events':       1.0,
    'login_count':       1.0,
    'avg_hour':          1.0,
    'std_hour':          1.0,
    'total_events':      0.5,
}

# Features where only an INCREASE above personal baseline is a risk signal.
# e.g. less USB activity than usual isn't suspicious, only MORE is.
# avg_hour, total_events, login_count, weekend_activity stay two-directional:
# a shift in EITHER direction from someone's personal routine is meaningful.
ONE_DIRECTIONAL = {
    'usb_events', 'after_hours_count', 'after_hours_rate',
    'file_events', 'email_events', 'http_events', 'unique_pcs', 'std_hour',
}

TOTAL_WEIGHT = sum(FEATURE_WEIGHTS.values())
Z_CAP = 6.0
SCALE = 25.0
MIN_DAYS_FOR_BASELINE = 10


def compute_risk_scores(features_df=None, baselines_df=None):
    if features_df is None:
        features_df = pd.read_csv(FEATURES_CSV)
    if baselines_df is None:
        baselines_df = pd.read_csv(BASELINES_CSV)

    df = features_df.merge(baselines_df, on='user_id', how='left')

    before = len(df)
    df = df.dropna(subset=['days_of_data'])
    df = df[df['days_of_data'] >= MIN_DAYS_FOR_BASELINE]
    skipped = before - len(df)
    if skipped:
        print(f'  Skipping {skipped} rows (cold start / insufficient baseline days).')

    if df.empty:
        print('  No users have enough data to score yet.')
        return df

    z_cols, contrib_cols = [], []

    for col in FEATURE_COLS:
        mean_col, std_col = f'{col}_mean', f'{col}_std'
        raw_z = (df[col] - df[mean_col]) / df[std_col]

        if col in ONE_DIRECTIONAL:
            # Only reward deviation in the risky direction (increase).
            z = raw_z.clip(lower=0, upper=Z_CAP).fillna(0)
        else:
            z = raw_z.clip(lower=-Z_CAP, upper=Z_CAP).fillna(0)

        z_col, contrib_col = f'{col}_z', f'{col}_contrib'
        df[z_col] = z
        df[contrib_col] = z.abs() * FEATURE_WEIGHTS[col]
        z_cols.append(z_col)
        contrib_cols.append(contrib_col)

    df['risk_score'] = (
        df[contrib_cols].sum(axis=1) / TOTAL_WEIGHT * SCALE
    ).clip(0, 100).round(2)

    z_matrix = df[z_cols].to_numpy()
    contrib_matrix = df[contrib_cols].to_numpy()
    top_idx = contrib_matrix.argmax(axis=1)

    df['top_reason'] = np.array(FEATURE_COLS)[top_idx]
    df['top_zscore'] = z_matrix[np.arange(len(df)), top_idx].round(2)

    out_cols = ['user_id', 'date', 'risk_score', 'top_reason', 'top_zscore'] + FEATURE_COLS
    result = df[out_cols].sort_values('risk_score', ascending=False)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    result.to_csv(RISK_SCORES_CSV, index=False)
    print(f'Risk scores computed: {len(result)} rows, {result["user_id"].nunique()} users')
    return result


def show_top_risky(n=10):
    df = pd.read_csv(RISK_SCORES_CSV)
    top = df.sort_values('risk_score', ascending=False).head(n)
    print(f'\nTop {n} riskiest user-days:')
    print(top[['user_id', 'date', 'risk_score', 'top_reason', 'top_zscore']].to_string(index=False))
    return top


if __name__ == '__main__':
    compute_risk_scores()
    show_top_risky(10)