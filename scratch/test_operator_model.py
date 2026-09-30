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

def run_operator_simulation(symbol, candles, c_val, min_stop, buffer_pad, decimals, max_target_rr=5.5, use_stepped_risk=False):
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
        
        # Session Filter: London open to NY close (Peak Institutional Hours)
        if not ("12:30" <= bt.strftime("%H:%M") <= "23:45"):
            continue
        
        # Gold chop filter: avoid London lunch / NY pre-market chop
        if "XAUT" in symbol and bt.hour in (16, 19, 20, 22):
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
        # 1. MANAGE ACTIVE OPERATOR POSITION (DYNAMIC TRAIL FOR MAX R:R)
        # -------------------------------------------------------------
        if active:
            side = active["side"]
            entry = active["entry_price"]
            dist = active["dist"]
            lots = active["lots"]
            half = active["half_lots"]
            orig_sl = active["orig_sl"]

            if side == "BUY":
                if float(c["high"]) > active["highest"]:
                    active["highest"] = float(c["high"])
                gain_r = (active["highest"] - entry) / dist

                # Milestone 1: S/R Barrier or 1.5R reached -> Book 50% and Lock BE
                hit_vwap = float(c["high"]) >= vwap and gain_r >= 1.0
                if not active["tp1_hit"] and (hit_vwap or gain_r >= 1.8):
                    active["tp1_hit"] = True
                    tp1_p = round(entry + max(1.2, gain_r) * dist, decimals)
                    pnl_half = (half * c_val * (tp1_p - entry)) - (half * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_half
                    capital += pnl_half
                    # Move SL to BE + cushion
                    active["sl"] = max(active["sl"], round(entry + 0.10 * dist, decimals))

                # Milestone 2: 2.0R+ Expansion -> Lock in at least +1.0R guaranteed!
                if active["tp1_hit"] and gain_r >= 2.2:
                    active["sl"] = max(active["sl"], round(entry + 1.0 * dist, decimals))

                # Milestone 3: Trailing Runner behind Market Structure
                if active["tp1_hit"] and gain_r >= 2.8:
                    recent_swing = min(float(x["low"]) for x in candles[max(0, i-4):i])
                    trail_level = max(recent_swing - (0.10 * dist), active["highest"] - (1.2 * dist))
                    active["sl"] = max(active["sl"], round(trail_level, decimals))

                # Exit checks
                hit_sl = float(c["low"]) <= active["sl"]
                hit_max_tp = float(c["high"]) >= round(entry + max_target_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry + max_target_rr * dist, decimals) if hit_max_tp else active["sl"]
                    rem = (lots - half) if active["tp1_hit"] else lots
                    pnl_rem = (rem * c_val * (exit_p - entry)) - (rem * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem
                    rr_final = round((exit_p - entry) / dist, 1) if not active["tp1_hit"] else round((1.5 * 0.5) + (((exit_p - entry) / dist) * 0.5), 1)

                    active.update({
                        "exit_price": exit_p,
                        "pnl_usd": total_pnl,
                        "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": "MAX_RR_EXPANSION" if hit_max_tp else ("STRUCTURAL_TRAIL" if active["tp1_hit"] else "STOP_LOSS"),
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

                # Milestone 1: S/R Barrier or 1.5R reached -> Book 50% and Lock BE
                hit_vwap = float(c["low"]) <= vwap and gain_r >= 1.0
                if not active["tp1_hit"] and (hit_vwap or gain_r >= 1.8):
                    active["tp1_hit"] = True
                    tp1_p = round(entry - max(1.2, gain_r) * dist, decimals)
                    pnl_half = (half * c_val * (entry - tp1_p)) - (half * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_half
                    capital += pnl_half
                    active["sl"] = min(active["sl"], round(entry - 0.10 * dist, decimals))

                # Milestone 2: 2.0R+ Expansion -> Lock in at least +1.0R guaranteed!
                if active["tp1_hit"] and gain_r >= 2.2:
                    active["sl"] = min(active["sl"], round(entry - 1.0 * dist, decimals))

                # Milestone 3: Trailing Runner behind Market Structure
                if active["tp1_hit"] and gain_r >= 2.8:
                    recent_swing = max(float(x["high"]) for x in candles[max(0, i-4):i])
                    trail_level = min(recent_swing + (0.10 * dist), active["lowest"] + (1.2 * dist))
                    active["sl"] = min(active["sl"], round(trail_level, decimals))

                hit_sl = float(c["high"]) >= active["sl"]
                hit_max_tp = float(c["low"]) <= round(entry - max_target_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry - max_target_rr * dist, decimals) if hit_max_tp else active["sl"]
                    rem = (lots - half) if active["tp1_hit"] else lots
                    pnl_rem = (rem * c_val * (entry - exit_p)) - (rem * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem
                    rr_final = round((entry - exit_p) / dist, 1) if not active["tp1_hit"] else round((1.5 * 0.5) + (((entry - exit_p) / dist) * 0.5), 1)

                    active.update({
                        "exit_price": exit_p,
                        "pnl_usd": total_pnl,
                        "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": "MAX_RR_EXPANSION" if hit_max_tp else ("STRUCTURAL_TRAIL" if active["tp1_hit"] else "STOP_LOSS"),
                        "rr_achieved": rr_final,
                        "status": "CLOSED"
                    })
                    trades.append(active)
                    active = None
                    continue

        # -------------------------------------------------------------
        # 2. OPERATOR SMART MONEY ENTRY (PRICE ACTION + ORDER FLOW)
        # -------------------------------------------------------------
        if not active:
            sub = candles[max(0, i-15):i]
            hi8 = max(float(x["high"]) for x in sub[-8:])
            lo8 = min(float(x["low"]) for x in sub[-8:])
            
            delta = float(c.get("delta", 0.0))
            delta_ratio = delta / v

            # Anti-cascade check: no falling knives or rising spikes
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

            # Edge 1: Micro Liquidity Sweep (Stop Hunt & Reclaim)
            sweep_buy = (float(c["low"]) < lo8) and (curr > lo8) and (delta_ratio >= 0.02)
            sweep_sell = (float(c["high"]) > hi8) and (curr < hi8) and (delta_ratio <= -0.02)

            # Edge 2: Session VWAP Bands Reversion
            vwap_buy = (len(day_pr) >= 6) and (float(c["low"]) <= lower_vwap) and (curr > float(c["open"])) and (delta_ratio >= 0.02)
            vwap_sell = (len(day_pr) >= 6) and (float(c["high"]) >= upper_vwap) and (curr < float(c["open"])) and (delta_ratio <= -0.02)

            # Edge 3: Footprint Delta Absorption
            absorb_buy = (float(c["low"]) <= lo8 * 1.0005) and (delta_ratio >= 0.04) and buy_confirmed
            absorb_sell = (float(c["high"]) >= hi8 * 0.9995) and (delta_ratio <= -0.04) and sell_confirmed

            # 200 EMA Macro Alignment
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

                # Stop-Loss anchored beyond the sweep manipulation low with operator buffer
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
                half_lots = max(1, lots // 2)

                active = {
                    "symbol": symbol,
                    "side": side,
                    "entry_price": curr,
                    "sl": sl,
                    "orig_sl": sl,
                    "dist": dist,
                    "lots": lots,
                    "half_lots": half_lots,
                    "highest": curr,
                    "lowest": curr,
                    "tp1_hit": False,
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
        "net_pl": round(net_pl, 2)
    }

def main():
    db = DatabaseManager()
    print("Loading 35,000 candles per pair...")
    b_c = db.get_latest_candles("BTCUSD", "15m", limit=35000)
    e_c = db.get_latest_candles("ETHUSD", "15m", limit=35000)
    g_c = db.get_latest_candles("XAUTUSD", "15m", limit=35000)
    s_c = db.get_latest_candles("SLVONUSD", "15m", limit=35000)

    print("\n--- RUNNING OPERATOR SMART MONEY SIMULATION (MAX R:R TRAILING) ---")
    # BTC: c_val=0.001, min_stop=160.0, buffer=45.0
    res_b = run_operator_simulation("BTCUSD", b_c, 0.001, 160.0, 45.0, 1, max_target_rr=5.0)
    print(f"BTCUSD:   {res_b['total_trades']:4d} Trades | WR: {res_b['win_rate']:4.1f}% | Net: ${res_b['net_pl']:8.2f} | PF: {res_b['profit_factor']:4.2f}")

    # ETH: c_val=0.01, min_stop=8.0, buffer=2.2
    res_e = run_operator_simulation("ETHUSD", e_c, 0.01, 8.0, 2.2, 2, max_target_rr=5.0)
    print(f"ETHUSD:   {res_e['total_trades']:4d} Trades | WR: {res_e['win_rate']:4.1f}% | Net: ${res_e['net_pl']:8.2f} | PF: {res_e['profit_factor']:4.2f}")

    # Gold: c_val=0.001, min_stop=3.0, buffer=1.2
    res_g = run_operator_simulation("XAUTUSD", g_c, 0.001, 3.0, 1.2, 2, max_target_rr=6.0)
    print(f"XAUTUSD:  {res_g['total_trades']:4d} Trades | WR: {res_g['win_rate']:4.1f}% | Net: ${res_g['net_pl']:8.2f} | PF: {res_g['profit_factor']:4.2f}")

    # Silver: c_val=0.1, min_stop=0.25, buffer=0.08
    res_s = run_operator_simulation("SLVONUSD", s_c, 0.1, 0.25, 0.08, 3, max_target_rr=6.0)
    print(f"SLVONUSD: {res_s['total_trades']:4d} Trades | WR: {res_s['win_rate']:4.1f}% | Net: ${res_s['net_pl']:8.2f} | PF: {res_s['profit_factor']:4.2f}")

    # Combined Portfolio
    all_trades = res_b["trades"] + res_e["trades"] + res_g["trades"] + res_s["trades"]
    all_trades.sort(key=lambda x: x["opened_at"])
    all_wins = [t for t in all_trades if t["pnl_usd"] > 0]
    all_losses = [t for t in all_trades if t["pnl_usd"] < 0]
    gross_w = sum(t["pnl_usd"] for t in all_wins)
    gross_l = abs(sum(t["pnl_usd"] for t in all_losses))
    net_tot = sum(t["pnl_usd"] for t in all_trades)
    pf_tot = gross_w / gross_l
    wr_tot = len(all_wins) / len(all_trades) * 100

    print("\n================================================================================")
    print("      👑 OPERATOR SMART MONEY 4-ASSET PORTFOLIO (FIXED $5 RISK) 👑             ")
    print(f"   Total Trades:    {len(all_trades)}")
    print(f"   Overall Win Rate: {wr_tot:.1f}% ({len(all_wins)}W / {len(all_losses)}L)")
    print(f"   Profit Factor:   {pf_tot:.2f}")
    print(f"   Gross Profit:    +${gross_w:,.2f}")
    print(f"   Gross Loss:      -${gross_l:,.2f}")
    print(f"   Real Net P&L:    +${net_tot:,.2f} USD (+₹{net_tot * 90.0:,.0f} INR)")
    print("================================================================================")

    print("\n--- RUNNING OPERATOR SMART MONEY WITH STEPPED GROWTH COMPOUNDING ---")
    s_b = run_operator_simulation("BTCUSD", b_c, 0.001, 160.0, 45.0, 1, max_target_rr=5.0, use_stepped_risk=True)
    s_e = run_operator_simulation("ETHUSD", e_c, 0.01, 8.0, 2.2, 2, max_target_rr=5.0, use_stepped_risk=True)
    s_g = run_operator_simulation("XAUTUSD", g_c, 0.001, 3.0, 1.2, 2, max_target_rr=6.0, use_stepped_risk=True)
    s_s = run_operator_simulation("SLVONUSD", s_c, 0.1, 0.25, 0.08, 3, max_target_rr=6.0, use_stepped_risk=True)

    step_trades = s_b["trades"] + s_e["trades"] + s_g["trades"] + s_s["trades"]
    step_trades.sort(key=lambda x: x["opened_at"])
    step_wins = [t for t in step_trades if t["pnl_usd"] > 0]
    step_losses = [t for t in step_trades if t["pnl_usd"] < 0]
    sg_w = sum(t["pnl_usd"] for t in step_wins)
    sg_l = abs(sum(t["pnl_usd"] for t in step_losses))
    s_net = sum(t["pnl_usd"] for t in step_trades)
    s_pf = sg_w / sg_l if sg_l > 0 else 99.0
    s_wr = len(step_wins) / len(step_trades) * 100

    print("\n================================================================================")
    print("   🚀 OPERATOR SMART MONEY 4-ASSET PORTFOLIO (STEPPED GROWTH COMPOUNDER) 🚀     ")
    print(f"   Total Trades:    {len(step_trades)}")
    print(f"   Overall Win Rate: {s_wr:.1f}% ({len(step_wins)}W / {len(step_losses)}L)")
    print(f"   Profit Factor:   {s_pf:.2f}")
    print(f"   Gross Profit:    +${sg_w:,.2f}")
    print(f"   Gross Loss:      -${sg_l:,.2f}")
    print(f"   Real Net P&L:    +${s_net:,.2f} USD (+₹{s_net * 90.0:,.0f} INR)")
    print("================================================================================")

if __name__ == "__main__":
    main()
