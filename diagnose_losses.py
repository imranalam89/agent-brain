import sys
from collections import defaultdict
from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db = DatabaseManager()
sim = MultiStrategyBacktester(db, 50.0)

for sym, rr in [("BTCUSD", 6.0), ("ETHUSD", 4.5), ("XAUTUSD", 20.0), ("SLVONUSD", 20.0)]:
    candles = db.get_latest_candles(sym, "15m", 35000)
    res = sim.run_operator_smart_money_strategy(sym, candles, max_target_rr=rr)
    trades = res["trades"]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    wins = [t for t in trades if t["pnl_usd"] > 0]

    # Hour of losses
    loss_hours = defaultdict(int)
    win_hours = defaultdict(int)
    for t in losses:
        h = int(t["opened_at"][11:13])
        loss_hours[h] += 1
    for t in wins:
        h = int(t["opened_at"][11:13])
        win_hours[h] += 1

    print(f"\n=================== {sym} (Net: +${res['net_pl']}, WR: {res['win_rate']}%, PF: {res['profit_factor']}) ===================")
    print("Hourly Win Rate Breakdown:")
    bad_hours = []
    for h in range(24):
        w = win_hours[h]
        l = loss_hours[h]
        tot = w + l
        if tot >= 5:
            wr = (w / tot) * 100
            flag = "🚨 BAD (<40% WR)" if wr < 40.0 else ("⭐ GREAT (>60% WR)" if wr >= 60.0 else "")
            print(f"  Hour {h:02d}:00 | Trades: {tot:<3} | Wins: {w:<3} | Losses: {l:<3} | WR: {wr:>5.1f}% {flag}")
            if wr < 42.0 and tot >= 10:
                bad_hours.append(h)
    print(f"Candidate Bad Hours to Filter: {bad_hours}")
