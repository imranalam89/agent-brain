import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("BTCUSD", "15m", limit=35000)

def test_btc_engine(skip_hours=set(), max_rr=3.5):
    c_val = 0.001
    decimals = 1
    _min_stop = 160.0
    _buffer_pad = 45.0
    capital = 50.0
    trades = []
    active = None
    last_close_ts = -999999999.0
    maker_fee = 0.0001

    curr_day = None
    day_v = 0.0; day_pv = 0.0; day_pr = []

    for i in range(50, len(candles)):
        c = candles[i]; curr = float(c["close"]); ts = c["timestamp"]
        bt = datetime.fromtimestamp(ts)
        hm = bt.strftime("%H:%M")

        if not ("06:00" <= hm <= "23:45"):
            continue

        if bt.hour in skip_hours:
            continue

        d_str = bt.strftime("%Y-%m-%d")
        typ = (float(c["high"]) + float(c["low"]) + curr) / 3.0
        v = max(1.0, float(c.get("volume", 1.0)))

        if d_str != curr_day:
            curr_day = d_str; day_v = 0.0; day_pv = 0.0; day_pr = []
        day_v += v; day_pv += typ * v; day_pr.append(typ)
        vwap = day_pv / day_v
        stdev = max(1.0, (sum((x - (sum(day_pr)/len(day_pr)))**2 for x in day_pr)/len(day_pr))**0.5)
        upper_vwap = vwap + 1.8 * stdev
        lower_vwap = vwap - 1.8 * stdev

        if active:
            side = active["side"]
            entry = active["entry_price"]
            dist = active["dist"]
            lots = active["lots"]
            p_lots = active["p_lots"]
            rem_lots = (lots - p_lots) if active["tp1_hit"] else lots

            if side == "BUY":
                if float(c["high"]) > active["highest"]:
                    active["highest"] = float(c["high"])
                gain_r = (active["highest"] - entry) / dist

                hit_vwap = float(c["high"]) >= vwap and gain_r >= 1.0
                trigger_tp1 = (hit_vwap or gain_r >= 1.8) if max_rr < 10.0 else (gain_r >= 2.0)
                if not active["tp1_hit"] and trigger_tp1:
                    active["tp1_hit"] = True
                    tp1_rr_used = max(1.2, min(gain_r, 2.0))
                    tp1_p = round(entry + tp1_rr_used * dist, decimals)
                    pnl_p = (p_lots * c_val * (tp1_p - entry)) - (p_lots * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_p
                    capital += pnl_p
                    active["sl"] = max(active["sl"], round(entry + 0.15 * dist, decimals))

                if active["tp1_hit"]:
                    if gain_r >= 2.2:
                        active["sl"] = max(active["sl"], round(entry + 1.0 * dist, decimals))

                hit_sl = float(c["low"]) <= active["sl"]
                hit_max_tp = float(c["high"]) >= round(entry + max_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry + max_rr * dist, decimals) if hit_max_tp else active["sl"]
                    pnl_rem = (rem_lots * c_val * (exit_p - entry)) - (rem_lots * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem
                    rr_final = round((exit_p - entry) / dist, 1) if not active["tp1_hit"] else round((1.8 * 0.5) + (((exit_p - entry) / dist) * 0.5), 1)
                    active.update({"exit_price": exit_p, "pnl_usd": total_pnl, "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S")})
                    trades.append(active)
                    active = None
                    last_close_ts = float(c["timestamp"])
                    continue
            else: # SELL
                if float(c["low"]) < active["lowest"]:
                    active["lowest"] = float(c["low"])
                gain_r = (entry - active["lowest"]) / dist

                hit_vwap = float(c["low"]) <= vwap and gain_r >= 1.0
                trigger_tp1 = (hit_vwap or gain_r >= 1.8) if max_rr < 10.0 else (gain_r >= 2.0)
                if not active["tp1_hit"] and trigger_tp1:
                    active["tp1_hit"] = True
                    tp1_rr_used = max(1.2, min(gain_r, 2.0))
                    tp1_p = round(entry - tp1_rr_used * dist, decimals)
                    pnl_p = (p_lots * c_val * (entry - tp1_p)) - (p_lots * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_p
                    capital += pnl_p
                    active["sl"] = min(active["sl"], round(entry - 0.15 * dist, decimals))

                if active["tp1_hit"]:
                    if gain_r >= 2.2:
                        active["sl"] = min(active["sl"], round(entry - 1.0 * dist, decimals))

                hit_sl = float(c["high"]) >= active["sl"]
                hit_max_tp = float(c["low"]) <= round(entry - max_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry - max_rr * dist, decimals) if hit_max_tp else active["sl"]
                    pnl_rem = (rem_lots * c_val * (entry - exit_p)) - (rem_lots * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem
                    rr_final = round((entry - exit_p) / dist, 1) if not active["tp1_hit"] else round((1.8 * 0.5) + (((entry - exit_p) / dist) * 0.5), 1)
                    active.update({"exit_price": exit_p, "pnl_usd": total_pnl, "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S")})
                    trades.append(active)
                    active = None
                    last_close_ts = float(c["timestamp"])
                    continue

        time_since_close = float(c["timestamp"]) - last_close_ts
        is_in_cooldown = time_since_close < 600.0

        if not active and not is_in_cooldown:
            sub = candles[max(0, i-15):i]
            hi8 = max(float(x["high"]) for x in sub[-8:])
            lo8 = min(float(x["low"]) for x in sub[-8:])
            delta = float(c.get("delta", 0.0))
            delta_ratio = delta / v

            p1 = candles[i-1]
            p2 = candles[i-2] if i >= 2 else p1
            prev_bear_cascade = (float(p1["close"]) < float(p1["open"])) and (float(p2["close"]) < float(p2["open"]))
            prev_bull_cascade = (float(p1["close"]) > float(p1["open"])) and (float(p2["close"]) > float(p2["open"]))

            bar_range = max(0.01, float(c["high"]) - float(c["low"]))
            lower_wick = (min(float(c["open"]), curr) - float(c["low"])) / bar_range
            upper_wick = (float(c["high"]) - max(float(c["open"]), curr)) / bar_range

            buy_confirmed = (curr > float(c["open"])) or (lower_wick >= 0.28 and curr >= float(c["low"]) + 0.40 * bar_range)
            buy_not_knife = not (prev_bear_cascade and curr < float(c["open"]) and lower_wick < 0.35)
            sell_confirmed = (curr < float(c["open"])) or (upper_wick >= 0.28 and curr <= float(c["high"]) - 0.40 * bar_range)
            sell_not_spike = not (prev_bull_cascade and curr > float(c["open"]) and upper_wick < 0.35)

            sweep_buy = (float(c["low"]) < lo8) and (curr > lo8) and (delta_ratio >= 0.02)
            sweep_sell = (float(c["high"]) > hi8) and (curr < hi8) and (delta_ratio <= -0.02)
            vwap_buy = (len(day_pr) >= 6) and (float(c["low"]) <= lower_vwap) and (curr > float(c["open"])) and (delta_ratio >= 0.02)
            vwap_sell = (len(day_pr) >= 6) and (float(c["high"]) >= upper_vwap) and (curr < float(c["open"])) and (delta_ratio <= -0.02)
            absorb_buy = (float(c["low"]) <= lo8 * 1.0005) and (delta_ratio >= 0.04) and buy_confirmed
            absorb_sell = (float(c["high"]) >= hi8 * 0.9995) and (delta_ratio <= -0.04) and sell_confirmed

            if i >= 200:
                ema200 = sum(float(x["close"]) for x in candles[i-200:i]) / 200.0
                macro_bull = curr > ema200
                macro_bear = curr < ema200
            else:
                macro_bull = macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            is_morning = ("06:00" <= hm < "12:30")
            min_score = 3 if is_morning else 2

            is_buy = (buy_score >= min_score) and (sell_score == 0) and buy_confirmed and buy_not_knife
            is_sell = (sell_score >= min_score) and (buy_score == 0) and sell_confirmed and sell_not_spike

            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                recent_window = candles[max(0, i-6):i]
                if is_buy:
                    sw_low = min(float(x["low"]) for x in recent_window)
                    dist = max(_min_stop, (curr - sw_low) + _buffer_pad)
                    sl = round(curr - dist, decimals)
                else:
                    sw_high = max(float(x["high"]) for x in recent_window)
                    dist = max(_min_stop, (sw_high - curr) + _buffer_pad)
                    sl = round(curr + dist, decimals)

                trade_risk = 5.0
                lots = max(2, int(round(trade_risk / (dist * c_val))))
                p_lots = max(1, int(round(lots * 0.50)))
                active = {
                    "side": side, "entry_price": curr, "sl": sl, "dist": dist,
                    "lots": lots, "p_lots": p_lots, "highest": curr, "lowest": curr,
                    "tp1_hit": False, "opened_at": bt.strftime("%Y-%m-%d %H:%M:%S")
                }

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    gp = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    net = gp - gl
    pf = gp / gl if gl else 99.0
    print(f"Skip: {skip_hours} | MaxRR: {max_rr} -> Trades: {len(trades)}, WR: {wr:.1f}%, Net: ${net:<+8.2f}, PF: {pf:.2f}")

for sk in [set(), {13, 16}, {13, 15, 16}, {13, 15, 16, 17, 18}]:
    for mr in [3.0, 3.5, 4.0, 5.0, 6.0]:
        test_btc_engine(skip_hours=sk, max_rr=mr)
