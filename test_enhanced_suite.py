import sys
from datetime import datetime
from data.database import DatabaseManager

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db = DatabaseManager()

def evaluate_smart_scaleout(symbol, tp1_rr=1.5, max_rr=6.0, trail_be_cushion=0.15, score_threshold=2):
    c_val = {"BTCUSD": 0.001, "ETHUSD": 0.01, "SLVONUSD": 0.1, "XAUTUSD": 0.001}[symbol]
    decimals = {"BTCUSD": 1, "ETHUSD": 2, "SLVONUSD": 3, "XAUTUSD": 1}[symbol]
    min_stop = {"BTCUSD": 160.0, "ETHUSD": 8.0, "SLVONUSD": 0.30, "XAUTUSD": 3.0}[symbol]
    pad = {"BTCUSD": 45.0, "ETHUSD": 2.2, "SLVONUSD": 0.06, "XAUTUSD": 1.2}[symbol]
    bad_hours = {
        "BTCUSD": [12, 13, 15, 16],
        "ETHUSD": [14, 16, 18, 19],
        "XAUTUSD": [11, 12, 16, 19, 20, 21, 22],
        "SLVONUSD": [6, 7, 8, 9, 16, 18, 19, 20, 22, 23]
    }[symbol]

    candles = db.get_latest_candles(symbol, "15m", 35000)
    capital = 50.0
    maker_fee = 0.0001
    trades = []
    active = None
    last_close_ts = -999999999.0

    curr_day = None
    day_v = 0.0; day_pv = 0.0; day_pr = []

    for i in range(50, len(candles)):
        c = candles[i]
        curr = float(c["close"])
        ts = c["timestamp"]
        bt = datetime.fromtimestamp(ts)
        hm = bt.strftime("%H:%M")

        if not ("06:00" <= hm <= "23:45") or bt.hour in bad_hours:
            continue

        d_str = bt.strftime("%Y-%m-%d")
        typ = (float(c["high"]) + float(c["low"]) + curr) / 3.0
        v = max(1.0, float(c.get("volume", 1.0)))

        if d_str != curr_day:
            curr_day = d_str; day_v = 0.0; day_pv = 0.0; day_pr = []
        day_v += v; day_pv += typ * v; day_pr.append(typ)
        vwap = day_pv / day_v
        stdev = max(1.0, (sum((x - (sum(day_pr)/len(day_pr)))**2 for x in day_pr)/len(day_pr))**0.5)

        # 1. Manage Active Position
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

                # Scale-out condition: reach tp1_rr OR reach 1.1R + VWAP resistance
                hit_vwap = float(c["high"]) >= vwap and gain_r >= 1.0
                trigger_tp1 = (gain_r >= tp1_rr) or (hit_vwap and gain_r >= 1.1)

                if not active["tp1_hit"] and trigger_tp1:
                    active["tp1_hit"] = True
                    actual_r = max(1.0, min(gain_r, tp1_rr))
                    tp1_p = round(entry + actual_r * dist, decimals)
                    pnl_p = (p_lots * c_val * (tp1_p - entry)) - (p_lots * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_p
                    capital += pnl_p
                    # Move SL to Breakeven + cushion
                    active["sl"] = max(active["sl"], round(entry + trail_be_cushion * dist, decimals))

                if active["tp1_hit"]:
                    if gain_r >= 2.5:
                        active["sl"] = max(active["sl"], round(entry + 1.2 * dist, decimals))
                    if gain_r >= 4.0:
                        active["sl"] = max(active["sl"], round(entry + 2.5 * dist, decimals))
                    if gain_r >= 6.0:
                        active["sl"] = max(active["sl"], round(entry + 4.0 * dist, decimals))
                    if gain_r >= 10.0:
                        active["sl"] = max(active["sl"], round(entry + 7.0 * dist, decimals))
                    if gain_r >= 15.0:
                        active["sl"] = max(active["sl"], round(entry + 11.0 * dist, decimals))

                    if gain_r >= 2.2:
                        recent_swing = min(float(x["low"]) for x in candles[max(0, i-4):i])
                        trail_level = max(recent_swing - (0.08 * dist), active["highest"] - (1.1 * dist))
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
                trigger_tp1 = (gain_r >= tp1_rr) or (hit_vwap and gain_r >= 1.1)

                if not active["tp1_hit"] and trigger_tp1:
                    active["tp1_hit"] = True
                    actual_r = max(1.0, min(gain_r, tp1_rr))
                    tp1_p = round(entry - actual_r * dist, decimals)
                    pnl_p = (p_lots * c_val * (entry - tp1_p)) - (p_lots * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_p
                    capital += pnl_p
                    active["sl"] = min(active["sl"], round(entry - trail_be_cushion * dist, decimals))

                if active["tp1_hit"]:
                    if gain_r >= 2.5:
                        active["sl"] = min(active["sl"], round(entry - 1.2 * dist, decimals))
                    if gain_r >= 4.0:
                        active["sl"] = min(active["sl"], round(entry - 2.5 * dist, decimals))
                    if gain_r >= 6.0:
                        active["sl"] = min(active["sl"], round(entry - 4.0 * dist, decimals))
                    if gain_r >= 10.0:
                        active["sl"] = min(active["sl"], round(entry - 7.0 * dist, decimals))
                    if gain_r >= 15.0:
                        active["sl"] = min(active["sl"], round(entry - 11.0 * dist, decimals))

                    if gain_r >= 2.2:
                        recent_swing = max(float(x["high"]) for x in candles[max(0, i-4):i])
                        trail_level = min(recent_swing + (0.08 * dist), active["lowest"] + (1.1 * dist))
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
            req_score = 3 if is_morning else score_threshold

            is_buy = (buy_score >= req_score) and (sell_score == 0) and buy_confirmed and buy_not_knife
            is_sell = (sell_score >= req_score) and (buy_score == 0) and sell_confirmed and sell_not_spike

            if is_buy or is_sell:
                recent_window = candles[max(0, i-6):i]
                if is_buy:
                    sw_low = min(float(x["low"]) for x in recent_window)
                    dist = max(min_stop, (curr - sw_low) + pad)
                    sl = round(curr - dist, decimals)
                else:
                    sw_high = max(float(x["high"]) for x in recent_window)
                    dist = max(min_stop, (sw_high - curr) + pad)
                    sl = round(curr + dist, decimals)

                side = "BUY" if is_buy else "SELL"
                lots = max(2, int(round(5.0 / (dist * c_val))))
                p_lots = max(1, lots // 2)

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

    print(f"{symbol:<8} (TP1={tp1_rr}R, Max={max_rr}R): Net=+${net:>8.2f} | WR={wr:>5.1f}% ({len(wins)}W/{len(losses)}L) | PF={pf:>4.2f} | Trades={len(trades)}")
    return {"net": net, "wr": wr, "pf": pf, "trades": trades}

print("=== TESTING ENHANCED HIGH WIN-RATE + HIGH PROFIT ===")
for sym, rrs in [("BTCUSD", [(1.3, 6.0), (1.5, 6.0), (1.8, 6.0)]),
                 ("ETHUSD", [(1.3, 4.5), (1.5, 4.5), (1.8, 4.5)]),
                 ("XAUTUSD", [(1.3, 20.0), (1.5, 20.0), (1.8, 20.0)]),
                 ("SLVONUSD", [(1.3, 20.0), (1.5, 20.0), (1.8, 20.0)])]:
    for tp1, mx in rrs:
        evaluate_smart_scaleout(sym, tp1_rr=tp1, max_rr=mx)
