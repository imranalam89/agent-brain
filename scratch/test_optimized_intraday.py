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

def test_session_scalper(
    symbol: str,
    candles: list,
    strategy_name: str,
    tp1_rr: float = 2.0,
    max_rr: float = 4.0,
    trail_mult: float = 1.0,
    del_th: float = 0.025,
    min_dist_val: float = None,
    allow_reentry_bars: int = 2,
    enable_multi_session: bool = True
):
    is_silver = "SLV" in symbol.upper()
    contract_val = 1.0 if is_silver else 0.001
    min_dist = (0.25 if is_silver else 2.2) if min_dist_val is None else min_dist_val
    dist_pad = 0.05 if is_silver else 0.5
    maker_fee = 0.0001
    fixed_risk = 5.0
    capital = 50.0

    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trade = None
    last_exit_idx = -999

    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []
    day_trades_count = defaultdict(int)

    # High liquidity trading windows:
    # London: 07:00 - 11:30 UTC
    # NY Overlap & Afternoon: 12:30 - 23:45 UTC
    valid_sessions = [("07:00", "11:30"), ("12:30", "23:45")] if enable_multi_session else [("12:30", "23:45")]

    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        bar_time = datetime.fromtimestamp(ts)

        if bar_time.weekday() in (5, 6):
            continue

        day_str = bar_time.strftime("%Y-%m-%d")
        hm = bar_time.strftime("%H:%M")

        in_session = any(start <= hm <= end for start, end in valid_sessions)

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

        upper_vwap = vwap + (1.6 * stdev)
        lower_vwap = vwap - (1.6 * stdev)

        # Active trade management
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

                # Scale out 50% @ TP1
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven + buffer
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 3 if is_silver else 2))

                # Dynamic trailing
                if active_trade["tp1_hit"] and gain_r >= (tp1_rr + 0.5):
                    new_sl = round(active_trade["highest"] - (trail_mult * dist), 3 if is_silver else 2)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 3 if is_silver else 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 3 if is_silver else 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((exit_price - entry) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_rr * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(active_trade)
                    day_trades_count[day_str] += 1
                    active_trade = None
                    last_exit_idx = i
                    continue

            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                # Scale out 50% @ TP1
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 3 if is_silver else 2))

                # Dynamic trailing
                if active_trade["tp1_hit"] and gain_r >= (tp1_rr + 0.5):
                    new_sl = round(active_trade["lowest"] + (trail_mult * dist), 3 if is_silver else 2)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 3 if is_silver else 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 3 if is_silver else 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((entry - exit_price) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_rr * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(active_trade)
                    day_trades_count[day_str] += 1
                    active_trade = None
                    last_exit_idx = i
                    continue

        # Check entry
        if not active_trade and in_session and (i - last_exit_idx >= allow_reentry_bars):
            sub = candles[i-20:i]
            hi6 = max(x["high"] for x in sub[-6:])
            lo6 = min(x["low"] for x in sub[-6:])
            hi10 = max(x["high"] for x in sub[-10:])
            lo10 = min(x["low"] for x in sub[-10:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            # Alpha 1: 6-bar Micro Sweep with Delta Confirmation
            sweep_buy = (c["low"] < lo6) and (c["close"] > lo6) and (delta_ratio >= del_th)
            sweep_sell = (c["high"] > hi6) and (c["close"] < hi6) and (delta_ratio <= -del_th)

            # Alpha 2: VWAP Band Reversion
            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            # Alpha 3: Delta Absorption Divergence
            absorb_buy = (c["low"] <= lo10 * 1.0003) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi10 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

            # 100 EMA Intraday Trend
            if i >= 100:
                ema100 = sum(x["close"] for x in candles[i-100:i]) / 100.0
                trend_bull = (curr > ema100)
                trend_bear = (curr < ema100)
            else:
                trend_bull = trend_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (trend_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (trend_bear and sweep_sell)])

            is_buy = (buy_score >= 1) and (sell_score == 0)
            is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                score = buy_score if is_buy else sell_score
                side = "BUY" if is_buy else "SELL"
                dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                sl_price = round(curr - dist if is_buy else curr + dist, 3 if is_silver else 2)
                lots = max(2, int(round(fixed_risk / (dist * contract_val))))
                notional = lots * contract_val * curr

                active_trade = {
                    "id": f"SCLP_{symbol}_{c['timestamp']}",
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
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "setup_type": "Multi-Alpha Scalp" if score >= 2 else "Intraday Micro-Sweep",
                    "orderflow_notes": f"Intraday Scalp ({hm} UTC) | Score: {score}★ | Delta Ratio: {delta_ratio:+.1%}"
                }

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
        "max_drawdown_usd": round(max_dd, 2)
    }

print("=== TESTING TUNED INTRADAY SCALPERS ON GOLD ===")
test_session_scalper("XAUTUSD", gold_candles, "⚡ Active Session Scalper (London+NY | Cut 50% @ 1:2.0)", tp1_rr=2.0, max_rr=4.0, trail_mult=1.0, del_th=0.025, enable_multi_session=True)
test_session_scalper("XAUTUSD", gold_candles, "🎯 Fast Turnover Micro-Scalper (Cut 50% @ 1:1.5)", tp1_rr=1.5, max_rr=3.0, trail_mult=0.9, del_th=0.025, enable_multi_session=True)
test_session_scalper("XAUTUSD", gold_candles, "💎 London + NY Overlap Momentum Scalper", tp1_rr=2.0, max_rr=3.5, trail_mult=1.0, del_th=0.03, enable_multi_session=True)

print("\n=== TESTING TUNED INTRADAY SCALPERS ON SILVER ===")
test_session_scalper("SLVONUSD", silver_candles, "⚡ Active Session Scalper (Silver | London+NY | Cut 50% @ 1:2.0)", tp1_rr=2.0, max_rr=4.0, trail_mult=1.0, del_th=0.025, enable_multi_session=True)
test_session_scalper("SLVONUSD", silver_candles, "🎯 Fast Turnover Micro-Scalper (Silver | Cut 50% @ 1:1.5)", tp1_rr=1.5, max_rr=3.0, trail_mult=0.9, del_th=0.025, enable_multi_session=True)
test_session_scalper("SLVONUSD", silver_candles, "💎 London + NY Overlap Momentum Scalper (Silver)", tp1_rr=2.0, max_rr=3.5, trail_mult=1.0, del_th=0.03, enable_multi_session=True)
