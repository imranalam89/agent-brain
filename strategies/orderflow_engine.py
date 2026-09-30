from typing import List, Dict, Any, Tuple

class OrderFlowEngine:
    """
    Microstructure & Order Flow Engine:
    - Analyzes DOM (Depth of Market) bid/ask liquidity imbalance & iceberg walls
    - Calculates CVD (Cumulative Volume Delta) and Delta Divergence
    - Detects Institutional Absorption at Key S/R Levels
    - Detects Liquidity Sweeps / Stop Hunts (Institutional Spring / Upthrust)
    """
    def __init__(self, min_imbalance_ratio: float = 1.8):
        self.min_imbalance = min_imbalance_ratio

    def analyze_dom(self, bids: List[List[float]], asks: List[List[float]]) -> Dict[str, Any]:
        """
        Analyzes Level 2 Order Book Depth.
        Each entry is [price, size].
        """
        total_bid_size = sum(float(b[1]) for b in bids) if bids else 0.0
        total_ask_size = sum(float(a[1]) for a in asks) if asks else 0.0

        bid_imbalance = (total_bid_size / total_ask_size) if total_ask_size > 0 else 1.0
        ask_imbalance = (total_ask_size / total_bid_size) if total_bid_size > 0 else 1.0

        dominant_side = "NEUTRAL"
        if bid_imbalance >= self.min_imbalance:
            dominant_side = "BUYERS"
        elif ask_imbalance >= self.min_imbalance:
            dominant_side = "SELLERS"

        return {
            "total_bid_size": round(total_bid_size, 3),
            "total_ask_size": round(total_ask_size, 3),
            "bid_imbalance_ratio": round(bid_imbalance, 2),
            "ask_imbalance_ratio": round(ask_imbalance, 2),
            "dominant_side": dominant_side
        }

    def detect_liquidity_sweep(
        self,
        current_candle: Dict[str, Any],
        recent_candles: List[Dict[str, Any]],
        lookback: int = 20
    ) -> Tuple[bool, str, str]:
        """
        Detects an Institutional Liquidity Sweep (Stop Hunt / Fakeout):
        - Bullish Sweep (Spring): Price spikes below the swing low of the last `lookback` candles,
          triggers retail sell stops, but immediately closes BACK INSIDE the range with a long lower wick.
        - Bearish Sweep (Upthrust): Price spikes above the swing high of the last `lookback` candles,
          triggers retail buy stops/breakouts, but closes BACK INSIDE the range with a long upper wick.
        Returns: (is_sweep, sweep_type: 'BULLISH'/'BEARISH'/'NONE', details)
        """
        if len(recent_candles) < lookback:
            return False, "NONE", "Insufficient candle history"

        window = recent_candles[-lookback:]
        swing_high = max(c["high"] for c in window)
        swing_low = min(c["low"] for c in window)

        c_high = current_candle["high"]
        c_low = current_candle["low"]
        c_close = current_candle["close"]
        c_open = current_candle["open"]
        total_range = max(0.1, c_high - c_low)

        upper_wick = c_high - max(c_open, c_close)
        lower_wick = min(c_open, c_close) - c_low
        delta = current_candle.get("delta", 0.0)

        # Bullish Stop Hunt / Liquidity Sweep
        if c_low < swing_low and c_close > swing_low:
            if (lower_wick / total_range) >= 0.35:
                return (
                    True,
                    "BULLISH",
                    f"Institutional Liquidity Sweep: Price pierced swing low ({swing_low:.2f}) to trigger stops, then reclaimed level with {int(lower_wick/total_range*100)}% rejection wick."
                )

        # Bearish Stop Hunt / Liquidity Sweep
        if c_high > swing_high and c_close < swing_high:
            if (upper_wick / total_range) >= 0.35:
                return (
                    True,
                    "BEARISH",
                    f"Institutional Liquidity Sweep: Price pierced swing high ({swing_high:.2f}) to trap breakout buyers, then rejected with {int(upper_wick/total_range*100)}% upper wick."
                )

        return False, "NONE", "No liquidity sweep"

    def detect_absorption(self, candle: Dict[str, Any], level_type: str) -> Tuple[bool, str]:
        """
        Detects if heavy aggressive market orders got absorbed by passive limit orders.
        - Bullish Absorption at Support: Strong negative delta or high volume, but candle has long lower wick and closes above support.
        - Bearish Absorption at Resistance: Strong positive delta, but candle has long upper wick and closes below resistance.
        """
        c_open = candle["open"]
        c_high = candle["high"]
        c_low = candle["low"]
        c_close = candle["close"]
        candle_range = c_high - c_low
        delta = candle.get("delta", 0.0)
        volume = max(1.0, candle.get("volume", 1.0))
        delta_pct = delta / volume

        if candle_range <= 0:
            return False, "Zero range"

        upper_wick = c_high - max(c_open, c_close)
        lower_wick = min(c_open, c_close) - c_low

        # Bullish absorption check at Support
        if level_type == "SUPPORT":
            if (lower_wick / candle_range) >= 0.30 and (delta_pct < 0 or c_close >= c_open):
                return True, f"Bullish Absorption: Aggressive market sellers absorbed by institutional bids ({int(lower_wick/candle_range*100)}% lower wick, delta {int(delta_pct*100)}%)."

        # Bearish absorption check at Resistance
        if level_type == "RESISTANCE":
            if (upper_wick / candle_range) >= 0.30 and (delta_pct > 0 or c_close <= c_open):
                return True, f"Bearish Absorption: Aggressive market buyers absorbed by institutional asks ({int(upper_wick/candle_range*100)}% upper wick, delta {int(delta_pct*100)}%)."

        return False, "No absorption"

    def calculate_cvd_divergence(
        self,
        candles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Detects CVD Divergence over the last 10 candles:
        - Bullish: Price lower low, but CVD higher low (sellers exhausting)
        - Bearish: Price higher high, but CVD lower high (buyers exhausting)
        """
        if len(candles) < 10:
            return {"divergence": "NONE", "details": "Insufficient candle history"}

        recent = candles[-10:]
        price_lows = [c["low"] for c in recent]
        price_highs = [c["high"] for c in recent]

        cvd = []
        running_delta = 0.0
        for c in recent:
            running_delta += c.get("delta", 0.0)
            cvd.append(running_delta)

        # Bullish divergence check
        if price_lows[-1] < min(price_lows[:-1]) and cvd[-1] > min(cvd[:-1]):
            return {
                "divergence": "BULLISH",
                "details": "Price made lower low, but CVD made higher low (Absorption / Seller Exhaustion)"
            }

        # Bearish divergence check
        if price_highs[-1] > max(price_highs[:-1]) and cvd[-1] < max(cvd[:-1]):
            return {
                "divergence": "BEARISH",
                "details": "Price made higher high, but CVD made lower high (Absorption / Buyer Exhaustion)"
            }

        return {"divergence": "NONE", "details": "No divergence"}
