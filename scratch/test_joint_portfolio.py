import sys, os
from datetime import datetime
from pathlib import Path

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
gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=25000)
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)
print(f"Loaded {len(gold_candles)} Gold candles and {len(silver_candles)} Silver candles.")

tester = MultiStrategyBacktester(db, 50.0)

# 1. Run Gold strategies
gold_res = tester.run_all_strategies("XAUTUSD", gold_candles)

# 2. Run Silver strategies
silver_res = tester.run_all_strategies("SLVONUSD", silver_candles)

print("\n--- GOLD BEST ---")
for k in ["apex_pro_5", "active_scalper_5"]:
    s = gold_res[k]
    print(f"{k:18} | Net: ${s['net_pl']:+7.2f} | WR: {s['win_rate']:4.1f}% | PF: {s['profit_factor']:4.2f} | Trades: {s['total_trades']:3d} | DD: -${s['max_drawdown_usd']:5.2f}")

print("\n--- SILVER BEST ---")
for k in ["silver_titan", "silver_profit_max", "active_scalper_5"]:
    s = silver_res[k]
    print(f"{k:18} | Net: ${s['net_pl']:+7.2f} | WR: {s['win_rate']:4.1f}% | PF: {s['profit_factor']:4.2f} | Trades: {s['total_trades']:3d} | DD: -${s['max_drawdown_usd']:5.2f}")

def merge_joint_trades(trades1, trades2, initial_capital=50.0):
    all_trades = trades1 + trades2
    # Sort strictly by exit time (or entry time)
    all_trades.sort(key=lambda t: (t.get("closed_at") or t.get("opened_at") or ""))
    
    capital = initial_capital
    peak = initial_capital
    max_dd = 0.0
    equity_curve = [{"timestamp": 0, "equity": capital}]
    
    for t in all_trades:
        pnl = t.get("pnl_usd", 0.0)
        capital += pnl
        if capital > peak:
            peak = capital
        dd = peak - capital
        if dd > max_dd:
            max_dd = dd
        # parse timestamp
        cl_time = t.get("closed_at") or t.get("opened_at") or ""
        try:
            ts = int(datetime.strptime(cl_time, "%Y-%m-%d %H:%M:%S").timestamp())
        except Exception:
            ts = 0
        equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})
        
    wins = [t for t in all_trades if t.get("pnl_usd", 0.0) > 0]
    losses = [t for t in all_trades if t.get("pnl_usd", 0.0) < 0]
    total = len(all_trades)
    win_rate = round(len(wins)/total*100, 1) if total else 0.0
    gp = sum(t.get("pnl_usd", 0.0) for t in wins)
    gl = abs(sum(t.get("pnl_usd", 0.0) for t in losses))
    pf = round(gp/gl, 2) if gl else 99.0
    net = round(capital - initial_capital, 2)
    roi = round(net / initial_capital * 100, 1)
    
    return {
        "initial_capital": initial_capital,
        "final_capital": round(capital, 2),
        "net_pl": net,
        "roi_pct": roi,
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "profit_factor": pf,
        "gross_profit": round(gp, 2),
        "gross_loss": round(gl, 2),
        "max_drawdown_usd": round(max_dd, 2),
        "equity_curve": equity_curve,
        "trades": all_trades
    }

print("\n================ JOINT PORTFOLIO RESULTS ================")
# Joint Option 1: Institutional Apex Titan (Gold Apex Pro $5 + Silver Apex Titan $5)
joint_titan = merge_joint_trades(gold_res["apex_pro_5"]["trades"], silver_res["silver_titan"]["trades"], 50.0)
print(f"1. 💎 JOINT APEX TITAN (Gold Apex Pro + Silver Titan):")
print(f"   Net P&L:      ${joint_titan['net_pl']:+.2f} ({joint_titan['roi_pct']:+.1f}% ROI on $50)")
print(f"   Win Rate:     {joint_titan['win_rate']}% ({joint_titan['wins']} wins, {joint_titan['losses']} losses)")
print(f"   Profit Factor:{joint_titan['profit_factor']}")
print(f"   Total Trades: {joint_titan['total_trades']}")
print(f"   Max Drawdown: -${joint_titan['max_drawdown_usd']:.2f}")

# Joint Option 2: Profit Maximizer (Gold Apex Pro $5 + Silver Profit Maximizer $5)
joint_max = merge_joint_trades(gold_res["apex_pro_5"]["trades"], silver_res["silver_profit_max"]["trades"], 50.0)
print(f"\n2. 👑 JOINT PROFIT MAXIMIZER (Gold Apex Pro + Silver Profit Max):")
print(f"   Net P&L:      ${joint_max['net_pl']:+.2f} ({joint_max['roi_pct']:+.1f}% ROI on $50)")
print(f"   Win Rate:     {joint_max['win_rate']}% ({joint_max['wins']} wins, {joint_max['losses']} losses)")
print(f"   Profit Factor:{joint_max['profit_factor']}")
print(f"   Total Trades: {joint_max['total_trades']}")
print(f"   Max Drawdown: -${joint_max['max_drawdown_usd']:.2f}")

# Joint Option 3: Active Intraday Scalper (Gold Active Scalper + Silver Active Scalper)
joint_scalper = merge_joint_trades(gold_res["active_scalper_5"]["trades"], silver_res["active_scalper_5"]["trades"], 50.0)
print(f"\n3. ⚡ JOINT ACTIVE INTRADAY SCALPER (Gold + Silver Scalper | Daily 6-10 Trades):")
print(f"   Net P&L:      ${joint_scalper['net_pl']:+.2f} ({joint_scalper['roi_pct']:+.1f}% ROI on $50)")
print(f"   Win Rate:     {joint_scalper['win_rate']}% ({joint_scalper['wins']} wins, {joint_scalper['losses']} losses)")
print(f"   Profit Factor:{joint_scalper['profit_factor']}")
print(f"   Total Trades: {joint_scalper['total_trades']}")
print(f"   Max Drawdown: -${joint_scalper['max_drawdown_usd']:.2f}")
