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

for sym in ['BTCUSD', 'ETHUSD', 'XAUTUSD', 'SLVONUSD']:
    print(f"\n=================== {sym} ===================")
    p = trader.params[sym]
    ticker = client.get_ticker(sym)
    price = float(ticker.get("mark_price") or ticker.get("close") or 0.0)
    candles = client.get_candles(sym, resolution="15m")
    print(f"Total Candles Fetched: {len(candles)}")
    
    now_local = datetime.now()
    hm = now_local.strftime("%H:%M")
    session_active = ("12:30" <= hm <= "23:45")
    print(f"Session Active? {session_active} (Current HM: {hm})")
    
    today_str = now_local.strftime("%Y-%m-%d")
    today_candles = [c for c in candles if datetime.fromtimestamp(c["timestamp"]).strftime("%Y-%m-%d") == today_str]
    print(f"Today Candles: {len(today_candles)}")
    if len(today_candles) < 6:
        today_candles = candles[-24:]
        print(f"Fallback to last 24 candles: {len(today_candles)}")

    cum_vol = 0.0
    cum_pv = 0.0
    prices = []
    for c in today_candles:
        typ_p = (c["high"] + c["low"] + c["close"]) / 3.0
        v = max(1.0, c.get("volume", 1.0))
        cum_vol += v
        cum_pv += (typ_p * v)
        prices.append(typ_p)

    vwap = cum_pv / max(1.0, cum_vol)
    variance = sum((pr - vwap)**2 for pr in prices) / len(prices)
    stdev = max(1.0, variance**0.5)

    upper_band = vwap + (p["sigma"] * stdev)
    lower_band = vwap - (p["sigma"] * stdev)

    latest = today_candles[-1]
    delta = latest.get("delta", 0.0)
    v_latest = max(1.0, latest.get("volume", 1.0))
    delta_ratio = delta / v_latest

    print(f"Mark Price: ${price:,.2f}")
    print(f"VWAP: ${vwap:,.2f} | LowerBand: ${lower_band:,.2f} | UpperBand: ${upper_band:,.2f}")
    print(f"Latest Candle: Low=${latest['low']}, High=${latest['high']}, Close=${latest['close']}")
    
    is_buy = (latest["low"] <= lower_band) and (price > lower_band) and (delta_ratio >= -0.10)
    is_sell = (latest["high"] >= upper_band) and (price < upper_band) and (delta_ratio <= 0.10)
    print(f"is_buy={is_buy} (low<={lower_band:.2f}? {latest['low'] <= lower_band}, price>{lower_band:.2f}? {price > lower_band})")
    print(f"is_sell={is_sell} (high>={upper_band:.2f}? {latest['high'] >= upper_band}, price<{upper_band:.2f}? {price < upper_band})")
