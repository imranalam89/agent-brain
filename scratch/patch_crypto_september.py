import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from exchange.delta_client import DeltaExchangeClient
from data.database import DatabaseManager

def main():
    db = DatabaseManager()
    client = DeltaExchangeClient(environment="india")
    
    # Sep 1 to Sep 27, 2026
    start_ts = int(datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    now_ts = int(time.time())
    
    symbols = ["BTCUSD", "ETHUSD"]
    
    for symbol in symbols:
        print(f"\nFetching {symbol} 15m candles from Delta API...")
        try:
            raw = client.get_candles(symbol, resolution="15m", start=start_ts, end=now_ts)
            if not raw:
                print(f"  [WARN] No candles returned for {symbol}")
                continue
            
            raw.sort(key=lambda x: x["timestamp"])
            enriched = []
            for c in raw:
                if c["timestamp"] > now_ts:
                    continue
                vol = c.get("volume", 0.0)
                hi = c["high"]
                lo = c["low"]
                op = c["open"]
                cl = c["close"]
                hl = max(0.0001, hi - lo)
                co = cl - op
                ratio = max(-1.0, min(1.0, co / hl))
                delta = round(vol * ratio, 2)
                buy_vol = round(max(0.0, (vol + delta) / 2.0), 2)
                sell_vol = round(max(0.0, (vol - delta) / 2.0), 2)
                enriched.append({
                    "timestamp": c["timestamp"],
                    "open": op,
                    "high": hi,
                    "low": lo,
                    "close": cl,
                    "volume": vol,
                    "buy_volume": buy_vol,
                    "sell_volume": sell_vol,
                    "delta": delta
                })
            
            # Save into DB
            db.save_candles(symbol, "15m", enriched)
            print(f"  Successfully patched {len(enriched)} 15m candles for {symbol} up to {datetime.fromtimestamp(enriched[-1]['timestamp'], timezone.utc)}")
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")

    print("\nUpdated candle counts:")
    for sym in ["XAUTUSD", "SLVONUSD", "BTCUSD", "ETHUSD"]:
        c = db.get_latest_candles(sym, "15m", limit=100000)
        start_d = datetime.fromtimestamp(c[0]["timestamp"]).strftime("%Y-%m-%d")
        end_d = datetime.fromtimestamp(c[-1]["timestamp"]).strftime("%Y-%m-%d %H:%M")
        print(f"  {sym:10s}: {len(c):,} candles | {start_d} -> {end_d}")

if __name__ == '__main__':
    main()
