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

db = DatabaseManager()
b_c = db.get_latest_candles("BTCUSD", "15m", limit=35000)
e_c = db.get_latest_candles("ETHUSD", "15m", limit=35000)
g_c = db.get_latest_candles("XAUTUSD", "15m", limit=35000)
s_c = db.get_latest_candles("SLVONUSD", "15m", limit=35000)

def test_strategy_engine(
    name,
    strat_type="OPERATOR_HYBRID", # "OPERATOR_HYBRID", "MEGA_RUNNER_20R", "MEGA_RUNNER_30R", "ASIAN_FILTERED"
    allow_morning=True,
    morning_min_score=3, # Stricter filter during 06:00-12:00 IST
    max_rr=20.0,
    tp1_rr=2.0,
    tp1_pct=0.40,
    use_stepped=False
):
    maker_fee = 0.0001
    TARGET_RISK = 5.0
    symbols_data = [
        ("BTCUSD", b_c, 0.001, 160.0, 45.0, 1),
        ("ETHUSD", e_c, 0.01, 8.0, 2.2, 2),
        ("XAUTUSD", g_c, 0.001, 3.0, 1.2, 2),
        ("SLVONUSD", s_c, 0.1, 0.25, 0.08, 3)
    ]
    all_trades = []

    for symbol, candles, c_val, min_stop, buffer_pad, decimals in symbols_data:
        capital = 50.0
        active = None
        curr_day = None
        day_v = 0.0; day_pv = 0.0; day_pr = []

        for i in range(50, len(candles)):
            c = candles[i]; curr = float(c["close"]); ts = c["timestamp"]
            bt = dt.datetime.fromtimestamp(ts)
            hm = bt.strftime("%H:%M")
            is_morning = ("06:00" <= hm < "12:30")
            
            # If morning is not allowed at all:
            if is_morning and not allow_morning:
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

            # ---------------------------------------------------------
            # TRADE MANAGEMENT
            # ---------------------------------------------------------
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

                    # Milestone 1: Scale out part at tp1_rr (e.g. 2.0R) and lock BE
                    if not active["tp1_hit"] and gain_r >= tp1_rr:
                        active["tp1_hit"] = True
                        tp1_p = round(entry + tp1_rr * dist, decimals)
                        pnl_p = (p_lots * c_val * (tp1_p - entry)) - (p_lots * c_val * tp1_p * maker_fee * 2)
                        active["booked"] = pnl_p
                        capital += pnl_p
                        active["sl"] = max(active["sl"], round(entry + 0.15 * dist, decimals))

                    # Milestone 2: At 3.5R, lock +1.5R
                    if active["tp1_hit"] and gain_r >= 3.5:
                        active["sl"] = max(active["sl"], round(entry + 1.5 * dist, decimals))

                    # Milestone 3: At 6.0R, lock +3.5R
                    if active["tp1_hit"] and gain_r >= 6.0:
                        active["sl"] = max(active["sl"], round(entry + 3.5 * dist, decimals))

                    # Milestone 4: At 10.0R, lock +6.0R
                    if active["tp1_hit"] and gain_r >= 10.0:
                        active["sl"] = max(active["sl"], round(entry + 6.0 * dist, decimals))

                    # Milestone 5: At 15.0R, lock +10.0R
                    if active["tp1_hit"] and gain_r >= 15.0:
                        active["sl"] = max(active["sl"], round(entry + 10.0 * dist, decimals))

                    # Milestone 6: At 20.0R, lock +15.0R
                    if active["tp1_hit"] and gain_r >= 20.0:
                        active["sl"] = max(active["sl"], round(entry + 15.0 * dist, decimals))

                    # Dynamic structural trail behind swing low
                    if active["tp1_hit"] and gain_r >= 2.5:
                        recent_swing = min(float(x["low"]) for x in candles[max(0, i-4):i])
                        trail_level = max(recent_swing - (0.10 * dist), active["highest"] - (1.3 * dist))
                        active["sl"] = max(active["sl"], round(trail_level, decimals))

                    hit_sl = float(c["low"]) <= active["sl"]
                    hit_max_tp = float(c["high"]) >= round(entry + max_rr * dist, decimals)

                    if hit_sl or hit_max_tp:
                        exit_p = round(entry + max_rr * dist, decimals) if hit_max_tp else active["sl"]
                        pnl_rem = (rem_lots * c_val * (exit_p - entry)) - (rem_lots * c_val * exit_p * maker_fee * 2)
                        total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                        capital += pnl_rem
                        rr_final = round((exit_p - entry) / dist, 1) if not active["tp1_hit"] else round((tp1_rr * tp1_pct) + (((exit_p - entry) / dist) * (1.0 - tp1_pct)), 1)

                        active.update({
                            "exit_price": exit_p,
                            "pnl_usd": total_pnl,
                            "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                            "close_reason": f"MAX_RR_{max_rr}R" if hit_max_tp else ("RUNNER_TRAIL" if active["tp1_hit"] else "STOP_LOSS"),
                            "rr_achieved": rr_final,
                            "status": "CLOSED"
                        })
                        all_trades.append(active)
                        active = None
                        continue

                else: # SELL
                    if float(c["low"]) < active["lowest"]:
                        active["lowest"] = float(c["low"])
                    gain_r = (entry - active["lowest"]) / dist

                    if not active["tp1_hit"] and gain_r >= tp1_rr:
                        active["tp1_hit"] = True
                        tp1_p = round(entry - tp1_rr * dist, decimals)
                        pnl_p = (p_lots * c_val * (entry - tp1_p)) - (p_lots * c_val * tp1_p * maker_fee * 2)
                        active["booked"] = pnl_p
                        capital += pnl_p
                        active["sl"] = min(active["sl"], round(entry - 0.15 * dist, decimals))

                    if active["tp1_hit"] and gain_r >= 3.5:
                        active["sl"] = min(active["sl"], round(entry - 1.5 * dist, decimals))

                    if active["tp1_hit"] and gain_r >= 6.0:
                        active["sl"] = min(active["sl"], round(entry - 3.5 * dist, decimals))

                    if active["tp1_hit"] and gain_r >= 10.0:
                        active["sl"] = min(active["sl"], round(entry - 6.0 * dist, decimals))

                    if active["tp1_hit"] and gain_r >= 15.0:
                        active["sl"] = min(active["sl"], round(entry - 10.0 * dist, decimals))

                    if active["tp1_hit"] and gain_r >= 20.0:
                        active["sl"] = min(active["sl"], round(entry - 15.0 * dist, decimals))

                    if active["tp1_hit"] and gain_r >= 2.5:
                        recent_swing = max(float(x["high"]) for x in candles[max(0, i-4):i])
                        trail_level = min(recent_swing + (0.10 * dist), active["lowest"] + (1.3 * dist))
                        active["sl"] = min(active["sl"], round(trail_level, decimals))

                    hit_sl = float(c["high"]) >= active["sl"]
                    hit_max_tp = float(c["low"]) <= round(entry - max_rr * dist, decimals)

                    if hit_sl or hit_max_tp:
                        exit_p = round(entry - max_rr * dist, decimals) if hit_max_tp else active["sl"]
                        pnl_rem = (rem_lots * c_val * (entry - exit_p)) - (rem_lots * c_val * exit_p * maker_fee * 2)
                        total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                        capital += pnl_rem
                        rr_final = round((entry - exit_p) / dist, 1) if not active["tp1_hit"] else round((tp1_rr * tp1_pct) + (((entry - exit_p) / dist) * (1.0 - tp1_pct)), 1)

                        active.update({
                            "exit_price": exit_p,
                            "pnl_usd": total_pnl,
                            "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                            "close_reason": f"MAX_RR_{max_rr}R" if hit_max_tp else ("RUNNER_TRAIL" if active["tp1_hit"] else "STOP_LOSS"),
                            "rr_achieved": rr_final,
                            "status": "CLOSED"
                        })
                        all_trades.append(active)
                        active = None
                        continue

            # ---------------------------------------------------------
            # ENTRY LOGIC
            # ---------------------------------------------------------
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

                vwap_buy = (len(day_pr) >= 6) and (float(c["low"]) <= lower_vwap) and (curr > float(c["open"])) and (delta_ratio >= 0.02)
                vwap_sell = (len(day_pr) >= 6) and (float(c["high"]) >= upper_vwap) and (curr < float(c["open"])) and (delta_ratio <= -0.02)

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

                # In morning 06:00-12:30 IST, require higher score to ensure institutional conviction
                if is_morning:
                    req_score = morning_min_score
                else:
                    req_score = 2 if ("BTC" in symbol or "ETH" in symbol) else 1

                is_buy = (buy_score >= req_score) and (sell_score == 0) and buy_confirmed and buy_not_knife
                is_sell = (sell_score >= req_score) and (buy_score == 0) and sell_confirmed and sell_not_spike

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

                    if use_stepped:
                        gain_ratio = max(0.0, (capital - 50.0) / 50.0)
                        trade_risk = min(35.0, round(TARGET_RISK * (1.0 + 0.50 * gain_ratio), 2))
                    else:
                        trade_risk = TARGET_RISK

                    lots = max(2, int(round(trade_risk / (dist * c_val))))
                    p_lots = max(1, int(round(lots * tp1_pct)))

                    active = {
                        "symbol": symbol,
                        "side": side,
                        "entry_price": curr,
                        "sl": sl,
                        "orig_sl": sl,
                        "dist": dist,
                        "lots": lots,
                        "p_lots": p_lots,
                        "highest": curr,
                        "lowest": curr,
                        "tp1_hit": False,
                        "opened_at": bt.strftime("%Y-%m-%d %H:%M:%S")
                    }

    all_trades.sort(key=lambda x: x["opened_at"])
    wins = [t for t in all_trades if t["pnl_usd"] > 0]
    losses = [t for t in all_trades if t["pnl_usd"] < 0]
    gw = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    net = sum(t["pnl_usd"] for t in all_trades)
    pf = gw / gl if gl > 0 else 99.0
    wr = len(wins) / len(all_trades) * 100 if all_trades else 0
    max_win = max((t["pnl_usd"] for t in wins), default=0.0)

    # Morning trades analysis
    m_trades = [t for t in all_trades if "06:00" <= t["opened_at"].split(" ")[1][:5] < "12:30"]
    m_wins = [t for t in m_trades if t["pnl_usd"] > 0]
    m_net = sum(t["pnl_usd"] for t in m_trades)
    m_wr = (len(m_wins) / len(m_trades) * 100) if m_trades else 0

    return {
        "name": name,
        "total": len(all_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "gross_profit": round(gw, 2),
        "gross_loss": round(gl, 2),
        "net_pl": round(net, 2),
        "max_win": round(max_win, 2),
        "morning_count": len(m_trades),
        "morning_net": round(m_net, 2),
        "morning_wr": round(m_wr, 1)
    }

print("Simulating Strategies with R:R up to 1:20 and 1:30 & IST 06:00 to 12:00 PM Data...")
strats = [
    # 1. High R:R 1:20 with Morning Institutional Filter (score >= 3)
    test_strategy_engine("👑 1:20 R:R Institutional Runner (Morning Filtered)", max_rr=20.0, tp1_rr=2.0, tp1_pct=0.40, allow_morning=True, morning_min_score=3),
    # 2. High R:R 1:30 with Morning Institutional Filter
    test_strategy_engine("💎 1:30 R:R Grandmaster Runner (Morning Filtered)", max_rr=30.0, tp1_rr=2.0, tp1_pct=0.40, allow_morning=True, morning_min_score=3),
    # 3. 1:15 R:R Asymmetric Monster
    test_strategy_engine("⚡ 1:15 R:R Asymmetric Monster (Cut 50% @ 2.0R)", max_rr=15.0, tp1_rr=2.0, tp1_pct=0.50, allow_morning=True, morning_min_score=3),
    # 4. 1:10 R:R Balanced Runner
    test_strategy_engine("🏆 1:10 R:R Balanced Runner (Cut 50% @ 2.0R)", max_rr=10.0, tp1_rr=2.0, tp1_pct=0.50, allow_morning=True, morning_min_score=3),
    # 5. 1:20 R:R Stepped Growth Compounder
    test_strategy_engine("🚀 1:20 R:R Stepped Growth Compounder", max_rr=20.0, tp1_rr=2.0, tp1_pct=0.40, allow_morning=True, morning_min_score=3, use_stepped=True),
    # 6. 1:30 R:R Stepped Growth Compounder
    test_strategy_engine("🚀 1:30 R:R Stepped Growth Compounder", max_rr=30.0, tp1_rr=2.0, tp1_pct=0.40, allow_morning=True, morning_min_score=3, use_stepped=True),
]

for s in strats:
    print("\n" + "="*85)
    print(f"STRATEGY: {s['name']}")
    print(f"Total Trades: {s['total']:4d} | Win Rate: {s['win_rate']:4.1f}% | Profit Factor: {s['profit_factor']:4.2f}")
    print(f"Gross Win: +${s['gross_profit']:,.2f} | Gross Loss: -${s['gross_loss']:,.2f}")
    print(f"Real Net P&L: +${s['net_pl']:,.2f} USD (+₹{s['net_pl']*90:,.0f} INR)")
    print(f"Max Single Win: +${s['max_win']:,.2f} (Huge Runner Asymmetry)")
    print(f"Morning Session (06:00-12:30 IST): {s['morning_count']} Trades | WR: {s['morning_wr']}% | Morning Net: ${s['morning_net']:+7.2f}")
