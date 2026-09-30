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

print("=" * 70)
print("🔍 LIVE MARKET & STRATEGY DIAGNOSTIC AUDIT")
print("=" * 70)

now_utc = datetime.utcnow()
now_local = datetime.now()
print(f"Current Local Time (IST): {now_local.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Current UTC Time:        {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")

hm = now_utc.strftime("%H:%M")
session_active = ("12:30" <= hm <= "23:45")
print(f"\n1. Session Filter Check:")
print(f"   Required Window:      12:30 – 23:45 UTC (6:00 PM – 5:15 AM IST)")
print(f"   Current Time Status:  {hm} UTC -> {'✅ IN TRADING SESSION' if session_active else '⏳ OUTSIDE SESSION WINDOW (Pre-Market / Asian Session)'}")

print(f"\n2. Asset Level & Signal Inspection:")
for sym in ["BTCUSD", "ETHUSD", "XAUTUSD", "SLVONUSD"]:
    t = client.get_ticker(sym)
    price = float(t.get("mark_price") or t.get("close") or 0.0)
    candles = client.get_candles(sym, resolution="15m")
    
    today_str = now_utc.strftime("%Y-%m-%d")
    today_candles = [c for c in candles if datetime.fromtimestamp(c["timestamp"]).strftime("%Y-%m-%d") == today_str]
    if len(today_candles) < 6:
        today_candles = candles[-24:] if len(candles) >= 24 else candles
    
    if not today_candles:
        print(f"   {sym}: No candle data returned.")
        continue
        
    cum_vol = sum(max(1.0, c.get("volume", 1.0)) for c in today_candles)
    cum_pv = sum(((c["high"] + c["low"] + c["close"]) / 3.0) * max(1.0, c.get("volume", 1.0)) for c in today_candles)
    vwap = cum_pv / max(1.0, cum_vol)
    
    p = trader.params[sym]
    variance = sum(((c["high"] + c["low"] + c["close"])/3.0 - vwap)**2 for c in today_candles) / max(1, len(today_candles))
    stdev = max(1.0, variance**0.5)
    ub = vwap + (p["sigma"] * stdev)
    lb = vwap - (p["sigma"] * stdev)
    
    latest = today_candles[-1]
    is_buy = (latest["low"] <= lb) and (price > lb)
    is_sell = (latest["high"] >= ub) and (price < ub)

    print(f"\n   [{sym}] (Mark Price: ${price:,.2f})")
    print(f"      VWAP: ${vwap:,.2f} | Lower Band: ${lb:,.2f} | Upper Band: ${ub:,.2f}")
    if price < lb:
        print(f"      Status: 🟡 Below Lower Band (Waiting for sweep & bounce back above ${lb:,.2f})")
    elif price > ub:
        print(f"      Status: 🟡 Above Upper Band (Waiting for sweep & rejection below ${ub:,.2f})")
    else:
        dist_lb = ((price - lb) / price) * 100
        dist_ub = ((ub - price) / price) * 100
        print(f"      Status: ⚪ Inside Band Channel ({dist_lb:.2f}% to Lower Band, {dist_ub:.2f}% to Upper Band)")
    print(f"      Signal Triggered?: {'🟢 YES' if (is_buy or is_sell) else '⚪ No (Consolidating inside equilibrium)'}")

print("=" * 70)
