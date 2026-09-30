import time
from pathlib import Path
from datetime import datetime

# Test fast parsing vs standard parsing on 100,000 rows
sample_file = Path("data/csv_imports/futures-trades-monthly-BTCUSD-2026-09.csv/BTCUSD_2026-09.csv")
print(f"Testing on {sample_file} ({sample_file.stat().st_size / 1024 / 1024:.2f} MB)...")

t0 = time.time()
rows = 0
candles = {}
interval_sec = 900 # 15m

# Cache timestamp conversions: 'YYYY-MM-DD HH:MM:SS' -> epoch
ts_cache = {}

with open(sample_file, "r", encoding="utf-8") as f:
    header = f.readline()
    for line in f:
        rows += 1
        parts = line.strip().split(",")
        if len(parts) < 5:
            continue
        sym, price_s, size_s, ts_s, role = parts[0], parts[1], parts[2], parts[3], parts[4]
        sec_str = ts_s[:19] # 'YYYY-MM-DD HH:MM:SS'
        epoch = ts_cache.get(sec_str)
        if epoch is None:
            # parse
            # Fast int parse
            # 2026-09-01 00:00:00
            # or datetime.fromisoformat
            epoch = int(datetime.fromisoformat(sec_str).timestamp())
            if len(ts_cache) < 100000:
                ts_cache[sec_str] = epoch
        
        bucket = (epoch // interval_sec) * interval_sec
        price = float(price_s)
        size = float(size_s)
        is_taker = (role == "taker")

        if bucket not in candles:
            candles[bucket] = [price, price, price, price, 0.0, 0.0, 0.0, sym] # O, H, L, C, vol, buy_vol, sell_vol, sym
        c = candles[bucket]
        if price > c[1]: c[1] = price
        if price < c[2]: c[2] = price
        c[3] = price
        c[4] += size
        if is_taker:
            c[5] += size
        else:
            c[6] += size

t1 = time.time()
print(f"Parsed {rows:,} rows in {t1 - t0:.2f}s -> {len(candles)} candles!")
