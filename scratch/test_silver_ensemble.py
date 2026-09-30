import sys, os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)
print(f"Loaded {len(candles)} Silver candles.")

def run_silver_ensemble_sim(candles, tp1_rr=1.6, max_rr=4.5, trail_mult=1.2, min_dist=0.30, dist_pad=0.06, del_th=0.03, max_concurrent=2, filter_bad_hours=True):
    capital = 50.0
    initial_capital = 50.0
    c_val = 1.0 # 1 contract = 1 oz
    maker_fee_pct = 0.0001
    bad_hours = {16, 18, 19, 23} if filter_bad_hours else set()
    
    trades = []
    active_trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    
    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []
    
    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        bar_time = datetime.fromtimestamp(ts)
        
        if bar_time.weekday() in (5, 6):
            continue
            
        hm = bar_time.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue
            
        day_str = bar_time.strftime("%Y-%m-%d")
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
        stdev = max(0.1, variance**0.5)
        
        upper_vwap = vwap + (1.7 * stdev)
        lower_vwap = vwap - (1.7 * stdev)
        
        # 1. Manage active trades
        still_active = []
        for at in active_trades:
            side = at["side"]
            entry = at["entry_price"]
            dist = at["dist"]
            lots = at["lots"]
            half_lots = max(1, lots // 2)
            
            if side == "BUY":
                if c["high"] > at["highest"]:
                    at["highest"] = c["high"]
                gain_r = (at["highest"] - entry) / dist
                
                # Check Partial TP (Cut 50%)
                if not at["tp1_hit"] and gain_r >= tp1_rr:
                    at["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 3)
                    pnl_half = (half_lots * c_val * (tp1_p - entry)) - (half_lots * c_val * tp1_p * maker_fee_pct * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven (+0.12R buffer)
                    at["stop_loss"] = max(at["stop_loss"], round(entry + 0.12 * dist, 3))
                    
                # Dynamic ATR runner trailing
                if at["tp1_hit"] and gain_r >= 1.8:
                    new_sl = round(at["highest"] - (trail_mult * dist), 3)
                    if new_sl > at["stop_loss"]:
                        at["stop_loss"] = new_sl
                        
                hit_sl = c["low"] <= at["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 3)
                
                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 3) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * maker_fee_pct * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    
                    rr_final = round((exit_price - entry) / dist, 1) if not at["tp1_hit"] else round((tp1_rr * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)
                    
                    at.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final,
                    })
                    trades.append(at)
                else:
                    still_active.append(at)
                    
            else: # SELL
                if c["low"] < at["lowest"]:
                    at["lowest"] = c["low"]
                gain_r = (entry - at["lowest"]) / dist
                
                # Check Partial TP (Cut 50%)
                if not at["tp1_hit"] and gain_r >= tp1_rr:
                    at["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 3)
                    pnl_half = (half_lots * c_val * (entry - tp1_p)) - (half_lots * c_val * tp1_p * maker_fee_pct * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven (+0.12R buffer)
                    at["stop_loss"] = min(at["stop_loss"], round(entry - 0.12 * dist, 3))
                    
                # Dynamic ATR runner trailing
                if at["tp1_hit"] and gain_r >= 1.8:
                    new_sl = round(at["lowest"] + (trail_mult * dist), 3)
                    if new_sl < at["stop_loss"]:
                        at["stop_loss"] = new_sl
                        
                hit_sl = c["high"] >= at["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 3)
                
                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 3) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * maker_fee_pct * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    
                    rr_final = round((entry - exit_price) / dist, 1) if not at["tp1_hit"] else round((tp1_rr * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)
                    
                    at.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final,
                    })
                    trades.append(at)
                else:
                    still_active.append(at)
                    
        active_trades = still_active
        
        # 2. Check Entries
        if len(active_trades) < max_concurrent and (bar_time.hour not in bad_hours):
            sub = candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])
            
            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol
            
            # Alpha 1: Liquidity Sweep
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)
            
            # Alpha 2: VWAP Band Reversion
            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)
            
            # Alpha 3: Footprint Absorption
            absorb_buy = (c["low"] <= lo12 * 1.0003) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])
            
            # Macro EMA
            if i >= 100:
                ema100 = sum(x["close"] for x in candles[i-100:i]) / 100.0
                macro_bull = (curr > ema100)
                macro_bear = (curr < ema100)
            else:
                macro_bull = macro_bear = True
                
            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])
            
            is_buy = (buy_score >= 1) and (sell_score == 0)
            is_sell = (sell_score >= 1) and (buy_score == 0)
            
            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                if not any(at["side"] == side for at in active_trades):
                    score = buy_score if is_buy else sell_score
                    is_high_conv = (score >= 2)
                    
                    dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                    sl_price = round(curr - dist if is_buy else curr + dist, 3)
                    lots = max(2, int(round(5.0 / (dist * c_val))))
                    notional = lots * c_val * curr
                    
                    active_trades.append({
                        "id": f"SILVER_ENS_{ts}_{len(active_trades)}",
                        "symbol": "SLVONUSD",
                        "side": side,
                        "entry_price": curr,
                        "stop_loss": sl_price,
                        "dist": dist,
                        "highest": curr,
                        "lowest": curr,
                        "lots": lots,
                        "notional_usd": round(notional, 2),
                        "margin_usd": round(notional / 100.0, 2),
                        "leverage": 100,
                        "risk_usd": 5.0,
                        "conviction_stars": 5.0 if is_high_conv else 4.2,
                        "tp1_hit": False,
                        "booked_pnl": 0.0,
                        "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    total = len(trades)
    win_rate = round(len(wins)/total*100, 1) if total else 0.0
    gp = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    pf = round(gp/gl, 2) if gl else 99.0
    net = round(capital - initial_capital, 2)
    peak = initial_capital
    max_dd = 0.0
    for pt in equity_curve:
        if pt["equity"] > peak: peak = pt["equity"]
        dd = peak - pt["equity"]
        if dd > max_dd: max_dd = dd
        
    return {
        "trades": total,
        "win_rate": win_rate,
        "pf": pf,
        "net_pl": net,
        "max_dd": round(max_dd, 2),
        "wins": len(wins),
        "losses": len(losses)
    }

print("Running parameter tests on Silver Ensemble...")
for tp1 in [1.2, 1.4, 1.5, 1.6, 1.8, 2.0]:
    for max_rr in [3.5, 4.0, 4.5, 5.0]:
        for min_d in [0.28, 0.30, 0.35]:
            for max_c in [1, 2]:
                res = run_silver_ensemble_sim(candles, tp1_rr=tp1, max_rr=max_rr, min_dist=min_d, max_concurrent=max_c)
                if res["pf"] >= 1.60 and res["net_pl"] >= 200:
                    print(f"TP1={tp1} Max={max_rr} MinD={min_d} Conc={max_c} | WR: {res['win_rate']}% | PF: {res['pf']} | Net: ${res['net_pl']:+7.2f} | Trades: {res['trades']} | DD: -${res['max_dd']}")
