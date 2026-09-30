import sys
from pathlib import Path
from datetime import datetime

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
gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=30000)
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=30000)

print(f"Loaded Gold: {len(gold_candles):,} candles | Silver: {len(silver_candles):,} candles")

# Let's inspect price range and typical ATR
def get_atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev = candles[i-1]
        tr = max(c["high"] - c["low"], abs(c["high"] - prev["close"]), abs(c["low"] - prev["close"]))
        trs.append(tr)
    return sum(trs[-period:]) / period if trs else 1.0

print(f"Current Gold ATR(14): ${get_atr(gold_candles):.2f}")
print(f"Current Silver ATR(14): ${get_atr(silver_candles):.3f}")
