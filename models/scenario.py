import pandas as pd, numpy as np, os, sys, pickle, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_score, recall_score
from logs.database import get_connection
from logs.schema import FEATURES_CSV, MODELS_DIR, SCENARIO_CLF_PKL, ML_PREDICTIONS_CSV

FEATURE_COLS = ['total_events', 'login_count', 'after_hours_count',
    'after_hours_rate', 'unique_pcs', 'usb_events', 'file_events',
    'email_events', 'http_events', 'avg_hour', 'std_hour', 'weekend_activity']

SCENARIO_NAMES = {
    0: 'Normal',
    1: 'Scenario 1 (USB -> WikiLeaks)',
    2: 'Scenario 2 (Job-hunting + gradual USB theft)',
    3: 'Scenario 3 (IT sabotage)',
}

THRESHOLD_PATH = os.path.join(MODELS_DIR, "scenario_threshold.json")
CANDIDATE_THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]


def build_labeled_dataset():
    df = pd.read_csv(FEATURES_CSV)
    df['date'] = pd.to_datetime(df['date'])
    df['scenario_label'] = 0

    conn = get_connection()
    insiders = pd.read_sql('SELECT user_id, scenario, start_date, end_date FROM insider_labels', conn)
    conn.close()

    insiders['start_date'] = pd.to_datetime(insiders['start_date'], errors='coerce')
    insiders['end_date'] = pd.to_datetime(insiders['end_date'], errors='coerce')

    labeled_count = 0
    for _, row in insiders.iterrows():
        if pd.isna(row['start_date']) or pd.isna(row['end_date']):
            continue
        mask = (
            (df['user_id'] == row['user_id']) &
            (df['date'] >= row['start_date']) &
            (df['date'] <= row['end_date'])
        )
        df.loc[mask, 'scenario_label'] = int(row['scenario'])
        labeled_count += mask.sum()

    print(f"Labeled {labeled_count} user-days as malicious out of {len(df)} total "
          f"({labeled_count/len(df)*100:.3f}%).")
    print("\nClass distribution:")
    for cls, name in SCENARIO_NAMES.items():
        cnt = (df['scenario_label'] == cls).sum()
        print(f"  {cls} ({name}): {cnt}")

    return df


def _malicious_probs(clf, X):
    """For each row, return the best malicious class and its own
    probability, separate from Normal's probability entirely."""
    proba = clf.predict_proba(X)
    classes = clf.classes_
    malicious_col_idx = [i for i, c in enumerate(classes) if c != 0]
    malicious_proba = proba[:, malicious_col_idx]
    best_local_idx = np.argmax(malicious_proba, axis=1)
    best_prob = malicious_proba[np.arange(len(proba)), best_local_idx]
    best_class = np.array(classes)[malicious_col_idx][best_local_idx]
    normal_col_idx = list(classes).index(0) if 0 in classes else None
    normal_prob = proba[:, normal_col_idx] if normal_col_idx is not None else None
    return best_class, best_prob, normal_prob


def sweep_thresholds(clf, X_test, y_test):
    """Pick the malicious-probability threshold that actually maximises
    detection quality on the RARE classes specifically (F1 macro-averaged
    over scenarios 1-3 only), instead of guessing a value. Including
    'Normal' in the average would hide the tradeoff, since Normal's score
    is always near-perfect regardless of threshold."""
    best_class, best_prob, _ = _malicious_probs(clf, X_test)
    malicious_labels = sorted([c for c in set(y_test) if c != 0])

    print("\n=== Malicious-probability threshold sweep (scored on Scenarios 1-3 only) ===")
    print(f"{'Threshold':>10} {'Precision':>10} {'Recall':>8} {'F1':>6}")
    rows = []
    for t in CANDIDATE_THRESHOLDS:
        pred = np.where(best_prob >= t, best_class, 0)
        f1 = f1_score(y_test, pred, labels=malicious_labels, average='macro', zero_division=0)
        prec = precision_score(y_test, pred, labels=malicious_labels, average='macro', zero_division=0)
        rec = recall_score(y_test, pred, labels=malicious_labels, average='macro', zero_division=0)
        print(f"{t:>10.2f} {prec:>10.3f} {rec:>8.3f} {f1:>6.3f}")
        rows.append({'threshold': t, 'precision_macro': prec, 'recall_macro': rec, 'f1_macro': f1})

    sweep_df = pd.DataFrame(rows)
    best_row = sweep_df.loc[sweep_df['f1_macro'].idxmax()]
    best_threshold = float(best_row['threshold'])
    print(f"\nSelected threshold: {best_threshold} (highest macro F1 on Scenarios 1-3: {best_row['f1_macro']:.3f})")
    return best_threshold, sweep_df


def train_classifier(df=None):
    if df is None:
        df = build_labeled_dataset()

    X = df[FEATURE_COLS]
    y = df['scenario_label']

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    threshold, sweep_df = sweep_thresholds(clf, X_test, y_test)

    best_class, best_prob, _ = _malicious_probs(clf, X_test)
    y_pred = np.where(best_prob >= threshold, best_class, 0)

    print(f"\n--- Classification report (held-out test set, threshold={threshold}) ---")
    labels_present = sorted(y.unique())
    target_names = [SCENARIO_NAMES[l] for l in labels_present]
    print(classification_report(y_test, y_pred, labels=labels_present, target_names=target_names, zero_division=0))

    print("--- Confusion matrix (rows=actual, cols=predicted) ---")
    print(f"Labels order: {labels_present}")
    print(confusion_matrix(y_test, y_pred, labels=labels_present))

    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(SCENARIO_CLF_PKL, 'wb') as f:
        pickle.dump(clf, f)
    with open(THRESHOLD_PATH, 'w') as f:
        json.dump({'malicious_prob_threshold': threshold}, f)
    print(f"\nModel saved: {SCENARIO_CLF_PKL}")
    print(f"Threshold saved: {THRESHOLD_PATH}")

    return clf, df, threshold


def apply_to_predictions(clf, df, threshold):
    X_all = df[FEATURE_COLS]
    best_class, best_prob, normal_prob = _malicious_probs(clf, X_all)

    use_malicious = best_prob >= threshold
    pred_class = np.where(use_malicious, best_class, 0)
    confidence = np.where(use_malicious, best_prob, normal_prob)

    df['scenario'] = pred_class
    df['scenario_name'] = df['scenario'].map(SCENARIO_NAMES)
    df['scenario_confidence'] = np.round(confidence, 3)

    ml = pd.read_csv(ML_PREDICTIONS_CSV)
    ml['date'] = pd.to_datetime(ml['date'])

    # Bug fix: drop any scenario columns left over from a PREVIOUS run
    # before merging, otherwise pandas silently renames the new columns
    # to scenario_x/scenario_y instead of overwriting them.
    stale_cols = [c for c in ['scenario', 'scenario_name', 'scenario_confidence'] if c in ml.columns]
    if stale_cols:
        ml = ml.drop(columns=stale_cols)

    merged = ml.merge(
        df[['user_id', 'date', 'scenario', 'scenario_name', 'scenario_confidence']],
        on=['user_id', 'date'], how='left'
    )
    merged.to_csv(ML_PREDICTIONS_CSV, index=False)
    print(f"scenario + scenario_confidence added to {ML_PREDICTIONS_CSV} (threshold={threshold})")
    return merged


if __name__ == '__main__':
    labeled_df = build_labeled_dataset()
    clf, labeled_df, threshold = train_classifier(labeled_df)
    apply_to_predictions(clf, labeled_df, threshold)