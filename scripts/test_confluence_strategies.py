import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from config.settings import TARGET_RISK_USD

def simulate_engine():
    db = DatabaseManager()
    candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)
    print(f"Total candles loaded: {len(candles)}")

    # Define strategy configurations
    configs = [
        {
            "name": "1. Baseline Trend (EMA Pullback 1:2.5)",
            "use_footprint": False,
            "use_wick_rejection": False,
            "trailing": False,
            "target_rr": 2.5,
            "be_at_rr": 0.0,
            "trail_mult": 0.0
        },
        {
            "name": "2. Footprint Order Flow (Delta Imbalance > 15%)",
            "use_footprint": True,
            "min_delta_pct": 0.15,
            "use_wick_rejection": False,
            "trailing": False,
            "target_rr": 2.5,
            "be_at_rr": 0.0,
            "trail_mult": 0.0
        },
        {
            "name": "3. Confluence: Trend + Footprint + Wick Rejection",
            "use_footprint": True,
            "min_delta_pct": 0.15,
            "use_wick_rejection": True,
            "trailing": False,
            "target_rr": 2.5,
            "be_at_rr": 0.0,
            "trail_mult": 0.0
        },
        {
            "name": "4. High RR (1:3.5 Target) + Footprint Confluence",
            "use_footprint": True,
            "min_delta_pct": 0.15,
            "use_wick_rejection": True,
            "trailing": False,
            "target_rr": 3.5,
            "be_at_rr": 0.0,
            "trail_mult": 0.0
        },
        {
            "name": "5. Confluence + Breakeven Lock (+1.5R) + 1:3.5 TP",
            "use_footprint": True,
            "min_delta_pct": 0.15,
            "use_wick_rejection": True,
            "trailing": False,
            "target_rr": 3.5,
            "be_at_rr": 1.5,
            "trail_mult": 0.0
        },
        {
            "name": "6. Master Confluence: Order Flow + Dynamic ATR Trailing",
            "use_footprint": True,
            "min_delta_pct": 0.15,
            "use_wick_rejection": True,
            "trailing": True,
            "target_rr": 0.0,
            "be_at_rr": 1.5,
            "trail_mult": 1.5
        },
        {
            "name": "7. Ultimate Brain: Footprint Absorption + Confluence + Trailing",
            "use_footprint": True,
            "min_delta_pct": 0.12,
            "use_wick_rejection": True,
            "use_absorption": True,
            "trailing": True,
            "target_rr": 0.0,
            "be_at_rr": 1.5,
            "trail_mult": 1.5
        }
    ]

    for cfg in configs:
        capital = 50.0
        trades = []
        active_trade = None
        equity_curve = [capital]
        maker_fee_pct = 0.0001 # 0.01%

        for i in range(100, len(candles)):
            c = candles[i]
            prev = candles[i-100:i]
            current_price = c["close"]
            bar_time = datetime.fromtimestamp(c["timestamp"])

            # Session filter (London & NY peak liquidity)
            hm = bar_time.strftime("%H:%M")
            if not ("13:30" <= hm <= "23:00"):
                continue

            # Trade Management
            if active_trade:
                side = active_trade["side"]
                entry = active_trade["entry_price"]
                sl = active_trade["stop_loss"]
                tp = active_trade.get("take_profit")
                dist = active_trade["dist"]
                is_closed = False
                pnl = 0.0
                reason = ""

                if side == "BUY":
                    # Track high
                    if c["high"] > active_trade["highest"]:
                        active_trade["highest"] = c["high"]

                    gain_r = (active_trade["highest"] - entry) / dist

                    # Breakeven lock
                    if cfg.get("be_at_rr", 0.0) > 0 and gain_r >= cfg["be_at_rr"]:
                        new_sl = entry + (0.1 * dist) # slightly above entry
                        if new_sl > active_trade["stop_loss"]:
                            active_trade["stop_loss"] = new_sl

                    # Trailing stop
                    if cfg.get("trailing"):
                        if gain_r >= 1.5:
                            trail_sl = active_trade["highest"] - (cfg["trail_mult"] * dist)
                            if trail_sl > active_trade["stop_loss"]:
                                active_trade["stop_loss"] = trail_sl

                    # Check SL
                    if c["low"] <= active_trade["stop_loss"]:
                        is_closed = True
                        exit_price = active_trade["stop_loss"]
                        rr = round((exit_price - entry) / dist, 2)
                        pnl = rr * TARGET_RISK_USD
                        reason = "SL" if rr < 0 else f"TRAIL (+{rr}R)"

                    # Check TP if fixed
                    elif tp and c["high"] >= tp:
                        is_closed = True
                        exit_price = tp
                        rr = cfg["target_rr"]
                        pnl = rr * TARGET_RISK_USD
                        reason = "TP"

                else: # SELL
                    if c["low"] < active_trade["lowest"]:
                        active_trade["lowest"] = c["low"]

                    gain_r = (entry - active_trade["lowest"]) / dist

                    # Breakeven lock
                    if cfg.get("be_at_rr", 0.0) > 0 and gain_r >= cfg["be_at_rr"]:
                        new_sl = entry - (0.1 * dist)
                        if new_sl < active_trade["stop_loss"]:
                            active_trade["stop_loss"] = new_sl

                    # Trailing stop
                    if cfg.get("trailing"):
                        if gain_r >= 1.5:
                            trail_sl = active_trade["lowest"] + (cfg["trail_mult"] * dist)
                            if trail_sl < active_trade["stop_loss"]:
                                active_trade["stop_loss"] = trail_sl

                    # Check SL
                    if c["high"] >= active_trade["stop_loss"]:
                        is_closed = True
                        exit_price = active_trade["stop_loss"]
                        rr = round((entry - exit_price) / dist, 2)
                        pnl = rr * TARGET_RISK_USD
                        reason = "SL" if rr < 0 else f"TRAIL (+{rr}R)"

                    # Check TP if fixed
                    elif tp and c["low"] <= tp:
                        is_closed = True
                        exit_price = tp
                        rr = cfg["target_rr"]
                        pnl = rr * TARGET_RISK_USD
                        reason = "TP"

                if is_closed:
                    fee = active_trade["notional_usd"] * maker_fee_pct * 2
                    net_pnl = round(pnl - fee, 2)
                    capital += net_pnl
                    equity_curve.append(capital)
                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": net_pnl,
                        "reason": reason
                    })
                    trades.append(active_trade)
                    active_trade = None
                continue

            # Signal Generation
            ema20 = sum(x["close"] for x in prev[-20:]) / 20.0
            ema50 = sum(x["close"] for x in prev[-50:]) / 50.0
            ema100 = sum(x["close"] for x in prev[-100:]) / 100.0

            bull_trend = (c["close"] > ema50) and (ema50 > ema100)
            bear_trend = (c["close"] < ema50) and (ema50 < ema100)

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_pct = delta / vol

            total_range = max(0.1, c["high"] - c["low"])
            body_range = abs(c["close"] - c["open"])
            lower_wick = min(c["open"], c["close"]) - c["low"]
            upper_wick = c["high"] - max(c["open"], c["close"])

            # Base Pullback
            base_buy = bull_trend and (c["low"] <= ema20 * 1.0008) and (c["close"] > c["open"])
            base_sell = bear_trend and (c["high"] >= ema20 * 0.9992) and (c["close"] < c["open"])

            # Footprint filter
            if cfg.get("use_footprint"):
                min_dp = cfg.get("min_delta_pct", 0.10)
                base_buy = base_buy and (delta_pct >= min_dp)
                base_sell = base_sell and (delta_pct <= -min_dp)

            # Wick Rejection filter (Buyers defending support, sellers capping resistance)
            if cfg.get("use_wick_rejection"):
                base_buy = base_buy and (lower_wick / total_range >= 0.25)
                base_sell = base_sell and (upper_wick / total_range >= 0.25)

            # Absorption check: passive buyers absorbing heavy sellers or aggressive sellers pushing into trapped buyers
            if cfg.get("use_absorption"):
                # Bullish absorption: lower wick high with positive close
                bull_abs = (lower_wick / total_range >= 0.35) and (c["close"] >= c["open"])
                bear_abs = (upper_wick / total_range >= 0.35) and (c["close"] <= c["open"])
                base_buy = base_buy or (bull_trend and bull_abs and c["low"] <= ema50 * 1.001)
                base_sell = base_sell or (bear_trend and bear_abs and c["high"] >= ema50 * 0.999)

            if not (base_buy or base_sell):
                continue

            if base_buy:
                dist = max(3.5, current_price - (c["low"] - 0.8))
                sl_price = round(current_price - dist, 2)
                tp_price = round(current_price + (dist * cfg.get("target_rr", 2.5)), 2) if not cfg.get("trailing") else None
                side = "BUY"
            else:
                dist = max(3.5, (c["high"] + 0.8) - current_price)
                sl_price = round(current_price + dist, 2)
                tp_price = round(current_price - (dist * cfg.get("target_rr", 2.5)), 2) if not cfg.get("trailing") else None
                side = "SELL"

            lots = max(1, int(round(TARGET_RISK_USD / (dist * 0.001))))
            notional = lots * 0.001 * current_price

            active_trade = {
                "side": side,
                "entry_price": current_price,
                "stop_loss": sl_price,
                "take_profit": tp_price,
                "dist": dist,
                "highest": current_price,
                "lowest": current_price,
                "lots": lots,
                "notional_usd": round(notional, 2),
                "risk_usd": TARGET_RISK_USD
            }

        # Metrics calculation
        wins = [t for t in trades if t["pnl_usd"] > 0]
        losses = [t for t in trades if t["pnl_usd"] < 0]
        total = len(trades)
        win_rate = round(len(wins)/total*100, 1) if total > 0 else 0
        gross_win = sum(t["pnl_usd"] for t in wins)
        gross_loss = abs(sum(t["pnl_usd"] for t in losses))
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0
        net = round(capital - 50.0, 2)

        peak = 50.0
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd

        print(f"\n{cfg['name']}")
        print(f"  Trades: {total:3d} | Win Rate: {win_rate:5.1f}% | Profit Factor: {pf:4.2f} | Net P&L: ${net:+7.2f} | Max DD: -${max_dd:5.2f}")

if __name__ == "__main__":
    simulate_engine()
