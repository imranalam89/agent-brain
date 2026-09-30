import sqlite3

conn = sqlite3.connect("data/trading_brain.db")
cursor = conn.cursor()
cursor.execute("SELECT min(opened_at), max(opened_at), count(*) FROM trades WHERE symbol='BTCUSD'")
print("BTC in DB:", cursor.fetchall())
cursor.execute("SELECT opened_at, entry_price, side, close_reason, pnl_usd, rr_achieved FROM trades WHERE symbol='BTCUSD' ORDER BY opened_at LIMIT 15")
for r in cursor.fetchall():
    print(r)
