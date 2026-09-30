import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from data.historical_loader import HistoricalDataLoader
from backtest.backtester import BacktestSimulator
from reports.html_reporter import HTMLReporter

def main():
    db = DatabaseManager()
    loader = HistoricalDataLoader(db)
    reporter = HTMLReporter()

    # Check if candles already exist in SQLite
    candles = db.get_latest_candles("XAUTUSD", "15m", limit=3000)
    
    if len(candles) < 500:
        csv_path = Path("data/csv_imports/futures-trades-monthly-XAUTUSD-2026-08.csv/XAUTUSD_2026-08.csv")
        if not csv_path.exists():
            files = loader.find_all_csv_files()
            if files:
                csv_path = files[-1]
        print(f"Loading real Delta trade ticks from: {csv_path.name}...")
        loader.process_delta_csv_file(csv_path, timeframe_minutes=15)
        candles = db.get_latest_candles("XAUTUSD", "15m", limit=3000)

    print(f"Loaded {len(candles)} real 15m candles with true Volume Delta from SQLite.")
    print("\nRunning Institutional Trend-Pullback & Order Flow Confluence Backtest...")
    
    simulator = BacktestSimulator(db, initial_capital=50.0)
    results = simulator.run_backtest("XAUTUSD", candles)

    print("\n==============================================")
    print("      REAL DELTA TICK BACKTEST RESULTS        ")
    print("==============================================")
    print(f"Initial Capital  : ${results['initial_capital']:.2f}")
    print(f"Final Capital    : ${results['final_capital']:.2f}")
    print(f"Net Realized P&L : ${results['net_pl']:+.2f} ({results['roi_pct']:+.1f}%)")
    print(f"Total Trades     : {results['total_trades']}")
    print(f"Wins / Losses    : {results['wins']} Wins / {results['losses']} Losses")
    print(f"Win Rate         : {results['win_rate']}%")
    print(f"Profit Factor    : {results['profit_factor']}")
    print(f"Max Drawdown     : -${results['max_drawdown_usd']:.2f}")
    print("==============================================")

    # Save trades to SQLite database journal
    for t in results["trades"]:
        db.log_trade(t)

    # Update interactive reports
    r_path = reporter.generate_backtest_report(results, "XAUTUSD (Delta Real Data)")
    j_path = reporter.generate_agent_journal(
        results["trades"],
        [
            {
                "timestamp": "2026-09-25 15:45:00",
                "symbol": "XAUTUSD",
                "event_type": "CALIBRATION_SUCCESS",
                "conviction_stars": 5.0,
                "message": f"Real Delta backtest completed. Net PnL: ${results['net_pl']:+.2f} ({results['roi_pct']:+.1f}%), Win Rate: {results['win_rate']}%, PF: {results['profit_factor']}."
            }
        ]
    )

    print(f"\nGenerated interactive dashboards:\n1. {r_path}\n2. {j_path}")

if __name__ == "__main__":
    main()
