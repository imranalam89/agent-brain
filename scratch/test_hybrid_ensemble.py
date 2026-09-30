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

g_res = sim.run_all_strategies("XAUTUSD", g_c)
s_res = sim.run_all_strategies("SLVONUSD", s_c)
b_res = sim.run_all_strategies("BTCUSD", b_c)
e_res = sim.run_all_strategies("ETHUSD", e_c)

print("\n--- INDIVIDUAL CHAMPION SEARCH ---")
for sym, r_dict in [("Gold", g_res), ("Silver", s_res), ("BTC", b_res), ("ETH", e_res)]:
    best_k = max(r_dict.keys(), key=lambda k: r_dict[k].get("net_pl", -9999))
    s = r_dict[best_k]
    print(f"{sym:<7} Best: {best_k:<20} | Trades: {s['total_trades']:<5} | WR: {s['win_rate']:<5}% | Net: ${s['net_pl']:<+8.2f} | PF: {s['profit_factor']:<5.2f}")

# Joint Portfolio with Champions
# Gold: mega_runner_20r ($841.10)
# Silver: silver_profit_max ($466.43)
# ETH: grandmaster_30r ($756.67)
# BTC: operator_smart_money ($497.15)
g_trades = g_res["mega_runner_20r"]["trades"]
s_trades = s_res["silver_profit_max"]["trades"]
e_trades = e_res["grandmaster_30r"]["trades"]
b_trades = b_res["operator_smart_money"]["trades"]

# Let's merge them
all_trades = g_trades + s_trades + e_trades + b_trades
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
print(f"👑 HYBRID CHAMPION PORTFOLIO (Best Strategy per Asset | Strict $5 Risk):")
print(f"   Total Trades:    {len(all_trades)}")
print(f"   Win Rate:        {len(wins)/len(all_trades)*100:.1f}%")
print(f"   Profit Factor:   {pf:.2f}")
print(f"   Gross Profit:    +${gp:,.2f}")
print(f"   Gross Loss:      -${gl:,.2f}")
print(f"   Real Net P&L:    +${net:,.2f} USD (+₹{net*90:,.0f} INR)")
print(f"   Max Drawdown:    -${max_dd:.2f}")
print(f"================================================================================")
