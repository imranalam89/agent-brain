import sqlite3
from pathlib import Path

db_path = Path("data/trading_brain.db")
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT count(*), sum(pnl_usd) FROM trades")
print("Total trades in DB:", c.fetchall())

c.execute("SELECT symbol, count(*), sum(pnl_usd) FROM trades GROUP BY symbol")
for row in c.fetchall():
    print("Symbol summary:", row)

c.execute("SELECT strategy_name, count(*), sum(pnl_usd) FROM trades GROUP BY strategy_name")
for row in c.fetchall():
    print("Strategy summary:", row)
