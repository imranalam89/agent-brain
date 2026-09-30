import os
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
from exchange.delta_client import DeltaExchangeClient

client = DeltaExchangeClient(environment="india")

# September 2026 UTC timestamp range
start_ts = int(datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
end_ts = int(datetime(2026, 9, 27, 0, 0, 0, tzinfo=timezone.utc).timestamp())

print(f"Testing Candle Fetch for September 2026 ({start_ts} to {end_ts})...")

for symbol in ["XAUTUSD", "SLVONUSD"]:
    print(f"\n--- Inspecting {symbol} 15m candles ---")
    res = client.get_candles(symbol, resolution="15m", start=start_ts, end=end_ts)
    print(f"  Received {len(res)} candles")
    active = [c for c in res if c['high'] != c['low'] or c['volume'] > 0]
    print(f"  Active trading candles with price range/volume: {len(active)} / {len(res)}")
    for c in active[:5]:
        t = datetime.fromtimestamp(c["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"    {t} | O={c['open']} H={c['high']} L={c['low']} C={c['close']} V={c['volume']}")
    for c in active[-5:]:
        t = datetime.fromtimestamp(c["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"    {t} | O={c['open']} H={c['high']} L={c['low']} C={c['close']} V={c['volume']}")

