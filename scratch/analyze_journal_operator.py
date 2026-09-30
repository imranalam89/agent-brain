import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter
from data.database import DatabaseManager

db = DatabaseManager()
trades = db.get_trades(limit=200)
closed = [t for t in trades if t.get("status") == "CLOSED"]
print(f"Total Closed Trades in SQLite Journal: {len(closed)}")

wins = [t for t in closed if float(t.get("pnl_usd", 0)) > 0]
losses = [t for t in closed if float(t.get("pnl_usd", 0)) < 0]
be = [t for t in closed if float(t.get("pnl_usd", 0)) == 0]

gross_win = sum(float(t["pnl_usd"]) for t in wins)
gross_loss = sum(float(t["pnl_usd"]) for t in losses)
net_pnl = sum(float(t.get("pnl_usd", 0)) for t in closed)
win_rate = (len(wins) / len(closed) * 100) if closed else 0

print(f"Wins: {len(wins)} ({win_rate:.1f}%) | Losses: {len(losses)} | Breakeven: {len(be)}")
print(f"Gross Profit: +${gross_win:.2f}")
print(f"Gross Loss:   -${abs(gross_loss):.2f}")
print(f"Net Realized:  ${net_pnl:+.2f}")
print(f"Profit Factor: {(gross_win / abs(gross_loss)):.2f}" if gross_loss != 0 else "N/A")

print("\n=== TOP 10 WINNING TRADES (WHAT WORKED BEST) ===")
for t in sorted(wins, key=lambda x: float(x.get("pnl_usd", 0)), reverse=True)[:10]:
    print(f"{t['symbol']:7s} {t['side']:4s} | +${float(t['pnl_usd']):6.2f} | RR: {t.get('rr_achieved', 0)}R | Reason: {t.get('close_reason')} | Entry: ${float(t.get('entry_price', 0)):,.2f} -> Exit: ${float(t.get('exit_price', 0)):,.2f} | Time: {t.get('opened_at')}")

print("\n=== TOP 10 LOSING TRADES (WHY THEY FAILED) ===")
for t in sorted(losses, key=lambda x: float(x.get("pnl_usd", 0)))[:10]:
    print(f"{t['symbol']:7s} {t['side']:4s} | -${abs(float(t['pnl_usd'])):6.2f} | Reason: {t.get('close_reason')} | Entry: ${float(t.get('entry_price', 0)):,.2f} -> Exit: ${float(t.get('exit_price', 0)):,.2f} | Time: {t.get('opened_at')}")

print("\n=== LOSS PATTERNS BY HOUR (IST) ===")
loss_hours = Counter(t.get("opened_at", "")[11:13] for t in losses if t.get("opened_at"))
for h, cnt in sorted(loss_hours.items(), key=lambda x: x[1], reverse=True):
    print(f"Hour {h}:00 IST: {cnt} losses")

print("\n=== WIN PATTERNS BY HOUR (IST) ===")
win_hours = Counter(t.get("opened_at", "")[11:13] for t in wins if t.get("opened_at"))
for h, cnt in sorted(win_hours.items(), key=lambda x: x[1], reverse=True):
    print(f"Hour {h}:00 IST: {cnt} wins")
