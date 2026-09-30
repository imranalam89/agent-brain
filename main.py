import sys
import os
import time
import webbrowser
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from config.settings import (
    BASE_DIR,
    ACTIVE_SYMBOLS,
    ACCOUNT_CAPITAL_USD,
    TARGET_RISK_USD,
    DAILY_MAX_LOSS_USD,
    DEFAULT_LEVERAGE,
    DELTA_ENVIRONMENT
)
from data.database import DatabaseManager
from exchange.delta_client import DeltaExchangeClient
from data.historical_loader import HistoricalDataLoader
from backtest.backtester import BacktestSimulator
from reports.html_reporter import HTMLReporter
from execution.risk_manager import RiskManager
from strategies.sr_engine import SupportResistanceEngine
from strategies.orderflow_engine import OrderFlowEngine
from strategies.confluence_brain import ConfluenceBrain

def print_banner():
    print("""
========================================================================
     🧠 AGENT BRAIN | QUANTITATIVE TRADING & RISK COCKPIT 🧠
   Assets: BTCUSD, XAUTUSD (Gold), SLVONUSD (Silver) | Delta Exchange
   Risk: $3-$5 / Trade | Daily Limit: $20 | Leverage: 100x Isolated
========================================================================
    """)

def run_backtest_pipeline(db: DatabaseManager, client: DeltaExchangeClient, reporter: HTMLReporter):
    print("\n--- Running 6-Month Multi-Strategy Backtester (Gold & Silver) ---")
    gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=25000)
    silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)

    from backtest.multi_strategy_backtester import MultiStrategyBacktester
    multi_sim = MultiStrategyBacktester(db, initial_capital=ACCOUNT_CAPITAL_USD)

    gold_results = multi_sim.run_all_strategies("XAUTUSD", gold_candles) if gold_candles else {}
    silver_results = multi_sim.run_all_strategies("SLVONUSD", silver_candles) if silver_candles else {}

    print(f"Loaded {len(gold_candles):,} Gold 15m candles and {len(silver_candles):,} Silver 15m candles.")

    print("\n==========================================================================================")
    print("                    GOLD (XAUTUSD) SCORECARD ($50 BASE CAPITAL)                           ")
    print("==========================================================================================")
    print(f"{'Strategy Name':<60} | {'Trades':<6} | {'Win %':<6} | {'PF':<5} | {'Net P&L':<9} | {'Max DD':<7}")
    print("-" * 98)
    for key, s in sorted(gold_results.items(), key=lambda x: x[1]['net_pl'], reverse=True)[:5]:
        print(f"{s['strategy_name'][:58]:<60} | {s['total_trades']:<6} | {s['win_rate']:<5.1f}% | {s['profit_factor']:<5.2f} | ${s['net_pl']:<+8.2f} | -${s['max_drawdown_usd']:<6.2f}")

    print("\n==========================================================================================")
    print("                   SILVER (SLVONUSD) SCORECARD ($50 BASE CAPITAL)                         ")
    print("==========================================================================================")
    print(f"{'Strategy Name':<60} | {'Trades':<6} | {'Win %':<6} | {'PF':<5} | {'Net P&L':<9} | {'Max DD':<7}")
    print("-" * 98)
    for key, s in sorted(silver_results.items(), key=lambda x: x[1]['net_pl'], reverse=True)[:5]:
        print(f"{s['strategy_name'][:58]:<60} | {s['total_trades']:<6} | {s['win_rate']:<5.1f}% | {s['profit_factor']:<5.2f} | ${s['net_pl']:<+8.2f} | -${s['max_drawdown_usd']:<6.2f}")
    print("==========================================================================================")

    report_path = reporter.generate_multi_strategy_backtest_report(
        gold_results,
        "Multi-Asset (Gold & Silver)",
        silver_results=silver_results
    )
    print(f"\nReport generated at:\n  {report_path}")

    try:
        webbrowser.open(report_path.as_uri())
    except Exception:
        pass

