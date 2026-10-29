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
# Environment: 'india' (Delta India FIU registered), 'global', or 'demo'
DELTA_ENVIRONMENT = os.getenv("DELTA_ENVIRONMENT", "india")

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
    "BTCUSD",     # Bitcoin Perpetual (100x Isolated, 1 Lot = 0.001 BTC, Fee = 0.02% Maker / 0.05% Taker)
    "ETHUSD"      # Ethereum Perpetual (100x Isolated, 1 Lot = 0.01 ETH, Fee = 0.02% Maker / 0.05% Taker)
]

# Dedicated Level 2 DOM orderbook recording symbols (Ultra-high fidelity 1s orderbook)
DOM_RECORDER_SYMBOLS = [
    "BTCUSD",     # Bitcoin Perpetual (100x Isolated, 1 Lot = 0.001 BTC)
    "ETHUSD",     # Ethereum Perpetual (100x Isolated, 1 Lot = 0.01 ETH)
    "XAUTUSD",    # Tether Gold Token Perpetual (100x Isolated, 1 Lot = 0.001 XAUT)
]

# Delta Exchange Fee & Contract Specifications:
# - XAUTUSD, PAXGUSD (Gold) & SLVONUSD (Silver): 0.01% Maker (0.0001) & 0.02% Taker (0.0002)
# - BTCUSD & ETHUSD & UNIUSD: 0.02% Maker (0.0002) & 0.05% Taker (0.0005)
# - Delta India: 18% GST on brokerage fees
DELTA_GST_RATE = 0.18
DELTA_BROKERAGE_FEE_PCT = 0.0002  # Default maker reference (0.02%)
DELTA_FEES = {
    "XAUTUSD": {"mode": "pct", "maker": 0.0001, "taker": 0.0002},
    "SLVONUSD": {"mode": "pct", "maker": 0.0001, "taker": 0.0002},
    "BTCUSD": {"mode": "pct", "maker": 0.0002, "taker": 0.0005},
    "ETHUSD": {"mode": "pct", "maker": 0.0002, "taker": 0.0005},
    "PAXGUSD": {"mode": "pct", "maker": 0.0001, "taker": 0.0001},
    "UNIUSD": {"mode": "pct", "maker": 0.0002, "taker": 0.0005},
}

def calculate_brokerage_fee(symbol: str, notional: float, is_sl: bool = False, include_gst: bool = True) -> float:
    """Calculates contract-specific brokerage fee + 18% GST on Delta Exchange India."""
    s = symbol.upper()
    if "XAUT" in s or "SLV" in s or "PAXG" in s:
        entry_rate = 0.0001
        exit_rate = 0.0002 if is_sl else 0.0001
    else:  # BTC, ETH, UNI, etc.
        entry_rate = 0.0002
        exit_rate = 0.0005 if is_sl else 0.0002

    raw_fee = (notional * entry_rate) + (notional * exit_rate)
    total_fee = raw_fee * (1.0 + DELTA_GST_RATE) if include_gst else raw_fee
    return round(total_fee, 4)

