from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from config.settings import (
    MIN_CONVICTION_STARS,
    MIN_RR_RATIO,
    WEEKEND_LOCK_ENABLED,
    HIGH_LIQUIDITY_SESSIONS
)

class ConfluenceBrain:
    """
    The Master Institutional Decision Engine:
    - Synthesizes 4H/1H Macro Trend, Market Microstructure, and S/R Liquidity.
    - Evaluates Liquidity Sweeps (Stop Hunts) and Institutional Absorption.
    - Calculates the 1.0 to 5.0 Conviction Star Rating (Mirroring TradeEdge rules).
    - Formulates the Champion Scale-Out Trade Plan:
        1. Cut 50% lots at 1:2.5 to 1:3.0 (Guaranteed profit).
        2. Move Stop Loss to Break-Even (Zero risk).
        3. Dynamically trail remaining runner with 1.5x ATR.
    - Enforces strict institutional VETO rules.
    """
    def __init__(self, min_conviction: float = MIN_CONVICTION_STARS, min_rr: float = MIN_RR_RATIO):
        self.min_conviction = min_conviction
        self.min_rr = min_rr

    def is_weekend_locked(self, current_dt: Optional[datetime] = None) -> bool:
        """Returns True if today is Saturday or Sunday (Weekend trading freeze)."""
        if not WEEKEND_LOCK_ENABLED:
            return False
        dt = current_dt or datetime.now()
        # weekday(): Monday is 0, Sunday is 6
        return dt.weekday() in (5, 6)

    def is_peak_session(self, current_dt: Optional[datetime] = None) -> bool:
        """Checks if current time is within high-liquidity London or NY sessions (IST)."""
        dt = current_dt or datetime.now()
        current_time_str = dt.strftime("%H:%M")

        for session in HIGH_LIQUIDITY_SESSIONS.values():
            if session["start"] <= current_time_str <= session["end"]:
                return True
        return False

    def evaluate_setup(
        self,
        symbol: str,
        current_price: float,
        trend_macro: str,                  # 'BULLISH', 'BEARISH', or 'NEUTRAL' (200 EMA)
        sr_test: Optional[Dict[str, Any]], # {'type': 'SUPPORT'/'RESISTANCE', 'level': float}
        orderflow_dom: Dict[str, Any],     # DOM analysis dict
        absorption_result: Tuple[bool, str], # (is_absorbed, details)
        liquidity_sweep: Tuple[bool, str, str], # (is_sweep, sweep_type, details)
        cvd_result: Dict[str, Any],        # CVD divergence dict
        current_dt: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Runs the complete institutional confluence evaluation.
        Returns a detailed trade proposal with scale-out targets or a clear veto explanation.
        """
        # 1. Weekend Lock Check (Pillar 4: Capital Preservation)
        if self.is_weekend_locked(current_dt):
            return {
                "approved": False,
                "conviction_stars": 0.0,
                "reason": "VETO: Weekend trading lock active (Saturday/Sunday freeze). Preserving capital on off-days."
            }

        # 2. Key Level Check (Must be at high-value S/R or Liquidity Zone)
        is_sweep, sweep_type, sweep_details = liquidity_sweep
        if not sr_test and not is_sweep:
            return {
                "approved": False,
                "conviction_stars": 1.0,
                "reason": "VETO: Price is in no-man's land (Not testing any major S/R level or Liquidity Sweep zone)."
            }

        level_type = sr_test["type"] if sr_test else ("SUPPORT" if sweep_type == "BULLISH" else "RESISTANCE")
        key_level = sr_test["level"] if sr_test else current_price
        is_long = (level_type == "SUPPORT" or sweep_type == "BULLISH")
        side = "BUY" if is_long else "SELL"

        # 3. Confluence Scoring (1.0 to 5.0 Stars)
        stars = 1.0  # Base point for valid key level test
        breakdown = []

        # A. Macro Trend Alignment (200 EMA) (+1.0 Star)
        if (is_long and trend_macro == "BULLISH") or (not is_long and trend_macro == "BEARISH"):
            stars += 1.0
            breakdown.append(f"Macro Trend Aligned ({trend_macro}) [+1.0★]")
        else:
            breakdown.append(f"Counter-Trend to Macro ({trend_macro}) [+0.0★]")

        # B. Institutional Liquidity Sweep (+1.0 Star)
        if is_sweep and ((is_long and sweep_type == "BULLISH") or (not is_long and sweep_type == "BEARISH")):
            stars += 1.0
            breakdown.append(f"Liquidity Sweep / Stop Hunt: {sweep_details} [+1.0★]")

        # C. DOM Bid/Ask Imbalance (+0.5 Star)
        dominant_side = orderflow_dom.get("dominant_side")
        if (is_long and dominant_side == "BUYERS") or (not is_long and dominant_side == "SELLERS"):
            stars += 0.5
            breakdown.append(f"DOM Imbalance Confirmed ({dominant_side}) [+0.5★]")
        else:
            breakdown.append(f"DOM Neutral/Opposing ({dominant_side}) [+0.0★]")

        # D. Institutional Absorption (+1.0 Star)
        is_absorbed, abs_details = absorption_result
        if is_absorbed:
            stars += 1.0
            breakdown.append(f"Passive Absorption Confirmed: {abs_details} [+1.0★]")

        # E. CVD Divergence (+0.5 Star)
        div = cvd_result.get("divergence")
        if (is_long and div == "BULLISH") or (not is_long and div == "BEARISH"):
            stars += 0.5
            breakdown.append(f"CVD Exhaustion Divergence ({div}) [+0.5★]")

        # F. London/NY Peak Liquidity Session (+0.5 Star)
        if self.is_peak_session(current_dt):
            stars += 0.5
            breakdown.append("London/NY Peak Liquidity Session [+0.5★]")

        stars = min(5.0, round(stars, 1))

        # 4. Strict Institutional VETO Rules
        # VETO 1: Conviction Threshold
        if stars < self.min_conviction:
            return {
                "approved": False,
                "conviction_stars": stars,
                "reason": f"VETO: Conviction Score ({stars}★) is below minimum required {self.min_conviction}★. (TradeEdge Rule)",
                "breakdown": breakdown
            }

        # VETO 2: Severe DOM Opposition (Iceberg Wall blocking upside/downside)
        if is_long and orderflow_dom.get("ask_imbalance_ratio", 1.0) >= 2.5:
            return {
                "approved": False,
                "conviction_stars": stars,
                "reason": "VETO: Massive ask wall (>2.5x) blocking upside on DOM. Order flow rejection.",
                "breakdown": breakdown
            }
        if not is_long and orderflow_dom.get("bid_imbalance_ratio", 1.0) >= 2.5:
            return {
                "approved": False,
                "conviction_stars": stars,
                "reason": "VETO: Massive bid wall (>2.5x) supporting downside on DOM. Order flow rejection.",
                "breakdown": breakdown
            }

        # 5. Structure Stop Loss & Scale-Out Bracket Targets
        buffer_dist = abs(current_price - key_level) * 1.2
        if buffer_dist == 0:
            buffer_dist = current_price * 0.0015
        buffer_dist = max(3.5, buffer_dist)

        if is_long:
            stop_loss = round(min(key_level, current_price) - buffer_dist, 2)
            risk_dist = current_price - stop_loss
            tp1_target = round(current_price + (risk_dist * 2.5), 2)  # Scale out 50% at 1:2.5
            tp2_runner = round(current_price + (risk_dist * 5.0), 2)  # Runner target
        else:
            stop_loss = round(max(key_level, current_price) + buffer_dist, 2)
            risk_dist = stop_loss - current_price
            tp1_target = round(current_price - (risk_dist * 2.5), 2)  # Scale out 50% at 1:2.5
            tp2_runner = round(current_price - (risk_dist * 5.0), 2)  # Runner target

        return {
            "approved": True,
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit_1": tp1_target,
            "take_profit_2": tp2_runner,
            "risk_distance": round(risk_dist, 2),
            "scale_out_plan": {
                "tp1_rr": 2.5,
                "tp1_close_ratio": 0.50, # Cut 50% lots
                "breakeven_trigger": tp1_target,
                "runner_trail_atr": 1.5
            },
            "conviction_stars": stars,
            "strategy_name": f"Institutional Confluence ({'Sweep' if is_sweep else 'S/R'} + Order Flow)",
            "orderflow_notes": " | ".join(breakdown),
            "reason": f"APPROVED: High conviction {stars}★ setup with institutional order flow confirmation."
        }
