import pandas as pd
from logs.database import get_connection

conn = get_connection()
insiders = pd.read_sql('SELECT user_id, scenario, start_date, end_date FROM insider_labels', conn)
alerts = pd.read_sql('SELECT DISTINCT user_id FROM alerts', conn)

missed_ids = set(insiders['user_id']) - set(alerts['user_id'])
missed = insiders[insiders['user_id'].isin(missed_ids)]

risk = pd.read_csv('data/processed/risk_scores.csv')
ml = pd.read_csv('data/processed/ml_predictions.csv')
ml['date'] = pd.to_datetime(ml['date'])
risk['date'] = pd.to_datetime(risk['date'])

print("For each missed insider, best detection scores during their malicious window:\n")
for _, row in missed.iterrows():
    uid = row['user_id']
    start, end = pd.to_datetime(row['start_date']), pd.to_datetime(row['end_date'])

    r_window = risk[(risk['user_id'] == uid) & (risk['date'] >= start) & (risk['date'] <= end)]
    m_window = ml[(ml['user_id'] == uid) & (ml['date'] >= start) & (ml['date'] <= end)]

    max_risk = r_window['risk_score'].max() if len(r_window) else None
    max_ml = m_window['ml_score'].max() if len(m_window) else None
    scenarios_predicted = m_window['scenario'].unique().tolist() if len(m_window) else []

    print(f"{uid} (scenario {row['scenario']}): max risk_score={max_risk}, max ml_score={max_ml}, "
          f"classifier predicted scenarios during window={scenarios_predicted}")