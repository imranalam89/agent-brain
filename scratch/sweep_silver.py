import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)

def eval_silver(del_th=0.03, tp1_high=2.0, tp1_mod=1.5, trail=1.2, min_dist=0.20, pad=0.05, filter_chop=True):
    capital = 50.0
    equity_curve = [capital]
    trades = []
    active_trade = None
    contract_val = 1.0
    bad_hours = {16, 19, 20, 22} if filter_chop else set()

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

        upper_vwap = vwap + (1.8 * stdev)
        lower_vwap = vwap - (1.8 * stdev)

        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half_lots = max(1, lots // 2)
            tp1_target = active_trade["tp1_rr"]
            max_target = active_trade["max_rr"]

            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1_target:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_target * dist, 3)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * 0.0002)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 3))

                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["highest"] - (trail * dist), 3)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                if c["low"] <= active_trade["stop_loss"] or c["high"] >= round(entry + max_target * dist, 3):
                    exit_price = round(entry + max_target * dist, 3) if c["high"] >= round(entry + max_target * dist, 3) else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * 0.0002)
                    capital += rem_pnl
                    equity_curve.append(capital)
                    trades.append(active_trade["booked_pnl"] + rem_pnl)
                    active_trade = None
                    continue
            else:
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1_target:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_target * dist, 3)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * 0.0002)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 3))

                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["lowest"] + (trail * dist), 3)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                if c["high"] >= active_trade["stop_loss"] or c["low"] <= round(entry - max_target * dist, 3):
                    exit_price = round(entry - max_target * dist, 3) if c["low"] <= round(entry - max_target * dist, 3) else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * 0.0002)
                    capital += rem_pnl
                    equity_curve.append(capital)
                    trades.append(active_trade["booked_pnl"] + rem_pnl)
                    active_trade = None
                    continue

        if not active_trade and (bar_time.hour not in bad_hours):
            sub = candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)

            vwap_buy = (len(day_prices) >= 6) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 6) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            absorb_buy = (c["low"] <= lo12 * 1.0005) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9995) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

            if i >= 200:
                ema200 = sum(x["close"] for x in candles[i-200:i]) / 200.0
                macro_bull = (curr > ema200)
                macro_bear = (curr < ema200)
            else:
                macro_bull = macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            is_buy = (buy_score >= 1) and (sell_score == 0)
            is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                score = buy_score if is_buy else sell_score
                is_high_conv = (score >= 2)
                tp1_target = tp1_high if is_high_conv else tp1_mod
                max_target = 5.0 if is_high_conv else 2.5

                dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + pad)
                sl = round(curr - dist if is_buy else curr + dist, 3)
                lots = max(2, int(round(5.0 / (dist * contract_val))))
                active_trade = {
                    "side": "BUY" if is_buy else "SELL",
                    "entry_price": curr,
                    "stop_loss": sl,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "tp1_rr": tp1_target,
                    "max_rr": max_target,
                    "tp1_hit": False,
                    "booked_pnl": 0.0
                }

    if not trades:
        return None
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    wr = len(wins) / len(trades) * 100
    net = capital - 50.0
    gp = sum(wins)
    gl = abs(sum(losses))
    pf = (gp / gl) if gl > 0 else float("inf")
    
    peak = 50.0
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd

    return {
        "trades": len(trades),
        "wr": wr,
        "pf": pf,
        "net": net,
        "max_dd": max_dd,
        "params": (del_th, tp1_high, tp1_mod, trail, min_dist, pad, filter_chop)
    }

results = []
for del_th in [0.03, 0.04, 0.05]:
    for tp1_high in [1.5, 2.0, 2.5]:
        for tp1_mod in [1.0, 1.5]:
            for trail in [1.0, 1.2, 1.5]:
                for min_dist in [0.20, 0.30]:
                    r = eval_silver(del_th=del_th, tp1_high=tp1_high, tp1_mod=tp1_mod, trail=trail, min_dist=min_dist, pad=0.06, filter_chop=True)
                    if r and r["trades"] >= 80:
                        results.append(r)

results.sort(key=lambda x: x["net"], reverse=True)
print("TOP 5 PARAMETER SETS BY NET PROFIT:")
for r in results[:5]:
    print(f"Net: ${r['net']:+7.2f} | PF: {r['pf']:4.2f} | WR: {r['wr']:5.1f}% | Trades: {r['trades']:3d} | DD: -${r['max_dd']:5.2f} | Params: {r['params']}")

results.sort(key=lambda x: x["pf"], reverse=True)
print("\nTOP 5 PARAMETER SETS BY PROFIT FACTOR:")
for r in results[:5]:
    print(f"PF: {r['pf']:4.2f} | Net: ${r['net']:+7.2f} | WR: {r['wr']:5.1f}% | Trades: {r['trades']:3d} | DD: -${r['max_dd']:5.2f} | Params: {r['params']}")
