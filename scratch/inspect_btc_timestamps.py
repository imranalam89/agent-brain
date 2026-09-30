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

c.execute("SELECT MIN(opened_at), MAX(opened_at), COUNT(*) FROM trades WHERE strategy_name LIKE '%BTC Apex Profit Maximizer%';")
print(dict(c.fetchone()))

c.execute("SELECT id, entry_price, exit_price, stop_loss, take_profit, lots, risk_usd, pnl_usd, close_reason, opened_at, closed_at FROM trades WHERE strategy_name LIKE '%BTC Apex Profit Maximizer%' ORDER BY opened_at ASC LIMIT 10;")
for r in c.fetchall():
    print(dict(r))
