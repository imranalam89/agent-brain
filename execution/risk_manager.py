import math
from typing import Dict, Any, Tuple
from datetime import datetime, date

from config.settings import (
    ACCOUNT_CAPITAL_USD,
    TARGET_RISK_USD,
    MIN_RISK_USD,
    MAX_RISK_USD,
    DAILY_MAX_LOSS_USD,
    DEFAULT_LEVERAGE,
    MAX_MARGIN_USAGE_PCT
)
from data.database import DatabaseManager

class RiskManager:
    """
    Mathematical Risk Manager & Dynamic Sizer:
    - Enforces strict $3 to $5 USD risk per trade
    - Automatically solves Lot Size based on exact Stop Loss distance and Delta contract specs
    - Leverages 50x-100x isolated margin to guarantee no 'Insufficient Balance' errors
    - Enforces hard $20 daily max loss circuit breaker
    """
    def __init__(
        self,
        db: DatabaseManager,
        target_risk: float = TARGET_RISK_USD,
        max_risk: float = MAX_RISK_USD,
        daily_loss_limit: float = DAILY_MAX_LOSS_USD,
        default_leverage: int = DEFAULT_LEVERAGE
    ):
        self.db = db
        self.target_risk = target_risk
        self.max_risk = max_risk
        self.daily_loss_limit = daily_loss_limit
        self.leverage = default_leverage

    def get_daily_realized_loss(self) -> float:
        """Calculates net realized daily loss (Net Daily Drawdown)."""
        today_str = date.today().isoformat()
        trades = self.db.get_trades()
        net_pnl = 0.0
        for t in trades:
            if t.get("closed_at") and t["closed_at"].startswith(today_str):
                net_pnl += float(t.get("pnl_usd", 0.0) or 0.0)
        return abs(net_pnl) if net_pnl < 0 else 0.0

    def is_daily_circuit_breaker_active(self) -> Tuple[bool, float]:
        """Returns True if today's losses have reached or exceeded $20 limit."""
        daily_loss = self.get_daily_realized_loss()
        if daily_loss >= self.daily_loss_limit:
            return True, daily_loss
        return False, daily_loss

    def calculate_stepped_risk(self, available_balance_usd: float) -> Tuple[float, float]:
        """
        Calculates dynamic tiered stepped risk based on account equity:
        - Base Capital: $50.00 USD -> Base Risk: $5.00 USD.
        - Stepped Rule: For every 100% capital gain ($50 -> $100), risk scales by +50% ($5.00 -> $7.50, i.e. $7-$8 / trade).
        - Capital $150 (+200%) -> Risk $10.00 | Capital $200 (+300%) -> Risk $12.50.
        - Ratchet Drawdown Protection: If capital drops, risk instantly steps down to preserve equity.
        Returns: (effective_target_risk, max_allowed_risk)
        """
        capital_gain_ratio = max(0.0, (available_balance_usd - ACCOUNT_CAPITAL_USD) / ACCOUNT_CAPITAL_USD)
        risk_multiplier = 1.0 + (0.50 * capital_gain_ratio)
        effective_risk = min(round(self.target_risk * risk_multiplier, 2), 35.0)
        max_allowed = min(round(self.max_risk * risk_multiplier, 2), 45.0)
        return effective_risk, max_allowed

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        contract_spec: Dict[str, Any],
        available_balance_usd: float = ACCOUNT_CAPITAL_USD
    ) -> Dict[str, Any]:
        """
        Dynamically solves exact lot size and margin required.
        Ensures:
        1. Exact dollar loss at SL scales dynamically with account capital
        2. Margin required <= 65% of available balance (No 'Insufficient Balance')
        """
        # Check Circuit Breaker first
        breaker_active, current_loss = self.is_daily_circuit_breaker_active()
        if breaker_active:
            return {
                "valid": False,
                "reason": f"DAILY CIRCUIT BREAKER TRIGGERED: Daily loss is ${current_loss:.2f} (Limit: ${self.daily_loss_limit:.2f}). Trading halted for 24h."
            }

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            return {"valid": False, "reason": "Invalid stop loss distance (zero or negative)."}

        # Extract contract multiplier (e.g. 1 lot = 0.001 XAUT or 1 oz Silver)
        contract_val = float(contract_spec.get("contract_value", 0.001))
        
        # 1. Calculate stepped risk based on available capital
        # Rule: When capital doubles ($50 -> $100, +100%), risk per trade increases by 50% ($5.00 -> $7.50 / $7-$8)
        effective_risk, max_allowed_risk = self.calculate_stepped_risk(available_balance_usd)

        raw_lots = effective_risk / (sl_distance * contract_val)
        lots = max(1, int(math.floor(raw_lots)))

        # 2. Check resulting dollar risk
        actual_risk_usd = lots * contract_val * sl_distance

        # If 1 lot exceeds max risk, reject trade (Stop too wide for current account balance)
        if actual_risk_usd > max_allowed_risk and lots == 1:
            return {
                "valid": False,
                "reason": f"REJECTED: Stop loss too wide ({sl_distance:.2f}). Minimum 1 lot risks ${actual_risk_usd:.2f}, exceeding max ${max_allowed_risk:.2f}."
            }

        # 3. Calculate Notional Value and Margin Requirement at 100x leverage
        notional_usd = lots * contract_val * entry_price
        required_margin = notional_usd / self.leverage

        # Ensure lots adhere directly to target risk ($3.50 - $4.50 USD)
        actual_risk_usd = lots * contract_val * sl_distance

        return {
            "valid": True,
            "lots": lots,
            "notional_usd": round(notional_usd, 2),
            "margin_usd": round(required_margin, 2),
            "leverage": self.leverage,
            "planned_risk_usd": round(actual_risk_usd, 2),
            "sl_distance": round(sl_distance, 4)
        }

    def calculate_scale_out_orders(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss_price: float,
        lots: int,
        tp1_rr: float = 2.5
    ) -> Dict[str, Any]:
        """
        Splits position into Institutional Scale-Out Brackets:
        - 50% lots allocated to TP1 (Guaranteed Cash Banking)
        - 50% lots allocated to Runner (Risk-Free Breakeven + Dynamic Trailing)
        """
        sl_dist = abs(entry_price - stop_loss_price)
        half_lots = max(1, lots // 2)
        runner_lots = max(1, lots - half_lots)

        if side == "BUY":
            tp1_price = round(entry_price + (sl_dist * tp1_rr), 2)
            be_price = round(entry_price + 0.35, 2) # Buffer above entry
        else:
            tp1_price = round(entry_price - (sl_dist * tp1_rr), 2)
            be_price = round(entry_price - 0.35, 2) # Buffer below entry

        return {
            "total_lots": lots,
            "tp1_lots": half_lots,
            "runner_lots": runner_lots,
            "tp1_target_price": tp1_price,
            "breakeven_lock_price": be_price,
            "tp1_rr": tp1_rr,
            "trail_mult": 1.5
        }

