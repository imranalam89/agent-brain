import json
import sys
from collections import defaultdict
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

with open("reports/agent_journal.html", "r", encoding="utf-8") as f:
    text = f.read()

prefix = "const trades = "
start = text.find(prefix) + len(prefix)
end = text.find(";\n    let journalFilter", start)
trades = json.loads(text[start:end])

# Chronological order
trades_chrono = sorted(trades, key=lambda t: t.get("closed_at") or t.get("opened_at") or "")

max_win_streak = 0
max_loss_streak = 0
cur_win_streak = 0
cur_loss_streak = 0
cur_win_pnl = 0.0
cur_loss_pnl = 0.0
max_win_pnl = 0.0
max_loss_pnl = 0.0

for t in trades_chrono:
    pnl = t.get("pnl_usd", 0.0)
    if pnl > 0:
        cur_win_streak += 1
        cur_win_pnl += pnl
        if cur_win_streak > max_win_streak:
            max_win_streak = cur_win_streak
            max_win_pnl = cur_win_pnl
        cur_loss_streak = 0
        cur_loss_pnl = 0.0
    elif pnl < 0:
        cur_loss_streak += 1
        cur_loss_pnl += pnl
        if cur_loss_streak > max_loss_streak:
            max_loss_streak = cur_loss_streak
            max_loss_pnl = cur_loss_pnl
        cur_win_streak = 0
        cur_win_pnl = 0.0

# Current active streak
last_t = trades_chrono[-1]
is_last_win = last_t.get("pnl_usd", 0) > 0
active_streak_count = 0
active_streak_pnl = 0.0
for t in reversed(trades_chrono):
    p = t.get("pnl_usd", 0)
    if (p > 0) == is_last_win:
        active_streak_count += 1
        active_streak_pnl += p
    else:
        break

streak_label = "Wins" if is_last_win else "Losses"
print(f"Max Win Streak:  {max_win_streak} in a row (+${max_win_pnl:.2f})")
print(f"Max Loss Streak: {max_loss_streak} in a row (-${abs(max_loss_pnl):.2f})")
print(f"Current Streak:  {active_streak_count} {streak_label} (${active_streak_pnl:+.2f})")

# Hourly breakdown
hourly = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0.0})
for t in trades:
    dt_str = t.get("opened_at") or ""
    if len(dt_str) >= 13:
        hour = int(dt_str[11:13])
        pnl = t.get("pnl_usd", 0.0)
        hourly[hour]["count"] += 1
        if pnl > 0: hourly[hour]["wins"] += 1
        hourly[hour]["pnl"] += pnl

print("\n--- HOURLY PROFITABILITY (UTC) ---")
sorted_hours = sorted(hourly.items(), key=lambda x: x[0])
for h, d in sorted_hours:
    wr = d["wins"] / d["count"] * 100 if d["count"] > 0 else 0
    bar = "█" * int(abs(d['pnl']) / 5)
    sign = "+" if d['pnl'] > 0 else "-"
    print(f"Hour {h:02d}:00 UTC -> PnL: ${d['pnl']:+7.2f} | Trades: {d['count']:2d} | Win Rate: {wr:5.1f}% | {bar}")

# Day of week breakdown
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
dow_stats = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0.0})
for t in trades:
    dt_str = t.get("opened_at") or ""
    if len(dt_str) >= 10:
        dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
        pnl = t.get("pnl_usd", 0.0)
        dow_stats[dt.weekday()]["count"] += 1
        if pnl > 0: dow_stats[dt.weekday()]["wins"] += 1
        dow_stats[dt.weekday()]["pnl"] += pnl

print("\n--- DAY OF WEEK PROFITABILITY ---")
for w in range(5):
    d = dow_stats[w]
    wr = d["wins"] / d["count"] * 100 if d["count"] > 0 else 0
    print(f"{days[w]:9s} -> PnL: ${d['pnl']:+7.2f} | Trades: {d['count']:2d} | Win Rate: {wr:5.1f}%")
