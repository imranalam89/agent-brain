import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)

print(f"Total candles loaded for research: {len(candles)}")

def evaluate_strategy(name, trades, capital, equity_curve):
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    total = len(trades)
    wr = round((len(wins) / total * 100), 1) if total > 0 else 0.0
    gross_win = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses)) if losses else 1.0
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0.0
    net = round(capital - 50.0, 2)
    roi = round((net / 50.0) * 100, 1)
    
    peak = 50.0
    max_dd = 0.0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = peak - pt["equity"]
        if dd > max_dd:
            max_dd = dd
            
    print(f"[{name:<36}] Trades: {total:3d} | WR: {wr:4.1f}% | PF: {pf:4.2f} | Net: ${net:>7.2f} ({roi:>6.1f}%) | MaxDD: -${max_dd:>5.2f}")
    return {"name": name, "trades": total, "wr": wr, "pf": pf, "net": net, "roi": roi, "max_dd": max_dd, "equity_curve": equity_curve, "trades_list": trades}

# ==============================================================================
# 1. STRATEGY: Fair Value Gap (FVG) + Order Flow Re-test Sniper
# ==============================================================================
def test_fvg_strategy(tp1_rr=2.5, min_rr=4.0, trail_dist=1.5):
    capital = 50.0
    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trade = None
    maker_fee = 0.0001
    
    # Active FVGs
    active_fvgs = [] # list of dicts: {'type': 'BULL'/'BEAR', 'top': float, 'bottom': float, 'timestamp': int, 'mitigated': False}

    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        dt = datetime.fromtimestamp(ts)
        
        if dt.weekday() in (5, 6):
            continue
            
        hm = dt.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue
            
        # Detect new FVG from 3 candles back
        c1 = candles[i-2]
        c2 = candles[i-1]
        c3 = c
        
        # Bullish FVG: c1.high < c3.low
        if c3["low"] > c1["high"] + 0.3:
            active_fvgs.append({"type": "BULL", "top": c3["low"], "bottom": c1["high"], "timestamp": ts, "mitigated": False})
        # Bearish FVG: c3.high < c1.low
        elif c3["high"] < c1["low"] - 0.3:
            active_fvgs.append({"type": "BEAR", "top": c1["low"], "bottom": c3["high"], "timestamp": ts, "mitigated": False})
            
        # Keep only recent 20 unmitigated FVGs
        active_fvgs = [f for f in active_fvgs[-20:] if not f["mitigated"]]
        
        # Manage active trade
        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half = max(1, lots // 2)
            
            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist
                
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 2)
                    pnl_half = (half * 0.001 * (tp1_p - entry)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.2 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= 2.5:
                    new_sl = round(active_trade["highest"] - trail_dist * dist, 2)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl
                        
                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + min_rr * dist, 2)
                
                if hit_sl or hit_tp:
                    exit_p = round(entry + min_rr * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half) if active_trade["tp1_hit"] else lots
                    diff = exit_p - entry
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append({"pnl_usd": tot, "side": side, "entry": entry, "exit": exit_p})
                    active_trade = None
                    continue
            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist
                
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 2)
                    pnl_half = (half * 0.001 * (entry - tp1_p)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.2 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= 2.5:
                    new_sl = round(active_trade["lowest"] + trail_dist * dist, 2)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl
                        
                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - min_rr * dist, 2)
                
                if hit_sl or hit_tp:
                    exit_p = round(entry - min_rr * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_p
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append({"pnl_usd": tot, "side": side, "entry": entry, "exit": exit_p})
                    active_trade = None
                    continue
                    
        # Check FVG entry: Price retraces into an active FVG with delta reaction
        if not active_trade:
            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol
            
            for fvg in reversed(active_fvgs):
                if fvg["type"] == "BULL" and fvg["bottom"] <= c["low"] <= fvg["top"]:
                    if delta_ratio >= 0.04 and c["close"] > c["open"]:
                        fvg["mitigated"] = True
                        dist = max(2.2, curr - (fvg["bottom"] - 0.5))
                        sl_p = round(curr - dist, 2)
                        lots = max(2, int(round(4.0 / (dist * 0.001))))
                        active_trade = {
                            "side": "BUY", "entry_price": curr, "stop_loss": sl_p,
                            "dist": dist, "highest": curr, "lowest": curr, "lots": lots,
                            "tp1_hit": False, "booked_pnl": 0.0
                        }
                        break
                elif fvg["type"] == "BEAR" and fvg["bottom"] <= c["high"] <= fvg["top"]:
                    if delta_ratio <= -0.04 and c["close"] < c["open"]:
                        fvg["mitigated"] = True
                        dist = max(2.2, (fvg["top"] + 0.5) - curr)
                        sl_p = round(curr + dist, 2)
                        lots = max(2, int(round(4.0 / (dist * 0.001))))
                        active_trade = {
                            "side": "SELL", "entry_price": curr, "stop_loss": sl_p,
                            "dist": dist, "highest": curr, "lowest": curr, "lots": lots,
                            "tp1_hit": False, "booked_pnl": 0.0
                        }
                        break
                        
    return evaluate_strategy("Fair Value Gap (FVG) Sniper", trades, capital, equity_curve)

# ==============================================================================
# 2. STRATEGY: Session VWAP Mean Reversion & Bands
# ==============================================================================
def test_vwap_bands_strategy(sigma_entry=1.8, tp_vwap_rr=1.5, min_rr=2.5):
    capital = 50.0
    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trade = None
    maker_fee = 0.0001
    
    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []

    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        dt = datetime.fromtimestamp(ts)
        
        if dt.weekday() in (5, 6):
            continue
            
        hm = dt.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue
            
        day_str = dt.strftime("%Y-%m-%d")
        typ_p = (c["high"] + c["low"] + c["close"]) / 3.0
        v = max(1.0, c.get("volume", 1.0))
        
        if day_str != current_day:
            current_day = day_str
            day_cum_vol = 0.0
            day_cum_pv = 0.0
            day_prices = []
            
        day_cum_vol += v
        day_cum_pv += (typ_p * v)
        day_prices.append(typ_p)
        vwap = day_cum_pv / day_cum_vol
        
        # Stdev
        mean_p = sum(day_prices) / len(day_prices)
        variance = sum((p - mean_p)**2 for p in day_prices) / len(day_prices)
        stdev = max(1.0, variance**0.5)
        
        upper_band = vwap + (sigma_entry * stdev)
        lower_band = vwap - (sigma_entry * stdev)
        
        # Manage active trade
        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half = max(1, lots // 2)
            
            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist
                
                # Exit at VWAP touch or TP1
                hit_vwap = c["high"] >= vwap
                if not active_trade["tp1_hit"] and (hit_vwap or gain_r >= tp_vwap_rr):
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp_vwap_rr * dist, 2)
                    pnl_half = (half * 0.001 * (tp1_p - entry)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.1 * dist, 2))
                    
                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + min_rr * dist, 2)
                
                if hit_sl or hit_tp:
                    exit_p = round(entry + min_rr * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half) if active_trade["tp1_hit"] else lots
                    diff = exit_p - entry
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append({"pnl_usd": tot, "side": side, "entry": entry, "exit": exit_p})
                    active_trade = None
                    continue
            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist
                
                hit_vwap = c["low"] <= vwap
                if not active_trade["tp1_hit"] and (hit_vwap or gain_r >= tp_vwap_rr):
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp_vwap_rr * dist, 2)
                    pnl_half = (half * 0.001 * (entry - tp1_p)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.1 * dist, 2))
                    
                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - min_rr * dist, 2)
                
                if hit_sl or hit_tp:
                    exit_p = round(entry - min_rr * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_p
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append({"pnl_usd": tot, "side": side, "entry": entry, "exit": exit_p})
                    active_trade = None
                    continue
                    
        # Check Entry: Oversold/Overbought at bands with delta exhaustion
        if not active_trade and len(day_prices) >= 8:
            delta = c.get("delta", 0.0)
            delta_ratio = delta / v
            
            # Oversold below lower band, closes green with positive delta
            is_buy = (c["low"] <= lower_band) and (c["close"] > c["open"]) and (delta_ratio >= 0.04)
            # Overbought above upper band, closes red with negative delta
            is_sell = (c["high"] >= upper_band) and (c["close"] < c["open"]) and (delta_ratio <= -0.04)
            
            if is_buy or is_sell:
                dist = max(2.5, abs(curr - (c["low"] if is_buy else c["high"])) + 0.6)
                sl_p = round(curr - dist if is_buy else curr + dist, 2)
                lots = max(2, int(round(4.0 / (dist * 0.001))))
                active_trade = {
                    "side": "BUY" if is_buy else "SELL", "entry_price": curr,
                    "stop_loss": sl_p, "dist": dist, "highest": curr, "lowest": curr,
                    "lots": lots, "tp1_hit": False, "booked_pnl": 0.0
                }
                
    return evaluate_strategy("Session VWAP Bands Reversion", trades, capital, equity_curve)

# ==============================================================================
# 3. STRATEGY: Multi-Regime Adaptive Machine (Smart Switcher)
# ==============================================================================
def test_multi_regime_adaptive():
    capital = 50.0
    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trade = None
    maker_fee = 0.0001
    
    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        dt = datetime.fromtimestamp(ts)
        
        if dt.weekday() in (5, 6):
            continue
            
        hm = dt.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue
            
        # Detect Market Regime using ADX / Trend Strength:
        sub = candles[i-20:i]
        tr_list = [max(candles[k]["high"] - candles[k]["low"], abs(candles[k]["high"] - candles[k-1]["close"]), abs(candles[k]["low"] - candles[k-1]["close"])) for k in range(i-14, i)]
        atr14 = sum(tr_list) / 14.0
        
        ema9 = sum(x["close"] for x in sub[-9:]) / 9.0
        ema21 = sum(x["close"] for x in sub[-21:]) / 21.0
        
        trend_spread = abs(ema9 - ema21) / curr * 1000.0 # basis points
        is_trending_regime = (trend_spread >= 1.5)
        
        # Manage active trade
        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half = max(1, lots // 2)
            regime = active_trade["regime"]
            
            # If in Trending Regime: Use 1:3.0+ Trailing Runner
            # If in Range Regime: Use 1:2.0 Fast Scale-Out + BE
            tp1_target = 3.0 if regime == "TREND" else 2.0
            trail_mult = 1.5 if regime == "TREND" else 1.2
            
            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist
                
                if not active_trade["tp1_hit"] and gain_r >= tp1_target:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_target * dist, 2)
                    pnl_half = (half * 0.001 * (tp1_p - entry)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["highest"] - trail_mult * dist, 2)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl
                        
                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + (5.0 if regime == "TREND" else 2.5) * dist, 2)
                
                if hit_sl or hit_tp:
                    exit_p = round(entry + (5.0 if regime == "TREND" else 2.5) * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half) if active_trade["tp1_hit"] else lots
                    diff = exit_p - entry
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append({"pnl_usd": tot, "side": side, "entry": entry, "exit": exit_p})
                    active_trade = None
                    continue
            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist
                
                if not active_trade["tp1_hit"] and gain_r >= tp1_target:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_target * dist, 2)
                    pnl_half = (half * 0.001 * (entry - tp1_p)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["lowest"] + trail_mult * dist, 2)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl
                        
                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - (5.0 if regime == "TREND" else 2.5) * dist, 2)
                
                if hit_sl or hit_tp:
                    exit_p = round(entry - (5.0 if regime == "TREND" else 2.5) * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_p
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append({"pnl_usd": tot, "side": side, "entry": entry, "exit": exit_p})
                    active_trade = None
                    continue
                    
        # Check Entry Signal
        if not active_trade:
            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol
            
            is_buy = False
            is_sell = False
            trade_regime = "RANGE"
            
            if is_trending_regime:
                # Trend Momentum Pullback
                trade_regime = "TREND"
                is_buy = (ema9 > ema21) and (c["low"] <= ema9 * 1.0004) and (c["close"] > c["open"]) and (delta_ratio >= 0.08)
                is_sell = (ema9 < ema21) and (c["high"] >= ema9 * 0.9996) and (c["close"] < c["open"]) and (delta_ratio <= -0.08)
            else:
                # 8-bar Liquidity Sweep (Range Mean Reversion)
                trade_regime = "RANGE"
                hi8 = max(x["high"] for x in sub[-8:])
                lo8 = min(x["low"] for x in sub[-8:])
                is_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= 0.04)
                is_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -0.04)
                
            if is_buy or is_sell:
                dist = max(2.5, abs(curr - (c["low"] if is_buy else c["high"])) + 0.6)
                sl_p = round(curr - dist if is_buy else curr + dist, 2)
                lots = max(2, int(round(4.0 / (dist * 0.001))))
                active_trade = {
                    "side": "BUY" if is_buy else "SELL", "entry_price": curr,
                    "stop_loss": sl_p, "dist": dist, "highest": curr, "lowest": curr,
                    "lots": lots, "tp1_hit": False, "booked_pnl": 0.0, "regime": trade_regime
                }
                
    return evaluate_strategy("Multi-Regime Adaptive Machine", trades, capital, equity_curve)

