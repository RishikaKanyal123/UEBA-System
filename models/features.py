import pandas as pd, math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.database import get_connection
from logs.schema import FEATURES_CSV, BASELINES_CSV, PROCESSED_DIR

FEATURE_COLS = ['total_events','login_count','after_hours_count',
    'after_hours_rate','unique_pcs','usb_events','file_events',
    'email_events','http_events','avg_hour','std_hour','weekend_activity']

# Event categories used ONLY to compute after_hours_rate / avg_hour / std_hour
# as an equal-weighted average across categories, so a low-volume category
# (USB) isn't drowned out by a high-volume one (HTTP) when averaged.
CATEGORIES = {
    'logon': "event_type IN ('LOGON','LOGOFF')",
    'usb':   "event_type IN ('USB_CONNECT','USB_DISCONNECT')",
    'file':  "event_type = 'FILE_ACCESS'",
    'email': "event_type = 'EMAIL'",
    'http':  "event_type = 'WEB_VISIT'",
}

def _cat_cols(name, cond):
    return f"""
      SUM(CASE WHEN {cond} THEN 1 ELSE 0 END) as {name}_cnt,
      SUM(CASE WHEN {cond} AND is_after_hours=1 THEN 1 ELSE 0 END) as {name}_ah,
      SUM(CASE WHEN {cond} THEN hour_of_day ELSE 0 END) as {name}_sumh,
      SUM(CASE WHEN {cond} THEN hour_of_day*1.0*hour_of_day ELSE 0 END) as {name}_sumh2
    """

QUERY = f"""
    SELECT DATE(timestamp) as date,
      COUNT(*) as total_events,
      SUM(CASE WHEN event_type='LOGON' THEN 1 ELSE 0 END) as login_count,
      COUNT(DISTINCT pc) as unique_pcs,
      SUM(CASE WHEN is_after_hours=1 THEN 1 ELSE 0 END) as after_hours_count,
      MAX(CASE WHEN day_of_week>=5 THEN 1 ELSE 0 END) as weekend_activity,
      {','.join(_cat_cols(n, c) for n, c in CATEGORIES.items())}
    FROM events WHERE user_id = ?
    GROUP BY DATE(timestamp)
"""

def _cat_stats(row, name):
    """Return (after_hours_rate, avg_hour, std_hour) for one category on
    one day, using the algebraic std formula (SQLite has no STDEV).
    Returns None if the category had no activity that day."""
    cnt = row[f'{name}_cnt']
    if not cnt:
        return None
    ah = row[f'{name}_ah']
    sumh = row[f'{name}_sumh']
    sumh2 = row[f'{name}_sumh2']
    rate = ah / cnt
    avg_h = sumh / cnt
    if cnt > 1:
        var = (sumh2 - (sumh ** 2) / cnt) / (cnt - 1)
        std_h = math.sqrt(var) if var > 0 else 0.0
    else:
        std_h = 0.0
    return rate, avg_h, std_h


def build_daily_features():
    conn = get_connection()
    users = [r[0] for r in conn.execute("SELECT DISTINCT user_id FROM events").fetchall()]
    print(f"Found {len(users)} users. Processing one at a time...", flush=True)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out_cols = ['user_id', 'date'] + FEATURE_COLS
    buffer = []
    t_start = time.time()
    wrote_header = False

    for i, uid in enumerate(users, 1):
        t0 = time.time()
        rows = conn.execute(QUERY, (uid,)).fetchall()

        for r in rows:
            rates, avgs, stds = [], [], []
            for name in CATEGORIES:
                s = _cat_stats(r, name)
                if s:
                    rates.append(s[0]); avgs.append(s[1]); stds.append(s[2])
            # Equal-weighted mean across categories present that day —
            # each category counts once, regardless of its row volume.
            after_hours_rate = sum(rates) / len(rates) if rates else 0.0
            avg_hour = sum(avgs) / len(avgs) if avgs else 0.0
            std_hour = sum(stds) / len(stds) if stds else 0.0

            buffer.append([
                uid, r['date'],
                r['total_events'], r['login_count'], r['after_hours_count'],
                after_hours_rate, r['unique_pcs'],
                r['usb_cnt'], r['file_cnt'], r['email_cnt'], r['http_cnt'],
                avg_hour, std_hour, r['weekend_activity'],
            ])

        elapsed = time.time() - t0
        if i % 20 == 0 or elapsed > 1.0 or i == len(users):
            print(f"  [{i}/{len(users)}] user={uid} days={len(rows)} ({elapsed:.2f}s) | total {round(time.time()-t_start,1)}s", flush=True)

        if i % 100 == 0 or i == len(users):
            chunk_df = pd.DataFrame(buffer, columns=out_cols)
            chunk_df.to_csv(FEATURES_CSV, mode='a', header=not wrote_header, index=False)
            wrote_header = True
            buffer = []

    conn.close()
    result = pd.read_csv(FEATURES_CSV)
    print(f"Features built: {result.shape[0]} rows, {result['user_id'].nunique()} users", flush=True)
    return result


def build_baselines(df=None):
    if df is None:
        df = pd.read_csv(FEATURES_CSV)
    rows = []
    for uid, g in df.groupby('user_id'):
        row = {'user_id': uid, 'days_of_data': len(g)}
        for col in FEATURE_COLS:
            row[f'{col}_mean'] = g[col].mean()
            std = g[col].std()
            row[f'{col}_std'] = max(std, 0.01) if pd.notna(std) else 0.01
        rows.append(row)
    bdf = pd.DataFrame(rows)
    bdf.to_csv(BASELINES_CSV, index=False)
    print(f'Baselines computed for {len(bdf)} users', flush=True)
    return bdf


if __name__ == '__main__':
    if os.path.exists(FEATURES_CSV):
        os.remove(FEATURES_CSV)  # fresh start so append-mode doesn't duplicate old data
    feat = build_daily_features()
    build_baselines(feat)