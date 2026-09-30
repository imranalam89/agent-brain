import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("data/trading_brain.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM trades WHERE symbol='BTCUSD' AND close_reason='VWAP REVERSION' LIMIT 3")
cols = [d[0] for d in cursor.description]
print("--- Sample VWAP Reversion Win ---")
for r in cursor.fetchall():
    d = dict(zip(cols, r))
    for k, v in d.items():
        print(f"  {k}: {v}")
    print()

cursor.execute("SELECT * FROM trades WHERE symbol='BTCUSD' AND close_reason='SL' LIMIT 3")
print("\n--- Sample SL Loss ---")
for r in cursor.fetchall():
    d = dict(zip(cols, r))
    for k, v in d.items():
        print(f"  {k}: {v}")
    print()

cursor.execute("SELECT min(opened_at), max(opened_at), count(*) FROM trades")
print("\nDate range:", cursor.fetchall())
