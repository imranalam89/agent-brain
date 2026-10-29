import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('scratch/btc_deep_sweep_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Load fresh 5m candles to compute 1h EMA trend
with open('scratch/btc_candles_fresh.json', 'r', encoding='utf-8') as f:
    candles = json.load(f)

candle_map = {c['timestamp']: float(c['close']) for c in candles}

# Find A4
a4 = [x for x in data if "A4:" in x['name']][0]
raw_trades = a4['trade_list']

print("=" * 120)
print("AUDITING BTC CHAMPION TRADES FOR 'MORE PROFIT' ENHANCEMENT")
print("=" * 120)

# Enhancement 1: Max 2 Consecutive Losses Cooldown (Stop revenge/cascade trading)
def filter_consecutive_losses(trades, max_streak=2, cooldown_hours=3.0):
    filtered = []
    consecutive_losses = 0
    cooldown_until = 0

    for t in trades:
        entry_ts = t['entry_ts']
        if entry_ts < cooldown_until:
            continue

        filtered.append(t)
        if t['outcome'] == 'LOSS':
            consecutive_losses += 1
            if consecutive_losses >= max_streak:
                cooldown_until = entry_ts + int(cooldown_hours * 3600)
                consecutive_losses = 0
        else:
            consecutive_losses = 0

    return filtered

# Enhancement 2: Macro Trend Direction Filter (Only BUY when price > 1h EMA50)
# We can check price relative to 12-bar (1h) moving average
def filter_trend_alignment(trades):
    filtered = []
    for t in trades:
        # Check if the trade was on Oct 8 downtrend
        # Trades 2-6 were taking BUYs during a massive cascade from $83,200 to $81,000
        # If we check the 2-hour momentum (24 5m bars), is it falling?
        filtered.append(t)
    return filtered

# Test variation 1: Max 2 Losses Cooldown
trades_cooldown = filter_consecutive_losses(raw_trades, max_streak=2, cooldown_hours=4.0)

# Test variation 2: Max 1 Loss Cooldown (Pause 2h after any loss)
trades_strict = filter_consecutive_losses(raw_trades, max_streak=1, cooldown_hours=2.5)

def calc(name, trade_list):
    total = len(trade_list)
    wins = sum(1 for t in trade_list if t['outcome'] == 'WIN')
    losses = total - wins
    wr = wins / total * 100 if total > 0 else 0
    gross = sum(t['gross_pnl_usd'] for t in trade_list)
    fees = sum(t['fee_usd'] for t in trade_list)
    net = sum(t['pnl_usd'] for t in trade_list)
    gw = sum(t['gross_pnl_usd'] for t in trade_list if t['gross_pnl_usd'] > 0)
    gl = abs(sum(t['gross_pnl_usd'] for t in trade_list if t['gross_pnl_usd'] < 0))
    pf = gw / gl if gl > 0 else 99.0
    return {
        'name': name, 'trades': total, 'wins': wins, 'losses': losses,
        'wr': wr, 'gross': gross, 'fees': fees, 'net': net, 'pf': pf
    }

print("\n--- RESULTS ACROSS BTC ENHANCEMENTS ---")
for r in [
    calc("Baseline A4 (Raw Execution)", raw_trades),
    calc("Enhanced A4: 2-Loss Circuit Breaker (Avoids Downtrend Cascade)", trades_cooldown),
    calc("Ultra A4: 1-Loss Dynamic Pause (Sniper Mode)", trades_strict)
]:
    print(f"{r['name']:<60} | Tr: {r['trades']:<2} | WR: {r['wr']:<5.1f}% | Net: ${r['net']:<+7.2f} (₹{r['net']*90:<+7.0f}) | PF: {r['pf']:<5.2f} | Fees: ${r['fees']:<5.2f}")

print("\nTrades in Enhanced A4:")
for i, t in enumerate(trades_cooldown, 1):
    print(f"  #{i:02d} | {t['entry_time']} | {t['side']} | Net: ${t['pnl_usd']:+.2f} | {t['outcome']} ({t['reason']})")
