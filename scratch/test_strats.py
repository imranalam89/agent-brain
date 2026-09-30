import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

db = DatabaseManager()
sim = MultiStrategyBacktester(db)
btc_c = db.get_latest_candles("BTCUSD", "15m", limit=35000)
eth_c = db.get_latest_candles("ETHUSD", "15m", limit=35000)
gold_c = db.get_latest_candles("XAUTUSD", "15m", limit=35000)
silv_c = db.get_latest_candles("SLVONUSD", "15m", limit=35000)

print("=== BTC STRATEGIES ===")
b_res = sim.run_all_strategies("BTCUSD", btc_c)
for k, v in sorted(b_res.items(), key=lambda x: x[1]["net_pl"], reverse=True):
    print(f"{k:20s} | Net: ${v['net_pl']:8.2f} | WR: {v['win_rate']:5.1f}% | PF: {v['profit_factor']:4.2f} | Trades: {v['total_trades']}")

print("\n=== ETH STRATEGIES ===")
e_res = sim.run_all_strategies("ETHUSD", eth_c)
for k, v in sorted(e_res.items(), key=lambda x: x[1]["net_pl"], reverse=True):
    print(f"{k:20s} | Net: ${v['net_pl']:8.2f} | WR: {v['win_rate']:5.1f}% | PF: {v['profit_factor']:4.2f} | Trades: {v['total_trades']}")

print("\n=== GOLD STRATEGIES ===")
g_res = sim.run_all_strategies("XAUTUSD", gold_c)
for k, v in sorted(g_res.items(), key=lambda x: x[1]["net_pl"], reverse=True):
    print(f"{k:20s} | Net: ${v['net_pl']:8.2f} | WR: {v['win_rate']:5.1f}% | PF: {v['profit_factor']:4.2f} | Trades: {v['total_trades']}")

print("\n=== SILVER STRATEGIES ===")
s_res = sim.run_all_strategies("SLVONUSD", silv_c)
for k, v in sorted(s_res.items(), key=lambda x: x[1]["net_pl"], reverse=True):
    print(f"{k:20s} | Net: ${v['net_pl']:8.2f} | WR: {v['win_rate']:5.1f}% | PF: {v['profit_factor']:4.2f} | Trades: {v['total_trades']}")
