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

def test_morning_setups(symbol, candles, c_val, min_stop, buffer_pad, decimals, tp1_rr=1.5, max_rr=5.0, trail_mult=1.0):
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

        # Check morning window: 06:00 to 12:00 IST
        in_morning = ("06:00" <= hm <= "12:00")
        
        d_str = bt.strftime("%Y-%m-%d")
        typ = (float(c["high"]) + float(c["low"]) + curr) / 3.0
        v = max(1.0, float(c.get("volume", 1.0)))

        if d_str != curr_day:
            curr_day = d_str; day_v = 0.0; day_pv = 0.0; day_pr = []
        day_v += v; day_pv += typ * v; day_pr.append(typ)
        vwap = day_pv / day_v
        stdev = max(1.0, (sum((x - (sum(day_pr)/len(day_pr)))**2 for x in day_pr)/len(day_pr))**0.5)

        if active:
            side = active["side"]
            entry = active["entry_price"]
            dist = active["dist"]
            lots = active["lots"]
            half = active["half_lots"]

            if side == "BUY":
                if float(c["high"]) > active["highest"]:
                    active["highest"] = float(c["high"])
                gain_r = (active["highest"] - entry) / dist

                if not active["tp1_hit"] and gain_r >= tp1_rr:
                    active["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, decimals)
                    pnl_half = (half * c_val * (tp1_p - entry)) - (half * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_half
                    capital += pnl_half
                    active["sl"] = max(active["sl"], round(entry + 0.10 * dist, decimals))

                if active["tp1_hit"] and gain_r >= 2.5:
                    active["sl"] = max(active["sl"], round(entry + 1.2 * dist, decimals))

                if active["tp1_hit"] and gain_r >= 3.5:
                    recent_swing = min(float(x["low"]) for x in candles[max(0, i-4):i])
                    trail_level = max(recent_swing - (0.10 * dist), active["highest"] - (trail_mult * dist))
                    active["sl"] = max(active["sl"], round(trail_level, decimals))

                hit_sl = float(c["low"]) <= active["sl"]
                hit_max_tp = float(c["high"]) >= round(entry + max_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry + max_rr * dist, decimals) if hit_max_tp else active["sl"]
                    rem = (lots - half) if active["tp1_hit"] else lots
                    pnl_rem = (rem * c_val * (exit_p - entry)) - (rem * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem
                    rr_final = round((exit_p - entry) / dist, 1)

                    active.update({
                        "exit_price": exit_p,
                        "pnl_usd": total_pnl,
                        "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": "MAX_RR" if hit_max_tp else ("TRAIL" if active["tp1_hit"] else "STOP_LOSS"),
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

                if not active["tp1_hit"] and gain_r >= tp1_rr:
                    active["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, decimals)
                    pnl_half = (half * c_val * (entry - tp1_p)) - (half * c_val * tp1_p * maker_fee * 2)
                    active["booked"] = pnl_half
                    capital += pnl_half
                    active["sl"] = min(active["sl"], round(entry - 0.10 * dist, decimals))

                if active["tp1_hit"] and gain_r >= 2.5:
                    active["sl"] = min(active["sl"], round(entry - 1.2 * dist, decimals))

                if active["tp1_hit"] and gain_r >= 3.5:
                    recent_swing = max(float(x["high"]) for x in candles[max(0, i-4):i])
                    trail_level = min(recent_swing + (0.10 * dist), active["lowest"] + (trail_mult * dist))
                    active["sl"] = min(active["sl"], round(trail_level, decimals))

                hit_sl = float(c["high"]) >= active["sl"]
                hit_max_tp = float(c["low"]) <= round(entry - max_rr * dist, decimals)

                if hit_sl or hit_max_tp:
                    exit_p = round(entry - max_rr * dist, decimals) if hit_max_tp else active["sl"]
                    rem = (lots - half) if active["tp1_hit"] else lots
                    pnl_rem = (rem * c_val * (entry - exit_p)) - (rem * c_val * exit_p * maker_fee * 2)
                    total_pnl = round(active.get("booked", 0.0) + pnl_rem, 2)
                    capital += pnl_rem
                    rr_final = round((entry - exit_p) / dist, 1)

                    active.update({
                        "exit_price": exit_p,
                        "pnl_usd": total_pnl,
                        "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": "MAX_RR" if hit_max_tp else ("TRAIL" if active["tp1_hit"] else "STOP_LOSS"),
                        "rr_achieved": rr_final,
                        "status": "CLOSED"
                    })
                    trades.append(active)
                    active = None
                    continue

        # ONLY enter if in trading window
        if not active and in_morning:
            sub = candles[max(0, i-15):i]
            hi8 = max(float(x["high"]) for x in sub[-8:])
            lo8 = min(float(x["low"]) for x in sub[-8:])
            delta = float(c.get("delta", 0.0))
            delta_ratio = delta / v

            bar_range = max(0.01, float(c["high"]) - float(c["low"]))
            lower_wick = (min(float(c["open"]), curr) - float(c["low"])) / bar_range
            upper_wick = (float(c["high"]) - max(float(c["open"]), curr)) / bar_range

            buy_confirmed = (curr > float(c["open"])) or (lower_wick >= 0.28)
            sell_confirmed = (curr < float(c["open"])) or (upper_wick >= 0.28)

            # In morning Asian session: Asian Range Reversal (High / Low of Asian box)
            # Sweep of Asian high or low with delta divergence
            sweep_buy = (float(c["low"]) < lo8) and (curr > lo8) and (delta_ratio >= 0.01)
            sweep_sell = (float(c["high"]) > hi8) and (curr < hi8) and (delta_ratio <= -0.01)

            # Volatility threshold: require minimum candle range so we don't enter dead chop
            is_active_vol = bar_range >= (dist_est := min_stop * 0.35)

            is_buy = sweep_buy and buy_confirmed and is_active_vol
            is_sell = sweep_sell and sell_confirmed and is_active_vol

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

                lots = max(2, int(round(TARGET_RISK / (dist * c_val))))
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
    gw = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    net = sum(t["pnl_usd"] for t in trades)
    pf = gw / gl if gl > 0 else 99.0
    wr = len(wins) / len(trades) * 100 if trades else 0

    return {
        "symbol": symbol,
        "trades": trades,
        "total": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "net": round(net, 2)
    }

print("Testing Asian Morning Session (06:00 - 12:00 IST) across pairs:")
r_b = test_morning_setups("BTCUSD", b_c, 0.001, 160.0, 45.0, 1, tp1_rr=1.5, max_rr=5.0)
r_e = test_morning_setups("ETHUSD", e_c, 0.01, 8.0, 2.2, 2, tp1_rr=1.5, max_rr=5.0)
r_g = test_morning_setups("XAUTUSD", g_c, 0.001, 3.0, 1.2, 2, tp1_rr=2.0, max_rr=6.0)
r_s = test_morning_setups("SLVONUSD", s_c, 0.1, 0.25, 0.08, 3, tp1_rr=2.0, max_rr=6.0)

all_m = r_b["trades"] + r_e["trades"] + r_g["trades"] + r_s["trades"]
m_wins = [t for t in all_m if t["pnl_usd"] > 0]
m_losses = [t for t in all_m if t["pnl_usd"] < 0]
m_gw = sum(t["pnl_usd"] for t in m_wins)
m_gl = abs(sum(t["pnl_usd"] for t in m_losses))
m_net = sum(t["pnl_usd"] for t in all_m)
m_pf = m_gw / m_gl if m_gl > 0 else 99.0
m_wr = len(m_wins) / len(all_m) * 100 if all_m else 0

print(f"BTC:   {r_b['total']} Trades | WR: {r_b['win_rate']}% | Net: ${r_b['net']:+7.2f} | PF: {r_b['profit_factor']}")
print(f"ETH:   {r_e['total']} Trades | WR: {r_e['win_rate']}% | Net: ${r_e['net']:+7.2f} | PF: {r_e['profit_factor']}")
print(f"GOLD:  {r_g['total']} Trades | WR: {r_g['win_rate']}% | Net: ${r_g['net']:+7.2f} | PF: {r_g['profit_factor']}")
print(f"SILV:  {r_s['total']} Trades | WR: {r_s['win_rate']}% | Net: ${r_s['net']:+7.2f} | PF: {r_s['profit_factor']}")
print(f"TOTAL MORNING (06:00 - 12:00 IST): {len(all_m)} Trades | WR: {m_wr:.1f}% | Net: ${m_net:+7.2f} USD (+₹{m_net * 90.0:,.0f} INR) | PF: {m_pf:.2f}")
