import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import datetime as dt
from data.database import DatabaseManager

def run_simulation(
    symbol, candles, c_val, min_stop, buffer_pad, decimals,
    max_target_rr=20.0,
    partial_take_profit_rr=2.5,
    partial_pct=0.33,
    start_hour_str="06:00",
    end_hour_str="23:45",
    use_stepped_risk=False
):
    capital = 50.0
    trades = []
    active = None
    curr_day = None
    day_v = 0.0; day_pv = 0.0; day_pr = []
    maker_fee = 0.0001
    TARGET_RISK = 5.0

    for i in range(50, len(candles)):
        c = candles[i]; curr = float(c["close"]); ts = c["timestamp"]
        bt = dt.datetime.fromtimestamp(ts)
        hm = bt.strftime("%H:%M")
        
        # User requirement: Trade from IST 06:00 AM to 12:00 PM and throughout the day!
        if not (start_hour_str <= hm <= end_hour_str):
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

        # -------------------------------------------------------------
        # 1. MANAGE ACTIVE POSITION FOR ULTRA-HIGH R:R (1:10, 1:20, 1:30)
        # -------------------------------------------------------------
        if active:
            side = active["side"]
            entry = active["entry_price"]
            dist = active["dist"]
            lots = active["lots"]
            partial_lots = active["partial_lots"]
            rem_lots = (lots - partial_lots) if active["partial_taken"] else lots

            if side == "BUY":
                if float(c["high"]) > active["highest"]:
                    active["highest"] = float(c["high"])
                gain_r = (active["highest"] - entry) / dist

                # Milestone 1: Partial Profit Booking & BE Lock
                if not active["partial_taken"] and gain_r >= partial_take_profit_rr:
                    active["partial_taken"] = True
                    tp_price = round(entry + (partial_take_profit_rr * dist), decimals)
                    booked = (partial_lots * c_val * (tp_price - entry)) - (partial_lots * c_val * tp_price * maker_fee * 2)
                    active["booked"] = booked
                    capital += booked
                    # Lock Stop to BE + fee cushion (+0.15R)
                    active["sl"] = max(active["sl"], round(entry + 0.15 * dist, decimals))

                # Milestone 2: 4.0R reached -> Lock in +2.0R guaranteed
                if active["partial_taken"] and gain_r >= 4.0:
                    active["sl"] = max(active["sl"], round(entry + 2.0 * dist, decimals))

                # Milestone 3: 8.0R reached -> Lock in +5.0R guaranteed
                if active["partial_taken"] and gain_r >= 8.0:
                    active["sl"] = max(active["sl"], round(entry + 5.0 * dist, decimals))

                # Milestone 4: 15.0R reached -> Lock in +10.0R guaranteed
                if active["partial_taken"] and gain_r >= 15.0:
                    active["sl"] = max(active["sl"], round(entry + 10.0 * dist, decimals))

                # Dynamic Trailing behind Market Structure Swing Lows (4 bars)
                if active["partial_taken"] and gain_r >= 3.0:
                    recent_swing = min(float(x["low"]) for x in candles[max(0, i-5):i])
                    trail_level = max(recent_swing - (0.15 * dist), active["highest"] - (1.5 * dist))
                    active["sl"] = max(active["sl"], round(trail_level, decimals))

                hit_sl = float(c["low"]) <= active["sl"]
                hit_max_tp = float(c["high"]) >= round(entry + max_target_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry + max_target_rr * dist, decimals) if hit_max_tp else active["sl"]
                    pnl_rem = (rem_lots * c_val * (exit_p - entry)) - (rem_lots * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem
                    rr_final = round((exit_p - entry) / dist, 1) if not active["partial_taken"] else round((partial_take_profit_rr * partial_pct) + (((exit_p - entry) / dist) * (1.0 - partial_pct)), 1)

                    active.update({
                        "exit_price": exit_p,
                        "pnl_usd": total_pnl,
                        "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"MAX_RR_{max_target_rr}R" if hit_max_tp else ("RUNNER_TRAIL" if active["partial_taken"] else "STOP_LOSS"),
                        "rr_achieved": rr_final,
                        "status": "CLOSED"
                    })
                    trades.append(active)
                    active = None
                    continue

            else: # SELL
                if float(c["low"]) < active["lowest"]:
                    active["lowest"] = float(c["low"])
                gain_r = (entry - active["lowest"]) / dist

                # Milestone 1: Partial Profit Booking & BE Lock
                if not active["partial_taken"] and gain_r >= partial_take_profit_rr:
                    active["partial_taken"] = True
                    tp_price = round(entry - (partial_take_profit_rr * dist), decimals)
                    booked = (partial_lots * c_val * (entry - tp_price)) - (partial_lots * c_val * tp_price * maker_fee * 2)
                    active["booked"] = booked
                    capital += booked
                    active["sl"] = min(active["sl"], round(entry - 0.15 * dist, decimals))

                # Milestone 2: 4.0R reached -> Lock in +2.0R guaranteed
                if active["partial_taken"] and gain_r >= 4.0:
                    active["sl"] = min(active["sl"], round(entry - 2.0 * dist, decimals))

                # Milestone 3: 8.0R reached -> Lock in +5.0R guaranteed
                if active["partial_taken"] and gain_r >= 8.0:
                    active["sl"] = min(active["sl"], round(entry - 5.0 * dist, decimals))

                # Milestone 4: 15.0R reached -> Lock in +10.0R guaranteed
                if active["partial_taken"] and gain_r >= 15.0:
                    active["sl"] = min(active["sl"], round(entry - 10.0 * dist, decimals))

                # Dynamic Trailing behind Market Structure Swing Highs (4 bars)
                if active["partial_taken"] and gain_r >= 3.0:
                    recent_swing = max(float(x["high"]) for x in candles[max(0, i-5):i])
                    trail_level = min(recent_swing + (0.15 * dist), active["lowest"] + (1.5 * dist))
                    active["sl"] = min(active["sl"], round(trail_level, decimals))

                hit_sl = float(c["high"]) >= active["sl"]
                hit_max_tp = float(c["low"]) <= round(entry - max_target_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry - max_target_rr * dist, decimals) if hit_max_tp else active["sl"]
                    pnl_rem = (rem_lots * c_val * (entry - exit_p)) - (rem_lots * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem
                    rr_final = round((entry - exit_p) / dist, 1) if not active["partial_taken"] else round((partial_take_profit_rr * partial_pct) + (((entry - exit_p) / dist) * (1.0 - partial_pct)), 1)

                    active.update({
                        "exit_price": exit_p,
                        "pnl_usd": total_pnl,
                        "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"MAX_RR_{max_target_rr}R" if hit_max_tp else ("RUNNER_TRAIL" if active["partial_taken"] else "STOP_LOSS"),
                        "rr_achieved": rr_final,
                        "status": "CLOSED"
                    })
                    trades.append(active)
                    active = None
                    continue

        # -------------------------------------------------------------
        # 2. ENTRY LOGIC: OPERATOR SMART MONEY + ASIAN MORNING & BEYOND
        # -------------------------------------------------------------
        if not active:
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

            vwap_buy = (len(day_pr) >= 4) and (float(c["low"]) <= lower_vwap) and (curr > float(c["open"])) and (delta_ratio >= 0.02)
            vwap_sell = (len(day_pr) >= 4) and (float(c["high"]) >= upper_vwap) and (curr < float(c["open"])) and (delta_ratio <= -0.02)

            absorb_buy = (float(c["low"]) <= lo8 * 1.0005) and (delta_ratio >= 0.04) and buy_confirmed
            absorb_sell = (float(c["high"]) >= hi8 * 0.9995) and (delta_ratio <= -0.04) and sell_confirmed

            if i >= 200:
                ema200 = sum(float(x["close"]) for x in candles[i-200:i]) / 200.0
                macro_bull = curr > ema200
                macro_bear = curr < ema200
            else:
                macro_bull = True
                macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            min_score = 2 if ("BTC" in symbol or "ETH" in symbol) else 1

            is_buy = (buy_score >= min_score) and (sell_score == 0) and buy_confirmed and buy_not_knife
            is_sell = (sell_score >= min_score) and (buy_score == 0) and sell_confirmed and sell_not_spike

            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                recent_window = candles[max(0, i-6):i]

                if is_buy:
                    sweep_low = min(float(x["low"]) for x in recent_window)
                    dist = max(min_stop, (curr - sweep_low) + buffer_pad)
                    sl = round(curr - dist, decimals)
                else:
                    sweep_high = max(float(x["high"]) for x in recent_window)
                    dist = max(min_stop, (sweep_high - curr) + buffer_pad)
                    sl = round(curr + dist, decimals)

                if use_stepped_risk:
                    gain_ratio = max(0.0, (capital - 50.0) / 50.0)
                    trade_risk = min(35.0, round(TARGET_RISK * (1.0 + 0.50 * gain_ratio), 2))
                else:
                    trade_risk = TARGET_RISK

                lots = max(2, int(round(trade_risk / (dist * c_val))))
                partial_lots = max(1, int(round(lots * partial_pct)))

                active = {
                    "symbol": symbol,
                    "side": side,
                    "entry_price": curr,
                    "sl": sl,
                    "orig_sl": sl,
                    "dist": dist,
                    "lots": lots,
                    "partial_lots": partial_lots,
                    "highest": curr,
                    "lowest": curr,
                    "partial_taken": False,
                    "opened_at": bt.strftime("%Y-%m-%d %H:%M:%S")
                }

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    gross_win = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses))
    net_pl = sum(t["pnl_usd"] for t in trades)
    pf = (gross_win / gross_loss) if gross_loss > 0 else 99.0
    wr = (len(wins) / len(trades) * 100) if trades else 0

    return {
        "symbol": symbol,
        "trades": trades,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "gross_profit": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pl": round(net_pl, 2),
        "max_win": max((t["pnl_usd"] for t in wins), default=0.0)
    }

