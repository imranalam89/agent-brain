import sys, os
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

db = DatabaseManager()
gold_candles = db.get_latest_candles('XAUTUSD', '15m', limit=25000)
silver_candles = db.get_latest_candles('SLVONUSD', '15m', limit=25000)
tester = MultiStrategyBacktester(db, 50.0)

gold_res = tester.run_all_strategies('XAUTUSD', gold_candles)
silver_res = tester.run_all_strategies('SLVONUSD', silver_candles)

def merge_trades(t1, t2, cap=50.0):
    all_t = t1 + t2
    all_t.sort(key=lambda t: (t.get('closed_at') or t.get('opened_at') or ''))
    c = cap
    peak = cap
    max_dd = 0.0
    eq_curve = [{'timestamp': 0, 'equity': c}]
    for t in all_t:
        pnl = t.get('pnl_usd', 0.0)
        c += pnl
        if c > peak: peak = c
        if peak - c > max_dd: max_dd = peak - c
        cl_time = t.get('closed_at') or t.get('opened_at') or ''
        try: ts = int(datetime.strptime(cl_time, '%Y-%m-%d %H:%M:%S').timestamp())
        except Exception: ts = 0
        eq_curve.append({'timestamp': ts, 'equity': round(c, 2)})
    wins = [t for t in all_t if t.get('pnl_usd', 0.0) > 0]
    losses = [t for t in all_t if t.get('pnl_usd', 0.0) < 0]
    total = len(all_t)
    wr = round(len(wins)/total*100, 1) if total else 0.0
    gp = sum(t.get('pnl_usd', 0.0) for t in wins)
    gl = abs(sum(t.get('pnl_usd', 0.0) for t in losses))
    pf = round(gp/gl, 2) if gl else 99.0
    net = round(c - cap, 2)
    roi = round(net/cap*100, 1)
    return {'net': net, 'roi': roi, 'wr': wr, 'pf': pf, 'total': total, 'dd': round(max_dd, 2)}

pairs = [
    ('Joint Titan', gold_res['apex_pro_5']['trades'], silver_res['silver_titan']['trades']),
    ('Joint Profit Max', gold_res['apex_pro_5']['trades'], silver_res['silver_profit_max']['trades']),
    ('Joint High WR', gold_res['apex_pro_5']['trades'], silver_res['silver_high_wr']['trades']),
    ('Joint Active Scalper', gold_res['active_scalper_5']['trades'], silver_res['active_scalper_5']['trades']),
    ('Joint Stepped', gold_res['apex_stepped']['trades'], silver_res['apex_stepped']['trades'])
]

print("=== JOINT STRATEGY COMBINATIONS ===")
for name, t1, t2 in pairs:
    r = merge_trades(t1, t2, 50.0)
    print(f"{name:<22} | Net: ${r['net']:>8.2f} ({r['roi']:>+6.1f}%) | WR: {r['wr']:4.1f}% | PF: {r['pf']:4.2f} | Trades: {r['total']:3d} | DD: -${r['dd']:5.2f}")
