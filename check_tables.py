from logs.database import get_connection
conn = get_connection()
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(tables)