def main():
    db = DatabaseManager()
    print("Loading 35,000 candles per pair...")
    b_c = db.get_latest_candles("BTCUSD", "15m", limit=35000)
    e_c = db.get_latest_candles("ETHUSD", "15m", limit=35000)
    g_c = db.get_latest_candles("XAUTUSD", "15m", limit=35000)
    s_c = db.get_latest_candles("SLVONUSD", "15m", limit=35000)

    print("\n" + "="*90)
    print(" 🚀 TESTING MULTIPLE STRATEGIES & HIGH R:R (1:5, 1:10, 1:15, 1:20, 1:30) [IST 06:00 - 23:45] 🚀")
    print("="*90)

    configs = [
        ("Balanced Asymmetric (1:6.0 Max R:R | Cut 50% @ 2.0R)", 6.0, 2.0, 0.50, False),
        ("High R:R Trend Runner (1:10.0 Max R:R | Cut 33% @ 2.5R)", 10.0, 2.5, 0.33, False),
        ("Ultra R:R Moonshot (1:15.0 Max R:R | Cut 33% @ 2.5R)", 15.0, 2.5, 0.33, False),
        ("👑 Apex Macro Monster (1:20.0 Max R:R | Cut 25% @ 2.5R)", 20.0, 2.5, 0.25, False),
        ("💎 Grandmaster Apex (1:30.0 Max R:R | Cut 20% @ 2.5R)", 30.0, 2.5, 0.20, False),
        ("🚀 1:20 R:R Stepped Growth Compounder", 20.0, 2.5, 0.25, True),
        ("🚀 1:30 R:R Stepped Growth Compounder", 30.0, 2.5, 0.20, True),
    ]

    for title, max_rr, pt_rr, pt_pct, stepped in configs:
        res_b = run_simulation("BTCUSD", b_c, 0.001, 160.0, 45.0, 1, max_target_rr=max_rr, partial_take_profit_rr=pt_rr, partial_pct=pt_pct, use_stepped_risk=stepped)
        res_e = run_simulation("ETHUSD", e_c, 0.01, 8.0, 2.2, 2, max_target_rr=max_rr, partial_take_profit_rr=pt_rr, partial_pct=pt_pct, use_stepped_risk=stepped)
        res_g = run_simulation("XAUTUSD", g_c, 0.001, 3.0, 1.2, 2, max_target_rr=max_rr, partial_take_profit_rr=pt_rr, partial_pct=pt_pct, use_stepped_risk=stepped)
        res_s = run_simulation("SLVONUSD", s_c, 0.1, 0.25, 0.08, 3, max_target_rr=max_rr, partial_take_profit_rr=pt_rr, partial_pct=pt_pct, use_stepped_risk=stepped)

        all_t = res_b["trades"] + res_e["trades"] + res_g["trades"] + res_s["trades"]
        all_t.sort(key=lambda x: x["opened_at"])
        wins = [t for t in all_t if t["pnl_usd"] > 0]
        losses = [t for t in all_t if t["pnl_usd"] < 0]
        gw = sum(t["pnl_usd"] for t in wins)
        gl = abs(sum(t["pnl_usd"] for t in losses))
        net = sum(t["pnl_usd"] for t in all_t)
        pf = gw / gl if gl > 0 else 99.0
        wr = len(wins) / len(all_t) * 100 if all_t else 0
        max_single = max((t["pnl_usd"] for t in wins), default=0.0)

        # Count morning trades (06:00 - 12:00 IST)
        morning_trades = [t for t in all_t if "06:00" <= t["opened_at"].split(" ")[1][:5] <= "12:00"]
        m_pnl = sum(t["pnl_usd"] for t in morning_trades)

        print(f"\n▶ STRATEGY: {title}")
        print(f"   Total Trades: {len(all_t):4d} (Morning 06:00-12:00 IST: {len(morning_trades)} trades, Net: ${m_pnl:+7.2f})")
        print(f"   Win Rate:     {wr:4.1f}% ({len(wins)}W / {len(losses)}L)")
        print(f"   Profit Factor:{pf:4.2f}")
        print(f"   Max Single Win: +${max_single:6.2f} (Single Trade Return: +{round(max_single/5.0, 1)}R)")
        print(f"   Gross Win/Loss: +${gw:,.2f} / -${gl:,.2f}")
        print(f"   Real Net P&L:   ${net:+9.2f} USD (+₹{net * 90.0:,.0f} INR)")

if __name__ == "__main__":
    main()
