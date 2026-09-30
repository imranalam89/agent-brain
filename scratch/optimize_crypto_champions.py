import os
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

def optimize_crypto_champions():
    db = DatabaseManager()
    btc_candles = db.get_latest_candles("BTCUSD", "15m", limit=30000)
    eth_candles = db.get_latest_candles("ETHUSD", "15m", limit=30000)
    
    maker_fee = 0.0001
    initial_capital = 50.0
    
    configs = [
        ("BTCUSD", btc_candles, 0.001, 180.0, 30.0, 35.0, 1),
        ("ETHUSD", eth_candles, 0.01, 8.0, 1.5, 1.5, 2)
    ]
    
    for symbol, candles, c_val, min_dist, pad, stdev_floor, decimals in configs:
        print(f"\n=======================================================")
        print(f"OPTIMIZING HIGH-WINRATE CHAMPION ON {symbol}")
        print(f"=======================================================")
        
        # Test varying sigma (1.6 to 2.0), tp1_rr (1.2 to 2.0), trail_mult, and bad_hours filter
        best_cfg = None
        best_score = -1
        
        for sigma in [1.7, 1.8, 1.9, 2.0]:
            for tp1_rr in [1.2, 1.5, 1.8, 2.0]:
                for max_rr in [3.0, 4.0, 5.0]:
                    for use_scale_out in [True, False]:
                        for filter_low_hours in [True, False]:
                            capital = initial_capital
                            peak = capital
                            max_dd = 0.0
                            trades = []
                            active_trade = None
                            
                            current_day = None
                            day_cum_vol = 0.0
                            day_cum_pv = 0.0
                            day_prices = []
                            bad_hours = {16, 19, 20} if filter_low_hours else set()
                            
                            for i in range(50, len(candles)):
                                c = candles[i]
                                curr = c["close"]
                                ts = c["timestamp"]
                                bar_time = datetime.fromtimestamp(ts)
                                hm = bar_time.strftime("%H:%M")
                                
                                # Session timing (12:30 - 23:45 UTC)
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
                                
                                if len(day_prices) < 4:
                                    continue
                                    
                                mean_p = sum(day_prices) / len(day_prices)
                                variance = sum((p - mean_p)**2 for p in day_prices) / len(day_prices)
                                stdev = max(stdev_floor, variance**0.5)
                                
                                upper_vwap = vwap + (sigma * stdev)
                                lower_vwap = vwap - (sigma * stdev)
                                
                                if active_trade:
                                    side = active_trade["side"]
                                    entry = active_trade["entry_price"]
                                    dist = active_trade["dist"]
                                    lots = active_trade["lots"]
                                    half_lots = max(1, lots // 2) if use_scale_out else lots
                                    
                                    if side == "BUY":
                                        if c["high"] > active_trade["highest"]:
                                            active_trade["highest"] = c["high"]
                                        gain_r = (active_trade["highest"] - entry) / dist
                                        
                                        if use_scale_out and not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                                            active_trade["tp1_hit"] = True
                                            tp1_p = round(entry + tp1_rr * dist, decimals)
                                            pnl_half = (half_lots * c_val * (tp1_p - entry)) - (half_lots * c_val * tp1_p * maker_fee * 2)
                                            active_trade["booked_pnl"] = pnl_half
                                            capital += pnl_half
                                            active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.10 * dist, decimals))
                                            
                                        hit_sl = c["low"] <= active_trade["stop_loss"]
                                        hit_tp = c["high"] >= round(entry + max_rr * dist, decimals) or curr >= vwap
                                        
                                        if hit_sl or hit_tp:
                                            exit_p = round(entry + max_rr * dist, decimals) if c["high"] >= round(entry + max_rr * dist, decimals) else (curr if hit_tp else active_trade["stop_loss"])
                                            rem_lots = (lots - half_lots) if (use_scale_out and active_trade["tp1_hit"]) else lots
                                            diff = exit_p - entry
                                            rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_p * maker_fee * 2)
                                            total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                                            capital += rem_pnl
                                            if capital > peak: peak = capital
                                            dd = peak - capital
                                            if dd > max_dd: max_dd = dd
                                            active_trade["pnl_usd"] = total_pnl
                                            trades.append(active_trade)
                                            active_trade = None
                                            continue
                                    else: # SELL
                                        if c["low"] < active_trade["lowest"]:
                                            active_trade["lowest"] = c["low"]
                                        gain_r = (entry - active_trade["lowest"]) / dist
                                        
                                        if use_scale_out and not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                                            active_trade["tp1_hit"] = True
                                            tp1_p = round(entry - tp1_rr * dist, decimals)
                                            pnl_half = (half_lots * c_val * (entry - tp1_p)) - (half_lots * c_val * tp1_p * maker_fee * 2)
                                            active_trade["booked_pnl"] = pnl_half
                                            capital += pnl_half
                                            active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.10 * dist, decimals))
                                            
                                        hit_sl = c["high"] >= active_trade["stop_loss"]
                                        hit_tp = c["low"] <= round(entry - max_rr * dist, decimals) or curr <= vwap
                                        
                                        if hit_sl or hit_tp:
                                            exit_p = round(entry - max_rr * dist, decimals) if c["low"] <= round(entry - max_rr * dist, decimals) else (curr if hit_tp else active_trade["stop_loss"])
                                            rem_lots = (lots - half_lots) if (use_scale_out and active_trade["tp1_hit"]) else lots
                                            diff = entry - exit_p
                                            rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_p * maker_fee * 2)
                                            total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                                            capital += rem_pnl
                                            if capital > peak: peak = capital
                                            dd = peak - capital
                                            if dd > max_dd: max_dd = dd
                                            active_trade["pnl_usd"] = total_pnl
                                            trades.append(active_trade)
                                            active_trade = None
                                            continue
                                
                                delta = c.get("delta", 0.0)
                                vol = max(1.0, c.get("volume", 1.0))
                                delta_ratio = delta / vol
                                
                                # Entry: Fade band extension with delta confirmation
                                is_buy = (c["low"] <= lower_vwap) and (c["close"] > lower_vwap) and (delta_ratio >= -0.10)
                                is_sell = (c["high"] >= upper_vwap) and (c["close"] < upper_vwap) and (delta_ratio <= 0.10)
                                
                                if is_buy or is_sell:
                                    side = "BUY" if is_buy else "SELL"
                                    dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + pad)
                                    sl_price = round(curr - dist if is_buy else curr + dist, decimals)
                                    lots = max(2, int(round(5.0 / (dist * c_val))))
                                    active_trade = {
                                        "side": side,
                                        "entry_price": curr,
                                        "stop_loss": sl_price,
                                        "dist": dist,
                                        "highest": curr,
                                        "lowest": curr,
                                        "lots": lots,
                                        "tp1_hit": False,
                                        "booked_pnl": 0.0
                                    }
                                    
                            wins = [t for t in trades if t["pnl_usd"] > 0]
                            losses = [t for t in trades if t["pnl_usd"] < 0]
                            gp = sum(t["pnl_usd"] for t in wins)
                            gl = abs(sum(t["pnl_usd"] for t in losses))
                            pf = round(gp / gl, 2) if gl else 99.0
                            net = round(capital - initial_capital, 2)
                            wr = round(len(wins) / len(trades) * 100, 1) if trades else 0.0
                            
                            # Score favoring high win rate & high profit factor
                            score = wr * pf * (net / max_dd if max_dd > 0 else 1.0)
                            
                            if wr >= 65.0 and pf >= 1.8 and net >= 800.0:
                                print(f"Sigma={sigma:.1f} | TP1={tp1_rr:.1f}R | Max={max_rr:.1f}R | ScaleOut={use_scale_out} | FilterChop={filter_low_hours} -> Net: ${net:+8.2f} (+{net/50*100:6.1f}%) | WR: {wr:4.1f}% | PF: {pf:4.2f} | Trades: {len(trades):3d} | Max DD: -${max_dd:5.2f}")

if __name__ == '__main__':
    optimize_crypto_champions()
