import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

db = DatabaseManager()
simulator = MultiStrategyBacktester(db, initial_capital=50.0)

gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=30000)
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=30000)

print("--- TESTING SILVER PROFIT MAX TUNINGS ---")
best_s_results = []
for tp1 in [1.8, 2.0, 2.2, 2.4]:
    for max_rr in [4.5, 5.0, 5.5, 6.0]:
        for trail in [0.8, 1.0, 1.2]:
            for min_d in [0.28, 0.30, 0.35]:
                r = simulator.run_silver_apex_titan_strategy(
                    "SLVONUSD", silver_candles,
                    tp1_rr=tp1, max_rr=max_rr, trail_mult=trail, min_dist=min_d, dist_pad=0.06,
                    name=f"Silver Test (TP1={tp1}, MaxRR={max_rr}, Trail={trail}, MinD={min_d})"
                )
                best_s_results.append((tp1, max_rr, trail, min_d, r))

best_s_results.sort(key=lambda x: x[4]["net_pl"], reverse=True)
print("\nTop 5 Silver Profit Boosters:")
for tp1, max_rr, trail, min_d, r in best_s_results[:5]:
    print(f"TP1: {tp1} MaxRR: {max_rr} Trail: {trail} MinD: {min_d} | Net: ${r['net_pl']:+8.2f} ({r['roi_pct']:+6.1f}%) | PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:4.1f}% | Trades: {r['total_trades']:3d} | DD: -${r['max_drawdown_usd']:5.2f}")

print("\n--- TESTING GOLD APEX PRO TUNINGS ---")
best_g_results = []
for tp1_h in [2.0, 2.2, 2.5, 2.8]:
    for min_rr_h in [4.5, 5.0, 5.5, 6.0]:
        for tr_h in [1.0, 1.2, 1.5]:
            for del_th in [0.03, 0.035, 0.04]:
                r = simulator.run_apex_master_strategy(
                    "XAUTUSD", gold_candles,
                    name=f"Gold Test (TP1={tp1_h}, MaxRR={min_rr_h}, Trail={tr_h}, Del={del_th})",
                    tp1_high=tp1_h, tp1_mod=1.6, min_rr_high=min_rr_h, min_rr_mod=2.8,
                    trail_high=tr_h, trail_mod=1.2, del_th=del_th, filter_session_chop=True,
                    use_stepped_risk=False, base_risk=5.0
                )
                best_g_results.append((tp1_h, min_rr_h, tr_h, del_th, r))

best_g_results.sort(key=lambda x: x[4]["net_pl"], reverse=True)
print("\nTop 5 Gold Profit Boosters:")
for tp1_h, min_rr_h, tr_h, del_th, r in best_g_results[:5]:
    print(f"TP1_H: {tp1_h} MaxRR_H: {min_rr_h} Trail_H: {tr_h} Del: {del_th} | Net: ${r['net_pl']:+8.2f} ({r['roi_pct']:+6.1f}%) | PF: {r['profit_factor']:4.2f} | WR: {r['win_rate']:4.1f}% | Trades: {r['total_trades']:3d} | DD: -${r['max_drawdown_usd']:5.2f}")

# Joint Test with Top 1
best_g = best_g_results[0][4]
best_s = best_s_results[0][4]

joint = simulator.generate_joint_portfolio_results({"best_g": best_g}, {"best_s": best_s}, 50.0)
merge = list(joint.values())[0] if joint else {}

# Merge the best pair directly
all_t = [dict(t) for t in best_g["trades"]] + [dict(t) for t in best_s["trades"]]
all_t.sort(key=lambda x: x.get("closed_at") or "")
cap = 50.0
peak = 50.0
m_dd = 0.0
for t in all_t:
    cap += t.get("pnl_usd", 0.0)
    if cap > peak: peak = cap
    dd = peak - cap
    if dd > m_dd: m_dd = dd
wins = [t for t in all_t if t.get("pnl_usd", 0.0) > 0]
losses = [t for t in all_t if t.get("pnl_usd", 0.0) < 0]
gp = sum(t.get("pnl_usd", 0.0) for t in wins)
gl = abs(sum(t.get("pnl_usd", 0.0) for t in losses))
net = round(cap - 50.0, 2)
roi = round(net / 50.0 * 100, 1)
pf = round(gp / gl, 2)
wr = round(len(wins) / len(all_t) * 100, 1)

print("\n==================================================================")
print(f"👑 ENHANCED JOINT PROFIT MAXIMIZER RESULT:")
print(f"  Net P&L:      ${net:+8.2f} ({roi:+6.1f}% ROI)")
print(f"  Profit Factor: {pf:4.2f}")
print(f"  Win Rate:      {wr:4.1f}% ({len(wins)} Wins / {len(losses)} Losses)")
print(f"  Total Trades:  {len(all_t):3d}")
print(f"  Max Drawdown: -${m_dd:5.2f}")
print("==================================================================")
