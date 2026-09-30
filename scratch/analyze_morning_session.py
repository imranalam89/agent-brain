import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import datetime as dt
from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("BTCUSD", "15m", limit=35000)

hourly_stats = {h: {"wins": 0, "losses": 0, "net": 0.0, "total": 0} for h in range(24)}

for i in range(50, len(candles)):
    c = candles[i]
    bt = dt.datetime.fromtimestamp(c["timestamp"])
    h = bt.hour
    hourly_stats[h]["total"] += 1

print("Hour (IST) | Total Candles in DB")
for h in range(24):
    print(f"  {h:02d}:00    | {hourly_stats[h]['total']} candles")
