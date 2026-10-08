import sys
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from data.database import DatabaseManager

GLOBAL_DELTA_URL = "https://api.delta.exchange"
INDIA_DELTA_URL = "https://api.india.delta.exchange"

def fetch_candle_chunks(base_url: str, symbol: str, resolution: str, start_ts: int, end_ts: int, chunk_days: int = 25):
    """
    Fetches historical candles from Delta Exchange API in sequential forward chunks.
    Delta API returns candles descending (latest first). We sort ascending and yield.
    """
    chunk_sec = chunk_days * 86400
    current_start = start_ts
    all_candles = []
    seen_timestamps = set()

    session = requests.Session()
    session.headers.update({"User-Agent": "AgentBrain/1.0"})

    total_chunks = max(1, (end_ts - current_start) // chunk_sec + 1)
    chunk_idx = 0

    print(f"[*] Fetching {symbol} ({resolution}) from {base_url}...")
    print(f"    Range: {datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime('%Y-%m-%d')} -> {datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime('%Y-%m-%d')} (~{total_chunks} chunks)")

    while current_start < end_ts:
        chunk_idx += 1
        current_end = min(end_ts, current_start + chunk_sec)
        
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "start": current_start,
            "end": current_end
        }

        retries = 3
        items = []
        while retries > 0:
            try:
                r = session.get(f"{base_url}/v2/history/candles", params=params, timeout=12)
                if r.status_code == 200:
                    data = r.json()
                    items = data.get("result", [])
                    break
                else:
                    time.sleep(1.0)
                    retries -= 1
            except Exception as e:
                time.sleep(1.0)
                retries -= 1

        new_count = 0
        for c in items:
            t = c.get("time")
            if t and t not in seen_timestamps:
                seen_timestamps.add(t)
                all_candles.append(c)
                new_count += 1

        start_dt_str = datetime.fromtimestamp(current_start, tz=timezone.utc).strftime('%Y-%m-%d')
        end_dt_str = datetime.fromtimestamp(current_end, tz=timezone.utc).strftime('%Y-%m-%d')
        print(f"    [{chunk_idx}/{total_chunks}] {symbol} {start_dt_str} to {end_dt_str}: got {len(items)} items (+{new_count} new, total: {len(all_candles):,})")

        current_start = current_end
        time.sleep(0.1)  # polite rate-limiting

    # Sort ascending
    all_candles.sort(key=lambda x: x["time"])
    return all_candles

def enrich_and_save_candles(db: DatabaseManager, symbol: str, timeframe: str, raw_candles: list):
    if not raw_candles:
        return 0

    enriched = []
    for c in raw_candles:
        vol = float(c.get("volume", 0.0))
        hi = float(c["high"])
        lo = float(c["low"])
        op = float(c["open"])
        cl = float(c["close"])
        hl = max(0.0001, hi - lo)
        co = cl - op
        ratio = max(-1.0, min(1.0, co / hl))
        delta = round(vol * ratio, 2)
        buy_vol = round(max(0.0, (vol + delta) / 2.0), 2)
        sell_vol = round(max(0.0, (vol - delta) / 2.0), 2)

        enriched.append({
            "timestamp": int(c["time"]),
            "open": op,
            "high": hi,
            "low": lo,
            "close": cl,
            "volume": vol,
            "buy_volume": buy_vol,
            "sell_volume": sell_vol,
            "delta": delta
        })

    # Batch save directly to database
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT OR REPLACE INTO candles 
            (symbol, timeframe, timestamp, open, high, low, close, volume, buy_volume, sell_volume, delta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                symbol, timeframe, c["timestamp"], c["open"], c["high"], c["low"], c["close"],
                c["volume"], c["buy_volume"], c["sell_volume"], c["delta"]
            )
            for c in enriched
        ])
        conn.commit()

    return len(enriched)

def main():
    print("=" * 80)
    print("🚀 DELTA EXCHANGE 3-YEAR HISTORICAL DATA FETCHER (OCT 2023 - OCT 2026)")
    print("=" * 80)

    db = DatabaseManager()
    now_ts = int(time.time())
    # 3 years = 3 * 365 days = 1095 days
    start_3yr_ts = now_ts - (3 * 365 * 86400)

    print(f"Target Start: {datetime.fromtimestamp(start_3yr_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Target End:   {datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # 1. Fetch BTCUSD (3 Years from Global Delta API)
    btc_candles = fetch_candle_chunks(GLOBAL_DELTA_URL, "BTCUSD", "15m", start_3yr_ts, now_ts, chunk_days=30)
    saved_btc = enrich_and_save_candles(db, "BTCUSD", "15m", btc_candles)
    print(f"✅ BTCUSD: Successfully saved {saved_btc:,} 15m candles to SQLite database.\n")

    # 2. Fetch ETHUSD (3 Years from Global Delta API)
    eth_candles = fetch_candle_chunks(GLOBAL_DELTA_URL, "ETHUSD", "15m", start_3yr_ts, now_ts, chunk_days=30)
    saved_eth = enrich_and_save_candles(db, "ETHUSD", "15m", eth_candles)
    print(f"✅ ETHUSD: Successfully saved {saved_eth:,} 15m candles to SQLite database.\n")

    # 3. Fetch SLVONUSD (All available from Delta India API up to now)
    # SLVONUSD began in Feb/March 2026
    slv_start_ts = int(datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    slv_candles = fetch_candle_chunks(INDIA_DELTA_URL, "SLVONUSD", "15m", slv_start_ts, now_ts, chunk_days=30)
    saved_slv = enrich_and_save_candles(db, "SLVONUSD", "15m", slv_candles)
    print(f"✅ SLVONUSD: Successfully saved {saved_slv:,} 15m candles to SQLite database.\n")

    # 4. Fetch XAUTUSD (All available from Delta India API up to now)
    # XAUTUSD began in April 2026
    xaut_start_ts = int(datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    xaut_candles = fetch_candle_chunks(INDIA_DELTA_URL, "XAUTUSD", "15m", xaut_start_ts, now_ts, chunk_days=30)
    saved_xaut = enrich_and_save_candles(db, "XAUTUSD", "15m", xaut_candles)
    print(f"✅ XAUTUSD: Successfully saved {saved_xaut:,} 15m candles to SQLite database.\n")

    # Verify counts in SQLite
    print("-" * 80)
    print("📊 FINAL DATABASE CANDLE STATUS ACROSS 3 YEARS:")
    print("-" * 80)
    with db.get_connection() as conn:
        c = conn.cursor()
        for sym in ["BTCUSD", "ETHUSD", "SLVONUSD", "XAUTUSD"]:
            c.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM candles WHERE symbol = ? AND timeframe = '15m'", (sym,))
            row = c.fetchone()
            t_min = datetime.fromtimestamp(row[1], tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if row[1] else "None"
            t_max = datetime.fromtimestamp(row[2], tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if row[2] else "None"
            print(f"{sym:<10} | {row[0]:>7,} candles | {t_min} -> {t_max}")
    print("=" * 80)

if __name__ == "__main__":
    main()
