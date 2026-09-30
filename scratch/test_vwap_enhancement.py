import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)

def test_vwap_compounding(sigma=1.8, risk_pct=0.06, tp1_rr=2.0, min_rr=3.0, trail_dist=1.2):
    capital = 50.0
    trades = []
    equity = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active = None
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
        
        if active:
            side = active["side"]
            entry = active["entry_price"]
            dist = active["dist"]
            lots = active["lots"]
            half = max(1, lots // 2)
            
            if side == "BUY":
                if c["high"] > active["highest"]:
                    active["highest"] = c["high"]
                gain_r = (active["highest"] - entry) / dist
                if not active["tp1_hit"] and gain_r >= tp1_rr:
                    active["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 2)
                    pnl_half = (half * 0.001 * (tp1_p - entry)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active["stop_loss"] = max(active["stop_loss"], round(entry + 0.15 * dist, 2))
                if active["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active["highest"] - trail_dist * dist, 2)
                    if new_sl > active["stop_loss"]:
                        active["stop_loss"] = new_sl
                if c["low"] <= active["stop_loss"] or c["high"] >= (entry + min_rr * dist):
                    exit_p = (entry + min_rr * dist) if c["high"] >= (entry + min_rr * dist) else active["stop_loss"]
                    rem_lots = (lots - half) if active["tp1_hit"] else lots
                    diff = exit_p - entry
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    trades.append(tot)
                    equity.append({"timestamp": ts, "equity": round(capital, 2)})
                    active = None
            else: # SELL
                if c["low"] < active["lowest"]:
                    active["lowest"] = c["low"]
                gain_r = (entry - active["lowest"]) / dist
                if not active["tp1_hit"] and gain_r >= tp1_rr:
                    active["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 2)
                    pnl_half = (half * 0.001 * (entry - tp1_p)) - (half * 0.001 * tp1_p * maker_fee * 2)
                    active["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active["stop_loss"] = min(active["stop_loss"], round(entry - 0.15 * dist, 2))
                if active["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active["lowest"] + trail_dist * dist, 2)
                    if new_sl < active["stop_loss"]:
                        active["stop_loss"] = new_sl
                if c["high"] >= active["stop_loss"] or c["low"] <= (entry - min_rr * dist):
                    exit_p = (entry - min_rr * dist) if c["low"] <= (entry - min_rr * dist) else active["stop_loss"]
                    rem_lots = (lots - half) if active["tp1_hit"] else lots
                    diff = entry - exit_p
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_p * maker_fee * 2)
                    tot = round(active["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    trades.append(tot)
                    equity.append({"timestamp": ts, "equity": round(capital, 2)})
                    active = None
                    
        if not active and len(day_prices) >= 6:
            delta = c.get("delta", 0.0)
            delta_ratio = delta / v
            
            is_buy = (c["low"] <= lower_band) and (c["close"] > c["open"]) and (delta_ratio >= 0.04)
            is_sell = (c["high"] >= upper_band) and (c["close"] < c["open"]) and (delta_ratio <= -0.04)
            
            if is_buy or is_sell:
                dist = max(2.5, abs(curr - (c["low"] if is_buy else c["high"])) + 0.6)
                sl_p = round(curr - dist if is_buy else curr + dist, 2)
                risk_usd = max(2.0, min(capital * risk_pct, 30.0))
                lots = max(2, int(round(risk_usd / (dist * 0.001))))
                active = {
                    "side": "BUY" if is_buy else "SELL",
                    "entry_price": curr,
                    "stop_loss": sl_p,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "tp1_hit": False,
                    "booked_pnl": 0.0
                }
                
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    gw = sum(wins)
    gl = abs(sum(losses)) if losses else 1.0
    pf = gw/gl if gl>0 else 0
    net = capital - 50.0
    roi = (net / 50.0) * 100
    peak = 50.0
    max_dd = 0.0
    for pt in equity:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = peak - pt["equity"]
        if dd > max_dd:
            max_dd = dd
    print(f"Sig:{sigma:.1f} Risk:{risk_pct*100:3.0f}% TP1:{tp1_rr:.1f} RR:{min_rr:.1f} | Trades:{len(trades):3d} | WR:{wr:4.1f}% | PF:{pf:4.2f} | Net:+${net:>7.2f} ({roi:>6.1f}%) | EndCap:${capital:>7.2f} | MaxDD:-${max_dd:>5.2f}")

print("=" * 105)
for s in [1.5, 1.8, 2.0]:
    for rp in [0.04, 0.06, 0.08]:
        for tp in [1.5, 2.0]:
            for r in [2.5, 3.5]:
                test_vwap_compounding(sigma=s, risk_pct=rp, tp1_rr=tp, min_rr=r)
