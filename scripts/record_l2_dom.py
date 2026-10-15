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
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import ACTIVE_SYMBOLS, DOM_RECORDER_SYMBOLS, DOM_DATABASE_PATH
from exchange.delta_client import DeltaExchangeClient
from strategies.orderflow_engine import OrderFlowEngine
from data.database import DatabaseManager

# IST timezone helper
IST = timezone(timedelta(hours=5, minutes=30))

class L2DOMRecorder:
    def __init__(
        self,
        symbols: List[str] = None,
        poll_interval: float = 1.0,
        depth: int = 50,
        db_path: Any = None,
        max_errors_before_alert: int = 10
    ):
        self.symbols = symbols or DOM_RECORDER_SYMBOLS
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
        self.first_cycle_logged = False
        
        # Concurrent worker pool to ensure all symbols fetch comfortably within 1.0s
        worker_count = min(max(len(self.symbols), 1), 10)
        self.executor = ThreadPoolExecutor(max_workers=worker_count)
        
        # Setup graceful signal handlers
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame):
        print(f"\n[DOM Recorder] Received shutdown signal ({signum}). Flushing and stopping cleanly...")
        self.running = False

    def _fetch_symbol_snapshot(self, symbol: str, now_ts: int, now_ist: str) -> Optional[Dict[str, Any]]:
        """Worker function: fetches Level 2 DOM orderbook and computes microstructure metrics."""
        try:
            # 1. Fetch full Level 2 depth from Delta Exchange
            book_res = self.client.get_l2_orderbook(symbol, depth=self.depth)
            if not book_res.get("success"):
                return None

            bids = book_res.get("bids", [])
            asks = book_res.get("asks", [])
            if not bids or not asks:
                return None

            # 2. Analyze microstructure metrics (imbalance, spread, walls)
            analysis = self.orderflow_engine.analyze_dom(bids, asks)

            return {
                "symbol": symbol,
                "timestamp": now_ts,
                "datetime_ist": now_ist,
                "bids": bids,
                "asks": asks,
                "analysis": analysis
            }
        except Exception as e:
            print(f"[DOM Recorder Fetch Error] {symbol}: {e}")
            return None

    def record_cycle(self):
        """Performs a single high-frequency round of L2 orderbook fetching across all monitored symbols concurrently."""
        cycle_start = time.time()
        now_ts = int(cycle_start)
        now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        if not self.running:
            return

        # Fetch all symbols in parallel threads to achieve true 1-second cadence
        futures = [
            self.executor.submit(self._fetch_symbol_snapshot, symbol, now_ts, now_ist)
            for symbol in self.symbols
        ]

        snapshots = []
        for f in futures:
            try:
                res = f.result(timeout=4.0)
                if res:
                    snapshots.append(res)
            except Exception as e:
                pass

        if snapshots and self.running:
            # Atomic single-transaction batch write to SQLite (avoids disk thrashing at 1s frequency)
            self.db.save_dom_snapshots_batch(snapshots)
            self.snapshot_counter += len(snapshots)

            # Log the initial round immediately so the user knows all pairs are active
            if not self.first_cycle_logged:
                for s in snapshots:
                    an = s.get("analysis", {})
                    print(f"[{now_ist}] Initial snapshot: {s['symbol']:<8} at ${an.get('mid_price')} (Imbalance: {an.get('bid_imbalance_ratio', 1.0):.2f}x)")
                self.first_cycle_logged = True

        # Periodic status logging every 60 snapshots (~10 seconds at 6 pairs @ 1s)
        if self.snapshot_counter > 0 and self.snapshot_counter % 60 < len(self.symbols):
            uptime_min = (time.time() - self.start_time) / 60.0
            cycle_dur = time.time() - cycle_start
            print(f"[{now_ist}] {self.snapshot_counter} snapshots | Rate: 1.0s ({cycle_dur:.2f}s latency) | Monitored: {', '.join(self.symbols)}")

    def run(self):
        """Main 24/7 continuous ultra-high-frequency recording loop."""
        print("=" * 70)
        print("  🧠 DELTA EXCHANGE 24/7 ULTRA-HIGH-FREQUENCY (1s) LEVEL 2 DOM RECORDER")
        print("=" * 70)
        print(f"  Symbols       : {', '.join(self.symbols)}")
        print(f"  Poll Interval : {self.poll_interval}s (Concurrent Multi-Threaded Engine)")
        print(f"  Depth Levels  : {self.depth} bids / {self.depth} asks per symbol")
        print(f"  Target Storage: SQLite dom_snapshots (Atomic Batch Insert WAL)")
        print(f"  Environment   : {self.client.environment} ({self.client.base_url})")
        print("=" * 70)

        consecutive_errors = 0

        try:
            while self.running:
                t0 = time.time()
                try:
                    self.record_cycle()
                    consecutive_errors = 0
                except Exception as loop_err:
                    consecutive_errors += 1
                    print(f"[DOM Recorder Loop Exception]: {loop_err}")
                    if consecutive_errors >= self.max_errors:
                        print(f"⚠️ Warning: {consecutive_errors} consecutive errors encountered. Throttling 5s...")
                        time.sleep(5.0)

                # Precise interval sleep
                elapsed = time.time() - t0
                sleep_time = max(0.01, self.poll_interval - elapsed)
                time.sleep(sleep_time)
        finally:
            self.executor.shutdown(wait=False)

        print(f"[DOM Recorder Stopped] Total snapshots logged: {self.snapshot_counter}")

def main():
    parser = argparse.ArgumentParser(description="Delta Exchange 24/7 Ultra-High-Frequency (1s) L2 DOM Orderbook Recorder")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated symbols (default: BTCUSD,ETHUSD,XAUTUSD)")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0s)")
    parser.add_argument("--depth", type=int, default=50, help="Orderbook depth per side (default: 50)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else DOM_RECORDER_SYMBOLS
    recorder = L2DOMRecorder(symbols=symbols, poll_interval=args.interval, depth=args.depth)
    recorder.run()

if __name__ == "__main__":
    main()
