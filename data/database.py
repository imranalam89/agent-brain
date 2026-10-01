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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
