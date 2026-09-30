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

res = sim.run_operator_smart_money_strategy("BTCUSD", b_c, base_risk=5.0, max_target_rr=3.0)

# Filter out trades opened during chop hours (13, 15, 16, 17, 18)
filtered_trades = []
for t in res["trades"]:
    op = t.get("opened_at")
    dt = datetime.strptime(op, "%Y-%m-%d %H:%M:%S")
    if dt.hour in (13, 15, 16, 17, 18):
        continue
    filtered_trades.append(t)

wins = [t for t in filtered_trades if t["pnl_usd"] > 0]
losses = [t for t in filtered_trades if t["pnl_usd"] < 0]
wr = len(wins)/len(filtered_trades)*100 if filtered_trades else 0
gp = sum(t["pnl_usd"] for t in wins)
gl = abs(sum(t["pnl_usd"] for t in losses))
net = gp - gl
pf = gp / gl if gl else 99.0

print(f"BTC FILTERED (avoiding chop 13, 15-18):")
print(f"Trades: {len(filtered_trades)} | WR: {wr:.1f}% | Gross+: +${gp:,.2f} | Gross-: -${gl:,.2f} | Net: ${net:<+8.2f} | PF: {pf:.2f}")
