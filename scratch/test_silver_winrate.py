import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)

def eval_wr(tp1, max_rr, trail, min_d, del_th, bad_h, use_confluence_filter=True):
    contract_val = 1.0
    maker_fee = 0.0001
    fixed_risk = 5.0
    capital = 50.0

    trades = []
    equity_curve = [{"timestamp": silver_candles[50]["timestamp"], "equity": capital}]
    active_trade = None

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

        if bar_time.hour in bad_h:
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

            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1 * dist, 3)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 3))

                if active_trade["tp1_hit"] and gain_r >= (tp1 + 0.5):
                    new_sl = round(active_trade["highest"] - (trail * dist), 3)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 3)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 3) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append(total_pnl)
                    active_trade = None
                    continue
            else:
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1 * dist, 3)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 3))

                if active_trade["tp1_hit"] and gain_r >= (tp1 + 0.5):
                    new_sl = round(active_trade["lowest"] + (trail * dist), 3)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 3)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 3) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    trades.append(total_pnl)
                    active_trade = None
                    continue

        if not active_trade:
            sub = silver_candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)

            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            absorb_buy = (c["low"] <= lo12 * 1.0003) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

            if i >= 100:
                ema100 = sum(x["close"] for x in silver_candles[i-100:i]) / 100.0
                macro_bull = (curr > ema100)
                macro_bear = (curr < ema100)
            else:
                macro_bull = macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and (sweep_buy or absorb_buy))])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and (sweep_sell or absorb_sell))])

            if use_confluence_filter:
                # Require 2+ confluences OR strong absorption
                is_buy = (buy_score >= 2 or absorb_buy) and (sell_score == 0)
                is_sell = (sell_score >= 2 or absorb_sell) and (buy_score == 0)
            else:
                is_buy = (buy_score >= 1) and (sell_score == 0)
                is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                dist = max(min_d, abs(curr - (c["low"] if is_buy else c["high"])) + 0.05)
                sl = round(curr - dist if is_buy else curr + dist, 3)
                lots = max(2, int(round(fixed_risk / (dist * contract_val))))
                active_trade = {
                    "side": side,
                    "entry_price": curr,
                    "stop_loss": sl,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
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
    dd = 0.0
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak: peak = eq
        if peak - eq > dd: dd = peak - eq

    return {
        "trades": len(trades),
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "net": round(net, 2),
        "dd": round(dd, 2)
    }

print("Testing High Win-Rate Variations on Silver...")
for tp1 in [1.2, 1.4, 1.6, 1.8, 2.0]:
    for max_rr in [3.5, 4.0, 4.5]:
        for min_d in [0.25, 0.30, 0.35]:
            r = eval_wr(tp1, max_rr, 1.0, min_d, 0.03, {16, 18, 19, 23}, use_confluence_filter=True)
            if r and r["wr"] >= 48.0:
                print(f"TP1=1:{tp1} Max={max_rr}R MinD=${min_d} | WR: {r['wr']:4.1f}% | PF: {r['pf']:4.2f} | Net: ${r['net']:+7.2f} | Trades: {r['trades']:3d} | DD: -${r['dd']:5.2f}")
