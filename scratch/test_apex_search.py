import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)

def test_apex_strategy(sigma=1.6, sweep_lb=8, tp1_rr=2.0, min_rr=3.5, trail_dist=1.2, del_min=0.04):
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
        
        mean_p = sum(day_prices) / len(day_prices)
        variance = sum((p - mean_p)**2 for p in day_prices) / len(day_prices)
        stdev = max(1.0, variance**0.5)
        
        upper_band = vwap + (sigma * stdev)
        lower_band = vwap - (sigma * stdev)
        
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
                
                # Partial TP (Cut 50% @ TP1)
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 2)
                    pnl_half = (half * 0.001 * (tp1_p - entry)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= 2.0:
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
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= 2.0:
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
                    
        # Check Entry: Outer Band Stretch + Liquidity Sweep + Delta Absorption
        if not active_trade and len(day_prices) >= 6:
            sub = candles[i-sweep_lb:i]
            hi = max(x["high"] for x in sub)
            lo = min(x["low"] for x in sub)
            
            delta = c.get("delta", 0.0)
            delta_ratio = delta / v
            
            # Confluence BUY: Price sweeps below 8-bar low OR touches lower band, closes green with positive delta
            buy_sweep = (c["low"] < lo) and (c["close"] > lo) and (delta_ratio >= del_min)
            buy_band = (c["low"] <= lower_band) and (c["close"] > c["open"]) and (delta_ratio >= del_min)
            is_buy = buy_sweep or buy_band
            
            # Confluence SELL: Price sweeps above 8-bar high OR touches upper band, closes red with negative delta
            sell_sweep = (c["high"] > hi) and (c["close"] < hi) and (delta_ratio <= -del_min)
            sell_band = (c["high"] >= upper_band) and (c["close"] < c["open"]) and (delta_ratio <= -del_min)
            is_sell = sell_sweep or sell_band
            
            if is_buy or is_sell:
                dist = max(2.5, abs(curr - (c["low"] if is_buy else c["high"])) + 0.6)
                sl_p = round(curr - dist if is_buy else curr + dist, 2)
                lots = max(2, int(round(4.0 / (dist * 0.001))))
                active_trade = {
                    "side": "BUY" if is_buy else "SELL", "entry_price": curr,
                    "stop_loss": sl_p, "dist": dist, "highest": curr, "lowest": curr,
                    "lots": lots, "tp1_hit": False, "booked_pnl": 0.0
                }
                
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
            
    print(f"Sig:{sigma:.1f} TP1:{tp1_rr:.1f} RR:{min_rr:.1f} Del:{del_min:.2f} | Trades: {total:3d} | WR: {wr:4.1f}% | PF: {pf:4.2f} | Net: ${net:>7.2f} ({roi:>6.1f}%) | MaxDD: -${max_dd:>5.2f}")
    return net

print("Grid search on Confluence Apex Strategy...")
for s in [1.5, 1.8, 2.0]:
    for tp in [1.5, 2.0, 2.5]:
        for r in [2.5, 3.5, 5.0]:
            for d in [0.03, 0.04, 0.06]:
                test_apex_strategy(sigma=s, tp1_rr=tp, min_rr=r, del_min=d)
