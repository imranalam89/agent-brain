import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

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

res = sim.run_operator_smart_money_strategy("BTCUSD", b_c, base_risk=5.0, max_target_rr=3.0)

by_h = defaultdict(list)
for t in res["trades"]:
    cl = t.get("closed_at") or t.get("opened_at")
    dt = datetime.strptime(cl, "%Y-%m-%d %H:%M:%S")
    by_h[dt.hour].append(t)

print("Hour | Trades | WR%   | Net PnL   | PF")
print("-" * 40)
for h in sorted(by_h.keys()):
    trades = by_h[h]
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    gp = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    net = gp - gl
    pf = gp / gl if gl else 99.0
    print(f"{h:<4} | {len(trades):<6} | {wr:<5.1f} | ${net:<+9.2f} | {pf:<5.2f}")
