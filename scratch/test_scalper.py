import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)

def evaluate_scalper(
    lookback_bars=8,
    delta_threshold=0.07,
    tp1_rr=1.5,
    trail_dist_rr=1.2,
    max_hold_bars=8, # 2 hours time stop
    sl_min_dist=2.2,
    max_daily_trades=10,
    allow_24h=True
):
    capital = 50.0
    trades = []
    daily_trades = {}
    active_trade = None
    maker_fee = 0.0001
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    
    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        dt = datetime.fromtimestamp(ts)
        
        # Weekend Freeze (no trading Saturday & Sunday)
        if dt.weekday() in (5, 6):
            continue
            
        if not allow_24h:
            # 07:00 UTC - 21:00 UTC (12:30 - 02:30 IST)
            hm = dt.strftime("%H:%M")
            if not ("12:30" <= hm <= "23:45"):
                continue
                
        day_key = dt.strftime("%Y-%m-%d")
        if day_key not in daily_trades:
            daily_trades[day_key] = 0
            
        # Manage active trade
        if active_trade:
            active_trade["bars_held"] += 1
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half_lots = max(1, lots // 2)
            
            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist
                
                # Partial TP (Cut 50% @ TP1)
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 2)
                    pnl_half = (half_lots * 0.001 * (tp1_p - entry)) - (half_lots * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven (+0.1R buffer)
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.1 * dist, 2))
                    
                # Dynamic Runner Trailing
                if active_trade["tp1_hit"] and gain_r >= (tp1_rr + 0.5):
                    new_sl = round(active_trade["highest"] - (trail_dist_rr * dist), 2)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl
                        
                # SL hit
                hit_sl = c["low"] <= active_trade["stop_loss"]
                # Time stop (if trade drags on past max_hold_bars without hitting target)
                hit_time_stop = (active_trade["bars_held"] >= max_hold_bars)
                
                if hit_sl or hit_time_stop:
                    exit_p = curr if hit_time_stop and not hit_sl else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_p - entry
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append(total_pnl)
                    active_trade = None
                    daily_trades[day_key] += 1
                    continue
            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist
                
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 2)
                    pnl_half = (half_lots * 0.001 * (entry - tp1_p)) - (half_lots * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.1 * dist, 2))
                    
                if active_trade["tp1_hit"] and gain_r >= (tp1_rr + 0.5):
                    new_sl = round(active_trade["lowest"] + (trail_dist_rr * dist), 2)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl
                        
                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_time_stop = (active_trade["bars_held"] >= max_hold_bars)
                
                if hit_sl or hit_time_stop:
                    exit_p = curr if hit_time_stop and not hit_sl else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_p
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append(total_pnl)
                    active_trade = None
                    daily_trades[day_key] += 1
                    continue
                    
        # Check Entry Signal
        if not active_trade and daily_trades[day_key] < max_daily_trades:
            sub = candles[i-lookback_bars:i]
            high_lb = max(x["high"] for x in sub)
            low_lb = min(x["low"] for x in sub)
            
            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol
            
            # 1. Micro Liquidity Sweep: Pierced range extreme then closed back inside with delta absorption
            is_bull_sweep = (c["low"] < low_lb) and (c["close"] > low_lb) and (delta_ratio >= delta_threshold)
            is_bear_sweep = (c["high"] > high_lb) and (c["close"] < high_lb) and (delta_ratio <= -delta_threshold)
            
            # 2. Footprint Delta Absorption: High volume at extreme + reversal wick
            lower_wick = min(c["open"], c["close"]) - c["low"]
            upper_wick = c["high"] - max(c["open"], c["close"])
            body = abs(c["close"] - c["open"])
            candle_range = max(0.1, c["high"] - c["low"])
            
            is_bull_absorption = (lower_wick >= 0.4 * candle_range) and (delta_ratio >= delta_threshold * 0.8) and (c["close"] > c["open"])
            is_bear_absorption = (upper_wick >= 0.4 * candle_range) and (delta_ratio <= -delta_threshold * 0.8) and (c["close"] < c["open"])
            
            is_buy = is_bull_sweep or is_bull_absorption
            is_sell = is_bear_sweep or is_bear_absorption
            
            if is_buy or is_sell:
                dist = max(sl_min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + 0.6)
                sl_p = round(curr - dist if is_buy else curr + dist, 2)
                lots = max(2, int(round(4.0 / (dist * 0.001))))
                active_trade = {
                    "side": "BUY" if is_buy else "SELL",
                    "entry_price": curr,
                    "stop_loss": sl_p,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "bars_held": 0
                }
                
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 1.0
    pf = gross_win / gross_loss if gross_loss > 0 else 0
    net_pnl = sum(trades)
    active_days = len([d for d, cnt in daily_trades.items() if cnt > 0])
    avg_per_day = len(trades) / active_days if active_days else 0
    
    peak = capital
    max_dd = 0.0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = peak - pt["equity"]
        if dd > max_dd:
            max_dd = dd
            
    print(
        f"LB: {lookback_bars:2d} | Del: {delta_threshold:.2f} | TP1: {tp1_rr:.1f}R | "
        f"Trades: {len(trades):3d} | Days: {active_days:2d} | Avg/Day: {avg_per_day:.1f} | "
        f"Win%: {win_rate:4.1f}% | PF: {pf:4.2f} | Net: ${net_pnl:+7.2f} | "
        f"MaxDD: -${max_dd:5.2f} | EndCap: ${capital:6.2f}"
    )

print("=" * 110)
for lb in [6, 8, 10]:
    for del_th in [0.05, 0.07, 0.10]:
        for tp1 in [1.2, 1.5, 2.0, 2.5]:
            for hold in [6, 8, 12]:
                evaluate_scalper(lookback_bars=lb, delta_threshold=del_th, tp1_rr=tp1, max_hold_bars=hold)
