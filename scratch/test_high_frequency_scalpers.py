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

print(f"Loaded Gold: {len(gold_candles)} candles | Silver: {len(silver_candles)} candles")

def run_hf_scalper_research(
    symbol: str,
    candles: list,
    strategy_name: str,
    tp1_rr: float = 1.5,
    max_rr: float = 3.0,
    trail_dist: float = 1.0,
    delta_th: float = 0.02,
    session_start: str = "07:00",
    session_end: str = "23:45",
    sweep_lookback: int = 5,
    allow_reentry_bars: int = 1,
    max_concurrent: int = 2
):
    is_silver = "SLV" in symbol.upper()
    contract_val = 1.0 if is_silver else 0.001
    min_dist = 0.20 if is_silver else 2.0
    dist_pad = 0.05 if is_silver else 0.5
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

        day_str = bar_time.strftime("%Y-%m-%d")
        hm = bar_time.strftime("%H:%M")

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

        upper_vwap = vwap + (1.5 * stdev)
        lower_vwap = vwap - (1.5 * stdev)

        # Manage active trades
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

                # Scale out 50% @ TP1
                if not at["tp1_hit"] and gain_r >= tp1_rr:
                    at["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move stop loss to breakeven + buffer
                    at["stop_loss"] = max(at["stop_loss"], round(entry + 0.1 * dist, 3 if is_silver else 2))

                # Dynamic trailing
                if at["tp1_hit"] and gain_r >= (tp1_rr + 0.5):
                    new_sl = round(at["highest"] - (trail_dist * dist), 3 if is_silver else 2)
                    if new_sl > at["stop_loss"]:
                        at["stop_loss"] = new_sl

                hit_sl = c["low"] <= at["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 3 if is_silver else 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 3 if is_silver else 2) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((exit_price - entry) / dist, 1) if not at["tp1_hit"] else round((tp1_rr * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    at.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
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

                # Scale out 50% @ TP1
                if not at["tp1_hit"] and gain_r >= tp1_rr:
                    at["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 3 if is_silver else 2)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    at["booked_pnl"] = pnl_half
                    capital += pnl_half
                    at["stop_loss"] = min(at["stop_loss"], round(entry - 0.1 * dist, 3 if is_silver else 2))

                # Dynamic trailing
                if at["tp1_hit"] and gain_r >= (tp1_rr + 0.5):
                    new_sl = round(at["lowest"] + (trail_dist * dist), 3 if is_silver else 2)
                    if new_sl < at["stop_loss"]:
                        at["stop_loss"] = new_sl

                hit_sl = c["high"] >= at["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 3 if is_silver else 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 3 if is_silver else 2) if hit_tp else at["stop_loss"]
                    rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((entry - exit_price) / dist, 1) if not at["tp1_hit"] else round((tp1_rr * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    at.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(at)
                    day_trades_count[day_str] += 1
                else:
                    still_active.append(at)

        active_trades = still_active

        # Entry logic: Allow up to max_concurrent positions and check session hours
        if len(active_trades) < max_concurrent and (session_start <= hm <= session_end):
            sub = candles[i-20:i]
            hi_sw = max(x["high"] for x in sub[-sweep_lookback:])
            lo_sw = min(x["low"] for x in sub[-sweep_lookback:])
            
            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            # Alpha A: Micro Sweep with Delta Confirmation
            sweep_buy = (c["low"] < lo_sw) and (c["close"] > lo_sw) and (delta_ratio >= delta_th)
            sweep_sell = (c["high"] > hi_sw) and (c["close"] < hi_sw) and (delta_ratio <= -delta_th)

            # Alpha B: VWAP Mean Reversion Stretch
            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= delta_th * 0.7)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -delta_th * 0.7)

            # Alpha C: EMA Pullback Momentum (9 EMA vs 21 EMA)
            ema9 = sum(x["close"] for x in sub[-9:]) / 9.0
            ema21 = sum(x["close"] for x in sub[-21:]) / 21.0
            pullback_buy = (ema9 > ema21) and (c["low"] <= ema9) and (c["close"] > ema9) and (delta_ratio >= delta_th * 0.5)
            pullback_sell = (ema9 < ema21) and (c["high"] >= ema9) and (c["close"] < ema9) and (delta_ratio <= -delta_th * 0.5)

            is_buy = (sweep_buy or vwap_buy or pullback_buy)
            is_sell = (sweep_sell or vwap_sell or pullback_sell)

            if is_buy != is_sell: # Clean signal without conflict
                side = "BUY" if is_buy else "SELL"
                
                # Check if we already have an active trade in the exact same direction on this exact bar
                has_same_side = any(at["side"] == side for at in active_trades)
                if not has_same_side:
                    dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                    sl_price = round(curr - dist if is_buy else curr + dist, 3 if is_silver else 2)
                    lots = max(2, int(round(fixed_risk / (dist * contract_val))))
                    notional = lots * contract_val * curr

                    active_trades.append({
                        "id": f"HF_{symbol}_{c['timestamp']}",
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
                        "tp1_rr": tp1_rr,
                        "max_rr": max_rr,
                        "trail_dist": trail_dist,
                        "tp1_hit": False,
                        "booked_pnl": 0.0,
                        "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "setup_type": "Micro Sweep" if (sweep_buy or sweep_sell) else ("VWAP Band Fade" if (vwap_buy or vwap_sell) else "EMA Momentum Pullback"),
                        "orderflow_notes": f"High-Freq Intraday Scalp ({hm} UTC) | Delta Ratio: {delta_ratio:+.1%}"
                    })

    # Stats
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

print("\n--- RESEARCHING HIGH FREQUENCY INTRADAY SCALPERS (GOLD) ---")
run_hf_scalper_research("XAUTUSD", gold_candles, "⚡ High-Frequency Scalper Pro (3-5 Trades/Day)", tp1_rr=1.5, max_rr=3.0, trail_dist=0.8, delta_th=0.02, max_concurrent=2)
run_hf_scalper_research("XAUTUSD", gold_candles, "🎯 Intraday Fast Turnover Scalper (Cut 50% @ 1:1.2)", tp1_rr=1.2, max_rr=2.5, trail_dist=0.8, delta_th=0.015, max_concurrent=2)
run_hf_scalper_research("XAUTUSD", gold_candles, "🌊 Session Micro-Wave Momentum (3-6 Trades/Day)", tp1_rr=1.5, max_rr=3.5, trail_dist=1.0, delta_th=0.02, max_concurrent=3)

print("\n--- RESEARCHING HIGH FREQUENCY INTRADAY SCALPERS (SILVER) ---")
run_hf_scalper_research("SLVONUSD", silver_candles, "⚡ High-Frequency Scalper Pro (Silver | 3-5 Trades/Day)", tp1_rr=1.5, max_rr=3.0, trail_dist=0.8, delta_th=0.02, max_concurrent=2)
run_hf_scalper_research("SLVONUSD", silver_candles, "🎯 Intraday Fast Turnover Scalper (Silver | Cut 50% @ 1:1.2)", tp1_rr=1.2, max_rr=2.5, trail_dist=0.8, delta_th=0.015, max_concurrent=2)
run_hf_scalper_research("SLVONUSD", silver_candles, "🌊 Session Micro-Wave Momentum (Silver | 3-6 Trades/Day)", tp1_rr=1.5, max_rr=3.5, trail_dist=1.0, delta_th=0.02, max_concurrent=3)