# ==============================================================================
# 4. STRATEGY: Institutional Footprint Volume Absorption & Delta Divergence
# ==============================================================================
def test_absorption_divergence():
    capital = 50.0
    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trade = None
    maker_fee = 0.0001
    
    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        dt = datetime.fromtimestamp(ts)
        
        if dt.weekday() in (5, 6):
            continue
            
        hm = dt.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue
            
        sub = candles[i-12:i]
        high_prev = max(x["high"] for x in sub)
        low_prev = min(x["low"] for x in sub)
        
        delta = c.get("delta", 0.0)
        vol = max(1.0, c.get("volume", 1.0))
        delta_ratio = delta / vol
        
        # Absorption Divergence:
        # Bullish Absorption: Price hits/pierces low_prev, heavy sell volume, BUT delta is positive or flips green!
        # (Passive Limit Buyer absorbs all market sellers)
        is_bull_absorb = (c["low"] <= low_prev * 1.0002) and (delta_ratio >= 0.03) and (c["close"] > c["open"])
        # Bearish Absorption: Price hits/pierces high_prev, heavy buy volume, BUT delta is negative or flips red!
        # (Passive Limit Seller absorbs all market buyers)
        is_bear_absorb = (c["high"] >= high_prev * 0.9998) and (delta_ratio <= -0.03) and (c["close"] < c["open"])
        
        # Manage active trade
        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half = max(1, lots // 2)
            
            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist
                
                # Cut 50% @ 2.5R
                if not active_trade["tp1_hit"] and gain_r >= 2.5:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + 2.5 * dist, 2)
                    pnl_half = (half * 0.001 * (tp1_p - entry)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.2 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= 3.0:
                    new_sl = round(active_trade["highest"] - 1.5 * dist, 2)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl
                        
                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + 5.0 * dist, 2)
                
                if hit_sl or hit_tp:
                    exit_p = round(entry + 5.0 * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half) if active_trade["tp1_hit"] else lots
                    diff = exit_p - entry
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append({"pnl_usd": tot, "side": side, "entry": entry, "exit": exit_p})
                    active_trade = None
                    continue
            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist
                
                if not active_trade["tp1_hit"] and gain_r >= 2.5:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - 2.5 * dist, 2)
                    pnl_half = (half * 0.001 * (entry - tp1_p)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.2 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= 3.0:
                    new_sl = round(active_trade["lowest"] + 1.5 * dist, 2)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl
                        
                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - 5.0 * dist, 2)
                
                if hit_sl or hit_tp:
                    exit_p = round(entry - 5.0 * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_p
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append({"pnl_usd": tot, "side": side, "entry": entry, "exit": exit_p})
                    active_trade = None
                    continue
                    
        # Check Entry
        if not active_trade:
            if is_bull_absorb or is_bear_absorb:
                dist = max(2.5, abs(curr - (c["low"] if is_bull_absorb else c["high"])) + 0.6)
                sl_p = round(curr - dist if is_bull_absorb else curr + dist, 2)
                lots = max(2, int(round(4.0 / (dist * 0.001))))
                active_trade = {
                    "side": "BUY" if is_bull_absorb else "SELL", "entry_price": curr,
                    "stop_loss": sl_p, "dist": dist, "highest": curr, "lowest": curr,
                    "lots": lots, "tp1_hit": False, "booked_pnl": 0.0
                }
                
    return evaluate_strategy("Footprint Absorption Divergence", trades, capital, equity_curve)

print("Running simulations on 12,509 candles...")
test_fvg_strategy()
test_vwap_bands_strategy()
test_multi_regime_adaptive()
test_absorption_divergence()
