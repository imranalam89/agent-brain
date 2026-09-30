import sys, os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)

def test_active_scalper_silver(min_dist, dist_pad, bad_hours, tp1_rr=1.5, max_rr=4.0):
    contract_val = 1.0
    maker_fee = 0.0001
    fixed_risk = 5.0
    capital = 50.0
    
    trades = []
    equity_curve = [{"timestamp": silver_candles[50]["timestamp"], "equity": capital}]
    active_trades = []
    
    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []
    
    for i in range(50, len(silver_candles)):
        c = silver_candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        bar_time = datetime.fromtimestamp(ts)
        
        if bar_time.weekday() in (5, 6):
            continue
            
        hm = bar_time.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue
            
        if bar_time.hour in bad_hours:
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
                
                if not at["tp1_hit"] and gain_r >= tp1_rr:
                    at["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 3)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    at["stop_loss"] = max(at["stop_loss"], round(entry + 0.15 * dist, 3))
                    
                if at["tp1_hit"] and gain_r >= (tp1_rr + 0.5):
                    new_sl = round(at["highest"] - (1.2 * dist), 3)
                    if new_sl > at["stop_loss"]:
                        at["stop_loss"] = new_sl
                        
                hit_sl = c["low"] <= at["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 3)
                
                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 3) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append(total_pnl)
                else:
                    still_active.append(at)
            else:
                if c["low"] < at["lowest"]:
                    at["lowest"] = c["low"]
                gain_r = (entry - at["lowest"]) / dist
                
                if not at["tp1_hit"] and gain_r >= tp1_rr:
                    at["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 3)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    at["stop_loss"] = min(at["stop_loss"], round(entry - 0.15 * dist, 3))
                    
                if at["tp1_hit"] and gain_r >= (tp1_rr + 0.5):
                    new_sl = round(at["lowest"] + (1.2 * dist), 3)
                    if new_sl < at["stop_loss"]:
                        at["stop_loss"] = new_sl
                        
                hit_sl = c["high"] >= at["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 3)
                
                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 3) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append(total_pnl)
                else:
                    still_active.append(at)
                    
        active_trades = still_active
        
        if len(active_trades) < 2:
            sub = silver_candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])
            
            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol
            
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= 0.03)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -0.03)
            
            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= 0.03)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -0.03)
            
            absorb_buy = (c["low"] <= lo12 * 1.0003) and (delta_ratio >= 0.03 * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9997) and (delta_ratio <= -0.03 * 0.8) and (c["close"] < c["open"])
            
            if i >= 100:
                ema100 = sum(x["close"] for x in silver_candles[i-100:i]) / 100.0
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
                    dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                    sl = round(curr - dist if is_buy else curr + dist, 3)
                    lots = max(2, int(round(fixed_risk / (dist * contract_val))))
                    active_trades.append({
                        "side": side,
                        "entry_price": curr,
                        "stop_loss": sl,
                        "dist": dist,
                        "highest": curr,
                        "lowest": curr,
                        "lots": lots,
                        "tp1_hit": False,
                        "booked_pnl": 0.0
                    })
                    
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    wr = len(wins) / len(trades) * 100 if trades else 0.0
    gp = sum(wins)
    gl = abs(sum(losses))
    pf = (gp / gl) if gl > 0 else 99.0
    net = capital - 50.0
    peak = 50.0
    dd = 0.0
    for pt in equity_curve:
        if pt["equity"] > peak: peak = pt["equity"]
        if peak - pt["equity"] > dd: dd = peak - pt["equity"]
        
    print(f"MinD={min_dist} Pad={dist_pad} TP1={tp1_rr} Max={max_rr} | WR: {wr:4.1f}% | PF: {pf:4.2f} | Net: ${net:+7.2f} | Trades: {len(trades)} | DD: -${dd:5.2f}")

for md in [0.28, 0.30, 0.32]:
    for pad in [0.05, 0.06]:
        for tp1 in [1.4, 1.6, 1.8]:
            test_active_scalper_silver(md, pad, {16, 18, 19, 23}, tp1_rr=tp1, max_rr=4.5)
