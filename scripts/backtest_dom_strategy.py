#!/usr/bin/env python3
"""
Institutional Level 2 DOM Strategy Backtester
==============================================
Loads historical DOM snapshots recorded by scripts/record_l2_dom.py from dom_recorder.db
and tests custom orderflow / DOM trading strategies.

Strategies you can test:
1. DOM Imbalance Momentum: Enter when one side dominates depth by >= 1.8x.
2. Iceberg Wall Bounce: Enter when price tests a resting liquidity wall and rejects.
3. Liquidity Absorption / Trap: Enter when opposing DOM fails to move price.
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import DOM_DATABASE_PATH, ACTIVE_SYMBOLS, CONTRACT_VALUES
from data.database import DatabaseManager
from strategies.orderflow_engine import OrderFlowEngine

IST = timezone(timedelta(hours=5, minutes=30))

class DOMStrategyBacktester:
    def __init__(self, db_path=DOM_DATABASE_PATH):
        self.db = DatabaseManager(db_path=db_path)
        self.engine = OrderFlowEngine()

    def get_available_stats(self) -> Dict[str, Any]:
        """Summarizes available recorded snapshots per symbol."""
        stats = {}
        for sym in ACTIVE_SYMBOLS:
            snaps = self.db.get_dom_snapshots(sym, limit=100000)
            if snaps:
                first_ts = snaps[0]["datetime_ist"]
                last_ts = snaps[-1]["datetime_ist"]
                stats[sym] = {
                    "count": len(snaps),
                    "start": first_ts,
                    "end": last_ts
                }
            else:
                stats[sym] = {"count": 0, "start": "N/A", "end": "N/A"}
        return stats

    def run_imbalance_wall_strategy(
        self,
        symbol: str,
        min_imbalance: float = 1.8,
        tp_pct: float = 0.003, # 0.3% Take Profit
        sl_pct: float = 0.0015 # 0.15% Stop Loss (1:2 R:R)
    ) -> Dict[str, Any]:
        """
        Backtests an Institutional DOM Imbalance & Liquidity Wall Strategy:
        - Long Trigger : Buyer Imbalance >= 1.8x AND Active Bid Wall support below price
        - Short Trigger: Seller Imbalance >= 1.8x AND Active Ask Wall resistance above price
        """
        snapshots = self.db.get_dom_snapshots(symbol, limit=50000)
        if len(snapshots) < 10:
            return {
                "success": False,
                "error": f"Insufficient snapshots recorded for {symbol} ({len(snapshots)} found). Let recorder run 24/7."
            }

        trades = []
        in_trade = False
        current_pos = None

        for i, snap in enumerate(snapshots):
            mid = snap["mid_price"]
            ratio = snap["imbalance_ratio"]
            side = snap["dominant_side"]
            bid_walls = snap.get("bid_walls", [])
            ask_walls = snap.get("ask_walls", [])
            ts_str = snap.get("datetime_ist", "")

            # 1. Manage Active Trade
            if in_trade:
                entry = current_pos["entry_price"]
                pos_side = current_pos["side"]

                if pos_side == "BUY":
                    if mid >= current_pos["take_profit"]:
                        current_pos["exit_price"] = mid
                        current_pos["exit_time"] = ts_str
                        current_pos["outcome"] = "WIN"
                        current_pos["pnl_pct"] = tp_pct
                        trades.append(current_pos)
                        in_trade = False
                    elif mid <= current_pos["stop_loss"]:
                        current_pos["exit_price"] = mid
                        current_pos["exit_time"] = ts_str
                        current_pos["outcome"] = "LOSS"
                        current_pos["pnl_pct"] = -sl_pct
                        trades.append(current_pos)
                        in_trade = False

                elif pos_side == "SELL":
                    if mid <= current_pos["take_profit"]:
                        current_pos["exit_price"] = mid
                        current_pos["exit_time"] = ts_str
                        current_pos["outcome"] = "WIN"
                        current_pos["pnl_pct"] = tp_pct
                        trades.append(current_pos)
                        in_trade = False
                    elif mid >= current_pos["stop_loss"]:
                        current_pos["exit_price"] = mid
                        current_pos["exit_time"] = ts_str
                        current_pos["outcome"] = "LOSS"
                        current_pos["pnl_pct"] = -sl_pct
                        trades.append(current_pos)
                        in_trade = False
                continue

            # 2. Check Entry Conditions
            if not in_trade:
                # Strong buyers + Bid wall detected
                if side == "BUYERS" and ratio >= min_imbalance and len(bid_walls) > 0:
                    tp = mid * (1.0 + tp_pct)
                    sl = mid * (1.0 - sl_pct)
                    current_pos = {
                        "symbol": symbol,
                        "side": "BUY",
                        "entry_price": mid,
                        "entry_time": ts_str,
                        "take_profit": tp,
                        "stop_loss": sl,
                        "imbalance_ratio": ratio,
                        "walls_count": len(bid_walls)
                    }
                    in_trade = True

                # Strong sellers + Ask wall detected
                elif side == "SELLERS" and ratio >= min_imbalance and len(ask_walls) > 0:
                    tp = mid * (1.0 - tp_pct)
                    sl = mid * (1.0 + sl_pct)
                    current_pos = {
                        "symbol": symbol,
                        "side": "SELL",
                        "entry_price": mid,
                        "entry_time": ts_str,
                        "take_profit": tp,
                        "stop_loss": sl,
                        "imbalance_ratio": ratio,
                        "walls_count": len(ask_walls)
                    }
                    in_trade = True

        total_trades = len(trades)
        wins = sum(1 for t in trades if t["outcome"] == "WIN")
        losses = sum(1 for t in trades if t["outcome"] == "LOSS")
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
        total_return_pct = sum(t["pnl_pct"] for t in trades) * 100.0

        return {
            "success": True,
            "symbol": symbol,
            "total_snapshots_analyzed": len(snapshots),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_return_pct": round(total_return_pct, 2),
            "trades": trades
        }

def main():
    tester = DOMStrategyBacktester()
    print("=" * 70)
    print("  📊 LEVEL 2 DOM HISTORICAL STRATEGY BACKTESTER")
    print("=" * 70)
    stats = tester.get_available_stats()
    for sym, st in stats.items():
        print(f"  {sym:<8} : {st['count']} snapshots recorded ({st['start']} to {st['end']})")
    print("=" * 70)

    for sym in ACTIVE_SYMBOLS:
        res = tester.run_imbalance_wall_strategy(sym)
        if res.get("success"):
            print(f"\n[Backtest Results: {sym}]")
            print(f"  Snapshots : {res['total_snapshots_analyzed']}")
            print(f"  Trades    : {res['total_trades']} (Wins: {res['wins']}, Losses: {res['losses']})")
            print(f"  Win Rate  : {res['win_rate']}%")
            print(f"  Return    : {res['total_return_pct']}%")
        else:
            print(f"  {sym}: {res.get('error')}")

if __name__ == "__main__":
    main()
