import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone, timedelta
ist = timezone(timedelta(hours=5, minutes=30))
from exchange.delta_client import DeltaExchangeClient
client = DeltaExchangeClient()

six_months_ago = int((datetime.now(ist) - timedelta(days=180)).timestamp())

print("Fetching 5m and 1m test candles from Delta Exchange (April 2026)...")
c5 = client.get_candles('ETHUSD', '5m', start=six_months_ago, end=six_months_ago + 86400 * 3)
t5 = datetime.fromtimestamp(c5[0]['timestamp'], tz=ist) if c5 else None
print(f"ETHUSD 5m: {len(c5)} candles, first={t5}")

c1 = client.get_candles('ETHUSD', '1m', start=six_months_ago, end=six_months_ago + 86400)
t1 = datetime.fromtimestamp(c1[0]['timestamp'], tz=ist) if c1 else None
print(f"ETHUSD 1m: {len(c1)} candles, first={t1}")
