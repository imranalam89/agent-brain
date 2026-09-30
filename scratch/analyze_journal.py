import sys
import sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

db_path = Path("data/trading_brain.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT * FROM trades")
trades = [dict(r) for r in c.fetchall()]

print(f"Total trades in DB: {len(trades)}")

# Breakdown by strategy_name
by_strat = defaultdict(list)
by_symbol = defaultdict(list)
by_reason = defaultdict(list)
by_hour = defaultdict(list)
by_dow = defaultdict(list)

for t in trades:
    strat = t.get("strategy_name") or "UNKNOWN"
    by_strat[strat].append(t)
    sym = t.get("symbol") or "UNKNOWN"
    by_symbol[sym].append(t)
    reason = t.get("close_reason") or "UNKNOWN"
    by_reason[reason].append(t)
    
    cl_time = t.get("closed_at") or t.get("opened_at") or ""
    try:
        dt = datetime.strptime(cl_time, "%Y-%m-%d %H:%M:%S")
        by_hour[dt.hour].append(t)
        by_dow[dt.strftime("%A")].append(t)
    except Exception:
        pass

def print_stats(title, group_dict):
    print(f"\n{'='*75}\n{title}\n{'='*75}")
    print(f"{'Category':<40} | {'Trades':<6} | {'WR%':<5} | {'Gross+':<9} | {'Gross-':<9} | {'Net P&L':<10} | {'PF':<5}")
    print("-" * 95)
    for cat, t_list in sorted(group_dict.items(), key=lambda x: sum(t.get('pnl_usd', 0) for t in x[1]), reverse=True):
        total = len(t_list)
        wins = [t for t in t_list if (t.get('pnl_usd') or 0) > 0]
        losses = [t for t in t_list if (t.get('pnl_usd') or 0) < 0]
        wr = len(wins) / total * 100 if total else 0
        gp = sum(t.get('pnl_usd') for t in wins)
        gl = abs(sum(t.get('pnl_usd') for t in losses))
        net = gp - gl
        pf = gp / gl if gl else (99.0 if gp else 0.0)
        cat_str = str(cat)
        print(f"{cat_str[:40]:<40} | {total:<6} | {wr:<5.1f} | {gp:<9.2f} | {gl:<9.2f} | {net:<+10.2f} | {pf:<5.2f}")

print_stats("PERFORMANCE BY STRATEGY IN JOURNAL", by_strat)
print_stats("PERFORMANCE BY SYMBOL", by_symbol)
print_stats("PERFORMANCE BY CLOSE REASON", by_reason)
print_stats("PERFORMANCE BY HOUR (UTC/DB TIME)", by_hour)
print_stats("PERFORMANCE BY DAY OF WEEK", by_dow)
