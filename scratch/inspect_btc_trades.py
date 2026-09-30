import sys
import sqlite3
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

db_path = Path("data/trading_brain.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT * FROM trades WHERE strategy_name LIKE '%BTC Apex Profit Maximizer%' LIMIT 5;")
for r in c.fetchall():
    print(dict(r))

c.execute("SELECT AVG(risk_usd), MAX(risk_usd), MIN(risk_usd), AVG(rr_achieved), AVG(pnl_usd) FROM trades WHERE strategy_name LIKE '%BTC Apex Profit Maximizer%';")
print("\nRisk & PnL stats in DB for BTC Apex Profit Maximizer:", dict(c.fetchone()))

c.execute("SELECT close_reason, count(*), sum(pnl_usd) FROM trades WHERE strategy_name LIKE '%BTC Apex Profit Maximizer%' GROUP BY close_reason;")
print("\nClose reasons for BTC Apex Profit Maximizer:")
for r in c.fetchall():
    print(dict(r))
