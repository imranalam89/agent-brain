import sys
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from data.database import DatabaseManager

db = DatabaseManager()
with db.get_connection() as conn:
    c = conn.cursor()
    for s in ['XAUTUSD', 'SLVONUSD']:
        c.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM candles WHERE symbol = ? AND timeframe = '15m'", (s,))
        row = c.fetchone()
        t_min = datetime.fromtimestamp(row[1], tz=timezone.utc).strftime('%Y-%m-%d %H:%M') if row[1] else 'None'
        t_max = datetime.fromtimestamp(row[2], tz=timezone.utc).strftime('%Y-%m-%d %H:%M') if row[2] else 'None'
        print(f"{s}: {row[0]:,} candles in DB, from {t_min} to {t_max}")
        
        c.execute("SELECT COUNT(*) FROM candles WHERE symbol = ? AND timeframe = '15m' AND timestamp >= 1788220800", (s,))
        sep_count = c.fetchone()[0]
        print(f"  September 2026 candles in DB: {sep_count:,}")
