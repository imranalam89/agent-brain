import sqlite3
import json

conn = sqlite3.connect("data/trading_brain.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT id, symbol, side, lots, notional_usd, entry_price, exit_price, pnl_usd, close_reason, opened_at, closed_at FROM trades WHERE is_paper=0 OR id LIKE 'LIVE_%'")
rows = [dict(r) for r in c.fetchall()]
print(f"Total LIVE rows: {len(rows)}")
for r in rows:
    print(r)
