import sys
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

db = DatabaseManager()
sim = MultiStrategyBacktester(db, initial_capital=50.0)

print("Loading Gold (XAUTUSD) candles...")
candles_gold = db.get_latest_candles("XAUTUSD", "15m", limit=25000)
print(f"Loaded {len(candles_gold)} Gold candles.")

print("\nRunning Gold Backtest...")
results_gold = sim.run_all_strategies("XAUTUSD", candles_gold)
print("=== GOLD (XAUTUSD) TOP 5 STRATEGIES ===")
sorted_gold = sorted(results_gold.items(), key=lambda x: x[1]["net_pl"], reverse=True)
for k, s in sorted_gold[:5]:
    print(f"{s['strategy_name'][:50]:<50} | Trades: {s['total_trades']:3d} | WR: {s['win_rate']:4.1f}% | PF: {s['profit_factor']:4.2f} | Net: ${s['net_pl']:+7.2f} | DD: -${s['max_drawdown_usd']:5.2f}")

print("\nLoading Silver (SLVONUSD) candles...")
candles_silver = db.get_latest_candles("SLVONUSD", "15m", limit=25000)
print(f"Loaded {len(candles_silver)} Silver candles.")

print("\nRunning Silver Backtest...")
results_silver = sim.run_all_strategies("SLVONUSD", candles_silver)
print("=== SILVER (SLVONUSD) TOP 5 STRATEGIES ===")
sorted_silver = sorted(results_silver.items(), key=lambda x: x[1]["net_pl"], reverse=True)
for k, s in sorted_silver[:5]:
    print(f"{s['strategy_name'][:50]:<50} | Trades: {s['total_trades']:3d} | WR: {s['win_rate']:4.1f}% | PF: {s['profit_factor']:4.2f} | Net: ${s['net_pl']:+7.2f} | DD: -${s['max_drawdown_usd']:5.2f}")
