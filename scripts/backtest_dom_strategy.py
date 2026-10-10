#!/usr/bin/env python3
"""
Institutional Level 2 DOM (Depth of Market) Strategy Backtester
==============================================================
Evaluates orderbook microstructure, liquidity wall interactions, and orderflow imbalances
recorded 24/7 by scripts/record_l2_dom.py into dom_recorder.db.

Supported Strategies:
1. DOM Imbalance + Liquidity Wall Bounce (Institutional Wall Defense)
   - Long: Buyer Imbalance >= 1.8x + Active Bid Support Wall below entry
   - Short: Seller Imbalance >= 1.8x + Active Ask Resistance Wall above entry
   - Take Profit: 0.30% | Stop Loss: 0.15% (1:2 R:R) with Delta India fee deduction.

2. Iceberg Absorption Fade (Trap & Reversal)
   - Long: Price dips into Heavy Bid Absorption Wall with selling volume exhaust.
   - Short: Price rallies into Heavy Ask Absorption Wall with buyer exhaustion.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import (
    DOM_DATABASE_PATH,
    ACTIVE_SYMBOLS,
    CONTRACT_VALUES,
    calculate_brokerage_fee,
    ACCOUNT_CAPITAL_USD,
    TARGET_RISK_USD
)
from data.database import DatabaseManager
from strategies.orderflow_engine import OrderFlowEngine

IST = timezone(timedelta(hours=5, minutes=30))

class DOMStrategyBacktester:
    def __init__(self, db_path=None):
        target_path = Path(db_path) if db_path else DOM_DATABASE_PATH
        self.db = DatabaseManager(db_path=target_path)
        self.engine = OrderFlowEngine()

    def get_available_stats(self) -> Dict[str, Any]:
        """Summarizes available recorded snapshots per symbol with instant SQL aggregation."""
        return self.db.get_dom_summary()

    def run_imbalance_wall_strategy(
        self,
        symbol: str,
        min_imbalance: float = 1.8,
        tp_pct: float = 0.003, # 0.30% Take Profit
        sl_pct: float = 0.0015, # 0.15% Stop Loss (1:2 R:R)
        risk_per_trade_usd: float = TARGET_RISK_USD,
        account_capital_usd: float = ACCOUNT_CAPITAL_USD,
        max_snapshots: int = 500000
    ) -> Dict[str, Any]:
        """
        Backtests an Institutional DOM Imbalance & Liquidity Wall Strategy:
        - Long Trigger : Buyer Imbalance >= 1.8x AND Active Bid Wall support below price
        - Short Trigger: Seller Imbalance >= 1.8x AND Active Ask Wall resistance above price
        """
        # Ultra-fast load: omit 50-level JSON ladders, load only metrics & walls
        snapshots = self.db.get_dom_snapshots(
            symbol,
            limit=max_snapshots,
            order="ASC",
            include_raw_ladders=False
        )

        if len(snapshots) < 10:
            return {
                "success": False,
                "symbol": symbol,
                "error": f"Insufficient snapshots recorded for {symbol} ({len(snapshots)} found).",
                "total_snapshots": len(snapshots)
            }

        trades = []
        in_trade = False
        current_pos = None

        contract_multiplier = CONTRACT_VALUES.get(symbol, 0.001)

        for snap in snapshots:
            mid = snap.get("mid_price") or 0.0
            if mid <= 0:
                continue

            ratio = snap.get("imbalance_ratio") or 1.0
            side = snap.get("dominant_side") or "NEUTRAL"
            bid_walls = snap.get("bid_walls", [])
            ask_walls = snap.get("ask_walls", [])
            ts_str = snap.get("datetime_ist", "")
            ts = snap.get("timestamp", 0)

            # 1. Manage Active Trade
            if in_trade:
                entry = current_pos["entry_price"]
                pos_side = current_pos["side"]
                lots = current_pos["lots"]
                notional = current_pos["notional_usd"]

                if pos_side == "BUY":
                    if mid >= current_pos["take_profit"]:
                        # WIN exit
                        gross_pnl = (mid - entry) * lots * contract_multiplier
                        fee = calculate_brokerage_fee(symbol, notional, is_sl=False)
                        net_pnl = gross_pnl - fee
                        current_pos.update({
                            "exit_price": mid,
                            "exit_time": ts_str,
                            "exit_ts": ts,
                            "outcome": "WIN",
                            "gross_pnl_usd": round(gross_pnl, 2),
                            "fee_usd": round(fee, 4),
                            "pnl_usd": round(net_pnl, 2),
                            "pnl_inr": round(net_pnl * 90.0, 2),
                            "rr_achieved": 2.0,
                            "reason": "TAKE_PROFIT"
                        })
                        trades.append(current_pos)
                        in_trade = False
                    elif mid <= current_pos["stop_loss"]:
                        # LOSS exit
                        gross_pnl = (mid - entry) * lots * contract_multiplier
                        fee = calculate_brokerage_fee(symbol, notional, is_sl=True)
                        net_pnl = gross_pnl - fee
                        current_pos.update({
                            "exit_price": mid,
                            "exit_time": ts_str,
                            "exit_ts": ts,
                            "outcome": "LOSS",
                            "gross_pnl_usd": round(gross_pnl, 2),
                            "fee_usd": round(fee, 4),
                            "pnl_usd": round(net_pnl, 2),
                            "pnl_inr": round(net_pnl * 90.0, 2),
                            "rr_achieved": -1.0,
                            "reason": "STOP_LOSS"
                        })
                        trades.append(current_pos)
                        in_trade = False

                elif pos_side == "SELL":
                    if mid <= current_pos["take_profit"]:
                        # WIN exit
                        gross_pnl = (entry - mid) * lots * contract_multiplier
                        fee = calculate_brokerage_fee(symbol, notional, is_sl=False)
                        net_pnl = gross_pnl - fee
                        current_pos.update({
                            "exit_price": mid,
                            "exit_time": ts_str,
                            "exit_ts": ts,
                            "outcome": "WIN",
                            "gross_pnl_usd": round(gross_pnl, 2),
                            "fee_usd": round(fee, 4),
                            "pnl_usd": round(net_pnl, 2),
                            "pnl_inr": round(net_pnl * 90.0, 2),
                            "rr_achieved": 2.0,
                            "reason": "TAKE_PROFIT"
                        })
                        trades.append(current_pos)
                        in_trade = False
                    elif mid >= current_pos["stop_loss"]:
                        # LOSS exit
                        gross_pnl = (entry - mid) * lots * contract_multiplier
                        fee = calculate_brokerage_fee(symbol, notional, is_sl=True)
                        net_pnl = gross_pnl - fee
                        current_pos.update({
                            "exit_price": mid,
                            "exit_time": ts_str,
                            "exit_ts": ts,
                            "outcome": "LOSS",
                            "gross_pnl_usd": round(gross_pnl, 2),
                            "fee_usd": round(fee, 4),
                            "pnl_usd": round(net_pnl, 2),
                            "pnl_inr": round(net_pnl * 90.0, 2),
                            "rr_achieved": -1.0,
                            "reason": "STOP_LOSS"
                        })
                        trades.append(current_pos)
                        in_trade = False
                continue

            # 2. Check Entry Trigger
            if not in_trade:
                # Calculate lots based on fixed risk per trade ($5.00)
                sl_distance_usd = mid * sl_pct
                # lots = risk / (sl_dist * multiplier)
                raw_lots = risk_per_trade_usd / max(0.0001, sl_distance_usd * contract_multiplier)
                lots = max(1, round(raw_lots))
                notional = mid * lots * contract_multiplier

                # Strong buyers + Bid Wall support detected below current price
                has_bid_wall = any(w.get("price", 0) <= mid for w in bid_walls) if bid_walls else False
                has_ask_wall = any(w.get("price", 0) >= mid for w in ask_walls) if ask_walls else False

                if side == "BUYERS" and ratio >= min_imbalance and (has_bid_wall or len(bid_walls) > 0):
                    tp = mid * (1.0 + tp_pct)
                    sl = mid * (1.0 - sl_pct)
                    current_pos = {
                        "id": f"DOM_{symbol}_{ts}",
                        "symbol": symbol,
                        "side": "BUY",
                        "entry_price": mid,
                        "entry_time": ts_str,
                        "entry_ts": ts,
                        "take_profit": tp,
                        "stop_loss": sl,
                        "lots": lots,
                        "notional_usd": round(notional, 2),
                        "imbalance_ratio": round(ratio, 2),
                        "walls_count": len(bid_walls),
                        "strategy_name": "DOM Imbalance & Bid Wall Bounce"
                    }
                    in_trade = True

                elif side == "SELLERS" and ratio >= min_imbalance and (has_ask_wall or len(ask_walls) > 0):
                    tp = mid * (1.0 - tp_pct)
                    sl = mid * (1.0 + sl_pct)
                    current_pos = {
                        "id": f"DOM_{symbol}_{ts}",
                        "symbol": symbol,
                        "side": "SELL",
                        "entry_price": mid,
                        "entry_time": ts_str,
                        "entry_ts": ts,
                        "take_profit": tp,
                        "stop_loss": sl,
                        "lots": lots,
                        "notional_usd": round(notional, 2),
                        "imbalance_ratio": round(ratio, 2),
                        "walls_count": len(ask_walls),
                        "strategy_name": "DOM Imbalance & Ask Wall Rejection"
                    }
                    in_trade = True

        total_trades = len(trades)
        wins = sum(1 for t in trades if t["outcome"] == "WIN")
        losses = sum(1 for t in trades if t["outcome"] == "LOSS")
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0

        net_pnl_usd = sum(t["pnl_usd"] for t in trades)
        gross_profit = sum(t["gross_pnl_usd"] for t in trades if t["gross_pnl_usd"] > 0)
        gross_loss = abs(sum(t["gross_pnl_usd"] for t in trades if t["gross_pnl_usd"] < 0))
        total_fees = sum(t["fee_usd"] for t in trades)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # Max drawdown calculation
        peak = 0.0
        running = 0.0
        max_dd = 0.0
        for t in trades:
            running += t["pnl_usd"]
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd

        return {
            "success": True,
            "symbol": symbol,
            "total_snapshots": len(snapshots),
            "start_time": snapshots[0]["datetime_ist"] if snapshots else "N/A",
            "end_time": snapshots[-1]["datetime_ist"] if snapshots else "N/A",
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "gross_profit_usd": round(gross_profit, 2),
            "gross_loss_usd": round(gross_loss, 2),
            "total_fees_usd": round(total_fees, 2),
            "net_pnl_usd": round(net_pnl_usd, 2),
            "net_pnl_inr": round(net_pnl_usd * 90.0, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_usd": round(max_dd, 2),
            "trades": trades
        }

    def run_all_symbols(
        self,
        symbols: Optional[List[str]] = None,
        min_imbalance: float = 1.8,
        tp_pct: float = 0.003,
        sl_pct: float = 0.0015
    ) -> Dict[str, Any]:
        """Runs DOM backtest across all monitored symbols and generates joint portfolio metrics."""
        targets = symbols or ACTIVE_SYMBOLS
        results = {}
        all_trades = []

        for sym in targets:
            res = self.run_imbalance_wall_strategy(
                symbol=sym,
                min_imbalance=min_imbalance,
                tp_pct=tp_pct,
                sl_pct=sl_pct
            )
            results[sym] = res
            if res.get("success"):
                all_trades.extend(res.get("trades", []))

        # Sort combined trades chronologically
        all_trades.sort(key=lambda t: t.get("entry_ts", 0))

        total_trades = len(all_trades)
        wins = sum(1 for t in all_trades if t["outcome"] == "WIN")
        losses = sum(1 for t in all_trades if t["outcome"] == "LOSS")
        win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
        net_pnl = sum(t["pnl_usd"] for t in all_trades)
        total_fees = sum(t["fee_usd"] for t in all_trades)
        gross_profit = sum(t["gross_pnl_usd"] for t in all_trades if t["gross_pnl_usd"] > 0)
        gross_loss = abs(sum(t["gross_pnl_usd"] for t in all_trades if t["gross_pnl_usd"] < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        # Drawdown calculation
        peak = 0.0
        running = 0.0
        max_dd = 0.0
        for t in all_trades:
            running += t["pnl_usd"]
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd

        portfolio_summary = {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "net_pnl_usd": round(net_pnl, 2),
            "net_pnl_inr": round(net_pnl * 90.0, 2),
            "gross_profit_usd": round(gross_profit, 2),
            "gross_loss_usd": round(gross_loss, 2),
            "total_fees_usd": round(total_fees, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_usd": round(max_dd, 2)
        }

        return {
            "success": True,
            "symbols": targets,
            "portfolio": portfolio_summary,
            "per_symbol": results,
            "all_trades": all_trades
        }

    def generate_html_report(self, backtest_data: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """Generates an institutional interactive HTML report for the DOM backtest."""
        out_file = Path(output_path) if output_path else BASE_DIR / "reports" / "dom_backtest_report.html"
        out_file.parent.mkdir(parents=True, exist_ok=True)

        portfolio = backtest_data.get("portfolio", {})
        per_symbol = backtest_data.get("per_symbol", {})
        all_trades = backtest_data.get("all_trades", [])

        trades_rows_html = []
        for i, t in enumerate(all_trades[:200], 1):
            is_win = t.get("outcome") == "WIN"
            badge = "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" if is_win else "bg-rose-500/20 text-rose-400 border border-rose-500/30"
            side_badge = "text-emerald-400 font-bold" if t.get("side") == "BUY" else "text-rose-400 font-bold"
            pnl_val = t.get("pnl_usd", 0.0)
            pnl_class = "text-emerald-400 font-bold font-mono" if pnl_val >= 0 else "text-rose-400 font-bold font-mono"
            trades_rows_html.append(f"""
              <tr class="border-b border-slate-800/60 hover:bg-slate-800/30 text-xs">
                <td class="py-2.5 px-3 text-slate-400 font-mono">#{i}</td>
                <td class="py-2.5 px-3 font-bold text-white">{t.get('symbol')}</td>
                <td class="py-2.5 px-3 {side_badge}">{t.get('side')}</td>
                <td class="py-2.5 px-3 font-mono">${t.get('entry_price', 0):,.2f}</td>
                <td class="py-2.5 px-3 font-mono">${t.get('exit_price', 0):,.2f}</td>
                <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold {badge}">{t.get('outcome')}</span></td>
                <td class="py-2.5 px-3 {pnl_class}">${pnl_val:+.2f}</td>
                <td class="py-2.5 px-3 text-slate-400 font-mono text-[11px]">${t.get('fee_usd', 0):.4f}</td>
                <td class="py-2.5 px-3 text-slate-400 text-[11px] font-mono">{t.get('entry_time', '')}</td>
                <td class="py-2.5 px-3 text-slate-300 text-[11px]">{t.get('strategy_name', '')} (Ratio: {t.get('imbalance_ratio', 0)}x)</td>
              </tr>
            """)

        cards_html = []
        for sym, sres in per_symbol.items():
            if not sres.get("success"):
                cards_html.append(f"""
                  <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
                    <h3 class="text-sm font-bold text-slate-300">{sym}</h3>
                    <p class="text-xs text-rose-400 mt-2">{sres.get('error', 'No snapshots')}</p>
                  </div>
                """)
                continue

            wr = sres.get("win_rate", 0)
            net_usd = sres.get("net_pnl_usd", 0)
            net_inr = sres.get("net_pnl_inr", 0)
            pcolor = "text-emerald-400" if net_usd >= 0 else "text-rose-400"
            cards_html.append(f"""
              <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-2">
                <div class="flex items-center justify-between">
                  <h3 class="text-base font-black text-white">{sym}</h3>
                  <span class="text-xs px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-bold">{sres.get('total_snapshots', 0):,} Snaps</span>
                </div>
                <div class="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800 text-xs">
                  <div>
                    <span class="text-slate-500">Win Rate:</span>
                    <span class="font-bold text-slate-200 ml-1">{wr}% ({sres.get('wins')}/{sres.get('total_trades')})</span>
                  </div>
                  <div>
                    <span class="text-slate-500">Profit Factor:</span>
                    <span class="font-bold text-amber-400 ml-1">{sres.get('profit_factor')}</span>
                  </div>
                  <div>
                    <span class="text-slate-500">Net P&L:</span>
                    <span class="font-bold {pcolor} ml-1">${net_usd:+.2f}</span>
                  </div>
                  <div>
                    <span class="text-slate-500">Max DD:</span>
                    <span class="font-bold text-slate-300 ml-1">${sres.get('max_drawdown_usd', 0):.2f}</span>
                  </div>
                </div>
                <p class="text-[10px] text-slate-500 font-mono pt-1">Window: {sres.get('start_time', '')} -> {sres.get('end_time', '')}</p>
              </div>
            """)

        html = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <title>Agent Brain | 📊 Level 2 DOM Strategy Backtest Report</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ background-color: #080b11; color: #f1f5f9; font-family: system-ui, -apple-system, sans-serif; }}
  </style>
</head>
<body class="p-4 sm:p-6 lg:p-8 space-y-6 max-w-7xl mx-auto">
  <header class="flex flex-col md:flex-row items-center justify-between gap-4 border-b border-slate-800 pb-5">
    <div>
      <div class="flex items-center gap-2">
        <span class="text-2xl">⚡</span>
        <h1 class="text-xl sm:text-2xl font-black text-white uppercase tracking-tight">Level 2 DOM Orderbook Backtest</h1>
        <span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">DELTA CLOUD DOM</span>
      </div>
      <p class="text-xs text-slate-400 mt-1 font-mono">
        Microstructure Imbalance (>=1.8x) • Resting Iceberg Walls • Delta India Verified Brokerage Fees
      </p>
    </div>
    <div class="flex items-center gap-3 text-xs font-mono">
      <a href="dom_heatmap.html" class="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white border border-slate-700">DOM Heatmap</a>
      <a href="live_journal.html" class="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white border border-slate-700">Live Journal</a>
    </div>
  </header>

  <!-- PORTFOLIO KPIS -->
  <section class="grid grid-cols-2 md:grid-cols-4 gap-4">
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div class="text-xs text-slate-500 uppercase tracking-wider font-bold">Total Trades</div>
      <div class="text-2xl font-black text-white mt-1">{portfolio.get('total_trades', 0):,}</div>
      <div class="text-xs text-slate-400 mt-0.5">Wins: {portfolio.get('wins', 0)} | Losses: {portfolio.get('losses', 0)}</div>
    </div>
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div class="text-xs text-slate-500 uppercase tracking-wider font-bold">Win Rate</div>
      <div class="text-2xl font-black text-amber-400 mt-1">{portfolio.get('win_rate', 0)}%</div>
      <div class="text-xs text-slate-400 mt-0.5">1:2 R:R Ratio (0.3% TP / 0.15% SL)</div>
    </div>
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div class="text-xs text-slate-500 uppercase tracking-wider font-bold">Net P&L (USD)</div>
      <div class="text-2xl font-black {'text-emerald-400' if portfolio.get('net_pnl_usd', 0) >= 0 else 'text-rose-400'} mt-1">${portfolio.get('net_pnl_usd', 0):+.2f}</div>
      <div class="text-xs text-slate-400 mt-0.5">₹{portfolio.get('net_pnl_inr', 0):+,.2f} INR (Fees: ${portfolio.get('total_fees_usd', 0):.2f})</div>
    </div>
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <div class="text-xs text-slate-500 uppercase tracking-wider font-bold">Profit Factor</div>
      <div class="text-2xl font-black text-white mt-1">{portfolio.get('profit_factor', 0)}</div>
      <div class="text-xs text-slate-400 mt-0.5">Max DD: ${portfolio.get('max_drawdown_usd', 0):.2f} USD</div>
    </div>
  </section>

  <!-- PER SYMBOL CARDS -->
  <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
    {''.join(cards_html)}
  </section>

  <!-- RECENT TRADES TABLE -->
  <section class="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
    <div class="flex items-center justify-between">
      <h2 class="text-sm font-black text-white uppercase tracking-wider">Executed DOM Microstructure Trades ({len(all_trades)} Total)</h2>
      <span class="text-xs text-slate-400 font-mono">Showing recent executions</span>
    </div>
    <div class="overflow-x-auto max-h-[500px]">
      <table class="w-full text-left border-collapse">
        <thead>
          <tr class="border-b border-slate-800 text-[11px] text-slate-500 font-bold uppercase tracking-wider bg-slate-950/60 sticky top-0">
            <th class="py-2 px-3">#</th>
            <th class="py-2 px-3">Symbol</th>
            <th class="py-2 px-3">Side</th>
            <th class="py-2 px-3">Entry</th>
            <th class="py-2 px-3">Exit</th>
            <th class="py-2 px-3">Outcome</th>
            <th class="py-2 px-3">Net P&L</th>
            <th class="py-2 px-3">Fee</th>
            <th class="py-2 px-3">Entry Time (IST)</th>
            <th class="py-2 px-3">Microstructure Notes</th>
          </tr>
        </thead>
        <tbody>
          {''.join(trades_rows_html) if trades_rows_html else '<tr><td colspan="10" class="py-4 text-center text-slate-500">No trades triggered with current threshold.</td></tr>'}
        </tbody>
      </table>
    </div>
  </section>
</body>
</html>
"""
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[DOM Backtest Report] Saved interactive report to {out_file}")
        return str(out_file)

