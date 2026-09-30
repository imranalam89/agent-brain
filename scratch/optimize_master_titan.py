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

def test_engine(
    symbol: str,
    candles: List[Dict[str, Any]],
    tp1_rr: float,
    max_rr: float,
    trail_mult: float,
    min_dist: float,
    dist_pad: float,
    del_th: float,
    allow_concurrency: int = 1
):
    is_silver = "SLV" in symbol.upper()
    c_val = 1.0 if is_silver else 0.001
    leverage = 50 if is_silver else 100
    maker_fee = 0.0001 # 0.01% Delta Exchange fee
    fixed_risk = 5.0
    initial_capital = 50.0
    capital = initial_capital
    peak = initial_capital
    max_dd = 0.0

    bad_hours = {16, 18, 19, 23} if is_silver else {10, 11, 12, 23}

    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trades: List[Dict[str, Any]] = []

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
        day_prices.append(curr)
        dev = (sum((p - vwap)**2 for p in day_prices) / len(day_prices))**0.5 if len(day_prices) > 1 else 0.05
        upper_vwap = vwap + (1.5 * dev)
        lower_vwap = vwap - (1.5 * dev)

        # Update active trades
        still_active = []
        for at in active_trades:
            side = at["side"]
            entry = at["entry_price"]
            dist = at["dist"]
            lots = at["lots"]
            half_lots = max(1, lots // 2)

            if side == "BUY":
                if c["high"] > at["highest"]:
                    at["highest"] = c["high"]
                gain_r = (at["highest"] - entry) / dist

                # Scale-out 50% lots at TP1
                if not at["tp1_hit"] and gain_r >= tp1_rr:
                    at["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * c_val * (tp1_p - entry)) - (half_lots * c_val * tp1_p * maker_fee * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven (+0.15R buffer)
                    at["stop_loss"] = max(at["stop_loss"], round(entry + 0.15 * dist, 3 if is_silver else 2))

                # Dynamic Runner Trailing
                if at["tp1_hit"] and gain_r >= (tp1_rr + 0.4):
                    new_sl = round(at["highest"] - (trail_mult * dist), 3 if is_silver else 2)
                    if new_sl > at["stop_loss"]:
                        at["stop_loss"] = new_sl

                hit_sl = c["low"] <= at["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 3 if is_silver else 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 3 if is_silver else 2) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * maker_fee * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl

                    if capital > peak:
                        peak = capital
                    dd = peak - capital
                    if dd > max_dd:
                        max_dd = dd

                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    rr_final = round((exit_price - entry) / dist, 1) if not at["tp1_hit"] else round((tp1_rr * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    at.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final,
                        "orderflow_notes": f"50% scaled out @ 1:{tp1_rr} (Banked +${round(at['booked_pnl'], 2)}) | SL to BE (+0.15R) | Trailed to ${exit_price}" if at["tp1_hit"] else "Stopped out before TP1"
                    })
                    trades.append(at)
                else:
                    still_active.append(at)

            else: # SELL
                if c["low"] < at["lowest"]:
                    at["lowest"] = c["low"]
                gain_r = (entry - at["lowest"]) / dist

                # Scale-out 50% lots at TP1
                if not at["tp1_hit"] and gain_r >= tp1_rr:
                    at["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * c_val * (entry - tp1_p)) - (half_lots * c_val * tp1_p * maker_fee * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven (+0.15R buffer)
                    at["stop_loss"] = min(at["stop_loss"], round(entry - 0.15 * dist, 3 if is_silver else 2))

                # Dynamic Runner Trailing
                if at["tp1_hit"] and gain_r >= (tp1_rr + 0.4):
                    new_sl = round(at["lowest"] + (trail_mult * dist), 3 if is_silver else 2)
                    if new_sl < at["stop_loss"]:
                        at["stop_loss"] = new_sl

                hit_sl = c["high"] >= at["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 3 if is_silver else 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 3 if is_silver else 2) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * maker_fee * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl

                    if capital > peak:
                        peak = capital
                    dd = peak - capital
                    if dd > max_dd:
                        max_dd = dd

                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
                    rr_final = round((entry - exit_price) / dist, 1) if not at["tp1_hit"] else round((tp1_rr * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    at.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final,
                        "orderflow_notes": f"50% scaled out @ 1:{tp1_rr} (Banked +${round(at['booked_pnl'], 2)}) | SL to BE (+0.15R) | Trailed to ${exit_price}" if at["tp1_hit"] else "Stopped out before TP1"
                    })
                    trades.append(at)
                else:
                    still_active.append(at)

        active_trades = still_active

        # Entry logic
        if len(active_trades) < allow_concurrency and (bar_time.hour not in bad_hours):
            sub = candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            # Setup 1: Micro Liquidity Sweep
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)

            # Setup 2: Session VWAP Reversion
            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            # Setup 3: S/R Footprint Delta Absorption
            absorb_buy = (c["low"] <= lo12 * 1.0003) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

            if i >= 100:
                ema100 = sum(x["close"] for x in candles[i-100:i]) / 100.0
                macro_bull = (curr > ema100)
                macro_bear = (curr < ema100)
            else:
                macro_bull = macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and (sweep_buy or absorb_buy))])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and (sweep_sell or absorb_sell))])

            is_buy = (buy_score >= 1) and (sell_score == 0)
            is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                if not any(at["side"] == side for at in active_trades):
                    dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                    sl_price = round(curr - dist if is_buy else curr + dist, 3 if is_silver else 2)
                    lots = max(2, int(round(fixed_risk / (dist * c_val))))
                    notional = lots * c_val * curr

                    active_trades.append({
                        "id": f"OPT_{symbol}_{ts}_{len(active_trades)}",
                        "symbol": symbol,
                        "side": side,
                        "entry_price": curr,
                        "stop_loss": sl_price,
                        "take_profit": round(curr + (dist * max_rr) if is_buy else curr - (dist * max_rr), 3 if is_silver else 2),
                        "dist": dist,
                        "highest": curr,
                        "lowest": curr,
                        "lots": lots,
                        "notional_usd": round(notional, 2),
                        "margin_usd": round(notional / leverage, 2),
                        "leverage": leverage,
                        "risk_usd": fixed_risk,
                        "conviction_stars": 5.0 if (buy_score >= 2 or sell_score >= 2) else 4.0,
                        "strategy_name": f"Master Institutional Titan ({symbol})",
                        "tp1_rr": tp1_rr,
                        "max_rr": max_rr,
                        "trail_mult": trail_mult,
                        "tp1_hit": False,
                        "booked_pnl": 0.0,
                        "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "OPEN",
                        "is_paper": 1
                    })

    if active_trades:
        final_c = candles[-1]
        exit_price = final_c["close"]
        for at in active_trades:
            side = at["side"]
            entry = at["entry_price"]
            dist = at["dist"]
            lots = at["lots"]
            half_lots = max(1, lots // 2)
            rem_lots = (lots - half_lots) if at.get("tp1_hit") else lots

            diff = (exit_price - entry) if side == "BUY" else (entry - exit_price)
            rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * maker_fee * 2)
            total_pnl = round(at.get("booked_pnl", 0.0) + rem_pnl, 2)
            capital += rem_pnl

            rr_final = round(diff / dist, 1) if not at.get("tp1_hit") else round((at["tp1_rr"] * 0.5) + ((diff / dist) * 0.5), 1)

            at.update({
                "exit_price": exit_price,
                "pnl_usd": total_pnl,
                "closed_at": datetime.fromtimestamp(final_c["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                "close_reason": f"HALF @ 1:{at['tp1_rr']} + MARK-TO-MARKET (+{rr_final}R)" if at.get("tp1_hit") else "MARK_TO_MARKET",
                "status": "CLOSED",
                "rr_achieved": rr_final,
                "orderflow_notes": f"Active position marked to market (+${total_pnl})"
            })
            trades.append(at)

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
        "symbol": symbol,
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

print("\n--- GOLD OPTIMIZATION (FUTURES 100x | 0.01% FEE | $5 RISK) ---")
for tp1 in [1.5, 1.8, 2.0]:
    for trail in [1.0, 1.2, 1.5]:
        for conc in [1, 2]:
            r = test_engine("XAUTUSD", gold_candles, tp1_rr=tp1, max_rr=5.0, trail_mult=trail, min_dist=3.0, dist_pad=0.6, del_th=0.03, allow_concurrency=conc)
            print(f"TP1: {tp1} Trail: {trail}x Conc: {conc} | Net: ${r['net_pl']:+8.2f} ({r['roi_pct']:+6.1f}%) | PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:4.1f}% | Trades: {r['total_trades']:3d} | DD: -${r['max_drawdown']:5.2f}")

print("\n--- SILVER OPTIMIZATION (FUTURES 50x | 0.01% FEE | $5 RISK) ---")
for tp1 in [1.5, 1.6, 2.0]:
    for trail in [0.8, 1.0, 1.2]:
        for conc in [1, 2]:
            r = test_engine("SLVONUSD", silver_candles, tp1_rr=tp1, max_rr=4.5, trail_mult=trail, min_dist=0.30, dist_pad=0.06, del_th=0.03, allow_concurrency=conc)
            print(f"TP1: {tp1} Trail: {trail}x Conc: {conc} | Net: ${r['net_pl']:+8.2f} ({r['roi_pct']:+6.1f}%) | PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:4.1f}% | Trades: {r['total_trades']:3d} | DD: -${r['max_drawdown']:5.2f}")
