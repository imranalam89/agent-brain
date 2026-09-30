import sqlite3

conn = sqlite3.connect("data/trading_brain.db")
cursor = conn.cursor()
cursor.execute("SELECT orderflow_notes, count(*) FROM trades GROUP BY orderflow_notes ORDER BY count(*) DESC LIMIT 20")
print("--- Top Orderflow Notes ---")
for r in cursor.fetchall():
    print(f"  {r[1]:<4} | {r[0]}")

cursor.execute("SELECT conviction_stars, count(*), sum(pnl_usd), avg(pnl_usd > 0)*100 FROM trades GROUP BY conviction_stars")
print("\n--- Conviction Stars ---")
for r in cursor.fetchall():
    print(r)
