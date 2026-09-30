import os
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

def sweep_crypto():
    db = DatabaseManager()
    btc_candles = db.get_latest_candles("BTCUSD", "15m", limit=30000)
    eth_candles = db.get_latest_candles("ETHUSD", "15m", limit=30000)
    
    maker_fee_pct = 0.0001
    
    test_configs = [
        ("BTCUSD", btc_candles, 0.001, 220.0, 40.0, 35.0),
        ("ETHUSD", eth_candles, 0.01, 10.0, 2.0, 2.0)
    ]
    
    for symbol, candles, c_val, min_dist, dist_pad, stdev_min in test_configs:
        print(f"\n=======================================================")
        print(f"Sweeping High-Conviction Models on {symbol} ({len(candles):,} candles)")
        print(f"=======================================================")
        
        # Test varying minimum confluence score (1 vs 2) and lookback sweeps
        for min_score in [2, 3]:
            for tp1_rr in [1.6, 2.0, 2.4]:
                for max_rr in [4.5, 6.0]:
                    for trail_mult in [0.8, 1.0]:
                        capital = 50.0
                        peak = capital
                        max_dd = 0.0
                        trades = []
                        active_trades = []
                        
                        current_day = None
                        day_cum_vol = 0.0
                        day_cum_pv = 0.0
                        day_prices = []
                        bad_hours = {19, 22}
                        
                        for i in range(50, len(candles)):
                            c = candles[i]
                            curr = c["close"]
                            ts = c["timestamp"]
                            bar_time = datetime.fromtimestamp(ts)
                            
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
                            stdev = max(stdev_min, variance**0.5)
                            
                            upper_vwap = vwap + (1.6 * stdev)
                            lower_vwap = vwap - (1.6 * stdev)
                            
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
                                        tp1_p = entry + tp1_rr * dist
                                        pnl_half = (half_lots * c_val * (tp1_p - entry)) - (half_lots * c_val * tp1_p * maker_fee_pct * 2)
                                        at["booked_pnl"] = pnl_half
                                        capital += pnl_half
                                        at["stop_loss"] = max(at["stop_loss"], entry + 0.15 * dist)
                                        
                                    if at["tp1_hit"] and gain_r >= 2.0:
                                        new_sl = at["highest"] - (trail_mult * dist)
                                        if new_sl > at["stop_loss"]:
                                            at["stop_loss"] = new_sl
                                            
                                    hit_sl = c["low"] <= at["stop_loss"]
                                    hit_tp = c["high"] >= (entry + max_rr * dist)
                                    
                                    if hit_sl or hit_tp:
                                        exit_p = (entry + max_rr * dist) if hit_tp else at["stop_loss"]
                                        rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                                        diff = exit_p - entry
                                        rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_p * maker_fee_pct * 2)
                                        total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                                        capital += rem_pnl
                                        if capital > peak: peak = capital
                                        if peak - capital > max_dd: max_dd = peak - capital
                                        at["pnl_usd"] = total_pnl
                                        trades.append(at)
                                    else:
                                        still_active.append(at)
                                else: # SELL
                                    if c["low"] < at["lowest"]:
                                        at["lowest"] = c["low"]
                                    gain_r = (entry - at["lowest"]) / dist
                                    
                                    if not at["tp1_hit"] and gain_r >= tp1_rr:
                                        at["tp1_hit"] = True
                                        tp1_p = entry - tp1_rr * dist
                                        pnl_half = (half_lots * c_val * (entry - tp1_p)) - (half_lots * c_val * tp1_p * maker_fee_pct * 2)
                                        at["booked_pnl"] = pnl_half
                                        capital += pnl_half
                                        at["stop_loss"] = min(at["stop_loss"], entry - 0.15 * dist)
                                        
                                    if at["tp1_hit"] and gain_r >= 2.0:
                                        new_sl = at["lowest"] + (trail_mult * dist)
                                        if new_sl < at["stop_loss"]:
                                            at["stop_loss"] = new_sl
                                            
                                    hit_sl = c["high"] >= at["stop_loss"]
                                    hit_tp = c["low"] <= (entry - max_rr * dist)
                                    
                                    if hit_sl or hit_tp:
                                        exit_p = (entry - max_rr * dist) if hit_tp else at["stop_loss"]
                                        rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                                        diff = entry - exit_p
                                        rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_p * maker_fee_pct * 2)
                                        total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                                        capital += rem_pnl
                                        if capital > peak: peak = capital
                                        if peak - capital > max_dd: max_dd = peak - capital
                                        at["pnl_usd"] = total_pnl
                                        trades.append(at)
                                    else:
                                        still_active.append(at)
                            active_trades = still_active
                            
                            if len(active_trades) < 2 and (bar_time.hour not in bad_hours):
                                sub = candles[i-20:i]
                                hi8 = max(x["high"] for x in sub[-8:])
                                lo8 = min(x["low"] for x in sub[-8:])
                                hi12 = max(x["high"] for x in sub[-12:])
                                lo12 = min(x["low"] for x in sub[-12:])
                                
                                delta = c.get("delta", 0.0)
                                vol = max(1.0, c.get("volume", 1.0))
                                delta_ratio = delta / vol
                                del_th = 0.03
                                
                                sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
                                sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)
                                
                                vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
                                vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)
                                
                                absorb_buy = (c["low"] <= lo12 * 1.0003) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
                                absorb_sell = (c["high"] >= hi12 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])
                                
                                ema100 = sum(x["close"] for x in candles[i-100:i]) / 100.0 if i >= 100 else curr
                                macro_bull = (curr > ema100)
                                macro_bear = (curr < ema100)
                                
                                buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
                                sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])
                                
                                is_buy = (buy_score >= min_score) and (sell_score == 0)
                                is_sell = (sell_score >= min_score) and (buy_score == 0)
                                
                                if is_buy or is_sell:
                                    side = "BUY" if is_buy else "SELL"
                                    if not any(at["side"] == side for at in active_trades):
                                        dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                                        sl_price = curr - dist if is_buy else curr + dist
                                        lots = max(2, int(round(5.0 / (dist * c_val))))
                                        active_trades.append({
                                            "side": side,
                                            "entry_price": curr,
                                            "stop_loss": sl_price,
                                            "dist": dist,
                                            "highest": curr,
                                            "lowest": curr,
                                            "lots": lots,
                                            "tp1_hit": False,
                                            "booked_pnl": 0.0
                                        })
                                        
                        wins = [t for t in trades if t["pnl_usd"] > 0]
                        losses = [t for t in trades if t["pnl_usd"] < 0]
                        gp = sum(t["pnl_usd"] for t in wins)
                        gl = abs(sum(t["pnl_usd"] for t in losses))
                        pf = round(gp / gl, 2) if gl else 99.0
                        net = round(capital - 50.0, 2)
                        wr = round(len(wins) / len(trades) * 100, 1) if trades else 0.0
                        if net > 0 and pf >= 1.2:
                            print(f"Score>={min_score} | TP1={tp1_rr}R | Max={max_rr}R | Trail={trail_mult} -> Net: ${net:+7.2f} (+{net/50*100:6.1f}%) | PF: {pf:4.2f} | WR: {wr:4.1f}% | Trades: {len(trades):3d} | DD: -${max_dd:5.2f}")

if __name__ == '__main__':
    sweep_crypto()
