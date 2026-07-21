import pandas as pd
from logs.database import get_connection

conn = get_connection()

alerts = pd.read_sql('SELECT DISTINCT user_id FROM alerts', conn)
insiders = pd.read_sql('SELECT user_id, scenario FROM insider_labels', conn)

alerted_users = set(alerts['user_id'])
insider_users = set(insiders['user_id'])

caught = alerted_users & insider_users
missed = insider_users - alerted_users
false_positives = alerted_users - insider_users

print(f'Total known insiders: {len(insider_users)}')
print(f'Insiders who received at least one alert: {len(caught)} ({len(caught)/len(insider_users)*100:.1f}%)')
print(f'Insiders MISSED entirely (zero alerts): {len(missed)}')
if missed:
    missed_detail = insiders[insiders['user_id'].isin(missed)]
    print(missed_detail)
print(f'Non-insiders who got at least one alert (false positives): {len(false_positives)}')
print(f'Total unique users alerted: {len(alerted_users)}')