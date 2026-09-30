import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester
from reports.html_reporter import HTMLReporter

db = DatabaseManager()
candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)
sim = MultiStrategyBacktester(50.0)
results = sim.run_all_strategies("XAUTUSD", candles)

reporter = HTMLReporter()
report_path = reporter.generate_multi_strategy_backtest_report(results, "XAUTUSD (April - September 2026)")

print("\n" + "=" * 80)
print("  MULTI-STRATEGY QUANTITATIVE SCORECARD (INCLUDING HIGH-FREQUENCY SCALPER)")
print("=" * 80)
for k, v in results.items():
    print(f"{k:<18}: Trades = {v['total_trades']:3d} | WR = {v['win_rate']:4.1f}% | PF = {v['profit_factor']:4.2f} | Net = ${v['net_pl']:>7.2f} | ROI = {v['roi_pct']:>6.1f}%")
print("=" * 80)
print(f"Report written to: {report_path}")
