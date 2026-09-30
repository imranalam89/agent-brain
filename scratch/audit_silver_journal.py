import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

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
sim = MultiStrategyBacktester(db, initial_capital=50.0)
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)

print(f"Loaded {len(silver_candles)} Silver candles.")

# Run all strategies on Silver to compare
results = sim.run_all_strategies("SLVONUSD", silver_candles)

print("\n==================================================================")
print("             CURRENT SILVER (SLVONUSD) STRATEGY AUDIT             ")
print("==================================================================")
for k, s in sorted(results.items(), key=lambda x: x[1]["net_pl"], reverse=True):
    print(f"[{k:<18}] Net: ${s['net_pl']:+7.2f} | PF: {s['profit_factor']:4.2f} | WR: {s['win_rate']:4.1f}% | Trades: {s['total_trades']:3d} | DD: -${s['max_drawdown_usd']:5.2f}")

# Detailed Post-Mortem of Apex Pro & Footprint Absorption
for strat_key in ["apex_pro_5", "fprint_absorption"]:
    strat = results[strat_key]
    trades = strat["trades"]
    print(f"\n--- Detailed Post-Mortem for: {strat['strategy_name']} ---")
    
    # Hour breakdown
    hour_pnl = defaultdict(float)
    hour_counts = defaultdict(int)
    hour_wins = defaultdict(int)
    
    # Reason breakdown
    reason_pnl = defaultdict(float)
    reason_counts = defaultdict(int)

    # MAE / MFE proxy
    for t in trades:
        h = int(t.get("opened_at", " 12:00").split(" ")[1].split(":")[0])
        pnl = t.get("pnl_usd", 0.0)
        hour_pnl[h] += pnl
        hour_counts[h] += 1
        if pnl > 0: hour_wins[h] += 1
        
        reason = t.get("close_reason", "OTHER")
        reason_pnl[reason] += pnl
        reason_counts[reason] += 1

    print("\nHourly Profitability Breakdown (UTC):")
    for h in sorted(hour_pnl.keys()):
        cnt = hour_counts[h]
        wr = (hour_wins[h] / cnt * 100) if cnt else 0
        print(f"  {h:02d}:00 UTC -> Net: ${hour_pnl[h]:+6.2f} | Trades: {cnt:2d} | Win Rate: {wr:4.1f}%")

    print("\nExit Reason Breakdown:")
    for r in sorted(reason_counts.keys(), key=lambda x: reason_pnl[x], reverse=True):
        print(f"  {r:<35} -> Count: {reason_counts[r]:3d} | PnL: ${reason_pnl[r]:+7.2f}")
