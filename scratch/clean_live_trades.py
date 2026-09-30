import sqlite3
from pathlib import Path

db_path = Path("data/trading_brain.db")
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check test LIVE trades
c.execute("SELECT id, symbol, pnl_usd, is_paper FROM trades WHERE id LIKE 'LIVE_%' OR is_paper = 0")
rows = c.fetchall()
print("Found test live trades:", rows)

# Delete test simulated live trades so we start 100% clean with 0 data
c.execute("DELETE FROM trades WHERE id LIKE 'LIVE_%' OR is_paper = 0")
conn.commit()
print("Deleted test trades. Ready for real live execution.")
