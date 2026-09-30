import os
import sys
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

def ingest_symbol(db: DatabaseManager, symbol: str):
    csv_dir = Path("data/csv_imports")
    # Find all CSV files for symbol
    all_files = [p for p in csv_dir.rglob("*.csv") if p.is_file() and symbol in p.name]
    all_files.sort(key=lambda x: x.name)
    
    print(f"\n=======================================================")
    print(f"  INGESTING {symbol} ({len(all_files)} monthly files found) ")
    print(f"=======================================================")
    
    interval_sec = 900 # 15 minutes
    ts_cache = {}
    now_epoch = int(time.time())
    total_rows = 0
    total_candles = 0

    for file_path in all_files:
        t0 = time.time()
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        print(f"\nProcessing {file_path.name} ({file_size_mb:.1f} MB)...")
        
        candles_dict = {}
        rows = 0
        
        with open(file_path, "r", encoding="utf-8") as f:
            header = f.readline()
            for line in f:
                rows += 1
                parts = line.strip().split(",")
                if len(parts) < 5:
                    continue
                sym, price_s, size_s, ts_s, role = parts[0], parts[1], parts[2], parts[3], parts[4]
                try:
                    price = float(price_s)
                    size = float(size_s)
                    if price <= 0:
                        continue
                        
                    sec_str = ts_s[:19] # YYYY-MM-DD HH:MM:SS
                    epoch = ts_cache.get(sec_str)
                    if epoch is None:
                        # parse datetime
                        dt = datetime.fromisoformat(sec_str)
                        epoch = int(dt.timestamp())
                        if len(ts_cache) < 200000:
                            ts_cache[sec_str] = epoch
                            
                    # Safety: skip any candle timestamp beyond present
                    if epoch > now_epoch + 86400:
                        continue
                        
                    bucket = (epoch // interval_sec) * interval_sec
                    is_taker = (role == "taker")
                    
                    if bucket not in candles_dict:
                        candles_dict[bucket] = [price, price, price, price, 0.0, 0.0, 0.0]
                    
                    c = candles_dict[bucket]
                    if price > c[1]: c[1] = price
                    if price < c[2]: c[2] = price
                    c[3] = price
                    c[4] += size
                    if is_taker:
                        c[5] += size
                    else:
                        c[6] += size
                except Exception:
                    continue
                    
        # Convert to DB tuples
        db_tuples = []
        for bucket, vals in candles_dict.items():
            o, h, l, cl, vol, buy_vol, sell_vol = vals
            delta = buy_vol - sell_vol
            db_tuples.append((
                symbol, "15m", bucket, o, h, l, cl, vol, buy_vol, sell_vol, delta
            ))
            
        # Fast bulk save with executemany
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO candles 
                (symbol, timeframe, timestamp, open, high, low, close, volume, buy_volume, sell_volume, delta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, db_tuples)
            conn.commit()
            
        elapsed = time.time() - t0
        total_rows += rows
        total_candles += len(db_tuples)
        print(f"  -> {rows:,} trades aggregated into {len(db_tuples):,} candles in {elapsed:.2f}s ({rows/max(0.1, elapsed):,.0f} rows/s)")

    print(f"\n[DONE] {symbol}: Total {total_rows:,} trades processed -> {total_candles:,} 15m candles stored in SQLite.")

def main():
    db = DatabaseManager()
    for sym in ["BTCUSD", "ETHUSD"]:
        ingest_symbol(db, sym)
        
    print("\n=======================================================")
    print("ALL CANDLE COUNTS IN SQLITE DATABASE:")
    print("=======================================================")
    for sym in ["XAUTUSD", "SLVONUSD", "BTCUSD", "ETHUSD"]:
        c = db.get_latest_candles(sym, "15m", limit=100000)
        if c:
            start_date = datetime.fromtimestamp(c[0]["timestamp"]).strftime("%Y-%m-%d")
            end_date = datetime.fromtimestamp(c[-1]["timestamp"]).strftime("%Y-%m-%d")
            print(f"  {sym:10s}: {len(c):,} candles (15m) | Range: {start_date} -> {end_date}")
        else:
            print(f"  {sym:10s}: 0 candles")

if __name__ == "__main__":
    main()
