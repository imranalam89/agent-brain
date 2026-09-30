import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment credentials (.env)
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# ==========================================
# 1. DELTA EXCHANGE API CREDENTIALS & VENUE
# ==========================================
# Environment: 'demo' (Delta Demo/Testnet), 'india' (Delta India), or 'global'
DELTA_ENVIRONMENT = os.getenv("DELTA_ENVIRONMENT", "demo")

# Delta API Endpoints
DELTA_BASE_URLS = {
    "demo": "https://cdn.delta.exchange",       # Delta demo uses main CDN endpoints with test credentials or testnet
    "india": "https://api.india.delta.exchange", # Delta India FIU registered
    "global": "https://api.delta.exchange"       # Delta Global
}

DELTA_WS_URLS = {
    "demo": "wss://socket.delta.exchange",
    "india": "wss://socket.india.delta.exchange",
    "global": "wss://socket.delta.exchange"
}

DELTA_API_KEY = os.getenv("DELTA_API_KEY", "")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "")

# ==========================================
# 2. INSTRUMENTS TO TRADE (FUTURES ONLY)
# ==========================================
ACTIVE_SYMBOLS = [
    "XAUTUSD",    # Tether Gold Token Perpetual (100x Isolated, 1 Lot = 0.001 XAUT, Fee = 0.01%)
    "SLVONUSD",   # iShares Silver Trust ONDO Perpetual (50x Isolated, 1 Lot = 0.1 SLVON, Fee = 0.01%)
    "BTCUSD",     # Bitcoin Perpetual (100x Isolated, 1 Lot = 0.001 BTC, Fee = 0.01%)
    "ETHUSD"      # Ethereum Perpetual (100x Isolated, 1 Lot = 0.01 ETH, Fee = 0.01%)
]

# Delta Exchange Fee & Contract Specifications:
# - XAUTUSD (Gold) & SLVONUSD (Silver): Flat $0.01 fixed brokerage fee per trade
# - BTCUSD & ETHUSD: 0.02% Maker (0.0002) & 0.05% Taker (0.0005)
DELTA_BROKERAGE_FEE_PCT = 0.0002  # Default maker reference (0.02%)
DELTA_FEES = {
    "XAUTUSD": {"mode": "flat", "fee": 0.01},
    "SLVONUSD": {"mode": "flat", "fee": 0.01},
    "BTCUSD": {"mode": "pct", "maker": 0.0002, "taker": 0.0005},
    "ETHUSD": {"mode": "pct", "maker": 0.0002, "taker": 0.0005},
}

def calculate_brokerage_fee(symbol: str, notional: float, is_sl: bool = False) -> float:
    """Calculates contract-specific brokerage fee on Delta Exchange India."""
    s = symbol.upper()
    if "XAUT" in s or "SLV" in s:
        return 0.01 # Flat $0.01 per trade
    else: # BTC or ETH
        entry_fee = notional * 0.0002
        exit_rate = 0.0005 if is_sl else 0.0002
        exit_fee = notional * exit_rate
        return round(entry_fee + exit_fee, 4)

LEVERAGE_MAP = {
    "XAUTUSD": 100,  # 100x Isolated Leverage on Gold Futures
    "SLVONUSD": 50,   # 50x Isolated Leverage on Silver Futures
    "BTCUSD": 100,   # 100x Isolated Leverage on Bitcoin Futures
    "ETHUSD": 100    # 100x Isolated Leverage on Ethereum Futures
}
CONTRACT_VALUES = {
    "XAUTUSD": 0.001, # 1 Lot = 0.001 XAUT ($4.29 per lot at $4,290)
    "SLVONUSD": 0.1,   # 1 Lot = 0.1 SLVON (~$5.81 per lot at $58.10, 50x Isolated)
    "BTCUSD": 0.001,  # 1 Lot = 0.001 BTC (~$65.00 per lot at $65,000, 100x Isolated)
    "ETHUSD": 0.01    # 1 Lot = 0.01 ETH (~$25.00 per lot at $2,500, 100x Isolated)
}

# Primary timeframe hierarchy
TIMEFRAMES = {
    "macro": "4h",        # Directional compass & macro S/R
    "intermediate": "1h", # Structural trend & key levels
    "setup": "15m",       # Pullbacks & consolidation
    "trigger": "5m"       # Sniper order flow entry
}

# ==========================================
# 3. RISK MANAGEMENT & ACCOUNT PARAMETERS
# ==========================================
ACCOUNT_CAPITAL_INR = 5000.0   # Approx 5,000 INR
ACCOUNT_CAPITAL_USD = 50.0     # Approx $50 to $60 USD base

# Risk Per Trade Constraints ($4.00 - $5.00 USD strict fixed risk)
TARGET_RISK_USD = 5.0          # Target risk per trade ($5.00 fixed risk per trade)
MIN_RISK_USD = 4.0             # Minimum risk per trade ($4.00 for scalps)
MAX_RISK_USD = 5.0             # Hard maximum risk ceiling ($5.00 per trade)

# Daily Loss Circuit Breaker ($25 USD hard stop)
DAILY_MAX_LOSS_USD = 25.0      # Auto-halts all trading for 24h if reached

# Leverage Settings (50x Silver, 100x Gold)
DEFAULT_LEVERAGE = 100
MAX_MARGIN_USAGE_PCT = 0.65    # Never commit more than 65% of available margin

# Minimum Risk-to-Reward Ratio for Trade Qualification
MIN_RR_RATIO = 2.0             # Min 1:2 R:R (e.g. Risk $4 to make $8+)

# ==========================================
# 4. CONVICTION & VETO THRESHOLDS
# ==========================================
# Star Rating: 1.0 to 5.0 (Mirroring your TradeEdge Golden Rule)
MIN_CONVICTION_STARS = 3.5     # Skip any setup with Conviction < 3.5 Stars

# Order Flow Thresholds
MIN_DOM_IMBALANCE_RATIO = 1.8  # Buyers/Sellers must dominate DOM by at least 1.8x
ABSORPTION_DELTA_PERCENTILE = 80 # Heavy volume candle with wick rejection

# ==========================================
# 5. TRADING SESSIONS & WEEKEND LOCK
# ==========================================
# Strict Weekend Rule: No trading Saturday and Sunday
WEEKEND_LOCK_ENABLED = True
# Friday NY close (approx 23:30 IST / 18:00 UTC) -> Monday Asian open (05:30 IST / 00:00 UTC)
FRIDAY_CLOSE_HOUR_IST = 23
FRIDAY_CLOSE_MINUTE_IST = 30
MONDAY_RESUME_HOUR_IST = 5
MONDAY_RESUME_MINUTE_IST = 30

# Peak Volume Hours (IST) for Gold & Silver
HIGH_LIQUIDITY_SESSIONS = {
    "london_open": {"start": "13:30", "end": "17:30"},
    "new_york_open": {"start": "18:30", "end": "23:00"}
}

# ==========================================
# 6. LOCAL PERSISTENCE & DATABASE
# ==========================================
DATABASE_PATH = BASE_DIR / "data" / "trading_brain.db"
REPORTS_DIR = BASE_DIR / "reports"
CSV_IMPORTS_DIR = BASE_DIR / "data" / "csv_imports"
