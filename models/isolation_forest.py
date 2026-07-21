import pandas as pd, numpy as np, os, sys, time, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from logs.schema import FEATURES_CSV, PROCESSED_DIR, MODELS_DIR, IF_MODELS_PKL, SCALERS_PKL, ML_PREDICTIONS_CSV

FEATURE_COLS = ['total_events', 'login_count', 'after_hours_count',
    'after_hours_rate', 'unique_pcs', 'usb_events', 'file_events',
    'email_events', 'http_events', 'avg_hour', 'std_hour', 'weekend_activity']

# Same cold-start threshold as baseline.py, so results stay comparable
# between the two detection methods.
MIN_DAYS_FOR_MODEL = 10

# We expect roughly 5% of any user's days to be anomalous — matches the
# project doc's stated design (Section 5.3).
CONTAMINATION = 0.05


def train_and_score():
    df = pd.read_csv(FEATURES_CSV)
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    models = {}
    scalers = {}
    results = []

    users = df['user_id'].unique()
    print(f"Training Isolation Forest for {len(users)} users...", flush=True)
    t_start = time.time()
    skipped = 0

    for i, uid in enumerate(users, 1):
        g = df[df['user_id'] == uid].sort_values('date').reset_index(drop=True)

        if len(g) < MIN_DAYS_FOR_MODEL:
            skipped += 1
            continue

        X = g[FEATURE_COLS].values

        # Isolation Forest is distance/split-based, so features need to be
        # on comparable scales first (e.g. avg_hour ~0-23 vs http_events
        # possibly in the hundreds) — StandardScaler handles that per user.
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = IsolationForest(
            contamination=CONTAMINATION,
            random_state=42,
            n_estimators=100,
        )
        preds = model.fit_predict(X_scaled)         # -1 = anomaly, 1 = normal
        scores = model.decision_function(X_scaled)   # higher = more normal

        models[uid] = model
        scalers[uid] = scaler

        for j in range(len(g)):
            results.append({
                'user_id': uid,
                'date': g.loc[j, 'date'],
                'ml_anomaly': 1 if preds[j] == -1 else 0,
                'ml_raw_score': scores[j],
            })

        if i % 100 == 0 or i == len(users):
            print(f"  [{i}/{len(users)}] trained | total {round(time.time()-t_start,1)}s", flush=True)

    result_df = pd.DataFrame(results)

    # Rescale so HIGHER ml_score = more anomalous, 0-100 — directly
    # comparable to baseline.py's risk_score, since decision_function's
    # native convention (lower = more anomalous) is the opposite of that.
    lo, hi = result_df['ml_raw_score'].min(), result_df['ml_raw_score'].max()
    result_df['ml_score'] = ((hi - result_df['ml_raw_score']) / (hi - lo) * 100).round(2)
    result_df = result_df.drop(columns=['ml_raw_score'])

    result_df.to_csv(ML_PREDICTIONS_CSV, index=False)

    with open(IF_MODELS_PKL, 'wb') as f:
        pickle.dump(models, f)
    with open(SCALERS_PKL, 'wb') as f:
        pickle.dump(scalers, f)

    print(f"\nSkipped {skipped} users (fewer than {MIN_DAYS_FOR_MODEL} days of data).")
    print(f"ml_predictions.csv written: {len(result_df)} rows, {result_df['user_id'].nunique()} users")
    print(f"Models saved: {IF_MODELS_PKL}")
    print(f"Scalers saved: {SCALERS_PKL}")
    return result_df


def show_top_anomalies(n=10):
    df = pd.read_csv(ML_PREDICTIONS_CSV)
    top = df[df['ml_anomaly'] == 1].sort_values('ml_score', ascending=False).head(n)
    print(f"\nTop {n} Isolation Forest anomalies:")
    print(top[['user_id', 'date', 'ml_anomaly', 'ml_score']].to_string(index=False))
    return top


if __name__ == '__main__':
    train_and_score()
    show_top_anomalies(10)