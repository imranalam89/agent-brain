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

print("--- Testing BTC parameter optimizations ---")
for min_stop in [160.0, 200.0, 250.0, 300.0]:
    for pad in [45.0, 80.0, 120.0]:
        for max_rr in [4.0, 6.0, 10.0, 15.0, 20.0]:
            res = sim.run_operator_smart_money_strategy(
                "BTCUSD", b_c,
                base_risk=5.0,
                min_stop=min_stop,
                buffer_pad=pad,
                max_target_rr=max_rr
            )
            net = res['net_pl']
            if net > 550.0:
                print(f"MinStop: {min_stop} | Pad: {pad} | MaxRR: {max_rr} -> Trades: {res['total_trades']}, WR: {res['win_rate']}%, Net: ${net:<+8.2f}, PF: {res['profit_factor']:.2f}")
