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
b_op = sim.run_operator_smart_money_strategy("BTCUSD", b_c, base_risk=5.0)
e_op = sim.run_operator_smart_money_strategy("ETHUSD", e_c, base_risk=5.0)
s_op = sim.run_operator_smart_money_strategy("SLVONUSD", s_c, base_risk=5.0)
g_op = sim.run_operator_smart_money_strategy("XAUTUSD", g_c, base_risk=5.0)

for sym, res in [("BTC", b_op), ("ETH", e_op), ("Silver", s_op), ("Gold", g_op)]:
    print(f"{sym:<8} | Trades: {res['total_trades']:<5} | WR: {res['win_rate']:<5}% | GP: +${res['gross_profit']:<8.2f} | GL: -${res['gross_loss']:<8.2f} | Net: ${res['net_pl']:<+8.2f} | PF: {res['profit_factor']:<5.2f}")

all_trades = b_op["trades"] + e_op["trades"] + s_op["trades"] + g_op["trades"]
all_trades.sort(key=lambda t: (t.get("closed_at") or t.get("opened_at") or ""))

capital = 50.0
peak = 50.0
max_dd = 0.0
for t in all_trades:
    pnl = t.get("pnl_usd", 0.0)
    capital += pnl
    if capital > peak: peak = capital
    dd = peak - capital
    if dd > max_dd: max_dd = dd

wins = [t for t in all_trades if t.get("pnl_usd", 0.0) > 0]
losses = [t for t in all_trades if t.get("pnl_usd", 0.0) < 0]
gp = sum(t.get("pnl_usd", 0.0) for t in wins)
gl = abs(sum(t.get("pnl_usd", 0.0) for t in losses))
net = capital - 50.0
pf = gp / gl if gl else 99.0

print(f"\n================================================================================")
print(f"👑 4-ASSET OPERATOR APEX SUITE:")
print(f"   Total Trades:    {len(all_trades)}")
print(f"   Win Rate:        {len(wins)/len(all_trades)*100:.1f}%")
print(f"   Profit Factor:   {pf:.2f}")
print(f"   Gross Profit:    +${gp:,.2f}")
print(f"   Gross Loss:      -${gl:,.2f}")
print(f"   Real Net P&L:    +${net:,.2f} USD (+₹{net*90:,.0f} INR)")
print(f"   Max Drawdown:    -${max_dd:.2f}")
print(f"================================================================================")
