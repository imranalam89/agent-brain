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

print("=" * 80)
print(" 🔬 COMPREHENSIVE HISTORICAL AUDIT OF TODAY'S CANDLES (ALL 4 ASSETS)")
print(f" Audit Run Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
print("=" * 80)

today_str = datetime.now().strftime("%Y-%m-%d")

for sym in ["BTCUSD", "ETHUSD", "XAUTUSD", "SLVONUSD"]:
    print(f"\n>>> ANALYZING {sym} FOR TODAY ({today_str}) <<<")
    p = trader.params[sym]
    candles = client.get_candles(sym, resolution="15m")
    
    today_candles = [c for c in candles if datetime.fromtimestamp(c["timestamp"]).strftime("%Y-%m-%d") == today_str]
    print(f"Total 15m Candles Fetched Today: {len(today_candles)}")
    
    if not today_candles:
        print(f"❌ No candles found for today on {sym}.")
        continue

    # Replay candle by candle from the beginning of today
    signals_found = []
    
    for idx in range(len(today_candles)):
        current_bar = today_candles[idx]
        bar_time = datetime.fromtimestamp(current_bar["timestamp"])
        hm = bar_time.strftime("%H:%M")
        
        # Check session window: 12:30 - 23:45 IST
        in_session = ("12:30" <= hm <= "23:45")
        
        # Sliced history up to current_bar for rolling session VWAP
        history_so_far = today_candles[:idx+1]
        if len(history_so_far) < 6:
            # Fallback to pre-today bars if early in the day
            pre_today = [c for c in candles if datetime.fromtimestamp(c["timestamp"]).strftime("%Y-%m-%d") < today_str]
            needed = 24 - len(history_so_far)
            history_so_far = (pre_today[-needed:] if len(pre_today) >= needed else pre_today) + history_so_far

        cum_vol = sum(max(1.0, c.get("volume", 1.0)) for c in history_so_far)
        cum_pv = sum(((c["high"] + c["low"] + c["close"]) / 3.0) * max(1.0, c.get("volume", 1.0)) for c in history_so_far)
        vwap = cum_pv / max(1.0, cum_vol)
        variance = sum(((c["high"] + c["low"] + c["close"])/3.0 - vwap)**2 for c in history_so_far) / max(1, len(history_so_far))
        stdev = max(1.0, variance**0.5)

        upper_band = vwap + (p["sigma"] * stdev)
        lower_band = vwap - (p["sigma"] * stdev)

        low = current_bar["low"]
        high = current_bar["high"]
        close = current_bar["close"]
        delta = current_bar.get("delta", 0.0)
        v = max(1.0, current_bar.get("volume", 1.0))
        delta_ratio = delta / v

        # Buy condition: low <= lower_band and close > lower_band and delta_ratio >= -0.10
        is_buy = (low <= lower_band) and (close > lower_band) and (delta_ratio >= -0.10)
        # Sell condition: high >= upper_band and close < upper_band and delta_ratio <= 0.10
        is_sell = (high >= upper_band) and (close < upper_band) and (delta_ratio <= 0.10)

        # Check chop hour filter for Gold
        is_gold_chop = (sym == "XAUTUSD" and bar_time.hour in (16, 19, 20, 22))

        # Check if extreme was touched
        touched_lower = (low <= lower_band)
        touched_upper = (high >= upper_band)

        if is_buy or is_sell:
            signals_found.append({
                "time": bar_time.strftime("%H:%M"),
                "type": "BUY" if is_buy else "SELL",
                "in_session": in_session,
                "is_gold_chop": is_gold_chop,
                "low": low,
                "high": high,
                "close": close,
                "lower_band": round(lower_band, 2),
                "upper_band": round(upper_band, 2),
                "vwap": round(vwap, 2)
            })
        elif in_session and (touched_lower or touched_upper):
            print(f"  [Near-Miss @ {hm}] Touched {'Lower' if touched_lower else 'Upper'} Band | Low={low}, High={high}, Close={close} vs LowerB={lower_band:.2f}, UpperB={upper_band:.2f}")

    print(f"Total Setups Met Criteria Today: {len(signals_found)}")
    if signals_found:
        for s in signals_found:
            status = "VALID ENTRY" if (s["in_session"] and not s["is_gold_chop"]) else "BLOCKED (Outside Session/Chop)"
            print(f"  👉 [{s['time']} IST] {s['type']} | Close=${s['close']} | VWAP=${s['vwap']} | Bands=[${s['lower_band']} - ${s['upper_band']}] -> {status}")
    else:
        print("  ⚪ No candle today fulfilled the complete sweep-and-reclaim criteria.")

print("\n" + "=" * 80)
