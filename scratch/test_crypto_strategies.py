import os
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

def test_crypto_ensemble():
    db = DatabaseManager()
    btc_candles = db.get_latest_candles("BTCUSD", "15m", limit=30000)
    eth_candles = db.get_latest_candles("ETHUSD", "15m", limit=30000)
    
    # Test different strategy concepts for BTC and ETH:
    # 1. VWAP Mean Reversion (Bands +/- 1.8 to 2.2 Sigma)
    # 2. Institutional Trend Pullback (200 EMA + 50 EMA Pullback with Footprint Delta)
    # 3. Liquidity Sweep Rejection (20-bar High/Low Sweep + CVD Absorption)
    
    for symbol, candles, c_val, min_dist, pad in [
        ("BTCUSD", btc_candles, 0.001, 200.0, 40.0),
        ("ETHUSD", eth_candles, 0.01, 10.0, 2.0)
    ]:
        print(f"\n=======================================================")
        print(f"Testing Strategy Concepts on {symbol} (Candles: {len(candles):,})")
        print(f"=======================================================")
        
        # Concept 1: Session VWAP Bands Reversion
        for sigma in [1.8, 2.0, 2.2]:
            for tp_rr in [1.5, 2.0, 2.5]:
                capital = 50.0
                peak = capital
                max_dd = 0.0
                trades = []
                active_trade = None
                
                current_day = None
                day_cum_vol = 0.0
                day_cum_pv = 0.0
                day_prices = []
                
                for i in range(50, len(candles)):
                    c = candles[i]
                    curr = c["close"]
                    ts = c["timestamp"]
                    bar_time = datetime.fromtimestamp(ts)
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
                    
                    if len(day_prices) < 10:
                        continue
                        
                    mean_p = sum(day_prices) / len(day_prices)
                    variance = sum((p - mean_p)**2 for p in day_prices) / len(day_prices)
                    stdev = max(1.0, variance**0.5)
                    
                    upper_vwap = vwap + (sigma * stdev)
                    lower_vwap = vwap - (sigma * stdev)
                    
                    if active_trade:
                        side = active_trade["side"]
                        entry = active_trade["entry_price"]
                        dist = active_trade["dist"]
                        lots = active_trade["lots"]
                        
                        if side == "BUY":
                            if c["low"] <= active_trade["stop_loss"]:
                                exit_p = active_trade["stop_loss"]
                                pnl = (lots * c_val * (exit_p - entry)) - (lots * c_val * exit_p * 0.0002)
                                capital += pnl
                                if capital > peak: peak = capital
                                if peak - capital > max_dd: max_dd = peak - capital
                                active_trade["pnl_usd"] = round(pnl, 2)
                                trades.append(active_trade)
                                active_trade = None
                            elif c["high"] >= round(entry + tp_rr * dist, 2) or curr >= vwap:
                                exit_p = round(entry + tp_rr * dist, 2) if c["high"] >= round(entry + tp_rr * dist, 2) else curr
                                pnl = (lots * c_val * (exit_p - entry)) - (lots * c_val * exit_p * 0.0002)
                                capital += pnl
                                if capital > peak: peak = capital
                                if peak - capital > max_dd: max_dd = peak - capital
                                active_trade["pnl_usd"] = round(pnl, 2)
                                trades.append(active_trade)
                                active_trade = None
                        else:
                            if c["high"] >= active_trade["stop_loss"]:
                                exit_p = active_trade["stop_loss"]
                                pnl = (lots * c_val * (entry - exit_p)) - (lots * c_val * exit_p * 0.0002)
                                capital += pnl
                                if capital > peak: peak = capital
                                if peak - capital > max_dd: max_dd = peak - capital
                                active_trade["pnl_usd"] = round(pnl, 2)
                                trades.append(active_trade)
                                active_trade = None
                            elif c["low"] <= round(entry - tp_rr * dist, 2) or curr <= vwap:
                                exit_p = round(entry - tp_rr * dist, 2) if c["low"] <= round(entry - tp_rr * dist, 2) else curr
                                pnl = (lots * c_val * (entry - exit_p)) - (lots * c_val * exit_p * 0.0002)
                                capital += pnl
                                if capital > peak: peak = capital
                                if peak - capital > max_dd: max_dd = peak - capital
                                active_trade["pnl_usd"] = round(pnl, 2)
                                trades.append(active_trade)
                                active_trade = None
                        continue
                        
                    # Entry condition: fade extension beyond bands
                    is_buy = c["low"] < lower_vwap and c["close"] > lower_vwap
                    is_sell = c["high"] > upper_vwap and c["close"] < upper_vwap
                    
                    if is_buy or is_sell:
                        side = "BUY" if is_buy else "SELL"
                        dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + pad)
                        sl_p = curr - dist if is_buy else curr + dist
                        lots = max(2, int(round(5.0 / (dist * c_val))))
                        active_trade = {
                            "side": side,
                            "entry_price": curr,
                            "stop_loss": sl_p,
                            "dist": dist,
                            "lots": lots
                        }
                        
                wins = [t for t in trades if t["pnl_usd"] > 0]
                losses = [t for t in trades if t["pnl_usd"] < 0]
                gp = sum(t["pnl_usd"] for t in wins)
                gl = abs(sum(t["pnl_usd"] for t in losses))
                pf = round(gp / gl, 2) if gl else 99.0
                net = round(capital - 50.0, 2)
                wr = round(len(wins) / len(trades) * 100, 1) if trades else 0.0
                if net > 0:
                    print(f"VWAP Sigma={sigma:.1f} | TP={tp_rr:.1f}R -> Net: ${net:+7.2f} (+{net/50*100:6.1f}%) | PF: {pf:4.2f} | WR: {wr:4.1f}% | Trades: {len(trades):3d} | DD: -${max_dd:5.2f}")

if __name__ == '__main__':
    test_crypto_ensemble()
