import pandas as pd, numpy as np, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.database import get_connection
from logs.schema import FEATURES_CSV, BASELINES_CSV, PROCESSED_DIR
 
FEATURE_COLS = ['total_events','login_count','after_hours_count',
    'after_hours_rate','unique_pcs','usb_events','file_events',
    'email_events','http_events','avg_hour','std_hour','weekend_activity']
 
def build_daily_features():
    conn = get_connection()
    df = pd.read_sql('''
        SELECT user_id, DATE(timestamp) as date,
          COUNT(*) as total_events,
          SUM(CASE WHEN event_type='LOGON' THEN 1 ELSE 0 END) as login_count,
          SUM(CASE WHEN is_after_hours=1 THEN 1 ELSE 0 END) as after_hours_count,
          CAST(SUM(CASE WHEN is_after_hours=1 THEN 1 ELSE 0 END) AS FLOAT)/COUNT(*) as after_hours_rate,
          COUNT(DISTINCT pc) as unique_pcs,
         SUM(CASE WHEN event_type IN ('USB_CONNECT','USB_DISCONNECT') THEN 1 ELSE 0 END) as usb_events,
SUM(CASE WHEN event_type='FILE_ACCESS' THEN 1 ELSE 0 END) as file_events,
SUM(CASE WHEN event_type='EMAIL' THEN 1 ELSE 0 END) as email_events,
SUM(CASE WHEN event_type='WEB_VISIT' THEN 1 ELSE 0 END) as http_events,
          AVG(hour_of_day) as avg_hour,
          MAX(CASE WHEN day_of_week>=5 THEN 1 ELSE 0 END) as weekend_activity
        FROM events GROUP BY user_id, DATE(timestamp) ORDER BY user_id, date''', conn)
    conn.close()
 
    # Compute std_hour separately (SQLite has no STDEV function)
    conn2 = get_connection()
    h = pd.read_sql('SELECT user_id, DATE(timestamp) as date, hour_of_day FROM events', conn2)
    conn2.close()
    std_h = h.groupby(['user_id','date'])['hour_of_day'].std().reset_index()
    std_h.columns = ['user_id','date','std_hour']
    df = df.merge(std_h, on=['user_id','date'], how='left').fillna(0)
 
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    df.to_csv(FEATURES_CSV, index=False)
    print(f'Features built: {df.shape[0]} rows, {df["user_id"].nunique()} users')
    return df
 
def build_baselines(df=None):
    if df is None: df = pd.read_csv(FEATURES_CSV)
    rows = []
    for uid, g in df.groupby('user_id'):
        row = {'user_id': uid, 'days_of_data': len(g)}
        for col in FEATURE_COLS:
            row[f'{col}_mean'] = g[col].mean()
            row[f'{col}_std']  = max(g[col].std(), 0.01)  # avoid zero
        rows.append(row)
    bdf = pd.DataFrame(rows)
    bdf.to_csv(BASELINES_CSV, index=False)
    print(f'Baselines computed for {len(bdf)} users')
    return bdf
 
if __name__ == '__main__':
    feat = build_daily_features()
    build_baselines(feat)