def run_paper_trading(db: DatabaseManager, client: DeltaExchangeClient, reporter: HTMLReporter):
    print("\n--- Starting Paper Trading Monitor (Live Delta Feed Simulation) ---")
    print("Press Ctrl+C to stop.\n")
    print("Checking Delta Exchange connectivity...")

    sr = SupportResistanceEngine()
    of = OrderFlowEngine()
    brain = ConfluenceBrain()
    risk = RiskManager(db)

    # Perform an institutional live evaluation loop
    for symbol in ACTIVE_SYMBOLS:
        print(f"\n[Institutional Scan: {symbol}]")
        spec = client.get_product_spec(symbol)
        dom = client.get_l2_orderbook(symbol)
        ticker = client.get_ticker(symbol)
        current_price = ticker.get("mark_price", 0.0)

        bids = dom.get("bids", [])
        asks = dom.get("asks", [])
        dom_analysis = of.analyze_dom(bids, asks)

        # Fetch recent candles for liquidity sweep & trend evaluation
        recent_candles = db.get_latest_candles(symbol, "15m", limit=30)
        is_sweep = False
        sweep_type = "NONE"
        sweep_details = "No sweep"
        if len(recent_candles) >= 20:
            is_sweep, sweep_type, sweep_details = of.detect_liquidity_sweep(recent_candles[-1], recent_candles[:-1])

        print(f"Price: ${current_price} | DOM: Buyers {dom_analysis['total_bid_size']} vs Sellers {dom_analysis['total_ask_size']} -> {dom_analysis['dominant_side']}")
        if is_sweep:
            print(f"🚨 INSTITUTIONAL ALERT: {sweep_details}")

        # Log brain evaluation thought into living database
        thought_msg = f"Scanning {symbol} at ${current_price}. DOM dominance: {dom_analysis['dominant_side']} (Ratio: {dom_analysis['bid_imbalance_ratio']}x). Liquidity Sweep: {sweep_type}."
        db.log_thought(
            symbol=symbol,
            event_type="INSTITUTIONAL_SCAN",
            stars=4.2 if is_sweep else 3.5,
            message=thought_msg,
            metrics={"dom": dom_analysis, "price": current_price, "sweep": sweep_type}
        )

    # Update living journal HTML
    journal_path = reporter.generate_agent_journal(db.get_trades(), db.get_recent_thoughts())
    print(f"\nLiving Journal updated at:\n  {journal_path}")

def run_post_mortem(db: DatabaseManager):
    print("\n--- Running AI Post-Mortem & Parameter Calibration ---")
    trades = db.get_trades()
    if not trades:
        print("No trade history in database yet to calibrate. Run backtest or paper trading first!")
        return

    wins = [t for t in trades if (t.get("pnl_usd") or 0) > 0]
    losses = [t for t in trades if (t.get("pnl_usd") or 0) < 0]
    total = len(trades)
    net_pnl = sum((t.get("pnl_usd") or 0) for t in trades)
    gross_win = sum((t.get("pnl_usd") or 0) for t in wins)
    gross_loss = abs(sum((t.get("pnl_usd") or 0) for t in losses))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0.0
    avg_win = round(gross_win / len(wins), 2) if wins else 0.0
    avg_loss = round(gross_loss / len(losses), 2) if losses else 0.0
    max_win = round(max((t.get("pnl_usd") or 0) for t in wins), 2) if wins else 0.0

    print(f"Total Audited Trades: {total}")
    print(f"Win Rate:             {len(wins)/total*100:.1f}% ({len(wins)} Wins / {len(losses)} Losses)")
    print(f"Profit Factor:        {pf}")
    print(f"Cumulative Net P&L:   ${net_pnl:+.2f}")
    print(f"Average Win / Loss:   +${avg_win} / -${avg_loss} (Ratio: {round(avg_win/max(0.01, avg_loss), 2)}x)")
    print(f"Max Single Runner:    +${max_win}")
    print("\nInstitutional Calibration:")
    print("1. Scale-Out Discipline: Cutting 50% lots at 1:2.5 - 1:3.0 locks in profits and completely protects capital.")
    print("2. Weekend Lock: Strictly active. Zero trades allowed on Saturday/Sunday.")
    print("3. Order Flow Veto: Retain Conviction Filter >= 3.5 Stars.")

def main():
    db = DatabaseManager()
    client = DeltaExchangeClient()
    reporter = HTMLReporter()

    while True:
        print_banner()
        print("1. Run Multi-Timeframe Backtest & Generate Interactive HTML Report")
        print("2. Run Paper Trading Engine (Live Delta Feed Simulation)")
        print("3. Run AI Post-Mortem & Parameter Calibration")
        print("4. Open Living Trade Journal (agent_journal.html)")
        print("5. Start Autonomous Multi-Pair Live Trader (Delta Exchange India)")
        print("6. Exit")
        print("------------------------------------------------------------------------")
        choice = input("Enter choice (1-6): ").strip()

        if choice == "1":
            run_backtest_pipeline(db, client, reporter)
            input("\nPress Enter to return to menu...")
        elif choice == "2":
            run_paper_trading(db, client, reporter)
            input("\nPress Enter to return to menu...")
        elif choice == "3":
            run_post_mortem(db)
            input("\nPress Enter to return to menu...")
        elif choice == "4":
            journal_path = reporter.generate_agent_journal(db.get_trades(), db.get_recent_thoughts())
            print(f"Opening: {journal_path}")
            try:
                webbrowser.open(journal_path.as_uri())
            except Exception:
                pass
            input("\nPress Enter to return to menu...")
        elif choice == "5":
            from execution.multi_pair_trader import MultiPairLiveTrader
            trader = MultiPairLiveTrader(fixed_risk_usd=5.0)
            print("\nStarting Autonomous Multi-Pair Live Trader... (Press Ctrl+C to stop)")
            try:
                while True:
                    trader.scan_and_manage_all_pairs()
                    time.sleep(15)
            except KeyboardInterrupt:
                print("\n[STOPPED] Live trader paused.")
            input("\nPress Enter to return to menu...")
        elif choice == "6":
            print("Exiting Agent Brain. Stay disciplined!")
            break
        else:
            print("Invalid choice, please enter 1-6.")

if __name__ == "__main__":
    main()
