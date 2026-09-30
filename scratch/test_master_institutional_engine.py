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

def simulate_master_engine(
    symbol: str,
    candles: List[Dict[str, Any]],
    fixed_risk: float = 5.0,
    tp1_rr: float = 1.8,
    max_rr: float = 5.0,
    trail_mult: float = 1.2,
    min_dist: float = 3.0,
    dist_pad: float = 0.6,
    max_daily_trades: int = 5,
    confluence_threshold: int = 2
):
    is_silver = "SLV" in symbol.upper()
    contract_val = 1.0 if is_silver else 0.001
    leverage = 50 if is_silver else 100
    maker_fee = 0.0001 # 0.01% Delta Exchange fee

    initial_capital = 50.0
    capital = initial_capital
    peak = initial_capital
    max_dd = 0.0

    trades = []
    equity_curve = [{"timestamp": candles[200]["timestamp"], "equity": capital}]
    active_trade: Optional[Dict[str, Any]] = None

    current_day = ""
    daily_trade_count = 0

    # Session VWAP tracking
    day_prices = []
    day_vols = []

    for i in range(200, len(candles)):
        c = candles[i]
        ts = c["timestamp"]
        curr = c["close"]
        bar_time = datetime.fromtimestamp(ts)
        day_str = bar_time.strftime("%Y-%m-%d")

        if day_str != current_day:
            current_day = day_str
            daily_trade_count = 0
            day_prices = []
            day_vols = []

        day_prices.append(curr)
        day_vols.append(max(1.0, c.get("volume", 1.0)))

        # Weekend Lock (No trades Saturday & Sunday)
        if bar_time.weekday() in (5, 6):
            continue

        # Trading Hours: European / London / NY sessions (06:00 to 22:00 UTC)
        hm = bar_time.strftime("%H:%M")
        if not ("06:00" <= hm <= "22:00"):
            continue

        # VWAP calculation
        vwap = sum(p * v for p, v in zip(day_prices, day_vols)) / max(1.0, sum(day_vols))
        dev = (sum((p - vwap)**2 for p in day_prices) / len(day_prices)) ** 0.5
        upper_vwap = vwap + (1.8 * dev)
        lower_vwap = vwap - (1.8 * dev)

        # ---------------- ACTIVE TRADE MANAGEMENT ----------------
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

                # Scale-Out 50% lots at TP1
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 3)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven (+0.15R buffer)
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 3))

                # Dynamic Runner Trailing
                if active_trade["tp1_hit"] and gain_r >= (tp1_rr + 0.4):
                    new_sl = round(active_trade["highest"] - (trail_mult * dist), 3)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 3)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 3) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
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
                        "orderflow_notes": f"Cut 50% @ 1:{tp1_rr} (Banked +${round(active_trade['booked_pnl'], 2)}) | SL to BE (+0.15R) | Trailed to ${exit_price}" if active_trade["tp1_hit"] else "SL hit before TP1"
                    })
                    trades.append(active_trade)
                    active_trade = None
                    continue

            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                # Scale-Out 50% lots at TP1
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 3)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven (+0.15R buffer)
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 3))

                # Dynamic Runner Trailing
                if active_trade["tp1_hit"] and gain_r >= (tp1_rr + 0.4):
                    new_sl = round(active_trade["lowest"] + (trail_mult * dist), 3)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 3)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 3) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
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
                        "orderflow_notes": f"Cut 50% @ 1:{tp1_rr} (Banked +${round(active_trade['booked_pnl'], 2)}) | SL to BE (+0.15R) | Trailed to ${exit_price}" if active_trade["tp1_hit"] else "SL hit before TP1"
                    })
                    trades.append(active_trade)
                    active_trade = None
                    continue

        # ---------------- ENTRY SIGNAL EVALUATION ----------------
        if not active_trade and daily_trade_count < max_daily_trades:
            sub = candles[i-20:i]
            # S/R levels from 8 and 16 bar lookbacks
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi16 = max(x["high"] for x in sub[-16:])
            lo16 = min(x["low"] for x in sub[-16:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            # 1. Liquidity Sweep Setup
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= 0.02)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -0.02)

            # 2. Session VWAP Stretch Reversion
            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= 0.02)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -0.02)

            # 3. Dynamic Support & Resistance Absorption
            sr_buy = (c["low"] <= lo16 * 1.0004) and (delta_ratio >= 0.025) and (c["close"] > c["open"])
            sr_sell = (c["high"] >= hi16 * 0.9996) and (delta_ratio <= -0.025) and (c["close"] < c["open"])

            # 4. Macro Trend Filter (50 EMA & 150 EMA)
            ema50 = sum(x["close"] for x in candles[i-50:i]) / 50.0
            macro_bull = curr > ema50
            macro_bear = curr < ema50

            buy_score = sum([sweep_buy, vwap_buy, sr_buy, (macro_bull and (sweep_buy or sr_buy))])
            sell_score = sum([sweep_sell, vwap_sell, sr_sell, (macro_bear and (sweep_sell or sr_sell))])

            is_buy = (buy_score >= confluence_threshold) and (sell_score == 0)
            is_sell = (sell_score >= confluence_threshold) and (buy_score == 0)

            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                sl_price = round(curr - dist if is_buy else curr + dist, 3)
                lots = max(2, int(round(fixed_risk / (dist * contract_val))))
                notional = lots * contract_val * curr
                margin_req = notional / leverage

                active_trade = {
                    "id": f"INST_{symbol}_{ts}",
                    "symbol": symbol,
                    "side": side,
                    "entry_price": curr,
                    "stop_loss": sl_price,
                    "take_profit": round(curr + (dist * max_rr) if is_buy else curr - (dist * max_rr), 3),
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "notional_usd": round(notional, 2),
                    "margin_usd": round(margin_req, 2),
                    "leverage": leverage,
                    "risk_usd": fixed_risk,
                    "conviction_stars": 5.0,
                    "strategy_name": f"Master Institutional 2.0 ({symbol})",
                    "tp1_rr": tp1_rr,
                    "max_rr": max_rr,
                    "trail_mult": trail_mult,
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "OPEN",
                    "is_paper": 1
                }
                daily_trade_count += 1

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
        rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
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

