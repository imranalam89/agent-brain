import sys
from pathlib import Path

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
e_c = db.get_latest_candles("ETHUSD", "15m", limit=35000)
s_c = db.get_latest_candles("SLVONUSD", "15m", limit=35000)
g_c = db.get_latest_candles("XAUTUSD", "15m", limit=35000)

print("[*] Running operator_smart_money on each symbol...")
b_op = sim.run_operator_smart_money_strategy("BTCUSD", b_c, base_risk=5.0, max_target_rr=6.0)
e_op = sim.run_operator_smart_money_strategy("ETHUSD", e_c, base_risk=5.0, max_target_rr=6.0)
s_op = sim.run_operator_smart_money_strategy("SLVONUSD", s_c, base_risk=5.0, max_target_rr=6.0)
g_op = sim.run_operator_smart_money_strategy("XAUTUSD", g_c, base_risk=5.0, max_target_rr=6.0)

for sym, res in [("BTC", b_op), ("ETH", e_op), ("Silver", s_op), ("Gold", g_op)]:
    print(f"{sym:<8} | Trades: {res['total_trades']:<5} | WR: {res['win_rate']:<5}% | GP: +${res['gross_profit']:<8.2f} | GL: -${res['gross_loss']:<8.2f} | Net: ${res['net_pl']:<+8.2f} | PF: {res['profit_factor']:<5.2f}")
