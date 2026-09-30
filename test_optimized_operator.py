import sys
from data.database import DatabaseManager

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db = DatabaseManager()

def run_pure_operator(symbol, candles, bad_hours, max_rr=20.0, tp1_rr=1.8, min_score=2, buffer_pad=None, min_stop=None):
    s = symbol.upper()
    p = {
        "BTCUSD": {"c_val": 0.001, "decimals": 1, "min_stop": 160.0, "pad": 45.0},
        "ETHUSD": {"c_val": 0.01, "decimals": 2, "min_stop": 8.0, "pad": 2.2},
        "SLVONUSD": {"c_val": 0.1, "decimals": 3, "min_stop": 0.30, "pad": 0.06},
        "XAUTUSD": {"c_val": 0.001, "decimals": 1, "min_stop": 3.0, "pad": 1.2}
    }[s]

    c_val = p["c_val"]
    decimals = p["decimals"]
    _min_stop = min_stop or p["min_stop"]
    _pad = buffer_pad or p["pad"]

    capital = 50.0
    maker_fee = 0.0001
    trades = []
    active = None
    last_close_ts = -999999999.0

    from datetime import datetime
    curr_day = None
    day_v = 0.0; day_pv = 0.0; day_pr = []

    for i in range(50, len(candles)):
        c = candles[i]
        curr = float(c["close"])
        ts = c["timestamp"]
        bt = datetime.fromtimestamp(ts)
        hm = bt.strftime("%H:%M")

        if not ("06:00" <= hm <= "23:45"):
            continue

        # Hour filter
        if bt.hour in bad_hours:
            continue

        d_str = bt.strftime("%Y-%m-%d")
        typ = (float(c["high"]) + float(c["low"]) + curr) / 3.0
        v = max(1.0, float(c.get("volume", 1.0)))

        if d_str != curr_day:
            curr_day = d_str; day_v = 0.0; day_pv = 0.0; day_pr = []
        day_v += v; day_pv += typ * v; day_pr.append(typ)
        vwap = day_pv / day_v
        stdev = max(1.0, (sum((x - (sum(day_pr)/len(day_pr)))**2 for x in day_pr)/len(day_pr))**0.5)

        # 1. Manage active trade
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

                # Scale out @ tp1_rr or VWAP
                hit_vwap = float(c["high"]) >= vwap and gain_r >= 1.0
                trigger_tp1 = (hit_vwap or gain_r >= tp1_rr) if max_rr < 10.0 else (gain_r >= tp1_rr)
                if not active["tp1_hit"] and trigger_tp1:
                    active["tp1_hit"] = True
                    tp1_used = max(1.2, min(gain_r, tp1_rr))
                    tp1_p = round(entry + tp1_used * dist, decimals)
                    pnl_p = (p_lots * c_val * (tp1_p - entry)) - (p_lots * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_p
                    capital += pnl_p
                    active["sl"] = max(active["sl"], round(entry + 0.15 * dist, decimals))

                if active["tp1_hit"]:
                    if gain_r >= 3.5:
                        active["sl"] = max(active["sl"], round(entry + 1.5 * dist, decimals))
                    elif gain_r >= 2.2:
                        active["sl"] = max(active["sl"], round(entry + 1.0 * dist, decimals))
                    if gain_r >= 6.0:
                        active["sl"] = max(active["sl"], round(entry + 3.5 * dist, decimals))
                    if gain_r >= 10.0:
                        active["sl"] = max(active["sl"], round(entry + 6.0 * dist, decimals))
                    if gain_r >= 15.0:
                        active["sl"] = max(active["sl"], round(entry + 10.0 * dist, decimals))
                    if gain_r >= 20.0:
                        active["sl"] = max(active["sl"], round(entry + 15.0 * dist, decimals))

                    if gain_r >= 2.8:
                        recent_swing = min(float(x["low"]) for x in candles[max(0, i-4):i])
                        trail_level = max(recent_swing - (0.10 * dist), active["highest"] - (1.2 * dist))
                        active["sl"] = max(active["sl"], round(trail_level, decimals))

                hit_sl = float(c["low"]) <= active["sl"]
                hit_max_tp = float(c["high"]) >= round(entry + max_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry + max_rr * dist, decimals) if hit_max_tp else active["sl"]
                    pnl_rem = (rem_lots * c_val * (exit_p - entry)) - (rem_lots * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem

                    active.update({
                        "exit_price": exit_p,
                        "pnl_usd": total_pnl,
                        "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": "MAX_TP" if hit_max_tp else ("BE_TRAIL" if active["tp1_hit"] else "SL")
                    })
                    trades.append(active)
                    active = None
                    last_close_ts = float(c["timestamp"])
                    continue

            else: # SELL
                if float(c["low"]) < active["lowest"]:
                    active["lowest"] = float(c["low"])
                gain_r = (entry - active["lowest"]) / dist

                hit_vwap = float(c["low"]) <= vwap and gain_r >= 1.0
                trigger_tp1 = (hit_vwap or gain_r >= tp1_rr) if max_rr < 10.0 else (gain_r >= tp1_rr)
                if not active["tp1_hit"] and trigger_tp1:
                    active["tp1_hit"] = True
                    tp1_used = max(1.2, min(gain_r, tp1_rr))
                    tp1_p = round(entry - tp1_used * dist, decimals)
                    pnl_p = (p_lots * c_val * (entry - tp1_p)) - (p_lots * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_p
                    capital += pnl_p
                    active["sl"] = min(active["sl"], round(entry - 0.15 * dist, decimals))

                if active["tp1_hit"]:
                    if gain_r >= 3.5:
                        active["sl"] = min(active["sl"], round(entry - 1.5 * dist, decimals))
                    elif gain_r >= 2.2:
                        active["sl"] = min(active["sl"], round(entry - 1.0 * dist, decimals))
                    if gain_r >= 6.0:
                        active["sl"] = min(active["sl"], round(entry - 3.5 * dist, decimals))
                    if gain_r >= 10.0:
                        active["sl"] = min(active["sl"], round(entry - 6.0 * dist, decimals))
                    if gain_r >= 15.0:
                        active["sl"] = min(active["sl"], round(entry - 10.0 * dist, decimals))
                    if gain_r >= 20.0:
                        active["sl"] = min(active["sl"], round(entry - 15.0 * dist, decimals))

                    if gain_r >= 2.8:
                        recent_swing = max(float(x["high"]) for x in candles[max(0, i-4):i])
                        trail_level = min(recent_swing + (0.10 * dist), active["lowest"] + (1.2 * dist))
                        active["sl"] = min(active["sl"], round(trail_level, decimals))

                hit_sl = float(c["high"]) >= active["sl"]
                hit_max_tp = float(c["low"]) <= round(entry - max_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry - max_rr * dist, decimals) if hit_max_tp else active["sl"]
                    pnl_rem = (rem_lots * c_val * (entry - exit_p)) - (rem_lots * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem

                    active.update({
                        "exit_price": exit_p,
                        "pnl_usd": total_pnl,
                        "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": "MAX_TP" if hit_max_tp else ("BE_TRAIL" if active["tp1_hit"] else "SL")
                    })
                    trades.append(active)
                    active = None
                    last_close_ts = float(c["timestamp"])
                    continue

        # 2. Entry
        time_since_close = float(c["timestamp"]) - last_close_ts
        if not active and time_since_close >= 600.0:
            sub = candles[max(0, i-15):i]
            hi8 = max(float(x["high"]) for x in sub[-8:])
            lo8 = min(float(x["low"]) for x in sub[-8:])
            delta = float(c.get("delta", 0.0))
            delta_ratio = delta / v

            p1 = candles[i-1]
            p2 = candles[i-2] if i >= 2 else p1
            prev_bear = (float(p1["close"]) < float(p1["open"])) and (float(p2["close"]) < float(p2["open"]))
            prev_bull = (float(p1["close"]) > float(p1["open"])) and (float(p2["close"]) > float(p2["open"]))

            bar_range = max(0.01, float(c["high"]) - float(c["low"]))
            lower_wick = (min(float(c["open"]), curr) - float(c["low"])) / bar_range
            upper_wick = (float(c["high"]) - max(float(c["open"]), curr)) / bar_range

            buy_confirmed = (curr > float(c["open"])) or (lower_wick >= 0.28 and curr >= float(c["low"]) + 0.40 * bar_range)
            buy_not_knife = not (prev_bear and curr < float(c["open"]) and lower_wick < 0.35)

            sell_confirmed = (curr < float(c["open"])) or (upper_wick >= 0.28 and curr <= float(c["high"]) - 0.40 * bar_range)
            sell_not_spike = not (prev_bull and curr > float(c["open"]) and upper_wick < 0.35)

            sweep_buy = (float(c["low"]) < lo8) and (curr > lo8) and (delta_ratio >= 0.02)
            sweep_sell = (float(c["high"]) > hi8) and (curr < hi8) and (delta_ratio <= -0.02)

            vwap_buy = (len(day_pr) >= 6) and (float(c["low"]) <= vwap - 1.8*stdev) and (curr > float(c["open"])) and (delta_ratio >= 0.02)
            vwap_sell = (len(day_pr) >= 6) and (float(c["high"]) >= vwap + 1.8*stdev) and (curr < float(c["open"])) and (delta_ratio <= -0.02)

            absorb_buy = (float(c["low"]) <= lo8 * 1.0005) and (delta_ratio >= 0.04) and buy_confirmed
            absorb_sell = (float(c["high"]) >= hi8 * 0.9995) and (delta_ratio <= -0.04) and sell_confirmed

            if i >= 200:
                ema200 = sum(float(x["close"]) for x in candles[i-200:i]) / 200.0
                macro_bull = curr > ema200
                macro_bear = curr < ema200
            else:
                macro_bull = True; macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            is_morning = ("06:00" <= hm < "12:30")
            req_score = 3 if is_morning else min_score

            is_buy = (buy_score >= req_score) and (sell_score == 0) and buy_confirmed and buy_not_knife
            is_sell = (sell_score >= req_score) and (buy_score == 0) and sell_confirmed and sell_not_spike

            if is_buy or is_sell:
                recent_window = candles[max(0, i-6):i]
                if is_buy:
                    sw_low = min(float(x["low"]) for x in recent_window)
                    dist = max(_min_stop, (curr - sw_low) + _pad)
                    sl = round(curr - dist, decimals)
                else:
                    sw_high = max(float(x["high"]) for x in recent_window)
                    dist = max(_min_stop, (sw_high - curr) + _pad)
                    sl = round(curr + dist, decimals)

                side = "BUY" if is_buy else "SELL"
                lots = max(2, int(round(5.0 / (dist * c_val))))
                tp_pct = 0.40 if max_rr >= 10.0 else 0.50
                p_lots = max(1, int(round(lots * tp_pct)))

                active = {
                    "id": f"OP_{symbol}_{c['timestamp']}",
                    "symbol": symbol,
                    "side": side,
                    "entry_price": curr,
                    "sl": sl,
                    "dist": dist,
                    "lots": lots,
                    "p_lots": p_lots,
                    "highest": curr,
                    "lowest": curr,
                    "tp1_hit": False,
                    "booked": 0.0,
                    "opened_at": bt.strftime("%Y-%m-%d %H:%M:%S")
                }

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    gp = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    pf = gp / gl if gl > 0 else 99.0
    net = round(capital - 50.0, 2)
    wr = len(wins) / len(trades) * 100 if trades else 0.0

    return {
        "net_pl": net,
        "win_rate": wr,
        "profit_factor": pf,
        "trades": trades,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses)
    }

# Test tuning BTC
b_c = db.get_latest_candles("BTCUSD", "15m", 35000)
print("=== BTC Tuning ===")
for bh in [[13, 15, 16], [12, 13, 15, 16], [12, 13, 15, 16, 18]]:
    res = run_pure_operator("BTCUSD", b_c, bad_hours=bh, max_rr=6.0)
    print(f"BTC BadHours={bh}: Net=+${res['net_pl']:>7.2f} | WR={res['win_rate']:>4.1f}% | PF={res['profit_factor']:>4.2f} | Trades={res['total_trades']}")

# Test tuning ETH
e_c = db.get_latest_candles("ETHUSD", "15m", 35000)
print("\n=== ETH Tuning ===")
for bh in [[16, 18, 19], [14, 16, 18, 19], [16, 18, 19, 23]]:
    res = run_pure_operator("ETHUSD", e_c, bad_hours=bh, max_rr=4.5)
    print(f"ETH BadHours={bh}: Net=+${res['net_pl']:>7.2f} | WR={res['win_rate']:>4.1f}% | PF={res['profit_factor']:>4.2f} | Trades={res['total_trades']}")

# Test tuning Gold
g_c = db.get_latest_candles("XAUTUSD", "15m", 35000)
print("\n=== Gold Tuning ===")
for bh in [[16, 19, 20, 22], [10, 11, 12, 16, 19, 20, 21, 22], [11, 12, 16, 19, 20, 21, 22]]:
    res = run_pure_operator("XAUTUSD", g_c, bad_hours=bh, max_rr=20.0)
    print(f"Gold BadHours={bh}: Net=+${res['net_pl']:>7.2f} | WR={res['win_rate']:>4.1f}% | PF={res['profit_factor']:>4.2f} | Trades={res['total_trades']}")

# Test tuning Silver
s_c = db.get_latest_candles("SLVONUSD", "15m", 35000)
print("\n=== Silver Tuning ===")
for bh in [[16, 18, 19, 23], [6, 7, 8, 9, 16, 18, 19, 20, 22, 23], [7, 8, 16, 18, 19, 20, 22, 23]]:
    res = run_pure_operator("SLVONUSD", s_c, bad_hours=bh, max_rr=20.0)
    print(f"Silver BadHours={bh}: Net=+${res['net_pl']:>7.2f} | WR={res['win_rate']:>4.1f}% | PF={res['profit_factor']:>4.2f} | Trades={res['total_trades']}")
