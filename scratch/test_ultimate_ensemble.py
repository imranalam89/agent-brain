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
e_c = db.get_latest_candles("ETHUSD", "15m", limit=35000)
s_c = db.get_latest_candles("SLVONUSD", "15m", limit=35000)
g_c = db.get_latest_candles("XAUTUSD", "15m", limit=35000)

print("[*] Running Optimized Champions per Asset...")
# Gold Champion: 20R/30R Macro Runner
g_strat = sim.run_operator_smart_money_strategy("XAUTUSD", g_c, base_risk=5.0, max_target_rr=20.0, name="👑 Gold Institutional 20R Macro Runner")
# Silver Champion: Apex Profit Maximizer (PF 2.30)
s_strat = sim.run_silver_apex_titan_strategy("SLVONUSD", s_c, tp1_rr=2.4, max_rr=6.0, trail_mult=0.8, min_dist=0.30, dist_pad=0.06, name="👑 Silver Apex Profit Maximizer (Cut 50% @ 2.4R | PF 2.30)")
# BTC Champion: 3.0R Target + Chop Filter (13, 15, 16)
b_strat = sim.run_operator_smart_money_strategy("BTCUSD", b_c, base_risk=5.0, max_target_rr=3.0, name="👑 BTC Institutional Precision Scalper (3.0R Target)")
# ETH Champion: 30R Grandmaster Macro
e_strat = sim.run_operator_smart_money_strategy("ETHUSD", e_c, base_risk=5.0, max_target_rr=30.0, name="💎 ETH Grandmaster 30R Macro Expansion")

print(f"Gold:   {g_strat['total_trades']:<5} trades | WR: {g_strat['win_rate']:<5}% | Net: ${g_strat['net_pl']:<+8.2f} | PF: {g_strat['profit_factor']:<5.2f}")
print(f"Silver: {s_strat['total_trades']:<5} trades | WR: {s_strat['win_rate']:<5}% | Net: ${s_strat['net_pl']:<+8.2f} | PF: {s_strat['profit_factor']:<5.2f}")
print(f"BTC:    {b_strat['total_trades']:<5} trades | WR: {b_strat['win_rate']:<5}% | Net: ${b_strat['net_pl']:<+8.2f} | PF: {b_strat['profit_factor']:<5.2f}")
print(f"ETH:    {e_strat['total_trades']:<5} trades | WR: {e_strat['win_rate']:<5}% | Net: ${e_strat['net_pl']:<+8.2f} | PF: {e_strat['profit_factor']:<5.2f}")

all_trades = g_strat["trades"] + s_strat["trades"] + b_strat["trades"] + e_strat["trades"]
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
print(f"👑 4-ASSET ULTIMATE PROFIT MAXIMIZER ENSEMBLE (Strict $5 Risk | 10-Min Cooldown):")
print(f"   Total Trades:    {len(all_trades)}")
print(f"   Win Rate:        {len(wins)/len(all_trades)*100:.1f}%")
print(f"   Profit Factor:   {pf:.2f}")
print(f"   Gross Profit:    +${gp:,.2f}")
print(f"   Gross Loss:      -${gl:,.2f}")
print(f"   Real Net P&L:    +${net:,.2f} USD (+₹{net*90:,.0f} INR)")
print(f"   Max Drawdown:    -${max_dd:.2f}")
print(f"================================================================================")
