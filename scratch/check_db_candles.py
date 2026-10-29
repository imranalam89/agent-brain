import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.database import DatabaseManager
from datetime import datetime, timezone, timedelta
ist = timezone(timedelta(hours=5, minutes=30))
db = DatabaseManager()
with db.get_connection() as conn:
    cur = conn.cursor()
    cur.execute("SELECT timestamp FROM candles WHERE symbol='BTCUSD' ORDER BY timestamp DESC LIMIT 5")
    rows = [r[0] for r in cur.fetchall()]
    print('Diff between consecutive candles (seconds):', rows[0] - rows[1], rows[1] - rows[2])
    cur.execute("SELECT * FROM candles WHERE symbol='BTCUSD' ORDER BY timestamp DESC LIMIT 1")
    row = dict(cur.fetchone())
    print('Sample row:', row)
