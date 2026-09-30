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

def test_ensemble_high_frequency(
    symbol: str,
    candles: list,
    strategy_name: str,
    max_active_positions: int = 2
):
    is_silver = "SLV" in symbol.upper()
    contract_val = 1.0 if is_silver else 0.001
    min_dist = 0.25 if is_silver else 2.5
    dist_pad = 0.06 if is_silver else 0.6
    maker_fee = 0.0001
    fixed_risk = 5.0
    capital = 50.0

    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trades = []

    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []
    day_trades_count = defaultdict(int)

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
        stdev = max(0.1 if is_silver else 1.0, variance**0.5)

        upper_vwap = vwap + (1.8 * stdev)
        lower_vwap = vwap - (1.8 * stdev)

        # Manage active trades
        still_active = []
        for at in active_trades:
            side = at["side"]
            entry = at["entry_price"]
            dist = at["dist"]
            lots = at["lots"]
            half_lots = max(1, lots // 2)
            tp1_target = at["tp1_rr"]
            max_target = at["max_rr"]
            trail_mult = at["trail_mult"]

            if side == "BUY":
                if c["high"] > at["highest"]:
                    at["highest"] = c["high"]
                gain_r = (at["highest"] - entry) / dist

                # Scale out 50%
                if not at["tp1_hit"] and gain_r >= tp1_target:
                    at["tp1_hit"] = True
                    tp1_p = round(entry + tp1_target * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    at["stop_loss"] = max(at["stop_loss"], round(entry + 0.15 * dist, 3 if is_silver else 2))

                # Dynamic Trailing
                if at["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(at["highest"] - (trail_mult * dist), 3 if is_silver else 2)
                    if new_sl > at["stop_loss"]:
                        at["stop_loss"] = new_sl

                hit_sl = c["low"] <= at["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_target * dist, 3 if is_silver else 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_target * dist, 3 if is_silver else 2) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((exit_price - entry) / dist, 1) if not at["tp1_hit"] else round((tp1_target * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    at.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_target} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(at)
                    day_trades_count[day_str] += 1
                else:
                    still_active.append(at)

            else: # SELL
                if c["low"] < at["lowest"]:
                    at["lowest"] = c["low"]
                gain_r = (entry - at["lowest"]) / dist

                # Scale out 50%
                if not at["tp1_hit"] and gain_r >= tp1_target:
                    at["tp1_hit"] = True
                    tp1_p = round(entry - tp1_target * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    at["stop_loss"] = min(at["stop_loss"], round(entry - 0.15 * dist, 3 if is_silver else 2))

                # Dynamic Trailing
                if at["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(at["lowest"] + (trail_mult * dist), 3 if is_silver else 2)
                    if new_sl < at["stop_loss"]:
                        at["stop_loss"] = new_sl

                hit_sl = c["high"] >= at["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_target * dist, 3 if is_silver else 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_target * dist, 3 if is_silver else 2) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((entry - exit_price) / dist, 1) if not at["tp1_hit"] else round((tp1_target * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    at.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_target} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(at)
                    day_trades_count[day_str] += 1
                else:
                    still_active.append(at)

        active_trades = still_active

        # Entry logic: Allow up to max_active_positions concurrent trades
        if len(active_trades) < max_active_positions:
            sub = candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol
            del_th = 0.035 if is_silver else 0.035

            # Alpha 1: 8-bar Micro Sweep
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)

            # Alpha 2: VWAP Bands Reversion
            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            # Alpha 3: Footprint Delta Absorption
            absorb_buy = (c["low"] <= lo10 if 'lo10' in locals() else lo12) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi10 if 'hi10' in locals() else hi12) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

            # 200 EMA
            if i >= 200:
                ema200 = sum(x["close"] for x in candles[i-200:i]) / 200.0
                macro_bull = (curr > ema200)
                macro_bear = (curr < ema200)
            else:
                macro_bull = macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            is_buy = (buy_score >= 1) and (sell_score == 0)
            is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                has_side = any(at["side"] == side for at in active_trades)
                
                # Take trade if not already holding same-bar trade
                if not has_side:
                    score = buy_score if is_buy else sell_score
                    is_high_conv = (score >= 2)
                    tp1_target = 2.0 if is_high_conv else 1.5
                    max_target = 4.0 if is_high_conv else 2.5
                    trail_mult = 1.2 if is_high_conv else 1.0

                    dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                    sl_price = round(curr - dist if is_buy else curr + dist, 3 if is_silver else 2)
                    lots = max(2, int(round(fixed_risk / (dist * contract_val))))
                    notional = lots * contract_val * curr

                    active_trades.append({
                        "id": f"APEX_HF_{c['timestamp']}_{len(active_trades)}",
                        "symbol": symbol,
                        "side": side,
                        "entry_price": curr,
                        "stop_loss": sl_price,
                        "dist": dist,
                        "highest": curr,
                        "lowest": curr,
                        "lots": lots,
                        "notional_usd": round(notional, 2),
                        "risk_usd": fixed_risk,
                        "tp1_rr": tp1_target,
                        "max_rr": max_target,
                        "trail_mult": trail_mult,
                        "tp1_hit": False,
                        "booked_pnl": 0.0,
                        "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "setup_type": "5-Star Multi-Alpha" if is_high_conv else "4-Star Scalp",
                        "orderflow_notes": f"High-Freq Intraday Scalp ({hm} UTC) | Score: {score}★ | Delta Ratio: {delta_ratio:+.1%}"
                    })

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    total_trades = len(trades)
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    net_pl = capital - 50.0
    gross_profit = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    peak = 50.0
    max_dd = 0.0
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd

    num_days = len(day_trades_count)
    avg_trades_day = (total_trades / num_days) if num_days > 0 else 0.0

    print(f"\n[{strategy_name}] ({symbol})")
    print(f"Total Trades: {total_trades} across {num_days} trading days -> Avg: {avg_trades_day:.1f} trades/day")
    print(f"Win Rate: {win_rate:.1f}% ({len(wins)} W / {len(losses)} L) | Profit Factor: {pf:.2f}")
    print(f"Initial: $50.00 -> Final: ${capital:.2f} (Net: ${net_pl:+.2f}, ROI: {(net_pl/50.0)*100:+.1f}%)")
    print(f"Max Drawdown: -${max_dd:.2f} (Risk strictly fixed at ${fixed_risk:.2f}/trade)")

    return {
        "strategy_name": strategy_name,
        "total_trades": total_trades,
        "avg_daily_trades": round(avg_trades_day, 1),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(pf, 2),
        "net_pl": round(net_pl, 2),
        "final_capital": round(capital, 2),
        "max_drawdown_usd": round(max_dd, 2),
        "trades": trades
    }

print("=== TESTING APEX HIGH FREQUENCY (GOLD) ===")
test_ensemble_high_frequency("XAUTUSD", gold_candles, "⚡ Apex High-Frequency Scalper (Max 2 Concurrent)", max_active_positions=2)
test_ensemble_high_frequency("XAUTUSD", gold_candles, "⚡ Apex High-Frequency Scalper (Max 3 Concurrent)", max_active_positions=3)

print("\n=== TESTING APEX HIGH FREQUENCY (SILVER) ===")
test_ensemble_high_frequency("SLVONUSD", silver_candles, "⚡ Apex High-Frequency Scalper (Silver | Max 2 Concurrent)", max_active_positions=2)
test_ensemble_high_frequency("SLVONUSD", silver_candles, "⚡ Apex High-Frequency Scalper (Silver | Max 3 Concurrent)", max_active_positions=3)
