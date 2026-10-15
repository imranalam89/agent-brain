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
    "SLVONUSD",   # iShares Silver Trust ONDO Perpetual (50x Isolated, 1 Lot = 0.1 SLVON, Fee = 0.01%)
    "BTCUSD",     # Bitcoin Perpetual (100x Isolated, 1 Lot = 0.001 BTC, Fee = 0.01%)
    "ETHUSD"      # Ethereum Perpetual (100x Isolated, 1 Lot = 0.01 ETH, Fee = 0.01%)
]

# Dedicated Level 2 DOM orderbook recording symbols (Ultra-high fidelity 1s orderbook)
DOM_RECORDER_SYMBOLS = [
    "BTCUSD",     # Bitcoin Perpetual (100x Isolated, 1 Lot = 0.001 BTC)
    "ETHUSD",     # Ethereum Perpetual (100x Isolated, 1 Lot = 0.01 ETH)
    "XAUTUSD",    # Tether Gold Token Perpetual (100x Isolated, 1 Lot = 0.001 XAUT)
    "SLVONUSD",   # iShares Silver Trust ONDO Perpetual (50x Isolated, 1 Lot = 0.1 SLVON)
    "PAXGUSD",    # PAX Gold Token Perpetual (100x Isolated, 1 Lot = 0.001 PAXG)
    "UNIUSD"      # Uniswap Perpetual (50x Isolated, 1 Lot = 1.0 UNI)
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
DOM_DATABASE_PATH = BASE_DIR / "data" / "dom_recorder.db"
REPORTS_DIR = BASE_DIR / "reports"
CSV_IMPORTS_DIR = BASE_DIR / "data" / "csv_imports"

# ==========================================
# ==========================================
# 7. UNIFIED RATCHETED TRAILING SL LADDER (ALL PAIRS)
# ==========================================
# Incorporates User Ratchet Table + 1.5R Buffer at 5.0R+:
# +1.0R -> +0.20R (Guaranteed Green, covers fees + GST)
# +1.5R -> +0.60R (+60% risk banked)
# +2.0R -> +1.00R ($5.00 net banked)
# +2.5R -> +1.50R ($7.50 net banked)
# +3.0R -> +2.00R ($10.00 net banked)
# +4.0R -> +2.50R (1.5R breathing buffer)
# +5.0R -> +3.50R ($17.50 net banked, 1.5R buffer)
# +6.0R+ -> Continuous 1.5R trailing buffer behind peak price
UNIFIED_TRAILING_LADDER = {
    "step_1_0r": {"trigger_r": 1.0, "lock_r": 0.20},  # Guaranteed Green (covers fees + GST)
    "step_1_5r": {"trigger_r": 1.5, "lock_r": 0.60},  # +60% profit banked
    "step_2_0r": {"trigger_r": 2.0, "lock_r": 1.00},  # 1 Full R ($5.00) locked
    "step_2_5r": {"trigger_r": 2.5, "lock_r": 1.50},  # 1.5R ($7.50) locked
    "step_3_0r": {"trigger_r": 3.0, "lock_r": 2.00},  # 2.0R ($10.00) locked
    "step_4_0r": {"trigger_r": 4.0, "lock_r": 2.50},  # 1.5R buffer starts
    "step_5_0r": {"trigger_r": 5.0, "lock_r": 3.50},  # 1.5R buffer (User Rule: SL @ 3.5R)
    "macro_runner": {"trigger_r": 6.0, "buffer_r": 1.50} # Continuous 1.5R trail behind peak
}

# ==========================================
# 8. CHAMPION PRODUCTION ENGINE: GOLD (XAUTUSD)
# ==========================================
# 72.7% Win Rate | +$69.87 USD (+₹6,288 INR) | 6.76 Profit Factor | $5.94 Max DD
CHAMPION_CONFIG = {
    "strategy_name": "⚡ Hybrid A (Session Breakout + CVD Order Flow Absorption)",
    "symbol": "XAUTUSD",
    "sizing_mode": "RAW_GROSS_RISK",     # $5.00 Gross Risk per trade
    "risk_per_trade_usd": 5.0,          # Strict $5.00 fixed initial risk
    "reversal_cut": {
        "enabled": True,                # Emergency full cut on opposing DOM absorption wall
        "cut_r": -0.45,                 # Exit at -0.45R rather than full -1.0R SL
        "min_wall_imbalance": 2.2       # Opposing wall imbalance threshold
    },
    "trailing_ladder": UNIFIED_TRAILING_LADDER, # Unified user trailing rule (1.5R buffer at 5R+)
    "breathing_mult": 1.10,             # 1.10x breathing trail distance behind peak
    "swing_lookback_bars": 4,           # Recent 4-bar swing low/high structural protection
    "session_window": {
        "enabled": True,
        "start_ist": "13:00",           # London & NY High-Liquidity Session
        "end_ist": "23:00",             # Avoids 00:00 - 12:30 IST Asian morning chop
        "blackout_hours": [16, 19, 20, 22] # High-impact news spike filters
    },
    "cooldown": {
        "post_exit_mins": 15,           # 15-minute rest after every trade exit
        "cascade_breaker_losses": 2,    # Circuit breaker if 2 losses in a row
        "cascade_breaker_hours": 2.0    # 2-hour trading halt after 2-loss streak
    },
    "dom_confirmation": {
        "enabled": True,
        "min_delta_ratio": 0.015,       # Institutional buyer/seller aggression into DOM
        "wick_rejection_min": 0.28      # Strong wick rejection confirming active DOM support/resistance
    }
}

# ==========================================
# 9. CHAMPION PRODUCTION ENGINE: BITCOIN (BTCUSD)
# ==========================================
# 24/7 Continuous Trading (Weekend Included, Oct 08 - Till Now):
# 71.4% Win Rate | +$86.64 USD (+₹7,798 INR) | 8.36 Profit Factor | $7.93 Max DD
CHAMPION_CONFIG_BTC = {
    "strategy_name": "⚡ DOM Imbalance & Ask Wall Sweep (L2 Depth ≥ 3.0x)",
    "symbol": "BTCUSD",
    "sizing_mode": "RAW_GROSS_RISK",     # $5.00 Gross Risk per trade
    "risk_per_trade_usd": 5.0,          # Strict $5.00 fixed initial risk
    "imbalance_threshold": 3.0,         # Minimum 3.0x Level 2 DOM wall imbalance
    "reversal_cut": {
        "enabled": True,                # Emergency full cut on opposing DOM reversal signal
        "cut_r": -0.45,                 # Exit at -0.45R (saves ~48% of loss)
        "profit_lock_r": 0.80           # Bank +0.8R at peak before retracing to breakeven
    },
    "trailing_ladder": UNIFIED_TRAILING_LADDER, # Unified user trailing rule (1.5R buffer at 5R+)
    "cooldown": {
        "post_exit_mins": 15,           # 15-minute rest after every trade exit
        "cascade_breaker_losses": 2,    # Circuit breaker if 2 losses in a row
        "cascade_breaker_hours": 4.0    # 4-hour halt after 2-loss streak (saved 3 losses on Oct 08)
    },
    "trail_mode": "DYNAMIC_RUNNER",     # Trailing runner engine
    "weekend_trading": True             # 24/7 continuous crypto trading
}

# ==========================================
# 10. CHAMPION PRODUCTION ENGINE: ETHEREUM (ETHUSD)
# ==========================================
# Full Continuous Unified Engine (Oct 08 - Oct 15 22:50 IST Till Now):
# 56.5% Win Rate | +$154.10 USD (+₹13,869 INR) | 4.49 Profit Factor | $20.22 Max DD
# Weekdays: Confluence DOM Sweep & CVD Trend Pullback (London/NY Session)
# Weekends: Bollinger & RSI Range Exhaustion Reversal (24/7 Weekend Trading)
CHAMPION_CONFIG_ETH = {
    "strategy_name": "⚡ Confluence DOM Sweep (Weekday) + BB Exhaustion (Weekend)",
    "symbol": "ETHUSD",
    "sizing_mode": "RAW_GROSS_RISK",     # $5.00 Gross Risk per trade
    "risk_per_trade_usd": 5.0,          # Strict $5.00 fixed initial risk
    "reversal_cut": {
        "enabled": True,                # Emergency full cut on opposing DOM absorption wall
        "cut_r": -0.45,                 # Exit at -0.45R rather than full -1.0R SL (saved $22.00)
        "min_wall_imbalance": 2.0       # Minimum 2.0x opposing wall depth
    },
    "trailing_ladder": UNIFIED_TRAILING_LADDER, # Unified user trailing rule (1.5R buffer at 5R+)
    "cooldown": {
        "post_exit_mins": 15,           # 15-minute rest after every trade exit
        "cascade_breaker_losses": 2,    # Circuit breaker if 2 losses in a row
        "cascade_breaker_hours": 2.0    # 2-hour trading halt after 2-loss streak (Sweet spot for ETH)
    },
    "session_window": {
        "enabled": True,                # Restricts weekday entries to institutional sessions
        "start_ist": "13:00",           # London open ramp up
        "end_ist": "23:00",             # NY session close
        "blackout_hours": [16, 19, 20, 22] # High-impact news spike avoidance
    },
    "weekend_module": {
        "enabled": True,                # 24/7 weekend trading enabled on ETH
        "strategy": "Bollinger & RSI Range Exhaustion Reversal",
        "tp_target_r": 2.0,             # Fixed +2.0R take profit on weekend mean reversion
        "reversal_cut_r": -0.45,        # Emergency cut at -0.45R on break of range
        "performance": "71.4% Win Rate, +$33.57 USD Net (+₹3,021 INR) across Oct 10-11"
    },
    "trail_mode": "DYNAMIC_RUNNER",     # Multi-stage trailing runner locking up to +14.8R
    "contract_lot_size": 0.01           # 1 Lot = 0.01 ETH
}

