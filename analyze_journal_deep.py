import sqlite3
from collections import defaultdict

conn = sqlite3.connect("data/trading_brain.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT * FROM trades")
rows = cursor.fetchall()
print(f"Total Trades in Journal: {len(rows)}")

if rows:
    print("\nColumns:", list(rows[0].keys()))

trades = [dict(r) for r in rows]

wins = [t for t in trades if (t.get("pnl_usd") or 0) > 0]
losses = [t for t in trades if (t.get("pnl_usd") or 0) < 0]
tot_pnl = sum((t.get("pnl_usd") or 0) for t in trades)

print(f"\nOverall Win Rate: {len(wins)/len(trades)*100:.1f}%")
print(f"Total PnL: ${tot_pnl:,.2f}")
if wins:
    print(f"Avg Win: ${sum(t['pnl_usd'] for t in wins)/len(wins):.2f}")
if losses:
    print(f"Avg Loss: ${sum(t['pnl_usd'] for t in losses)/len(losses):.2f}")

# Group by symbol
by_sym = defaultdict(list)
for t in trades:
    by_sym[t.get("symbol")].append(t)

print("\n--- Performance by Symbol ---")
for sym, t_list in sorted(by_sym.items()):
    w = [t for t in t_list if (t.get("pnl_usd") or 0) > 0]
    l = [t for t in t_list if (t.get("pnl_usd") or 0) < 0]
    gp = sum(t["pnl_usd"] for t in w)
    gl = abs(sum(t["pnl_usd"] for t in l))
    pf = gp / gl if gl > 0 else 99.0
    net = sum((t.get("pnl_usd") or 0) for t in t_list)
    wr = len(w) / len(t_list) * 100
    print(f"{str(sym):<10} | Trades: {len(t_list):<4} | WR: {wr:>5.1f}% | PF: {pf:>4.2f} | Net: ${net:>8.2f}")

# Group by close_reason
by_cr = defaultdict(list)
for t in trades:
    by_cr[t.get("close_reason")].append(t)

print("\n--- Performance by Close Reason ---")
for cr, t_list in sorted(by_cr.items(), key=lambda x: len(x[1]), reverse=True):
    w = [t for t in t_list if (t.get("pnl_usd") or 0) > 0]
    net = sum((t.get("pnl_usd") or 0) for t in t_list)
    wr = len(w) / len(t_list) * 100
    print(f"{str(cr):<22} | Trades: {len(t_list):<4} | WR: {wr:>5.1f}% | Net: ${net:>8.2f}")

# Group by hour of opened_at
by_hour = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
for t in trades:
    op = t.get("opened_at") or ""
    if len(op) >= 13:
        h = int(op[11:13])
        pnl = t.get("pnl_usd") or 0.0
        by_hour[h]["pnl"] += pnl
        by_hour[h]["trades"] += 1
        if pnl > 0:
            by_hour[h]["wins"] += 1

print("\n--- Performance by Hour (UTC) ---")
for h in range(24):
    d = by_hour[h]
    if d["trades"] > 0:
        wr = d["wins"] / d["trades"] * 100
        print(f"Hour {h:02d}:00 | Trades: {d['trades']:<3} | WR: {wr:>5.1f}% | Net: ${d['pnl']:>8.2f}")

# Group by conviction_stars
by_stars = defaultdict(list)
for t in trades:
    by_stars[t.get("conviction_stars")].append(t)

print("\n--- Performance by Conviction Stars ---")
for stars, t_list in sorted(by_stars.items(), key=lambda x: str(x[0])):
    w = [t for t in t_list if (t.get("pnl_usd") or 0) > 0]
    net = sum((t.get("pnl_usd") or 0) for t in t_list)
    wr = len(w) / len(t_list) * 100
    print(f"Stars {str(stars):<5} | Trades: {len(t_list):<4} | WR: {wr:>5.1f}% | Net: ${net:>8.2f}")

conn.close()