# Grid search on Gold
print("\n--- GOLD PARAMETER SWEEPS ---")
for tp1 in [1.5, 1.8, 2.0]:
    for max_daily in [3, 4, 6]:
        for conf in [2]:
            r = simulate_master_engine("XAUTUSD", gold_candles, tp1_rr=tp1, max_rr=5.0, trail_mult=1.2, min_dist=2.5, dist_pad=0.5, max_daily_trades=max_daily, confluence_threshold=conf)
            print(f"TP1: 1:{tp1:<3} MaxDaily: {max_daily} | Net: ${r['net_pl']:+8.2f} ({r['roi_pct']:+6.1f}%) | PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:4.1f}% | Trades: {r['total_trades']:3d} | DD: -${r['max_drawdown']:5.2f}")

# Grid search on Silver
print("\n--- SILVER PARAMETER SWEEPS ---")
for tp1 in [1.4, 1.6, 1.8, 2.0]:
    for max_daily in [3, 4, 6]:
        for conf in [2]:
            r = simulate_master_engine("SLVONUSD", silver_candles, tp1_rr=tp1, max_rr=4.5, trail_mult=1.0, min_dist=0.28, dist_pad=0.05, max_daily_trades=max_daily, confluence_threshold=conf)
            print(f"TP1: 1:{tp1:<3} MaxDaily: {max_daily} | Net: ${r['net_pl']:+8.2f} ({r['roi_pct']:+6.1f}%) | PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:4.1f}% | Trades: {r['total_trades']:3d} | DD: -${r['max_drawdown']:5.2f}")
