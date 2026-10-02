import sqlite3
from pathlib import Path

db_path = Path("trading_data.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Update the BTC trade to reflect real Delta fills:
    # 14 lots @ 86400 (+5.285) + 14 lots @ 86645.5 (+1.848) = 7.13 gross
    cur.execute("""
        UPDATE trades 
        SET exit_price = 86645.50,
            pnl_usd = 7.13,
            rr_achieved = 1.4,
            close_reason = 'TRAILING_STOP (PROFIT SECURED)',
            orderflow_notes = 'Delta Live Execution: 14 Lots @ $86,400 (+50%) + 14 Lots @ $86,645.5 (BE Stop). Total: +$7.13 USD.'
        WHERE id = 'LIVE_BTCUSD_1790915423'
    """)
    conn.commit()
    print(f"Updated {cur.rowcount} row(s) in {db_path}")
    conn.close()
