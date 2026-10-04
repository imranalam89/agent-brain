from typing import List, Dict, Any, Tuple, Optional
import math
from datetime import datetime

class DynamicTradeManager:
    """
    Institutional Context-Aware Dynamic Trade Management Engine:
    Continuously evaluates Order Flow and Support/Resistance (S/R) levels in real-time
    between 1:1 and 1:3 Risk-to-Reward (R:R).

    Rules:
    1. At 1:1 R:R Target (Default Action):
       - Full Hold Rule: If Order Flow is strongly aligned and no major S/R barriers exist
         between 1:1 and 1:3 R:R, hold 100% position to maximize run-up toward 1:2 and 1:3.
       - Early Partial Booking Triggers:
         * Book 50% profit at 1:1 if upcoming major S/R level detected directly ahead,
           or if Order Flow signals immediate potential reversal (CVD divergence, delta exhaust, heavy opposing DOM).
         * S/R Rejection Trigger: If price moves past 1:1 (~1:1.2 R:R), gets rejected by an S/R level,
           and pulls back toward entry, immediately book 50% profit.
         * Entry Retracement Exception: If price makes a normal retracement to retest entry S/R zone,
           do NOT move SL to BE prematurely. Keep original SL intact to avoid noise shakeouts.
    2. At 1:1.5 to 1:3 R:R Targets:
       - Context-Based Partial Exit: Once price reaches 1:1.5, 1:2, or 1:3 R:R, evaluate S/R and Order Flow
         to book 50% profit (if not already booked).
       - Stop-Loss Trailing: Immediately after booking 50%, trail remaining 50% SL to BE or lock in extra
         profit behind key market structural levels and Order Flow expansion.
    """

    def __init__(self):
        pass

    def extract_sr_levels(
        self,
        candles: List[Dict[str, Any]],
        lookback: int = 50,
        cluster_tol_pct: float = 0.0025
    ) -> Dict[str, Any]:
        """
        Identifies key Support & Resistance levels from recent candle history:
        - Pivot swing highs and swing lows (3-bar swing pivots)
        - Session VWAP and VWAP +/- 1.5, 2.0 sigma bands
        - Clustered horizontal structural zones
        """
        if len(candles) < 15:
            return {"resistances": [], "supports": [], "vwap": None, "pivot_highs": [], "pivot_lows": []}

        window = candles[-lookback:] if len(candles) > lookback else candles
        highs = [float(c["high"]) for c in window]
        lows = [float(c["low"]) for c in window]
        closes = [float(c["close"]) for c in window]

        # 1. Swing high/low pivots
        pivot_highs = []
        pivot_lows = []
        for i in range(2, len(window) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                pivot_highs.append(highs[i])
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                pivot_lows.append(lows[i])

        # 2. VWAP and Standard Deviation Bands
        cum_vol = 0.0
        cum_pv = 0.0
        prices = []
        for c in window:
            v = max(1.0, float(c.get("volume", 1.0)))
            typ = (float(c["high"]) + float(c["low"]) + float(c["close"])) / 3.0
            cum_vol += v
            cum_pv += (typ * v)
            prices.append(typ)

        vwap = (cum_pv / cum_vol) if cum_vol > 0 else closes[-1]
        mean_p = sum(prices) / len(prices)
        variance = sum((p - mean_p) ** 2 for p in prices) / len(prices)
        stdev = max(0.01, variance ** 0.5)

        upper_vwap_15 = vwap + (1.5 * stdev)
        lower_vwap_15 = vwap - (1.5 * stdev)
        upper_vwap_20 = vwap + (2.0 * stdev)
        lower_vwap_20 = vwap - (2.0 * stdev)

        # Merge resistance candidates (pivots above, VWAP upper bands)
        raw_res = pivot_highs + [upper_vwap_15, upper_vwap_20]
        raw_sup = pivot_lows + [lower_vwap_15, lower_vwap_20]

        # Cluster levels within tolerance
        def cluster_levels(levels: List[float]) -> List[float]:
            if not levels:
                return []
            sorted_lvls = sorted(levels)
            clustered = []
            curr_cluster = [sorted_lvls[0]]
            for lvl in sorted_lvls[1:]:
                if (lvl - curr_cluster[-1]) / curr_cluster[-1] <= cluster_tol_pct:
                    curr_cluster.append(lvl)
                else:
                    clustered.append(sum(curr_cluster) / len(curr_cluster))
                    curr_cluster = [lvl]
            if curr_cluster:
                clustered.append(sum(curr_cluster) / len(curr_cluster))
            return clustered

        return {
            "resistances": cluster_levels(raw_res),
            "supports": cluster_levels(raw_sup),
            "vwap": vwap,
            "upper_vwap_15": upper_vwap_15,
            "lower_vwap_15": lower_vwap_15,
            "pivot_highs": sorted(pivot_highs),
            "pivot_lows": sorted(pivot_lows),
            "recent_swing_high": max(highs[-10:]) if len(highs) >= 10 else max(highs),
            "recent_swing_low": min(lows[-10:]) if len(lows) >= 10 else min(lows)
        }

    def check_upcoming_sr_barrier(
        self,
        side: str,
        current_price: float,
        dist: float,
        target_3r_price: float,
        sr_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[float], str]:
        """
        Checks if a significant Support/Resistance barrier exists directly ahead between 1:1 and 1:3 R:R.
        """
        if side == "BUY":
            # For a Long trade, look for resistance levels between current price and 1:3 target
            barriers = [r for r in sr_data.get("resistances", []) if current_price <= r <= target_3r_price + (0.1 * dist)]
            # If there is a barrier within 0.4R of current price (imminent barrier):
            imminent = [r for r in barriers if abs(r - current_price) <= (0.45 * dist)]
            if imminent:
                lvl = imminent[0]
                return True, lvl, f"Major Resistance Barrier detected directly ahead at ${lvl:,.2f}"
        else: # SELL
            barriers = [s for s in sr_data.get("supports", []) if target_3r_price - (0.1 * dist) <= s <= current_price]
            imminent = [s for s in barriers if abs(current_price - s) <= (0.45 * dist)]
            if imminent:
                lvl = imminent[0]
                return True, lvl, f"Major Support Barrier detected directly ahead at ${lvl:,.2f}"

        return False, None, "Clear path: No major upcoming S/R barriers between 1:1 and 1:3 R:R"

    def check_sr_rejection(
        self,
        side: str,
        peak_rr: float,
        gain_rr: float,
        current_price: float,
        current_bar: Dict[str, Any],
        sr_data: Dict[str, Any],
        dist: float
    ) -> Tuple[bool, str]:
        """
        S/R Rejection Trigger:
        If price moves past 1:1 (reaches ~1:1.2 R:R), gets rejected by an S/R level,
        and starts pulling back toward entry (by >= 0.22R), immediately book 50% profit.
        """
        if peak_rr < 1.18:
            return False, "Not past ~1:1.2 R:R yet"

        pullback_r = peak_rr - gain_rr
        if pullback_r < 0.22:
            return False, "No significant pullback from peak"

        c_high = float(current_bar.get("high", current_price))
        c_low = float(current_bar.get("low", current_price))
        c_open = float(current_bar.get("open", current_price))
        c_close = float(current_bar.get("close", current_price))
        bar_range = max(0.001, c_high - c_low)

        if side == "BUY":
            upper_wick = c_high - max(c_open, c_close)
            wick_ratio = upper_wick / bar_range
            peak_price = current_price + (pullback_r * dist)
            near_res = any(abs(r - peak_price) <= (0.25 * dist) for r in sr_data.get("resistances", []))
            if near_res and (wick_ratio >= 0.25 or pullback_r >= 0.25):
                return True, f"S/R Rejection: Reached {peak_rr:.1f}R, rejected by Resistance with {int(wick_ratio*100)}% upper wick, pulled back by {pullback_r:.2f}R"
        else: # SELL
            lower_wick = min(c_open, c_close) - c_low
            wick_ratio = lower_wick / bar_range
            peak_price = current_price - (pullback_r * dist)
            near_sup = any(abs(s - peak_price) <= (0.25 * dist) for s in sr_data.get("supports", []))
            if near_sup and (wick_ratio >= 0.25 or pullback_r >= 0.25):
                return True, f"S/R Rejection: Reached {peak_rr:.1f}R, rejected by Support with {int(wick_ratio*100)}% lower wick, pulled back by {pullback_r:.2f}R"

        return False, "No S/R rejection"

    def check_orderflow_reversal(
        self,
        side: str,
        current_bar: Dict[str, Any],
        recent_candles: List[Dict[str, Any]],
        dom_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """
        Evaluates whether Order Flow signals an immediate potential reversal:
        - Opposing DOM book imbalance >= 1.8x
        - Opposing delta surge / aggressive selling on long or buying on short
        - CVD divergence against the position
        """
        # 1. DOM Imbalance check
        if dom_data:
            dominant = dom_data.get("dominant_side", "NEUTRAL")
            if side == "BUY" and dominant == "SELLERS":
                ratio = dom_data.get("ask_imbalance_ratio", 1.0)
                if ratio >= 1.8:
                    return True, f"Order Flow Reversal: Heavy DOM Ask Imbalance ({ratio:.1f}x sellers dominating book)"
            elif side == "SELL" and dominant == "BUYERS":
                ratio = dom_data.get("bid_imbalance_ratio", 1.0)
                if ratio >= 1.8:
                    return True, f"Order Flow Reversal: Heavy DOM Bid Imbalance ({ratio:.1f}x buyers dominating book)"

        # 2. Candle Delta check
        delta = float(current_bar.get("delta", 0.0))
        vol = max(1.0, float(current_bar.get("volume", 1.0)))
        delta_pct = delta / vol

        if side == "BUY" and delta_pct <= -0.40 and current_bar.get("close", 0) < current_bar.get("open", 0):
            return True, f"Order Flow Reversal: Heavy aggressive selling delta ({int(delta_pct*100)}% sell volume)"
        elif side == "SELL" and delta_pct >= 0.40 and current_bar.get("close", 0) > current_bar.get("open", 0):
            return True, f"Order Flow Reversal: Heavy aggressive buying delta (+{int(delta_pct*100)}% buy volume)"

        # 3. CVD Divergence check over last 8 candles
        if len(recent_candles) >= 8:
            window = recent_candles[-8:]
            p_highs = [float(c["high"]) for c in window]
            p_lows = [float(c["low"]) for c in window]
            deltas = [float(c.get("delta", 0.0)) for c in window]
            cvd = []
            cum = 0.0
            for d in deltas:
                cum += d
                cvd.append(cum)

            if side == "BUY":
                # Price higher high but CVD lower high = Buyer exhaustion
                if p_highs[-1] >= max(p_highs[:-1]) and cvd[-1] < max(cvd[:-1]) - 10:
                    return True, "Order Flow Reversal: Bearish CVD Divergence (Buyer exhaustion at highs)"
            else:
                # Price lower low but CVD higher low = Seller exhaustion
                if p_lows[-1] <= min(p_lows[:-1]) and cvd[-1] > min(cvd[:-1]) + 10:
                    return True, "Order Flow Reversal: Bullish CVD Divergence (Seller exhaustion at lows)"

        return False, "Order Flow is aligned or neutral"

    def check_entry_retracement_exception(
        self,
        side: str,
        entry_price: float,
        current_price: float,
        dist: float,
        sr_data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Entry Retracement Exception (SL Rule):
        If price is making a normal retracement to retest entry (due to an S/R level near the entry zone),
        do NOT move SL to Break-Even prematurely. Keep the original Stop-Loss intact so the trade isn't
        closed out on entry noise before moving to target.
        """
        # Retracement zone: price within -0.15R to +0.35R of entry
        if side == "BUY":
            gain_rr = (current_price - entry_price) / dist
            if -0.20 <= gain_rr <= 0.40:
                # Check if there is an S/R level near entry (+/- 0.35R)
                supports = sr_data.get("supports", [])
                pivots = sr_data.get("pivot_lows", [])
                near_sr = any(abs(s - entry_price) <= (0.40 * dist) for s in (supports + pivots))
                if near_sr:
                    return True, f"Entry Retracement Retest: Price (${current_price:,.2f}) retesting entry support zone (${entry_price:,.2f}). Hold original SL to prevent noise shakeout."
        else: # SELL
            gain_rr = (entry_price - current_price) / dist
            if -0.20 <= gain_rr <= 0.40:
                resistances = sr_data.get("resistances", [])
                pivots = sr_data.get("pivot_highs", [])
                near_sr = any(abs(r - entry_price) <= (0.40 * dist) for r in (resistances + pivots))
                if near_sr:
                    return True, f"Entry Retracement Retest: Price (${current_price:,.2f}) retesting entry resistance zone (${entry_price:,.2f}). Hold original SL to prevent noise shakeout."

        return False, "Not an entry retracement zone"

    def evaluate_position(
        self,
        pos: Dict[str, Any],
        current_price: float,
        current_bar: Dict[str, Any],
        recent_candles: List[Dict[str, Any]],
        dom_data: Optional[Dict[str, Any]] = None,
        decimals: int = 2
    ) -> Dict[str, Any]:
        """
        Full Context-Aware Dynamic Trade Management Decision Engine.
        Called on every cycle/candle to decide whether to:
        - HOLD_FULL_RUNNER: Hold 100% position across 1:1 toward 1:2 / 1:3
        - BOOK_50_PERCENT: Scale out 50% due to upcoming S/R, S/R rejection, or OF reversal
        - TRAIL_SL: Trail remaining 50% SL to BE or lock in profit behind structural levels
        - HOLD_ORIGINAL_SL: Maintain initial SL during entry zone retests
        - CLOSE_FULL: Hit max runner target or trailing stop
        """
        side = pos["side"]
        entry = float(pos["entry_price"])
        dist = float(pos["dist"])
        orig_sl = float(pos.get("orig_stop_loss", pos["stop_loss"]))
        curr_sl = float(pos["stop_loss"])
        tp1_hit = bool(pos.get("tp1_hit", False))
        lots = int(pos["lots"])
        half_lots = int(pos.get("half_lots", max(1, lots // 2)))

        # Update high/low watermark
        if side == "BUY":
            highest = max(float(pos.get("highest_price", entry)), float(current_bar.get("high", current_price)))
            pos["highest_price"] = highest
            gain_rr = (current_price - entry) / dist
            peak_rr = (highest - entry) / dist
            target_3r = round(entry + (3.0 * dist), decimals)
        else: # SELL
            lowest = min(float(pos.get("lowest_price", entry)), float(current_bar.get("low", current_price)))
            pos["lowest_price"] = lowest
            gain_rr = (entry - current_price) / dist
            peak_rr = (entry - lowest) / dist
            target_3r = round(entry - (3.0 * dist), decimals)

        # Sanity check: Ignore zero or wildly anomalous price ticks (protect against API hiccups)
        if current_price <= 0 or current_price < (0.4 * entry) or current_price > (2.5 * entry):
            return {
                "action": "HOLD_POSITION",
                "reason": "Anomalous or zero mark price detected. Position held securely on exchange.",
                "book_partial": False,
                "trail_sl": False,
                "new_sl": curr_sl,
                "gain_rr": 0.0,
                "peak_rr": 0.0
            }

        # 1. Stop Loss Check
        is_sl_hit = (current_price <= curr_sl) if side == "BUY" else (current_price >= curr_sl)
        if is_sl_hit:
            return {
                "action": "CLOSE_FULL",
                "reason": "STOP_LOSS" if not tp1_hit else "TRAILING_STOP",
                "exit_price": curr_sl,
                "book_partial": False,
                "trail_sl": False,
                "new_sl": curr_sl,
                "gain_rr": gain_rr,
                "peak_rr": peak_rr
            }

        # 2. Extract real-time S/R levels
        sr_data = self.extract_sr_levels(recent_candles)

        # 3. Check Entry Retracement Exception (SL Rule)
        is_retest, retest_reason = self.check_entry_retracement_exception(side, entry, current_price, dist, sr_data)
        if is_retest and not tp1_hit:
            # Strictly preserve original SL! Do NOT move to BE on noise!
            return {
                "action": "HOLD_ORIGINAL_SL",
                "reason": retest_reason,
                "book_partial": False,
                "trail_sl": False,
                "new_sl": orig_sl,
                "gain_rr": gain_rr,
                "peak_rr": peak_rr
            }

        # 4. Phase 1 & 2: Apex Grandmaster Continuous Trailing (1:10R to 1:40R) - Zero 50% Cut
        # Step 1: Breakeven Stop Loss Lock (+0.15R buffer to cover all exchange fees)
        # Gold/Silver Fast Breakeven Edge: lock BE at +1.0R MFE to protect wicks
        is_metal = ("XAUT" in str(pos.get("symbol", "")).upper() or "SLV" in str(pos.get("symbol", "")).upper())
        be_trigger = 1.0 if is_metal else 1.5

        if peak_rr >= be_trigger and not pos.get("be_locked"):
            pos["be_locked"] = True
            be_sl = round(entry + (0.15 * dist), decimals) if side == "BUY" else round(entry - (0.15 * dist), decimals)
            new_sl = max(curr_sl, be_sl) if side == "BUY" else min(curr_sl, be_sl)
            pos["stop_loss"] = new_sl
            return {
                "action": "LOCK_BREAKEVEN",
                "trigger": "BREAKEVEN_LOCKED",
                "reason": f"Breakeven locked (+0.15R buffer covering fees at {peak_rr:.1f}R MFE). Position is 100% risk-free.",
                "book_partial": False,
                "trail_sl": True,
                "new_sl": new_sl,
                "gain_rr": gain_rr,
                "peak_rr": peak_rr
            }

        # Step 2: Progressive Milestone Trailing (100% position maintained)
        new_sl = curr_sl
        if pos.get("be_locked"):
            # Milestone locks
            if peak_rr >= 3.5:
                lock_r = round(entry + 1.5 * dist, decimals) if side == "BUY" else round(entry - 1.5 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)
            if peak_rr >= 5.0:
                lock_r = round(entry + 3.0 * dist, decimals) if side == "BUY" else round(entry - 3.0 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)
            if peak_rr >= 8.0:
                lock_r = round(entry + 5.5 * dist, decimals) if side == "BUY" else round(entry - 5.5 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)
            if peak_rr >= 10.0:
                lock_r = round(entry + 7.5 * dist, decimals) if side == "BUY" else round(entry - 7.5 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)
            if peak_rr >= 15.0:
                lock_r = round(entry + 11.5 * dist, decimals) if side == "BUY" else round(entry - 11.5 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)
            if peak_rr >= 20.0:
                lock_r = round(entry + 15.5 * dist, decimals) if side == "BUY" else round(entry - 15.5 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)
            if peak_rr >= 25.0:
                lock_r = round(entry + 20.0 * dist, decimals) if side == "BUY" else round(entry - 20.0 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)
            if peak_rr >= 30.0:
                lock_r = round(entry + 24.5 * dist, decimals) if side == "BUY" else round(entry - 24.5 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)
            if peak_rr >= 35.0:
                lock_r = round(entry + 29.0 * dist, decimals) if side == "BUY" else round(entry - 29.0 * dist, decimals)
                new_sl = max(new_sl, lock_r) if side == "BUY" else min(new_sl, lock_r)

            # S/R Swing Pivot Trailing (15m structural trail)
            if peak_rr >= 2.8:
                if side == "BUY":
                    recent_swing = sr_data.get("recent_swing_low", entry)
                    trail_level = max(recent_swing - (0.05 * dist), highest - (1.2 * dist))
                    new_sl = max(new_sl, round(trail_level, decimals))
                else: # SELL
                    recent_swing = sr_data.get("recent_swing_high", entry)
                    trail_level = min(recent_swing + (0.05 * dist), lowest + (1.2 * dist))
                    new_sl = min(new_sl, round(trail_level, decimals))

            pos["stop_loss"] = new_sl

        # Step 3: Maximum 40.0R Apex Expansion Target Exit
        max_rr = float(pos.get("max_rr", 40.0))
        max_target = round(entry + (max_rr * dist), decimals) if side == "BUY" else round(entry - (max_rr * dist), decimals)
        is_max_hit = (current_price >= max_target) if side == "BUY" else (current_price <= max_target)
        if is_max_hit:
            return {
                "action": "CLOSE_FULL",
                "reason": f"APEX_GRANDMASTER_40R_TARGET (+{max_rr:.0f}R | $5 Risk)",
                "exit_price": max_target,
                "book_partial": False,
                "trail_sl": False,
                "new_sl": new_sl,
                "gain_rr": gain_rr,
                "peak_rr": peak_rr
            }

        return {
            "action": "HOLD_POSITION",
            "reason": f"⚡ Apex Runner Trailing Active: Gain {gain_rr:.1f}R (Peak: {peak_rr:.1f}R). SL @ ${new_sl:,.2f}.",
            "book_partial": False,
            "trail_sl": (new_sl != curr_sl),
            "new_sl": new_sl,
            "gain_rr": gain_rr,
            "peak_rr": peak_rr
        }
