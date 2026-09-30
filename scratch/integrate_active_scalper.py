import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

with open("backtest/multi_strategy_backtester.py", "r", encoding="utf-8") as f:
    text = f.read()

# Add active_scalper_5 to run_all_strategies in both branches
old_silver_branch = '''            return {
                "apex_pro_5": self.run_apex_master_strategy('''

new_silver_branch = '''            return {
                "active_scalper_5": self.run_active_intraday_scalper(
                    symbol, candles,
                    name="⚡ Active Intraday Scalper (Daily 3-6 Trades | Strict $5 Risk | Silver)"
                ),
                "apex_pro_5": self.run_apex_master_strategy('''

assert old_silver_branch in text, "old_silver_branch not found"
text = text.replace(old_silver_branch, new_silver_branch, 1)

old_gold_branch = '''        else:
            return {
                "apex_pro_5": self.run_apex_master_strategy('''

new_gold_branch = '''        else:
            return {
                "active_scalper_5": self.run_active_intraday_scalper(
                    symbol, candles,
                    name="⚡ Active Intraday Scalper (Daily 3-6 Trades | Strict $5 Risk)"
                ),
                "apex_pro_5": self.run_apex_master_strategy('''

assert old_gold_branch in text, "old_gold_branch not found"
text = text.replace(old_gold_branch, new_gold_branch, 1)

