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

for sym, c_data in [("BTCUSD", b_c), ("ETHUSD", e_c), ("SLVONUSD", s_c), ("XAUTUSD", g_c)]:
    print(f"\n=======================================================")
    print(f"       TESTING ALL STRATEGIES FOR {sym}")
    print(f"=======================================================")
    res = sim.run_all_strategies(sym, c_data)
    # Sort by net_pl descending
    sorted_strats = sorted(res.items(), key=lambda x: x[1].get('net_pl', -9999), reverse=True)
    print(f"{'Key':<22} | {'Trades':<6} | {'WR%':<5} | {'Net P&L ($)':<12} | {'PF':<5} | {'Strategy Name'}")
    print("-" * 95)
    for k, s in sorted_strats[:8]: # top 8
        print(f"{k:<22} | {s['total_trades']:<6} | {s['win_rate']:<5.1f} | ${s['net_pl']:<+11.2f} | {s['profit_factor']:<5.2f} | {s['strategy_name'][:40]}")
