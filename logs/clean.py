import sqlite3, pandas as pd, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.database import get_connection
 
def remove_duplicates():
    conn = get_connection()
    conn.execute('''
        DELETE FROM events WHERE rowid NOT IN (
          SELECT MIN(rowid) FROM events
          GROUP BY timestamp, user_id, event_type, pc)''')
    removed = conn.execute('SELECT changes()').fetchone()[0]
    conn.commit(); conn.close()
    print(f'Removed {removed} duplicate events')
 
def remove_null_users():
    conn = get_connection()
    conn.execute("DELETE FROM events WHERE user_id IS NULL OR user_id IN ('','UNKNOWN')")
    removed = conn.execute('SELECT changes()').fetchone()[0]
    conn.commit(); conn.close()
    print(f'Removed {removed} events with no user')
 
def normalise_user_ids():
    conn = get_connection()
    conn.execute('UPDATE events SET user_id = UPPER(TRIM(user_id))')
    conn.commit(); conn.close()
    print('User IDs normalised to uppercase')
 
if __name__ == '__main__':
    remove_duplicates()
    remove_null_users()
    normalise_user_ids()
    print('Cleaning complete.')