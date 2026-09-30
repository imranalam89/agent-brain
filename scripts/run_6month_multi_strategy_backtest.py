import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester
from reports.html_reporter import HTMLReporter

def main():
    db = DatabaseManager()
    reporter = HTMLReporter()
    simulator = MultiStrategyBacktester(db, initial_capital=50.0)

    print("Fetching all 6 months of historical candles from local SQLite...")
    candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)
    print(f"Loaded {len(candles):,} real 15m candles (spanning April - September 2026).")

    print("\nRunning Multi-Strategy Simulation Suite across 6 Months...")
    results = simulator.run_all_strategies("XAUTUSD", candles)

    print("\n==========================================================================================")
    print("                   6-MONTH MULTI-STRATEGY BACKTEST SCORECARD ($50 BASE)                   ")
    print("==========================================================================================")
    print(f"{'Strategy Name':<60} | {'Trades':<6} | {'Win %':<6} | {'PF':<5} | {'Net P&L':<9} | {'Max DD':<7}")
    print("-" * 98)

    for key, s in results.items():
        print(f"{s['strategy_name']:<60} | {s['total_trades']:<6} | {s['win_rate']:<5.1f}% | {s['profit_factor']:<5.2f} | ${s['net_pl']:<+8.2f} | -${s['max_drawdown_usd']:<6.2f}")
    print("==========================================================================================")

    # Generate interactive multi-strategy HTML dashboard
    report_path = reporter.generate_multi_strategy_backtest_report(results, "XAUTUSD (April - September 2026)")
    
    # Save the best strategy's trades to the living journal
    best_key = max(results.keys(), key=lambda k: results[k]["net_pl"])
    best_strat = results[best_key]

    db.clear_trades()
    for t in best_strat["trades"]:
        db.log_trade(t)

    journal_path = reporter.generate_agent_journal(
        best_strat["trades"],
        [
            {
                "timestamp": "2026-09-25 16:30:00",
                "symbol": "XAUTUSD",
                "event_type": "SCALE_OUT_CHAMPION",
                "conviction_stars": 5.0,
                "message": f"6-Month Multi-Strategy & Scale-Out Analysis Completed. Champion: {best_strat['strategy_name']} with Net P&L ${best_strat['net_pl']:+.2f}, Win Rate: {best_strat['win_rate']}%, PF: {best_strat['profit_factor']}, Max Drawdown: -${best_strat['max_drawdown_usd']}."
            }
        ]
    )

    print(f"\nInteractive Dashboards Ready:\n1. Multi-Strategy Report: {report_path}\n2. Living Trade Journal:  {journal_path}")

if __name__ == "__main__":
    main()