LEVERAGE_MAP = {
    "XAUTUSD": 100,  # 100x Isolated Leverage on Gold Futures
    "SLVONUSD": 50,   # 50x Isolated Leverage on Silver Futures
    "BTCUSD": 100,   # 100x Isolated Leverage on Bitcoin Futures
    "ETHUSD": 100,   # 100x Isolated Leverage on Ethereum Futures
    "PAXGUSD": 100,  # 100x Isolated Leverage on PAX Gold Futures
    "UNIUSD": 50     # 50x Isolated Leverage on Uniswap Futures
}
CONTRACT_VALUES = {
    "XAUTUSD": 0.001, # 1 Lot = 0.001 XAUT ($4.29 per lot at $4,290)
    "SLVONUSD": 0.1,   # 1 Lot = 0.1 SLVON (~$5.81 per lot at $58.10, 50x Isolated)
    "BTCUSD": 0.001,  # 1 Lot = 0.001 BTC (~$65.00 per lot at $65,000, 100x Isolated)
    "ETHUSD": 0.01,   # 1 Lot = 0.01 ETH (~$25.00 per lot at $2,500, 100x Isolated)
    "PAXGUSD": 0.001, # 1 Lot = 0.001 PAXG (~$2.70 per lot at $2,700, 100x Isolated)
    "UNIUSD": 1.0     # 1 Lot = 1.0 UNI (~$7.00 per lot at $7.00, 50x Isolated)
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
# 5. TRADING SESSIONS & WEEKEND POLICY
# ==========================================
# 24/7 Continuous Trading for Crypto (BTCUSD & ETHUSD trade 24/7 including weekends)
# Traditional Commodities (Gold / XAUTUSD) pause on weekends (Friday 23:30 IST -> Monday 05:30 IST)
WEEKEND_CRYPTO_24_7 = True
WEEKEND_TRADING_SYMBOLS = ["BTCUSD", "ETHUSD"]
WEEKEND_PAUSED_SYMBOLS = ["XAUTUSD"]
WEEKEND_LOCK_ENABLED = False  # Global lock disabled; handled per-symbol
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
DOM_DATABASE_PATH = BASE_DIR / "data" / "dom_recorder.db"
REPORTS_DIR = BASE_DIR / "reports"
CSV_IMPORTS_DIR = BASE_DIR / "data" / "csv_imports"

# ==========================================
# 7. CHAMPION PRODUCTION ENGINE: GOLD (XAUTUSD)
# ==========================================
# 72.4% Win Rate | 5.03 Profit Factor | +$222.31 USD (+₹20,008 INR)
CHAMPION_CONFIG = {
    "strategy_name": "Gold Level 2 DOM Trap with Order Flow Absorption",
    "symbol": "XAUTUSD",
    "target_rr": 3.0,                   # Fixed 1:3.00 Take Profit Target
    "risk_per_trade_usd": 5.0,          # Strict $5.00 fixed initial risk
    "min_risk": 2.50,                   # Minimum $2.50 structural cushion
    "sl_buffer": 0.50,                  # $0.50 buffer beyond sweep bar extreme
    "lookback_bars": 24,                # 24-bar (6-hour) swing high/low window
    "wick_rejection_min": 0.25,         # Rejection wick >= 25% of bar range
    "session_window": {
        "enabled": True,
        "start_ist": "13:00",           # London open (13:00 IST)
        "end_ist": "23:30",             # NY close (23:30 IST)
    },
    "weekend_trading": False,           # Paused on weekends (traditional markets closed)
    "cooldown_sec": 900,                # 15-minute rest after trade exit
}

# ==========================================
# 8. CHAMPION PRODUCTION ENGINE: BITCOIN (BTCUSD)
# ==========================================
# 50.0% Win Rate | 2.59 Profit Factor | +$68.42 USD (+₹6,158 INR)
CHAMPION_CONFIG_BTC = {
    "strategy_name": "Bitcoin 1H Macro Volume Climax + London Asian Judas Sweep",
    "symbol": "BTCUSD",
    "target_rr": 3.5,                   # Fixed 1:3.50 Take Profit Target
    "risk_per_trade_usd": 5.0,          # Strict $5.00 fixed initial risk
    "min_risk": 80.0,                   # Minimum $80 structural cushion
    "atr_cushion_mult": 0.35,           # Fixed 0.35xATR technical structural cushion
    "macro_lookback_hours": 20,         # 20-hour macro high/low window
    "vol_climax_mult": 1.20,            # 1.20x 10-bar average volume
    "asian_judas_vol_mult": 1.25,       # 1.25x volume climax on London Asian sweep
    "wick_rejection_min": 0.25,         # Rejection wick >= 25% of bar range
    "weekend_trading": True,            # 24/7 continuous crypto trading
    "cooldown_sec": 900,                # 15-minute rest after trade exit
}

# ==========================================
# 9. CHAMPION PRODUCTION ENGINE: ETHEREUM (ETHUSD)
# ==========================================
# 64.3% Win Rate | 4.57 Profit Factor | +$111.16 USD (+₹10,004 INR)
CHAMPION_CONFIG_ETH = {
    "strategy_name": "Ethereum Dual Engine (Momentum Breakout + DOM Liquidity Sweep)",
    "symbol": "ETHUSD",
    "target_rr": 3.5,                   # Fixed 1:3.50 Take Profit Target
    "risk_per_trade_usd": 5.0,          # Strict $5.00 fixed initial risk
    "min_risk": 3.00,                   # Minimum $3.00 structural cushion
    "sl_buffer": 0.50,                  # $0.50 buffer beyond swing extreme
    "session_window": {
        "enabled": True,
        "start_ist": "13:00",           # London open (13:00 IST)
        "end_ist": "23:30",             # NY close (23:30 IST)
    },
    "breakout_lookback": 33,            # 33-bar swing high/low
    "trap_lookback": 48,                # 48-bar swing high/low
    "counter_wick_max": 0.18,           # Breakout counter-wick < 18% (institutional push)
    "trap_wick_min": 0.25,              # Trap rejection wick >= 25% (absorption)
    "max_ema_ext_pct": 2.2,             # EMA50 extension limit (<= 2.2%)
    "weekend_trading": True,            # 24/7 continuous crypto trading
    "cooldown_sec": 900,                # 15-minute rest after trade exit
}

