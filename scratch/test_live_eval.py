import sys
import os
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange.delta_client import DeltaExchangeClient
from execution.multi_pair_trader import MultiPairLiveTrader

client = DeltaExchangeClient()
trader = MultiPairLiveTrader(fixed_risk_usd=5.0)

print(f"=== TESTING DIRECT LIVE CANDLE FETCH AT {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

for sym in ['BTCUSD', 'ETHUSD', 'XAUTUSD', 'SLVONUSD']:
    ticker = client.get_ticker(sym)
    price = float(ticker.get('mark_price') or ticker.get('close') or 0.0)
    
    # 1. Stale DB candles
    db_candles = trader.db.get_latest_candles(sym, "15m", limit=60)
    db_last = datetime.fromtimestamp(db_candles[-1]['timestamp']) if db_candles else "None"
    
    # 2. Real-time Exchange candles
    live_candles = client.get_candles(sym, resolution="15m")
    live_last = datetime.fromtimestamp(live_candles[-1]['timestamp']) if live_candles else "None"
    
    print(f"\n{sym}:")
    print(f"   Mark Price:           ${price:,.2f}")
    print(f"   Stale DB Candle Time: {db_last}")
    print(f"   Live Delta Candle:    {live_last} (Count: {len(live_candles)})")
