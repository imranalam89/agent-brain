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

c.execute("SELECT * FROM trades WHERE strategy_name LIKE '%BTC Apex Profit Maximizer%' AND pnl_usd > 0 LIMIT 10;")
print("--- 10 WINNING TRADES ---")
for r in c.fetchall():
    d = dict(r)
    gain_p = (d['exit_price'] - d['entry_price']) if d['side'] == 'BUY' else (d['entry_price'] - d['exit_price'])
    print(f"ID: {d['id']} | Side: {d['side']} | Entry: {d['entry_price']} | Exit: {d['exit_price']} | Gain: {gain_p:.1f} | PnL: ${d['pnl_usd']} | Reason: {d['close_reason']} | Notes: {d['orderflow_notes']}")

c.execute("SELECT * FROM trades WHERE strategy_name LIKE '%BTC Apex Profit Maximizer%' AND pnl_usd < 0 LIMIT 10;")
print("\n--- 10 LOSING TRADES ---")
for r in c.fetchall():
    d = dict(r)
    loss_p = (d['entry_price'] - d['exit_price']) if d['side'] == 'BUY' else (d['exit_price'] - d['entry_price'])
    print(f"ID: {d['id']} | Side: {d['side']} | Entry: {d['entry_price']} | Exit: {d['exit_price']} | Loss: {loss_p:.1f} | PnL: ${d['pnl_usd']} | Reason: {d['close_reason']} | Notes: {d['orderflow_notes']}")
