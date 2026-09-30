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
gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=25000)
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)

def run_fast_hf(symbol, candles, del_th, tp1, max_rr, trail, min_dist, pad, bad_h, allow_concurrent=True):
    is_silver = "SLV" in symbol.upper()
    c_val = 1.0 if is_silver else 0.001
    capital = 50.0
    equity = [capital]
    trades = []
    active = []
    max_pos = 2 if allow_concurrent else 1

    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []
    days = set()

    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        bt = datetime.fromtimestamp(ts)

        if bt.weekday() in (5, 6):
            continue

        hm = bt.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue

        day_str = bt.strftime("%Y-%m-%d")
        days.add(day_str)
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
        stdev = max(0.1 if is_silver else 1.0, variance**0.5)

        upper_vwap = vwap + (1.8 * stdev)
        lower_vwap = vwap - (1.8 * stdev)

        # Manage active
        still = []
        for at in active:
            side = at["side"]
            entry = at["entry_price"]
            dist = at["dist"]
            lots = at["lots"]
            half_lots = max(1, lots // 2)

            if side == "BUY":
                if c["high"] > at["highest"]:
                    at["highest"] = c["high"]
                gain_r = (at["highest"] - entry) / dist

                if not at["tp1_hit"] and gain_r >= tp1:
                    at["tp1_hit"] = True
                    tp1_p = round(entry + tp1 * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * c_val * (tp1_p - entry)) - (half_lots * c_val * tp1_p * 0.0002)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    at["stop_loss"] = max(at["stop_loss"], round(entry + 0.15 * dist, 3 if is_silver else 2))

                if at["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(at["highest"] - (trail * dist), 3 if is_silver else 2)
                    if new_sl > at["stop_loss"]:
                        at["stop_loss"] = new_sl

                if c["low"] <= at["stop_loss"] or c["high"] >= round(entry + max_rr * dist, 3 if is_silver else 2):
                    exit_price = round(entry + max_rr * dist, 3 if is_silver else 2) if c["high"] >= round(entry + max_rr * dist, 3 if is_silver else 2) else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * 0.0002)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity.append(capital)
                    trades.append(total_pnl)
                else:
                    still.append(at)
            else:
                if c["low"] < at["lowest"]:
                    at["lowest"] = c["low"]
                gain_r = (entry - at["lowest"]) / dist

                if not at["tp1_hit"] and gain_r >= tp1:
                    at["tp1_hit"] = True
                    tp1_p = round(entry - tp1 * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * c_val * (entry - tp1_p)) - (half_lots * c_val * tp1_p * 0.0002)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    at["stop_loss"] = min(at["stop_loss"], round(entry - 0.15 * dist, 3 if is_silver else 2))

                if at["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(at["lowest"] + (trail * dist), 3 if is_silver else 2)
                    if new_sl < at["stop_loss"]:
                        at["stop_loss"] = new_sl

                if c["high"] >= at["stop_loss"] or c["low"] <= round(entry - max_rr * dist, 3 if is_silver else 2):
                    exit_price = round(entry - max_rr * dist, 3 if is_silver else 2) if c["low"] <= round(entry - max_rr * dist, 3 if is_silver else 2) else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * 0.0002)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity.append(capital)
                    trades.append(total_pnl)
                else:
                    still.append(at)

        active = still

        if len(active) < max_pos and (bt.hour not in bad_h):
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

            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            absorb_buy = (c["low"] <= lo12 * 1.0003) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

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
                if not any(at["side"] == side for at in active):
                    dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + pad)
                    sl = round(curr - dist if is_buy else curr + dist, 3 if is_silver else 2)
                    lots = max(2, int(round(5.0 / (dist * c_val))))
                    active.append({
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
    for eq in equity:
        if eq > peak: peak = eq
        if peak - eq > dd: dd = peak - eq

    t_per_day = len(trades) / len(days) if days else 0

    return {
        "trades": len(trades),
        "t_per_day": round(t_per_day, 1),
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "net": round(net, 2),
        "dd": round(dd, 2)
    }

print("=== TESTING FOCUSED SETUPS ON GOLD ===")
for del_th in [0.03, 0.035]:
    for tp1 in [2.0, 2.5]:
        for max_rr in [3.5, 4.5]:
            for bad_h in [{19, 22}, {16, 19, 20, 22}]:
                for conc in [True, False]:
                    r = run_fast_hf("XAUTUSD", gold_candles, del_th, tp1, max_rr, 1.2, 2.5, 0.6, bad_h, conc)
                    if r:
                        print(f"del={del_th} tp1={tp1} max={max_rr} chop={len(bad_h)} conc={conc} | Trades={r['trades']:3d} ({r['t_per_day']} t/d) | WR={r['wr']:4.1f}% | PF={r['pf']:4.2f} | Net=${r['net']:+7.2f} | DD=-${r['dd']:5.2f}")
