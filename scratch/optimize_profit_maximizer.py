import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

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
gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=30000)
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=30000)

print(f"Loaded Gold: {len(gold_candles):,} | Silver: {len(silver_candles):,}")

def simulate_profit_max_gold(
    candles: List[Dict[str, Any]],
    tp1_rr: float = 2.0,
    max_rr: float = 5.5,
    trail_mult: float = 1.2,
    lock_rr: float = 1.0,
    del_th: float = 0.035
):
    c_val = 0.001
    leverage = 100
    maker_fee = 0.0001
    fixed_risk = 5.0
    capital = 50.0
    initial_capital = 50.0
    peak = 50.0
    max_dd = 0.0
    min_dist = 2.8
    dist_pad = 0.6
    bad_hours = {16, 19, 20, 22}

    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trade = None

    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []

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

        if bar_time.hour in bad_hours:
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
        vwap = day_cum_pv / day_cum_vol
        day_prices.append(typ_p)

        mean_p = sum(day_prices) / len(day_prices)
        stdev = max(1.0, (sum((p - mean_p)**2 for p in day_prices) / len(day_prices))**0.5)
        upper_vwap = vwap + (1.8 * stdev)
        lower_vwap = vwap - (1.8 * stdev)

        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half_lots = max(1, lots // 2)

            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist

                # Scale-out 50% at TP1
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 2)
                    pnl_half = (half_lots * c_val * (tp1_p - entry)) - (half_lots * c_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 2))

                # Profit Lock on Runner: once +3R reached, ratchet SL to at least +lock_rr
                if active_trade["tp1_hit"] and gain_r >= 3.0:
                    locked_sl = round(entry + lock_rr * dist, 2)
                    if locked_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = locked_sl

                # Dynamic Trailing
                if active_trade["tp1_hit"] and gain_r >= (tp1_rr + 0.4):
                    new_sl = round(active_trade["highest"] - (trail_mult * dist), 2)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl

                    if capital > peak:
                        peak = capital
                    dd = peak - capital
                    if dd > max_dd:
                        max_dd = dd

                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    rr_final = round((exit_price - entry) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_rr * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final,
                        "orderflow_notes": f"Scaled 50% @ 1:{tp1_rr} | Trailed to ${exit_price}" if active_trade["tp1_hit"] else "SL before TP1"
                    })
                    trades.append(active_trade)
                    active_trade = None
                    continue

            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 2)
                    pnl_half = (half_lots * c_val * (entry - tp1_p)) - (half_lots * c_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 2))

                if active_trade["tp1_hit"] and gain_r >= 3.0:
                    locked_sl = round(entry - lock_rr * dist, 2)
                    if locked_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = locked_sl

                if active_trade["tp1_hit"] and gain_r >= (tp1_rr + 0.4):
                    new_sl = round(active_trade["lowest"] + (trail_mult * dist), 2)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl

                    if capital > peak:
                        peak = capital
                    dd = peak - capital
                    if dd > max_dd:
                        max_dd = dd

                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    rr_final = round((entry - exit_price) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_rr * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final,
                        "orderflow_notes": f"Scaled 50% @ 1:{tp1_rr} | Trailed to ${exit_price}" if active_trade["tp1_hit"] else "SL before TP1"
                    })
                    trades.append(active_trade)
                    active_trade = None
                    continue

        if not active_trade:
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

            vwap_buy = (len(day_prices) >= 6) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 6) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            absorb_buy = (c["low"] <= lo12 * 1.0002) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9998) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

            if i >= 150:
                ema150 = sum(x["close"] for x in candles[i-150:i]) / 150.0
                macro_bull = curr > ema150
                macro_bear = curr < ema150
            else:
                macro_bull = macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            is_buy = (buy_score >= 1) and (sell_score == 0)
            is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                sl_price = round(curr - dist if is_buy else curr + dist, 2)
                lots = max(2, int(round(fixed_risk / (dist * c_val))))
                notional = lots * c_val * curr

                active_trade = {
                    "id": f"GOLD_OPT_{ts}",
                    "symbol": "XAUTUSD",
                    "side": side,
                    "entry_price": curr,
                    "stop_loss": sl_price,
                    "take_profit": round(curr + (dist * max_rr) if is_buy else curr - (dist * max_rr), 2),
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "notional_usd": round(notional, 2),
                    "margin_usd": round(notional / leverage, 2),
                    "leverage": leverage,
                    "risk_usd": fixed_risk,
                    "conviction_stars": 5.0,
                    "strategy_name": "Gold Apex Pro Optimized",
                    "tp1_rr": tp1_rr,
                    "max_rr": max_rr,
                    "trail_mult": trail_mult,
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "OPEN",
                    "is_paper": 1
                }

    if active_trade:
        final_c = candles[-1]
        exit_price = final_c["close"]
        side = active_trade["side"]
        entry = active_trade["entry_price"]
        dist = active_trade["dist"]
        lots = active_trade["lots"]
        half_lots = max(1, lots // 2)
        rem_lots = (lots - half_lots) if active_trade.get("tp1_hit") else lots

        diff = (exit_price - entry) if side == "BUY" else (entry - exit_price)
        rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * maker_fee * 2)
        total_pnl = round(active_trade.get("booked_pnl", 0.0) + rem_pnl, 2)
        capital += rem_pnl

        rr_final = round(diff / dist, 1) if not active_trade.get("tp1_hit") else round((active_trade["tp1_rr"] * 0.5) + ((diff / dist) * 0.5), 1)

        active_trade.update({
            "exit_price": exit_price,
            "pnl_usd": total_pnl,
            "closed_at": datetime.fromtimestamp(final_c["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
            "close_reason": f"HALF @ 1:{active_trade['tp1_rr']} + MARK-TO-MARKET (+{rr_final}R)" if active_trade.get("tp1_hit") else "MARK_TO_MARKET",
            "status": "CLOSED",
            "rr_achieved": rr_final,
            "orderflow_notes": f"Active position marked to market (+${total_pnl})"
        })
        trades.append(active_trade)

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    total = len(trades)
    win_rate = round(len(wins) / total * 100, 1) if total else 0.0
    gp = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    pf = round(gp / gl, 2) if gl else 99.0
    net = round(capital - initial_capital, 2)
    roi = round(net / initial_capital * 100, 1)

    return {
        "symbol": "XAUTUSD",
        "net_pl": net,
        "roi_pct": roi,
        "win_rate": win_rate,
        "profit_factor": pf,
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "max_drawdown": round(max_dd, 2),
        "final_capital": round(capital, 2),
        "trades": trades
    }

print("\n--- GOLD PROFIT MAXIMIZATION SEARCH ---")
results = []
for tp1 in [1.5, 1.8, 2.0, 2.2]:
    for max_rr in [4.0, 4.5, 5.0, 5.5]:
        for trail in [1.0, 1.2, 1.5]:
            for lock in [0.5, 1.0]:
                r = simulate_profit_max_gold(gold_candles, tp1_rr=tp1, max_rr=max_rr, trail_mult=trail, lock_rr=lock)
                results.append((tp1, max_rr, trail, lock, r))

results.sort(key=lambda x: x[4]["net_pl"], reverse=True)
for tp1, max_rr, trail, lock, r in results[:10]:
    print(f"TP1: {tp1} MaxRR: {max_rr} Trail: {trail} Lock: {lock} | Net: ${r['net_pl']:+8.2f} ({r['roi_pct']:+6.1f}%) | PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:4.1f}% | Trades: {r['total_trades']:3d} | DD: -${r['max_drawdown']:5.2f}")
