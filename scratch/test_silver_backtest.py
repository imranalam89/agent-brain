import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)
print(f"Total SLVONUSD candles loaded: {len(candles)}")

def run_silver_apex(
    candles,
    base_risk=5.0,
    use_stepped_risk=False,
    scale_factor=0.5,
    filter_session_chop=True,
    tp1_high=2.5,
    tp1_mod=1.5,
    min_rr_high=5.0,
    min_rr_mod=2.5,
    trail_high=1.2,
    trail_mod=1.2,
    del_th=0.03
):
    capital = 50.0
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    trades = []
    active_trade = None
    maker_fee = 0.0001
    contract_val = 1.0 # 1 contract = 1 SLVON
    min_dist = 0.20
    dist_pad = 0.05

    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []
    bad_hours = {16, 19, 20, 22} if filter_session_chop else set()

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

        # Manage active trade
        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half_lots = max(1, lots // 2)
            tp1_target = active_trade["tp1_rr"]
            max_target = active_trade["max_rr"]
            trail_mult = active_trade["trail_mult"]

            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1_target:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_target * dist, 3)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 3))

                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["highest"] - (trail_mult * dist), 3)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_target * dist, 3)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_target * dist, 3) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((exit_price - entry) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_target * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_target} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(active_trade)
                    active_trade = None
                    continue

            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1_target:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_target * dist, 3)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 3))

                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["lowest"] + (trail_mult * dist), 3)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_target * dist, 3)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_target * dist, 3) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((entry - exit_price) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_target * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_target} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(active_trade)
                    active_trade = None
                    continue

        # Entry logic
        if not active_trade and (bar_time.hour not in bad_hours):
            sub = candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            # Alpha 1: 8-bar Micro Sweep
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)

            # Alpha 2: VWAP Bands Reversion
            vwap_buy = (len(day_prices) >= 6) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 6) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            # Alpha 3: Footprint Delta Absorption
            absorb_buy = (c["low"] <= lo12 * 1.0005) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9995) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

            # 200 EMA Macro Trend
            if i >= 200:
                ema200 = sum(x["close"] for x in candles[i-200:i]) / 200.0
                macro_bull = (curr > ema200)
                macro_bear = (curr < ema200)
            else:
                macro_bull = True
                macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            is_buy = (buy_score >= 1) and (sell_score == 0)
            is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                score = buy_score if is_buy else sell_score
                is_high_conv = (score >= 2)

                tp1_target = tp1_high if is_high_conv else tp1_mod
                max_target = min_rr_high if is_high_conv else min_rr_mod
                trail_mult = trail_high if is_high_conv else trail_mod

                raw_dist = abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad
                dist = max(min_dist, raw_dist)
                sl_price = round(curr - dist if is_buy else curr + dist, 3)
                side = "BUY" if is_buy else "SELL"

                if use_stepped_risk:
                    capital_gain_ratio = max(0.0, (capital - 50.0) / 50.0)
                    risk_mult = 1.0 + (scale_factor * capital_gain_ratio)
                    trade_risk_usd = round(base_risk * risk_mult, 2)
                    trade_risk_usd = min(trade_risk_usd, 35.0)
                else:
                    trade_risk_usd = base_risk

                lots = max(2, int(round(trade_risk_usd / (dist * contract_val))))
                notional = lots * contract_val * curr

                active_trade = {
                    "id": f"SLV_APEX_{c['timestamp']}",
                    "symbol": "SLVONUSD",
                    "side": side,
                    "entry_price": curr,
                    "stop_loss": sl_price,
                    "take_profit": round(curr + (dist * max_target) if is_buy else curr - (dist * max_target), 3),
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "notional_usd": round(notional, 2),
                    "margin_usd": round(notional / 100.0, 2),
                    "risk_usd": round(trade_risk_usd, 2),
                    "tp1_rr": tp1_target,
                    "max_rr": max_target,
                    "trail_mult": trail_mult,
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "setup_type": "5-Star Multi-Alpha" if is_high_conv else "4-Star Scalp"
                }

    # Summary
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    total_trades = len(trades)
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    net_pl = capital - 50.0
    gross_profit = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Max Drawdown
    peak = 50.0
    max_dd = 0.0
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd

    print(f"\n--- Strategy Results: Risk=${base_risk}, Stepped={use_stepped_risk} ---")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {win_rate:.1f}% ({len(wins)} W / {len(losses)} L)")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Initial: $50.00 -> Final: ${capital:.2f} (Net: ${net_pl:+.2f}, ROI: {(net_pl/50.0)*100:.1f}%)")
    print(f"Max Drawdown: -${max_dd:.2f}")

    return {
        "trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": pf,
        "net_pl": net_pl,
        "final_capital": capital,
        "max_dd": max_dd
    }

print("\nTesting SLVONUSD with Fixed $5.00 Risk:")
run_silver_apex(candles, base_risk=5.0, use_stepped_risk=False)

print("\nTesting SLVONUSD with Fixed $4.00 Risk:")
run_silver_apex(candles, base_risk=4.0, use_stepped_risk=False)

print("\nTesting SLVONUSD with Stepped Growth Risk ($5.00 Base, +50% per 100% gain):")
run_silver_apex(candles, base_risk=5.0, use_stepped_risk=True)
