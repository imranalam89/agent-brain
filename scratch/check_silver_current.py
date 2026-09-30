import sys, os
sys.path.insert(0, os.path.abspath("."))
from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

db = DatabaseManager()
candles = db.get_recent_candles('SLVONUSD', 20000)
tester = MultiStrategyBacktester(db, 50.0)
res = tester.run_all_strategies('SLVONUSD', candles)
print("=== SILVER STRATEGIES COMPARISON ===")
for k, v in res.items():
    print(f"{k:20} | WR: {v['win_rate']:5.1f}% | PF: {v['profit_factor']:4.2f} | Net: ${v['net_pl']:7.2f} | Trades: {v['total_trades']:3d} | DD: ${v['max_drawdown_usd']:5.2f}")
