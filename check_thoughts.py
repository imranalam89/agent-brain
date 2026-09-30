import sqlite3

conn = sqlite3.connect("data/trading_brain.db")
cursor = conn.cursor()
cursor.execute("SELECT thought, context, timestamp FROM brain_thoughts ORDER BY timestamp LIMIT 10")
print("--- Brain Thoughts ---")
for r in cursor.fetchall():
    print(f"[{r[2]}] {r[0]} | Context: {r[1]}")

cursor.execute("SELECT distinct strategy_name, count(*) FROM trades GROUP BY strategy_name")
print("\n--- Distinct Strategies in DB ---")
for r in cursor.fetchall():
    name = r[0].encode('ascii', 'replace').decode('ascii')
    print(f"{r[1]} | {name}")
