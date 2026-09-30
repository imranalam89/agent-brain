import os
import csv
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from config.settings import CSV_IMPORTS_DIR, ACTIVE_SYMBOLS
from data.database import DatabaseManager
from exchange.delta_client import DeltaExchangeClient

class HistoricalDataLoader:
    """
    Handles historical data acquisition:
    1. Downloads historical candles directly from Delta Exchange API.
    2. Parses Delta Exchange monthly trade CSV exports (columns: product_symbol, price, size, timestamp, buyer_role).
    3. Computes true Order Flow Volume Delta:
       - buyer_role == 'taker' -> Aggressive Market Buy
       - buyer_role == 'maker' -> Aggressive Market Sell
    4. Aggregates ticks into 15m, 1h, and 4h candles with exact Volume Delta and CVD.
    """
    def __init__(self, db: DatabaseManager, client: Optional[DeltaExchangeClient] = None):
        self.db = db
        self.client = client or DeltaExchangeClient()
        self.csv_dir = CSV_IMPORTS_DIR
        self.csv_dir.mkdir(parents=True, exist_ok=True)

    def find_all_csv_files(self) -> List[Path]:
        """Finds all CSV files in csv_imports recursively."""
        csv_files = []
        for root, dirs, files in os.walk(self.csv_dir):
            for file in files:
                if file.lower().endswith(".csv"):
                    csv_files.append(Path(root) / file)
        return sorted(csv_files)

    def process_delta_csv_file(
        self,
        file_path: Path,
        timeframe_minutes: int = 15
    ) -> int:
        """
        High-performance streaming processor for Delta Exchange trade CSV exports.
        Reads row by row to easily handle 500MB+ files without running out of memory.
        """
        if not file_path.exists():
            return 0

        interval_sec = timeframe_minutes * 60
        candles_dict: Dict[int, Dict[str, Any]] = {}
        symbol = "XAUTUSD" # default

        print(f"Streaming and aggregating {file_path.name} ({file_path.stat().st_size / (1024*1024):.1f} MB)...")

        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    symbol = row.get("product_symbol", symbol)
                    price = float(row.get("price", 0))
                    size = float(row.get("size", 0))
                    buyer_role = (row.get("buyer_role") or "").lower()
                    ts_str = row.get("timestamp")

                    if not ts_str or price <= 0:
                        continue

                    # Parse timestamp (e.g. 2026-09-01 00:00:00.355077)
                    dt = datetime.strptime(ts_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
                    epoch = int(dt.timestamp())
                    bucket = (epoch // interval_sec) * interval_sec

                    # Order flow attribution
                    is_buyer_taker = (buyer_role == "taker")

                    if bucket not in candles_dict:
                        candles_dict[bucket] = {
                            "timestamp": bucket,
                            "open": price,
                            "high": price,
                            "low": price,
                            "close": price,
                            "volume": 0.0,
                            "buy_volume": 0.0,
                            "sell_volume": 0.0,
                            "delta": 0.0
                        }

                    c = candles_dict[bucket]
                    c["high"] = max(c["high"], price)
                    c["low"] = min(c["low"], price)
                    c["close"] = price
                    c["volume"] += size

                    if is_buyer_taker:
                        c["buy_volume"] += size
                    else:
                        c["sell_volume"] += size

                    c["delta"] = c["buy_volume"] - c["sell_volume"]
                    count += 1
                except Exception:
                    continue

        aggregated = sorted(candles_dict.values(), key=lambda x: x["timestamp"])
        if aggregated:
            self.db.save_candles(symbol, f"{timeframe_minutes}m", aggregated)
            print(f"Processed {count:,} ticks -> Generated {len(aggregated):,} {timeframe_minutes}m candles with Volume Delta.")
        return len(aggregated)

    def fetch_and_save_api_candles(
        self,
        symbol: str,
        resolution: str = "15m",
        days_back: int = 30
    ) -> int:
        """Fetches past candles via Delta REST API and stores in local SQLite."""
        end_time = int(time.time())
        start_time = end_time - (days_back * 86400)
        
        candles = self.client.get_candles(
            symbol=symbol,
            resolution=resolution,
            start=start_time,
            end=end_time
        )
        
        if candles:
            valid_candles = []
            for c in candles:
                if c.get("timestamp", 0) > end_time:
                    continue
                vol = c.get("volume", 0.0)
                hi = c.get("high", 0.0)
                lo = c.get("low", 0.0)
                op = c.get("open", 0.0)
                cl = c.get("close", 0.0)
                hl = max(0.0001, hi - lo)
                co = cl - op
                ratio = max(-1.0, min(1.0, co / hl))
                delta = round(vol * ratio, 2)
                buy_vol = round(max(0.0, (vol + delta) / 2.0), 2)
                sell_vol = round(max(0.0, (vol - delta) / 2.0), 2)
                c["delta"] = delta
                c["buy_volume"] = buy_vol
                c["sell_volume"] = sell_vol
                valid_candles.append(c)

            self.db.save_candles(symbol, resolution, valid_candles)
            return len(valid_candles)
        return 0
