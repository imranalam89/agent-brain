import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

def audit_crypto():
    db = DatabaseManager()
    bt = MultiStrategyBacktester(db, initial_capital=50.0)

    btc_candles = db.get_latest_candles("BTCUSD", "15m", limit=30000)
    eth_candles = db.get_latest_candles("ETHUSD", "15m", limit=30000)

    print(f"Loaded {len(btc_candles):,} BTC candles and {len(eth_candles):,} ETH candles.")

    # Run all strategies on BTC and ETH
    btc_res = bt.run_all_strategies("BTCUSD", btc_candles)
    eth_res = bt.run_all_strategies("ETHUSD", eth_candles)

    for sym, res, candles in [("BTCUSD", btc_res, btc_candles), ("ETHUSD", eth_res, eth_candles)]:
        print(f"\n=======================================================")
        print(f"AUDITING STRATEGY METRICS ON {sym}")
        print(f"=======================================================")
        for strat_name, s in sorted(res.items(), key=lambda x: x[1]["net_pl"], reverse=True):
            print(f"[{strat_name:<18}] Net: ${s['net_pl']:+8.2f} ({s['roi_pct']:+6.1f}%) | PF: {s['profit_factor']:4.2f} | WR: {s['win_rate']:4.1f}% | Trades: {s['total_trades']:3d} | DD: -${s['max_drawdown_usd']:5.2f}")

        # Deep dive into session_vwap (the highest win rate strategy)
        vwap_trades = res["session_vwap"]["trades"]
        print(f"\nDeep Dive on {sym} session_vwap ({len(vwap_trades)} trades):")
        wins = [t for t in vwap_trades if t["pnl_usd"] > 0]
        losses = [t for t in vwap_trades if t["pnl_usd"] < 0]
        print(f"  Wins: {len(wins)} ({len(wins)/len(vwap_trades)*100:.1f}%) | Losses: {len(losses)}")
        print(f"  Avg Win: ${sum(t['pnl_usd'] for t in wins)/len(wins):.2f} | Avg Loss: ${abs(sum(t['pnl_usd'] for t in losses))/len(losses):.2f}")

        # Check hour distribution of wins and losses
        hour_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})
        for t in vwap_trades:
            ts = t.get("opened_at", "")
            if len(ts) >= 13:
                hr = int(ts[11:13])
                p = t["pnl_usd"]
                hour_stats[hr]["pnl"] += p
                if p > 0:
                    hour_stats[hr]["wins"] += 1
                else:
                    hour_stats[hr]["losses"] += 1

        print("  Hourly Performance (Top 5 Hours by Net PnL):")
        sorted_hrs = sorted(hour_stats.items(), key=lambda x: x[1]["pnl"], reverse=True)
        for hr, h in sorted_hrs[:5]:
            total_h = h["wins"] + h["losses"]
            wr_h = (h["wins"] / total_h * 100) if total_h else 0
            print(f"    Hour {hr:02d}:00 UTC -> Net ${h['pnl']:+6.2f} | WR {wr_h:4.1f}% ({h['wins']}/{total_h} trades)")

        worst_hrs = sorted(hour_stats.items(), key=lambda x: x[1]["pnl"])
        print("  Hourly Performance (Worst 3 Hours):")
        for hr, h in worst_hrs[:3]:
            total_h = h["wins"] + h["losses"]
            wr_h = (h["wins"] / total_h * 100) if total_h else 0
            print(f"    Hour {hr:02d}:00 UTC -> Net ${h['pnl']:+6.2f} | WR {wr_h:4.1f}% ({h['wins']}/{total_h} trades)")

if __name__ == '__main__':
    audit_crypto()