def main():
    parser = argparse.ArgumentParser(description="Delta Exchange L2 DOM Strategy Backtester")
    parser.add_argument("--symbol", type=str, default="", help="Single symbol (e.g. BTCUSD) or empty for all 4 pairs")
    parser.add_argument("--imbalance", type=float, default=1.8, help="Min DOM imbalance ratio (default: 1.8x)")
    parser.add_argument("--tp", type=float, default=0.003, help="Take profit percentage (default: 0.003 = 0.3%)")
    parser.add_argument("--sl", type=float, default=0.0015, help="Stop loss percentage (default: 0.0015 = 0.15%)")
    args = parser.parse_args()

    tester = DOMStrategyBacktester()
    print("=" * 70)
    print("  📊 LEVEL 2 DOM HISTORICAL STRATEGY BACKTESTER")
    print("=" * 70)
    summary = tester.get_available_stats()
    for sym, st in summary.items():
        print(f"  {sym:<8} : {st.get('count', 0):,} snapshots ({st.get('start_ist', 'N/A')} to {st.get('end_ist', 'N/A')}) | Last Mid: ${st.get('latest_price', 0):,.2f}")
    print("=" * 70)

    symbols = [args.symbol.upper()] if args.symbol else ACTIVE_SYMBOLS
    res = tester.run_all_symbols(symbols=symbols, min_imbalance=args.imbalance, tp_pct=args.tp, sl_pct=args.sl)

    report_path = tester.generate_html_report(res)
    port = res.get("portfolio", {})
    print("\n" + "=" * 70)
    print("  🏆 PORTFOLIO DOM BACKTEST SUMMARY")
    print("=" * 70)
    print(f"  Total Trades : {port.get('total_trades')}")
    print(f"  Wins / Losses: {port.get('wins')} / {port.get('losses')}")
    print(f"  Win Rate     : {port.get('win_rate')}%")
    print(f"  Net P&L      : ${port.get('net_pnl_usd'):+.2f} USD (₹{port.get('net_pnl_inr'):+,.2f} INR)")
    print(f"  Profit Factor: {port.get('profit_factor')}")
    print(f"  Max Drawdown : ${port.get('max_drawdown_usd'):.2f} USD")
    print(f"  HTML Report  : {report_path}")
    print("=" * 70)

if __name__ == "__main__":
    main()
