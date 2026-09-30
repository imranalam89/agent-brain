import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

db = DatabaseManager()
sim = MultiStrategyBacktester(db, initial_capital=50.0)
b_c = db.get_latest_candles("BTCUSD", "15m", limit=35000)

print("--- BTC Target R:R Comparison ---")
for rr in [3.0, 4.5, 6.0, 10.0, 15.0, 20.0, 30.0]:
    res = sim.run_operator_smart_money_strategy("BTCUSD", b_c, base_risk=5.0, max_target_rr=rr)
    print(f"Target {rr:<4}R | Trades: {res['total_trades']:<5} | WR: {res['win_rate']:<5}% | Net: ${res['net_pl']:<+8.2f} | PF: {res['profit_factor']:<5.2f}")
