import sqlite3
from collections import defaultdict

def audit():
    conn = sqlite3.connect('data/trading_brain.db')
    c = conn.cursor()
    
    c.execute('SELECT symbol, pnl_usd, lots, entry_price, exit_price, close_reason FROM trades')
    all_trades = c.fetchall()
    
    print(f"Total Logged Trades in Master Journal: {len(all_trades):,}")
    
    by_symbol = defaultdict(list)
    for r in all_trades:
        by_symbol[r[0]].append(r)
        
    for sym, trs in sorted(by_symbol.items()):
        losses = [t for t in trs if t[1] < 0]
        sl_losses = [t for t in losses if t[5] == 'SL' or 'Stop' in (t[5] or '') or 'SL' in (t[5] or '')]
        loss_pnls = [t[1] for t in losses]
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
        
        print(f"\n--- {sym} (Total Trades: {len(trs)}, Losses: {len(losses)}) ---")
        print(f"  Average Loss across all stopped trades: ${avg_loss:.2f}")
        print(f"  Sample 5 Loss P&L amounts:")
        for t in losses[:5]:
            print(f"    Lots: {int(t[2]) if t[2] else 0:4d} | Entry: {t[3]!s:<10} | Exit: {t[4]!s:<10} | Loss: ${t[1]:6.2f} | Reason: {t[5]}")

if __name__ == '__main__':
    audit()
