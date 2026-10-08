#!/usr/bin/env python3
"""
Institutional 24/7 Level 2 DOM (Depth of Market) Recorder
===========================================================
Records live Delta Exchange orderbook depth ladders (bids & asks) and microstructure metrics
into the database for:
1. High-fidelity historical order flow & DOM backtesting
2. Microstructure DOM Heatmap visualization (Bookmap / TradingLite style)
3. Resting iceberg & liquidity wall tracking

Designed to run 24/7 as a background systemd service on cloud VPS or locally.
"""

import os
import sys
import time
import signal
import argparse
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import ACTIVE_SYMBOLS, DOM_DATABASE_PATH
from exchange.delta_client import DeltaExchangeClient
from strategies.orderflow_engine import OrderFlowEngine
from data.database import DatabaseManager

# IST timezone helper
IST = timezone(timedelta(hours=5, minutes=30))

class L2DOMRecorder:
    def __init__(
        self,
        symbols: List[str] = None,
        poll_interval: float = 3.0,
        depth: int = 50,
        db_path: Any = None,
        max_errors_before_alert: int = 10
    ):
        self.symbols = symbols or ACTIVE_SYMBOLS
        self.poll_interval = poll_interval
        self.depth = depth
        self.max_errors = max_errors_before_alert
        
        # Dedicated DOM database for 100% decoupling from live trader & strategies
        self.db = DatabaseManager(db_path=db_path or DOM_DATABASE_PATH)
        self.client = DeltaExchangeClient()
        self.orderflow_engine = OrderFlowEngine()
        self.running = True
        self.snapshot_counter = 0
        self.start_time = time.time()
        
        # Setup graceful signal handlers
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame):
        print(f"\n[DOM Recorder] Received shutdown signal ({signum}). Flushing and stopping cleanly...")
        self.running = False

    def record_cycle(self):
        """Performs a single round of L2 orderbook fetching across all monitored symbols."""
        cycle_start = time.time()
        now_ts = int(cycle_start)
        now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        for symbol in self.symbols:
            if not self.running:
                break

            try:
                # 1. Fetch full Level 2 depth from Delta Exchange
                book_res = self.client.get_l2_orderbook(symbol, depth=self.depth)
                if not book_res.get("success"):
                    print(f"[DOM Recorder Error] {symbol}: {book_res.get('error', 'Failed to fetch orderbook')}")
                    continue

                bids = book_res.get("bids", [])
                asks = book_res.get("asks", [])
                if not bids or not asks:
                    print(f"[DOM Recorder Warning] {symbol}: Empty bids/asks returned")
                    continue

                # 2. Analyze microstructure metrics (imbalance, spread, walls)
                analysis = self.orderflow_engine.analyze_dom(bids, asks)

                # 3. Store snapshot in database (both raw ladder and metrics)
                self.db.save_dom_snapshot(
                    symbol=symbol,
                    timestamp=now_ts,
                    datetime_ist=now_ist,
                    bids=bids,
                    asks=asks,
                    analysis=analysis
                )

                self.snapshot_counter += 1

                # Log the first round immediately so the user knows data is flowing
                if self.snapshot_counter <= len(self.symbols):
                    print(f"[{now_ist}] Initial snapshot recorded: {symbol} at ${analysis.get('mid_price')} (Ratio: {analysis.get('bid_imbalance_ratio')}x)")

            except Exception as e:
                print(f"[DOM Recorder Exception] {symbol}: {e}")

        # Periodic status logging every 20 snapshots
        if self.snapshot_counter > 0 and self.snapshot_counter % 20 == 0:
            uptime_min = (time.time() - self.start_time) / 60.0
            print(f"[{now_ist}] Recorded {self.snapshot_counter} snapshots | Uptime: {uptime_min:.1f}m | Monitored: {', '.join(self.symbols)}")

    def run(self):
        """Main 24/7 continuous recording loop."""
        print("=" * 70)
        print("  🧠 DELTA EXCHANGE 24/7 LEVEL 2 DOM RECORDER STARTED")
        print("=" * 70)
        print(f"  Symbols       : {', '.join(self.symbols)}")
        print(f"  Poll Interval : {self.poll_interval}s")
        print(f"  Depth Levels  : {self.depth} bids / {self.depth} asks")
        print(f"  Target Storage: SQLite dom_snapshots (Heatmaps & Backtesting)")
        print(f"  Environment   : {self.client.environment} ({self.client.base_url})")
        print("=" * 70)

        consecutive_errors = 0

        while self.running:
            t0 = time.time()
            try:
                self.record_cycle()
                consecutive_errors = 0
            except Exception as loop_err:
                consecutive_errors += 1
                print(f"[DOM Recorder Loop Exception]: {loop_err}")
                if consecutive_errors >= self.max_errors:
                    print(f"⚠️ Warning: {consecutive_errors} consecutive errors encountered. Throttling 10s...")
                    time.sleep(10.0)

            # Precise interval sleep
            elapsed = time.time() - t0
            sleep_time = max(0.2, self.poll_interval - elapsed)
            time.sleep(sleep_time)

        print(f"[DOM Recorder Stopped] Total snapshots logged: {self.snapshot_counter}")

def main():
    parser = argparse.ArgumentParser(description="Delta Exchange 24/7 L2 DOM Orderbook Recorder")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated symbols (e.g. BTCUSD,ETHUSD,XAUTUSD,SLVONUSD)")
    parser.add_argument("--interval", type=float, default=3.0, help="Poll interval in seconds (default: 3.0s)")
    parser.add_argument("--depth", type=int, default=50, help="Orderbook depth per side (default: 50)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else ACTIVE_SYMBOLS
    recorder = L2DOMRecorder(symbols=symbols, poll_interval=args.interval, depth=args.depth)
    recorder.run()

if __name__ == "__main__":
    main()
