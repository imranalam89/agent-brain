import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

def main():
    db = DatabaseManager()
    bt = MultiStrategyBacktester(db, initial_capital=50.0)

    print("Loading candles...")
    g_candles = db.get_latest_candles("XAUTUSD", "15m", limit=30000)
    s_candles = db.get_latest_candles("SLVONUSD", "15m", limit=30000)
    b_candles = db.get_latest_candles("BTCUSD", "15m", limit=30000)
    e_candles = db.get_latest_candles("ETHUSD", "15m", limit=30000)

    print(f"XAUTUSD:  {len(g_candles):,} candles")
    print(f"SLVONUSD: {len(s_candles):,} candles")
    print(f"BTCUSD:   {len(b_candles):,} candles")
    print(f"ETHUSD:   {len(e_candles):,} candles")

    print("\nRunning Gold strategies...")
    g_res = bt.run_all_strategies("XAUTUSD", g_candles)
    print("Running Silver strategies...")
    s_res = bt.run_all_strategies("SLVONUSD", s_candles)
    print("Running BTC strategies...")
    b_res = bt.run_all_strategies("BTCUSD", b_candles)
    print("Running ETH strategies...")
    e_res = bt.run_all_strategies("ETHUSD", e_candles)

    for sym, res in [("GOLD", g_res), ("SILVER", s_res), ("BTC", b_res), ("ETH", e_res)]:
        print(f"\n--- TOP 3 {sym} STRATEGIES ---")
        sorted_s = sorted(res.items(), key=lambda x: x[1]["net_pl"], reverse=True)
        for k, s in sorted_s[:3]:
            print(f"  {k:20s}: Net ${s['net_pl']:+8.2f} ({s['roi_pct']:+6.1f}%) | PF {s['profit_factor']:4.2f} | WR {s['win_rate']:4.1f}% | Trades {s['total_trades']:3d} | DD -${s['max_drawdown_usd']:5.2f}")

    print("\nSimulating Joint Portfolios (4 Assets)...")
    joint = bt.generate_joint_portfolio_results(g_res, s_res, b_res, e_res, 50.0)
    print("\n--- JOINT PORTFOLIO LEADERBOARD ---")
    for k, s in sorted(joint.items(), key=lambda x: x[1]["net_pl"], reverse=True):
        print(f"  {k:22s}: Net ${s['net_pl']:+8.2f} ({s['roi_pct']:+6.1f}%) | PF {s['profit_factor']:4.2f} | WR {s['win_rate']:4.1f}% | Trades {s['total_trades']:3d} | DD -${s['max_drawdown_usd']:5.2f}")

if __name__ == '__main__':
    main()