# Now add run_active_intraday_scalper before def _compile
active_scalper_code = '''    def run_active_intraday_scalper(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
        name: str = "⚡ Active Intraday Scalper (Daily 3-6 Trades | Strict $5 Risk)",
        tp1_rr: float = 2.0,
        max_rr: float = 4.5,
        trail_mult: float = 1.2,
        del_th: float = 0.03,
        max_active_positions: int = 2,
        fixed_risk: float = TARGET_RISK_USD
    ) -> Dict[str, Any]:
        """
        High-Frequency Active Intraday Scalper:
        - Specifically optimized to generate 3 to 6 high-probability trades daily.
        - Evaluates high-liquidity session windows (London + NY overlap 12:30 to 23:45 UTC).
        - Allows up to 2 concurrent independent setups to maximize intraday opportunities.
        - Strict fixed $5.00 risk per trade with 100x leverage.
        - Scale-out mechanism: Cuts 50% at 1:2.0 R:R, locks SL to Breakeven (+0.15R buffer), trails runner with 1.2x ATR.
        """
        is_silver = "SLV" in symbol.upper()
        c_val = 1.0 if is_silver else 0.001
        min_dist = 0.25 if is_silver else 2.2
        dist_pad = 0.05 if is_silver else 0.5
        capital = self.initial_capital
        equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
        trades = []
        active_trades = []

        current_day = None
        day_cum_vol = 0.0
        day_cum_pv = 0.0
        day_prices = []
        bad_hours = {19, 22}

        for i in range(50, len(candles)):
            c = candles[i]
            curr = c["close"]
            ts = c["timestamp"]
            bar_time = datetime.fromtimestamp(ts)

            if bar_time.weekday() in (5, 6):
                continue

            hm = bar_time.strftime("%H:%M")
            if not ("12:30" <= hm <= "23:45"):
                continue

            day_str = bar_time.strftime("%Y-%m-%d")
            typ_p = (c["high"] + c["low"] + c["close"]) / 3.0
            v = max(1.0, c.get("volume", 1.0))

            if day_str != current_day:
                current_day = day_str
                day_cum_vol = 0.0
                day_cum_pv = 0.0
                day_prices = []

            day_cum_vol += v
            day_cum_pv += (typ_p * v)
            day_prices.append(typ_p)
            vwap = day_cum_pv / day_cum_vol
            mean_p = sum(day_prices) / len(day_prices)
            variance = sum((p - mean_p)**2 for p in day_prices) / len(day_prices)
            stdev = max(0.1 if is_silver else 1.0, variance**0.5)

            upper_vwap = vwap + (1.7 * stdev)
            lower_vwap = vwap - (1.7 * stdev)

            # Manage active trades
            still_active = []
            for at in active_trades:
                side = at["side"]
                entry = at["entry_price"]
                dist = at["dist"]
                lots = at["lots"]
                half_lots = max(1, lots // 2)

                if side == "BUY":
                    if c["high"] > at["highest"]:
                        at["highest"] = c["high"]
                    gain_r = (at["highest"] - entry) / dist

                    if not at["tp1_hit"] and gain_r >= tp1_rr:
                        at["tp1_hit"] = True
                        tp1_p = round(entry + tp1_rr * dist, 3 if is_silver else 2)
                        pnl_half = (half_lots * c_val * (tp1_p - entry)) - (half_lots * c_val * tp1_p * self.maker_fee_pct * 2)
                        at["booked_pnl"] = pnl_half
                        capital += pnl_half
                        at["stop_loss"] = max(at["stop_loss"], round(entry + 0.15 * dist, 3 if is_silver else 2))

                    if at["tp1_hit"] and gain_r >= 2.0:
                        new_sl = round(at["highest"] - (trail_mult * dist), 3 if is_silver else 2)
                        if new_sl > at["stop_loss"]:
                            at["stop_loss"] = new_sl

                    hit_sl = c["low"] <= at["stop_loss"]
                    hit_tp = c["high"] >= round(entry + max_rr * dist, 3 if is_silver else 2)

                    if hit_sl or hit_tp:
                        exit_price = round(entry + max_rr * dist, 3 if is_silver else 2) if hit_tp else at["stop_loss"]
                        rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                        diff = exit_price - entry
                        rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * self.maker_fee_pct * 2)
                        total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                        capital += rem_pnl
                        equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                        rr_final = round((exit_price - entry) / dist, 1) if not at["tp1_hit"] else round((tp1_rr * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                        at.update({
                            "exit_price": exit_price,
                            "pnl_usd": total_pnl,
                            "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                            "status": "CLOSED",
                            "rr_achieved": rr_final,
                            "orderflow_notes": f"Active Scalp ({hm} UTC) | Scalp TP1 @ 1:{tp1_rr} (+${round(at['booked_pnl'], 2)}) | Trailed to ${exit_price}" if at["tp1_hit"] else f"Stopped out before 1:{tp1_rr}"
                        })
                        trades.append(at)
                    else:
                        still_active.append(at)

                else: # SELL
                    if c["low"] < at["lowest"]:
                        at["lowest"] = c["low"]
                    gain_r = (entry - at["lowest"]) / dist

                    if not at["tp1_hit"] and gain_r >= tp1_rr:
                        at["tp1_hit"] = True
                        tp1_p = round(entry - tp1_rr * dist, 3 if is_silver else 2)
                        pnl_half = (half_lots * c_val * (entry - tp1_p)) - (half_lots * c_val * tp1_p * self.maker_fee_pct * 2)
                        at["booked_pnl"] = pnl_half
                        capital += pnl_half
                        at["stop_loss"] = min(at["stop_loss"], round(entry - 0.15 * dist, 3 if is_silver else 2))

                    if at["tp1_hit"] and gain_r >= 2.0:
                        new_sl = round(at["lowest"] + (trail_mult * dist), 3 if is_silver else 2)
                        if new_sl < at["stop_loss"]:
                            at["stop_loss"] = new_sl

                    hit_sl = c["high"] >= at["stop_loss"]
                    hit_tp = c["low"] <= round(entry - max_rr * dist, 3 if is_silver else 2)

                    if hit_sl or hit_tp:
                        exit_price = round(entry - max_rr * dist, 3 if is_silver else 2) if hit_tp else at["stop_loss"]
                        rem_lots = (lots - half_lots) if at["tp1_hit"] else lots
                        diff = entry - exit_price
                        rem_pnl = (rem_lots * c_val * diff) - (rem_lots * c_val * exit_price * self.maker_fee_pct * 2)
                        total_pnl = round(at["booked_pnl"] + rem_pnl, 2)
                        capital += rem_pnl
                        equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                        rr_final = round((entry - exit_price) / dist, 1) if not at["tp1_hit"] else round((tp1_rr * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                        at.update({
                            "exit_price": exit_price,
                            "pnl_usd": total_pnl,
                            "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if at["tp1_hit"] else "SL",
                            "status": "CLOSED",
                            "rr_achieved": rr_final,
                            "orderflow_notes": f"Active Scalp ({hm} UTC) | Scalp TP1 @ 1:{tp1_rr} (+${round(at['booked_pnl'], 2)}) | Trailed to ${exit_price}" if at["tp1_hit"] else f"Stopped out before 1:{tp1_rr}"
                        })
                        trades.append(at)
                    else:
                        still_active.append(at)

            active_trades = still_active

            # Entry logic
            if len(active_trades) < max_active_positions and (bar_time.hour not in bad_hours):
                sub = candles[i-20:i]
                hi8 = max(x["high"] for x in sub[-8:])
                lo8 = min(x["low"] for x in sub[-8:])
                hi12 = max(x["high"] for x in sub[-12:])
                lo12 = min(x["low"] for x in sub[-12:])

                delta = c.get("delta", 0.0)
                vol = max(1.0, c.get("volume", 1.0))
                delta_ratio = delta / vol

                sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
                sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)

                vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
                vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

                absorb_buy = (c["low"] <= lo12 * 1.0003) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
                absorb_sell = (c["high"] >= hi12 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

                if i >= 100:
                    ema100 = sum(x["close"] for x in candles[i-100:i]) / 100.0
                    macro_bull = (curr > ema100)
                    macro_bear = (curr < ema100)
                else:
                    macro_bull = macro_bear = True

                buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
                sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

                is_buy = (buy_score >= 1) and (sell_score == 0)
                is_sell = (sell_score >= 1) and (buy_score == 0)

                if is_buy or is_sell:
                    side = "BUY" if is_buy else "SELL"
                    if not any(at["side"] == side for at in active_trades):
                        score = buy_score if is_buy else sell_score
                        is_high_conv = (score >= 2)

                        dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                        sl_price = round(curr - dist if is_buy else curr + dist, 3 if is_silver else 2)
                        lots = max(2, int(round(fixed_risk / (dist * c_val))))
                        notional = lots * c_val * curr

                        active_trades.append({
                            "id": f"ACT_{symbol}_{c['timestamp']}_{len(active_trades)}",
                            "symbol": symbol,
                            "side": side,
                            "entry_price": curr,
                            "stop_loss": sl_price,
                            "take_profit": round(curr + (dist * max_rr) if is_buy else curr - (dist * max_rr), 3 if is_silver else 2),
                            "dist": dist,
                            "highest": curr,
                            "lowest": curr,
                            "lots": lots,
                            "notional_usd": round(notional, 2),
                            "margin_usd": round(notional / 100.0, 2),
                            "leverage": 100,
                            "risk_usd": fixed_risk,
                            "conviction_stars": 5.0 if is_high_conv else 4.0,
                            "strategy_name": name,
                            "tp1_rr": tp1_rr,
                            "max_rr": max_rr,
                            "trail_mult": trail_mult,
                            "tp1_hit": False,
                            "booked_pnl": 0.0,
                            "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "setup_type": "5-Star Multi-Alpha" if is_high_conv else "4-Star Scalp"
                        })

        return self._compile(capital, equity_curve, trades, name)

'''

text = text.replace("    def _compile(", active_scalper_code + "    def _compile(")

with open("backtest/multi_strategy_backtester.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Integrated run_active_intraday_scalper into multi_strategy_backtester.py successfully!")
