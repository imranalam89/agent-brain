import sqlite3
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))

from config.settings import DATABASE_PATH

class DatabaseManager:
    """
    Manages local SQLite database persistence for Agent Brain.
    Guarantees state recovery across PC reboots and stores complete trade journal history.
    """
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
        except Exception:
            pass
        return conn

    def init_database(self):
        """Initializes tables for candles, S/R levels, order flow, trades, thoughts, and post-mortems."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Historical & Live Candles
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT,
                    timeframe TEXT,
                    timestamp INTEGER,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    buy_volume REAL DEFAULT 0,
                    sell_volume REAL DEFAULT 0,
                    delta REAL DEFAULT 0,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                )
            """)

            # 2. Support & Resistance Levels
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sr_levels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    timeframe TEXT,
                    level_type TEXT,
                    price REAL,
                    touches INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT,
                    last_tested_at TEXT
                )
            """)

            # 3. Order Flow Snapshots (DOM & CVD)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orderflow_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    timestamp INTEGER,
                    bid_depth_usd REAL,
                    ask_depth_usd REAL,
                    imbalance_ratio REAL,
                    delta REAL,
                    cvd REAL,
                    absorption_detected INTEGER DEFAULT 0
                )
            """)

            # 3b. Level 2 DOM Price Ladder Snapshots (for Heatmaps & Precision DOM Backtesting)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dom_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    datetime_ist TEXT NOT NULL,
                    best_bid REAL,
                    best_ask REAL,
                    mid_price REAL,
                    spread REAL,
                    total_bid_size REAL,
                    total_ask_size REAL,
                    imbalance_ratio REAL,
                    dominant_side TEXT,
                    bid_walls_json TEXT,
                    ask_walls_json TEXT,
                    bids_json TEXT NOT NULL,
                    asks_json TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dom_sym_time 
                ON dom_snapshots (symbol, timestamp)
            """)

            # 4. Master Trade Journal
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    lots REAL,
                    notional_usd REAL,
                    margin_usd REAL,
                    leverage INTEGER,
                    risk_usd REAL,
                    pnl_usd REAL,
                    rr_achieved REAL,
                    conviction_stars REAL,
                    strategy_name TEXT,
                    orderflow_notes TEXT,
                    status TEXT, -- 'OPEN', 'CLOSED', 'CANCELLED'
                    opened_at TEXT,
                    closed_at TEXT,
                    close_reason TEXT, -- 'TP', 'SL', 'CIRCUIT_BREAKER', 'WEEKEND_FLATTEN'
                    is_paper INTEGER DEFAULT 1
                )
            """)

            # 5. Live Brain Thoughts Feed (For interactive transparency)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS brain_thoughts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    event_type TEXT, -- 'EVALUATING', 'VETO', 'APPROVED', 'POST_MORTEM'
                    conviction_stars REAL,
                    message TEXT,
                    metrics_json TEXT
                )
            """)

            # 6. Daily Post-Mortem & Parameter History
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_post_mortems (
                    date TEXT PRIMARY KEY,
                    total_trades INTEGER,
                    wins INTEGER,
                    losses INTEGER,
                    win_rate REAL,
                    net_pnl REAL,
                    fomo_detected INTEGER,
                    lesson_text TEXT,
                    calibrations_json TEXT
                )
            """)

            # 7. Live System State (For seamless PC reboot recovery)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            """)

            conn.commit()

    # ------------------ Candles Operations ------------------
    def save_candles(self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]):
        """Saves batch of candles, ignoring duplicates."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for c in candles:
                cursor.execute("""
                    INSERT OR REPLACE INTO candles 
                    (symbol, timeframe, timestamp, open, high, low, close, volume, buy_volume, sell_volume, delta)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol, timeframe, c["timestamp"], c["open"], c["high"], c["low"], c["close"],
                    c.get("volume", 0), c.get("buy_volume", 0), c.get("sell_volume", 0), c.get("delta", 0)
                ))
            conn.commit()

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int = 200) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM candles 
                WHERE symbol = ? AND timeframe = ? 
                ORDER BY timestamp DESC LIMIT ?
            """, (symbol, timeframe, limit))
            rows = cursor.fetchall()
            return [dict(r) for r in reversed(rows)]

    # ------------------ Level 2 DOM Operations (Heatmaps & Backtesting) ------------------
    def save_dom_snapshot(
        self,
        symbol: str,
        timestamp: int,
        datetime_ist: str,
        bids: List[Any],
        asks: List[Any],
        analysis: Optional[Dict[str, Any]] = None
    ):
        """Saves a single L2 DOM snapshot with raw depth and orderflow metrics."""
        analysis = analysis or {}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO dom_snapshots (
                    symbol, timestamp, datetime_ist,
                    best_bid, best_ask, mid_price, spread,
                    total_bid_size, total_ask_size, imbalance_ratio,
                    dominant_side, bid_walls_json, ask_walls_json,
                    bids_json, asks_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, timestamp, datetime_ist,
                analysis.get("best_bid", 0.0),
                analysis.get("best_ask", 0.0),
                analysis.get("mid_price", 0.0),
                analysis.get("spread", 0.0),
                analysis.get("total_bid_size", 0.0),
                analysis.get("total_ask_size", 0.0),
                analysis.get("bid_imbalance_ratio", 1.0),
                analysis.get("dominant_side", "NEUTRAL"),
                json.dumps(analysis.get("bid_walls", [])),
                json.dumps(analysis.get("ask_walls", [])),
                json.dumps(bids),
                json.dumps(asks)
            ))
            conn.commit()

    def get_closest_dom_snapshot(self, symbol: str, timestamp: int, tolerance_seconds: int = 300) -> Optional[Dict[str, Any]]:
        """
        Retrieves the DOM snapshot closest to the given timestamp (for backtesting replay).
        Looks for the latest snapshot at or before the timestamp within tolerance.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM dom_snapshots 
                WHERE symbol = ? AND timestamp <= ? AND timestamp >= ?
                ORDER BY timestamp DESC LIMIT 1
            """, (symbol, timestamp, timestamp - tolerance_seconds))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["bids"] = json.loads(res.get("bids_json", "[]"))
                res["asks"] = json.loads(res.get("asks_json", "[]"))
                res["bid_walls"] = json.loads(res.get("bid_walls_json", "[]"))
                res["ask_walls"] = json.loads(res.get("ask_walls_json", "[]"))
            except Exception:
                pass
            return res

    def get_dom_snapshots(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Queries DOM snapshots within a time window."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM dom_snapshots WHERE symbol = ?"
            params = [symbol]
            if start_time is not None:
                query += " AND timestamp >= ?"
                params.append(start_time)
            if end_time is not None:
                query += " AND timestamp <= ?"
                params.append(end_time)
            query += " ORDER BY timestamp ASC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["bids"] = json.loads(item.get("bids_json", "[]"))
                    item["asks"] = json.loads(item.get("asks_json", "[]"))
                    item["bid_walls"] = json.loads(item.get("bid_walls_json", "[]"))
                    item["ask_walls"] = json.loads(item.get("ask_walls_json", "[]"))
                except Exception:
                    pass
                results.append(item)
            return results

    def get_dom_heatmap_data(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        max_snapshots: int = 300
    ) -> Dict[str, Any]:
        """
        Prepares aggregated DOM snapshots for visual Heatmap rendering (Bookmap style).
        Returns timestamp timeline, mid_prices, and price-liquidity grid.
        """
        snapshots = self.get_dom_snapshots(symbol, start_time, end_time, limit=max_snapshots)
        if not snapshots:
            return {"symbol": symbol, "count": 0, "timeline": [], "mid_prices": [], "levels": []}

        timeline = []
        mid_prices = []
        all_levels = []
        for s in snapshots:
            t = s["timestamp"]
            mid = s["mid_price"]
            timeline.append(s.get("datetime_ist") or str(t))
            mid_prices.append(mid)
            all_levels.append({
                "timestamp": t,
                "datetime_ist": s.get("datetime_ist"),
                "mid_price": mid,
                "spread": s.get("spread", 0.0),
                "total_bid_size": s.get("total_bid_size", 0.0),
                "total_ask_size": s.get("total_ask_size", 0.0),
                "imbalance_ratio": s.get("imbalance_ratio", 1.0),
                "dominant_side": s.get("dominant_side", "NEUTRAL"),
                "bids": s.get("bids", []),
                "asks": s.get("asks", []),
                "bid_walls": s.get("bid_walls", []),
                "ask_walls": s.get("ask_walls", [])
            })

        return {
            "symbol": symbol,
            "count": len(all_levels),
            "timeline": timeline,
            "mid_prices": mid_prices,
            "levels": all_levels
        }

    # ------------------ Trade Operations ------------------
    def log_trade(self, trade: Dict[str, Any]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO trades (
                    id, symbol, side, entry_price, exit_price, stop_loss, take_profit,
                    lots, notional_usd, margin_usd, leverage, risk_usd, pnl_usd,
                    rr_achieved, conviction_stars, strategy_name, orderflow_notes,
                    status, opened_at, closed_at, close_reason, is_paper
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade["id"], trade["symbol"], trade["side"], trade["entry_price"], trade.get("exit_price"),
                trade["stop_loss"], trade["take_profit"], trade["lots"], trade["notional_usd"],
                trade["margin_usd"], trade["leverage"], trade["risk_usd"], trade.get("pnl_usd", 0.0),
                trade.get("rr_achieved", 0.0), trade["conviction_stars"], trade["strategy_name"],
                trade.get("orderflow_notes", ""), trade["status"], trade["opened_at"],
                trade.get("closed_at"), trade.get("close_reason"), trade.get("is_paper", 1)
            ))
            conn.commit()

    def get_trades(self, limit: int = 10000) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def clear_trades(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trades")
            conn.commit()

    # ------------------ Brain Thoughts / Log ------------------
    def log_thought(self, symbol: str, event_type: str, stars: float, message: str, metrics: Optional[Dict] = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO brain_thoughts (timestamp, symbol, event_type, conviction_stars, message, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                symbol, event_type, stars, message,
                json.dumps(metrics or {})
            ))
            conn.commit()

    def get_recent_thoughts(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM brain_thoughts ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    # ------------------ System State & Interactive Control Settings ------------------
    def set_system_state(self, key: str, value: Any):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            val_str = json.dumps(value) if not isinstance(value, str) else value
            now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO system_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, val_str, now_str))
            conn.commit()

    def get_system_state(self, key: str, default: Any = None) -> Any:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_state WHERE key = ?", (key,))
            row = cursor.fetchone()
            if not row:
                return default
            val_str = row["value"]
            try:
                return json.loads(val_str)
            except Exception:
                return val_str

    def get_target_risk_usd(self, default_risk: float = 5.0) -> float:
        val = self.get_system_state("target_risk_usd", default_risk)
        try:
            return float(val)
        except Exception:
            return default_risk

    def set_target_risk_usd(self, risk_usd: float):
        self.set_system_state("target_risk_usd", float(risk_usd))

    def is_bot_paused(self) -> Tuple[bool, str, Optional[str]]:
        """
        Returns (is_paused, reason, pause_until_iso).
        Automatically clears pause if timed pause has expired!
        """
        status = str(self.get_system_state("bot_status", "ACTIVE")).upper()
        pause_until = self.get_system_state("pause_until", None)
        reason = str(self.get_system_state("pause_reason", "Manual News Pause"))

        if status == "PAUSED":
            if pause_until:
                try:
                    target_dt = datetime.fromisoformat(pause_until)
                    now_check = datetime.now(IST) if target_dt.tzinfo else datetime.now()
                    if now_check >= target_dt:
                        # Auto-expire pause!
                        self.set_system_state("bot_status", "ACTIVE")
                        self.set_system_state("pause_until", None)
                        self.set_system_state("pause_reason", "Timer Expired - Resumed Active")
                        return False, "Auto-Resumed", None
                    else:
                        return True, reason, pause_until
                except Exception:
                    pass
            return True, reason, pause_until
        return False, "Active", None

    def set_bot_status(self, status: str, duration_minutes: int = 0, reason: str = ""):
        status_clean = "PAUSED" if status.upper() == "PAUSED" else "ACTIVE"
        self.set_system_state("bot_status", status_clean)

        if status_clean == "PAUSED":
            if duration_minutes > 0:
                until_dt = datetime.now(IST) + timedelta(minutes=duration_minutes)
                self.set_system_state("pause_until", until_dt.isoformat())
            else:
                self.set_system_state("pause_until", None)
            self.set_system_state("pause_reason", reason or "User Paused from Live Journal")
        else:
            self.set_system_state("pause_until", None)
            self.set_system_state("pause_reason", "Resumed Active")
