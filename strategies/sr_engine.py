from typing import List, Dict, Any, Optional

class SupportResistanceEngine:
    """
    Identifies high-probability Support & Resistance levels:
    - Dynamic rolling swing pivots over lookback window
    - Exact level testing with wick sweeps and close confirmation
    - Rejection wick measurement
    """
    def __init__(self, pivot_window: int = 20):
        self.pivot_window = pivot_window

    def get_dynamic_sr_levels(self, candles: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        """
        Extracts recent major swing highs and swing lows from the recent candle window.
        """
        if len(candles) < self.pivot_window:
            return {"supports": [], "resistances": []}

        recent = candles[-self.pivot_window:]
        highs = [c["high"] for c in recent]
        lows = [c["low"] for c in recent]

        # Major local levels
        major_support = min(lows[:-1])
        major_resistance = max(highs[:-1])

        # Intermediate pivot levels
        supports = sorted(list(set([major_support])))
        resistances = sorted(list(set([major_resistance])))

        # Find clean fractal swing lows/highs
        for i in range(2, len(recent) - 2):
            if recent[i]["low"] < recent[i-1]["low"] and recent[i]["low"] < recent[i-2]["low"] and \
               recent[i]["low"] < recent[i+1]["low"] and recent[i]["low"] < recent[i+2]["low"]:
                supports.append(recent[i]["low"])

            if recent[i]["high"] > recent[i-1]["high"] and recent[i]["high"] > recent[i-2]["high"] and \
               recent[i]["high"] > recent[i+1]["high"] and recent[i]["high"] > recent[i+2]["high"]:
                resistances.append(recent[i]["high"])

        return {
            "supports": sorted(list(set(supports))),
            "resistances": sorted(list(set(resistances)))
        }

    def check_level_reaction(
        self,
        candle: Dict[str, Any],
        supports: List[float],
        resistances: List[float],
        price_tolerance: float = 3.0 # $3.00 max distance for Gold
    ) -> Optional[Dict[str, Any]]:
        """
        Detects if current candle tests and rejects a key level.
        Returns setup reaction details if confirmed, else None.
        """
        c_open = candle["open"]
        c_high = candle["high"]
        c_low = candle["low"]
        c_close = candle["close"]
        c_range = c_high - c_low

        if c_range <= 0.5:
            return None

        lower_wick = min(c_open, c_close) - c_low
        upper_wick = c_high - max(c_open, c_close)

        # 1. Test Support (Bullish Bounce Setup)
        for s in supports:
            # Low dipped near or slightly below support (sweep), but closed back above support
            if abs(c_low - s) <= price_tolerance or (c_low <= s and c_close >= s):
                # Strong lower rejection wick >= 35% of candle range
                if (lower_wick / c_range) >= 0.35 and c_close > c_low:
                    return {
                        "type": "SUPPORT",
                        "level": s,
                        "wick_low": c_low,
                        "rejection_wick_pct": round(lower_wick / c_range, 2)
                    }

        # 2. Test Resistance (Bearish Rejection Setup)
        for r in resistances:
            # High pushed near or slightly above resistance (sweep), but closed back below resistance
            if abs(c_high - r) <= price_tolerance or (c_high >= r and c_close <= r):
                # Strong upper rejection wick >= 35% of candle range
                if (upper_wick / c_range) >= 0.35 and c_close < c_high:
                    return {
                        "type": "RESISTANCE",
                        "level": r,
                        "wick_high": c_high,
                        "rejection_wick_pct": round(upper_wick / c_range, 2)
                    }

        return None
