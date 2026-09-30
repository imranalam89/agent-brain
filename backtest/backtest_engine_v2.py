import sys
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import math

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config.settings import ACCOUNT_CAPITAL_USD, LEVERAGE_MAP, CONTRACT_VALUES
from data.database import DatabaseManager
from execution.dynamic_trade_manager import DynamicTradeManager

class BacktestEngineV2:
    """
    Backtest Engine V2:
    Simulates institutional-grade multi-pair execution incorporating:
    - Dynamic Context-Aware Trade Management (S/R barriers, S/R rejection, Entry Retracement SL rule, 1:1 Full Hold, 1:1.5-1:3 Trailing)
    - Strict $5.00 Risk per trade & dynamic lot sizing
    - Explicit Fee Accounting:
      * Commissions (Delta maker fee 0.01% on entry & exit)
      * Spreads (0.01% average half-spread cost)
      * Funding / Swap (0.01% per 8hr hold duration)
    - Granular per-pair performance & joint portfolio aggregation
    """

    def __init__(self, db: DatabaseManager, initial_capital: float = ACCOUNT_CAPITAL_USD):
        self.db = db
        self.initial_capital = initial_capital
        self.dynamic_mgr = DynamicTradeManager()
        self.maker_fee_pct = 0.0001   # 0.01% Delta Maker fee
        self.spread_fee_pct = 0.0001  # 0.01% average half-spread
        self.funding_rate_8h = 0.0001 # 0.01% per 8-hour funding cycle

    def _get_params(self, symbol: str) -> Dict[str, Any]:
        s = symbol.upper()
        if "BTC" in s:
            return {
                "c_val": 0.001,
                "min_stop_dist": 220.0,
                "padding": 100.0,
                "sigma": 1.6,
                "decimals": 1,
                "leverage": 100,
                "is_crypto": True,
                "stdev_floor": 40.0
            }
        elif "ETH" in s:
            return {
                "c_val": 0.01,
                "min_stop_dist": 12.0,
                "padding": 5.0,
                "sigma": 1.6,
                "decimals": 2,
                "leverage": 100,
                "is_crypto": True,
                "stdev_floor": 1.5
            }
        elif "SLV" in s:
            return {
                "c_val": 0.1,
                "min_stop_dist": 0.40,
                "padding": 0.18,
                "sigma": 1.8,
                "decimals": 3,
                "leverage": 50,
                "is_crypto": False,
                "stdev_floor": 0.05
            }
        else: # XAUTUSD (Gold)
            return {
                "c_val": 0.001,
                "min_stop_dist": 5.0,
                "padding": 2.5,
                "sigma": 1.8,
                "decimals": 2,
                "leverage": 100,
                "is_crypto": False,
                "stdev_floor": 1.0
            }

    def run_symbol_backtest(
        self,
        symbol: str,
        candles_15m: List[Dict[str, Any]],
        fixed_risk_usd: float = 5.0
    ) -> Dict[str, Any]:
        """
        Runs full historical simulation on one instrument using Dynamic Trade Management
        and explicit fee accounting.
        """
        p = self._get_params(symbol)
        c_val = p["c_val"]
        min_stop = p["min_stop_dist"]
        pad = p["padding"]
        decimals = p["decimals"]
        sigma = p["sigma"]
        stdev_floor = p["stdev_floor"]
        leverage = p["leverage"]

        trades: List[Dict[str, Any]] = []
        active_pos: Optional[Dict[str, Any]] = None

        capital = self.initial_capital
        peak_capital = capital
        max_drawdown = 0.0

        current_day = None
        day_cum_vol = 0.0
        day_cum_pv = 0.0
        day_prices: List[float] = []

        # Fee accumulators for symbol
        total_commissions = 0.0
        total_spreads = 0.0
        total_funding = 0.0

        for i in range(50, len(candles_15m)):
            bar = candles_15m[i]
            prev_bars = candles_15m[max(0, i-50):i]
            curr_p = float(bar["close"])
            high_p = float(bar["high"])
            low_p = float(bar["low"])
            open_p = float(bar["open"])
            ts = bar["timestamp"]
            bar_time = datetime.fromtimestamp(ts)
            time_str = bar_time.strftime("%Y-%m-%d %H:%M:%S")
            day_str = bar_time.strftime("%Y-%m-%d")

            # Metals Weekend Lock
            if not p["is_crypto"] and bar_time.weekday() in (5, 6):
                continue

            # Day-based session VWAP tracking
            v = max(1.0, float(bar.get("volume", 1.0)))
            typ = (high_p + low_p + curr_p) / 3.0

            if day_str != current_day:
                current_day = day_str
                day_cum_vol = 0.0
                day_cum_pv = 0.0
                day_prices = []

            day_cum_vol += v
            day_cum_pv += (typ * v)
            day_prices.append(typ)

            vwap = day_cum_pv / day_cum_vol if day_cum_vol > 0 else curr_p
            mean_p = sum(day_prices) / len(day_prices)
            variance = sum((x - mean_p) ** 2 for x in day_prices) / len(day_prices)
            stdev = max(stdev_floor, variance ** 0.5)

            upper_band = vwap + (sigma * stdev)
            lower_band = vwap - (sigma * stdev)

            # =========================================================================
            # 1. MANAGE ACTIVE POSITION WITH DYNAMIC TRADE MANAGER
            # =========================================================================
            if active_pos is not None:
                side = active_pos["side"]
                entry = active_pos["entry_price"]
                dist = active_pos["dist"]
                lots = active_pos["lots"]
                half_lots = active_pos["half_lots"]

                # Step through intra-bar simulation (test extreme price touches)
                decision = self.dynamic_mgr.evaluate_position(
                    pos=active_pos,
                    current_price=curr_p,
                    current_bar=bar,
                    recent_candles=prev_bars,
                    dom_data=None,
                    decimals=decimals
                )

                action = decision["action"]

                # A. Handle Partial Scale-Out (50%)
                if decision.get("book_partial") and not active_pos["tp1_hit"]:
                    active_pos["tp1_hit"] = True
                    active_pos["partial_exit_price"] = curr_p
                    active_pos["partial_trigger"] = decision.get("trigger", "TARGET_MILESTONE")
                    active_pos["partial_reason"] = decision.get("reason", "")
                    active_pos["partial_time"] = time_str

                    # Calculate partial 50% gross and fees
                    half_diff = (curr_p - entry) if side == "BUY" else (entry - curr_p)
                    partial_gross = half_lots * c_val * half_diff
                    partial_comm = half_lots * c_val * curr_p * self.maker_fee_pct
                    partial_spread = half_lots * c_val * curr_p * self.spread_fee_pct

                    active_pos["partial_gross_pnl"] = partial_gross
                    active_pos["partial_comm"] = partial_comm
                    active_pos["partial_spread"] = partial_spread

                    # Stop-loss trailing after scale-out
                    be_sl = round(entry + (0.10 * dist), decimals) if side == "BUY" else round(entry - (0.10 * dist), decimals)
                    active_pos["stop_loss"] = be_sl
                    active_pos["remaining_lots"] = lots - half_lots

                # B. Handle Trailing Stop Adjustment
                if decision.get("trail_sl") and active_pos["tp1_hit"]:
                    new_sl = decision.get("new_sl")
                    if new_sl:
                        if side == "BUY" and new_sl > active_pos["stop_loss"]:
                            active_pos["stop_loss"] = new_sl
                            active_pos["trailing_reason"] = decision.get("reason", "")
                        elif side == "SELL" and new_sl < active_pos["stop_loss"]:
                            active_pos["stop_loss"] = new_sl
                            active_pos["trailing_reason"] = decision.get("reason", "")

                # C. Check if Position Closes (SL, Trailing Stop, or Max Runner Target)
                # Check intra-bar price extremes against stop loss or runner target
                sl_hit = (low_p <= active_pos["stop_loss"]) if side == "BUY" else (high_p >= active_pos["stop_loss"])
                max_target = round(entry + (3.5 * dist), decimals) if side == "BUY" else round(entry - (3.5 * dist), decimals)
                tp_hit = (high_p >= max_target) if side == "BUY" else (low_p <= max_target)

                if sl_hit or tp_hit or action == "CLOSE_FULL":
                    exit_price = max_target if tp_hit else active_pos["stop_loss"]
                    if action == "CLOSE_FULL" and not (sl_hit or tp_hit):
                        exit_price = decision.get("exit_price", curr_p)

                    close_reason = "RUNNER_MAX_TARGET_3.5R" if tp_hit else ("STOP_LOSS" if not active_pos["tp1_hit"] else "TRAILING_STOP")
                    if action == "CLOSE_FULL" and "RUNNER" in decision.get("reason", ""):
                        close_reason = "RUNNER_TARGET"

                    # Calculate hold duration and funding fees
                    entry_dt = datetime.strptime(active_pos["opened_at"], "%Y-%m-%d %H:%M:%S")
                    exit_dt = bar_time
                    hold_hours = max(0.25, (exit_dt - entry_dt).total_seconds() / 3600.0)

                    rem_lots = active_pos["remaining_lots"] if active_pos["tp1_hit"] else lots
                    rem_diff = (exit_price - entry) if side == "BUY" else (entry - exit_price)
                    rem_gross = rem_lots * c_val * rem_diff

                    entry_notional = lots * c_val * entry
                    exit_notional = (half_lots * c_val * active_pos.get("partial_exit_price", exit_price) + rem_lots * c_val * exit_price) if active_pos["tp1_hit"] else (lots * c_val * exit_price)

                    # Explicit Fee Calculation
                    # 1. Commissions: 0.01% on entry and exit
                    comm_entry = entry_notional * self.maker_fee_pct
                    comm_exit = exit_notional * self.maker_fee_pct
                    trade_commission = round(comm_entry + comm_exit, 4)

                    # 2. Spreads: 0.01% half spread on entry and exit
                    spread_entry = entry_notional * self.spread_fee_pct
                    spread_exit = exit_notional * self.spread_fee_pct
                    trade_spread = round(spread_entry + spread_exit, 4)

                    # 3. Funding / Financing: 0.01% per 8 hours
                    funding_cycles = hold_hours / 8.0
                    trade_funding = round(entry_notional * self.funding_rate_8h * funding_cycles, 4)

                    total_trade_fees = round(trade_commission + trade_spread + trade_funding, 4)

                    gross_pnl = round((active_pos.get("partial_gross_pnl", 0.0) + rem_gross), 4)
                    net_pnl = round(gross_pnl - total_trade_fees, 2)

                    capital += net_pnl
                    if capital > peak_capital:
                        peak_capital = capital
                    dd = peak_capital - capital
                    if dd > max_drawdown:
                        max_drawdown = dd

                    total_commissions += trade_commission
                    total_spreads += trade_spread
                    total_funding += trade_funding

                    closed_record = {
                        "id": f"BT2_{symbol}_{len(trades)+1}",
                        "symbol": symbol,
                        "side": side,
                        "entry_price": entry,
                        "exit_price": exit_price,
                        "stop_loss": active_pos["stop_loss"],
                        "initial_stop_loss": active_pos["orig_stop_loss"],
                        "dist": dist,
                        "lots": lots,
                        "notional_usd": round(entry_notional, 2),
                        "margin_usd": round(entry_notional / leverage, 2),
                        "leverage": leverage,
                        "risk_usd": fixed_risk_usd,
                        "gross_pnl_usd": round(gross_pnl, 2),
                        "commission_usd": round(trade_commission, 2),
                        "spread_cost_usd": round(trade_spread, 2),
                        "funding_cost_usd": round(trade_funding, 2),
                        "total_fees_usd": round(total_trade_fees, 2),
                        "pnl_usd": net_pnl, # Net PnL after all fees
                        "rr_achieved": round(gross_pnl / fixed_risk_usd, 2),
                        "opened_at": active_pos["opened_at"],
                        "closed_at": time_str,
                        "hold_duration_hours": round(hold_hours, 1),
                        "status": "CLOSED",
                        "close_reason": close_reason,
                        "tp1_hit": active_pos["tp1_hit"],
                        "partial_trigger": active_pos.get("partial_trigger", "NONE"),
                        "partial_reason": active_pos.get("partial_reason", ""),
                        "execution_type": "DYNAMIC_V2",
                        "strategy_name": f"Institutional Dynamic V2 ({symbol})",
                        "equity_after": round(capital, 2)
                    }
                    trades.append(closed_record)
                    active_pos = None
                continue

            # =========================================================================
            # 2. EVALUATE HIGH-PROBABILITY ENTRY SETUP (WHEN FLAT)
            # =========================================================================
            # Session filter (peak liquidity)
            hm = bar_time.strftime("%H:%M")
            if not ("12:30" <= hm <= "23:45"):
                continue

            # Confluence Entry Filter
            bad_hours = {19, 22} if not ("SLV" in symbol) else {16, 18, 19, 23}
            if bar_time.hour in bad_hours:
                continue

            sub = prev_bars[-20:] if len(prev_bars) >= 20 else prev_bars
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = float(bar.get("delta", 0.0))
            vol = max(1.0, float(bar.get("volume", 1.0)))
            delta_ratio = delta / vol
            del_th = 0.03

            sweep_buy = (low_p < lo8) and (curr_p > lo8) and (delta_ratio >= del_th)
            sweep_sell = (high_p > hi8) and (curr_p < hi8) and (delta_ratio <= -del_th)

            vwap_buy = (len(day_prices) >= 4) and (low_p <= lower_band) and (curr_p > open_p) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 4) and (high_p >= upper_band) and (curr_p < open_p) and (delta_ratio <= -del_th)

            absorb_buy = (low_p <= lo12 * 1.0003) and (delta_ratio >= del_th * 0.8) and (curr_p > open_p)
            absorb_sell = (high_p >= hi12 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (curr_p < open_p)

            ema100 = sum(x["close"] for x in prev_bars) / len(prev_bars) if prev_bars else curr_p
            macro_bull = (curr_p > ema100)
            macro_bear = (curr_p < ema100)

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            min_score = 3 if ("BTC" in symbol) else (2 if "ETH" in symbol else 1)

            # Anti-cascade and reversal confirmation checks
            p1 = prev_bars[-1]
            p2 = prev_bars[-2] if len(prev_bars) >= 2 else p1
            prev_bear_cascade = (p1["close"] < p1["open"]) and (p2["close"] < p2["open"])
            prev_bull_cascade = (p1["close"] > p1["open"]) and (p2["close"] > p2["open"])

            bar_range = max(0.01, high_p - low_p)
            lower_wick_ratio = (min(open_p, curr_p) - low_p) / bar_range
            upper_wick_ratio = (high_p - max(open_p, curr_p)) / bar_range

            buy_confirmed = (curr_p > open_p) or (lower_wick_ratio >= 0.28 and curr_p >= low_p + 0.40 * bar_range)
            buy_not_falling_knife = not (prev_bear_cascade and curr_p < open_p and lower_wick_ratio < 0.35)

            sell_confirmed = (curr_p < open_p) or (upper_wick_ratio >= 0.28 and curr_p <= high_p - 0.40 * bar_range)
            sell_not_rising_spike = not (prev_bull_cascade and curr_p > open_p and upper_wick_ratio < 0.35)

            is_buy = (buy_score >= min_score) and (sell_score == 0) and buy_confirmed and buy_not_falling_knife
            is_sell = (sell_score >= min_score) and (buy_score == 0) and sell_confirmed and sell_not_rising_spike

            sig_side = None
            if is_buy:
                sig_side = "BUY"
            elif is_sell:
                sig_side = "SELL"

            if not sig_side:
                continue

            # Calculate dynamic stop distance and size
            if sig_side == "BUY":
                recent_low = min(float(c["low"]) for c in prev_bars[-10:])
                stop_dist = max(min_stop, (curr_p - recent_low) + pad)
                sl_price = round(curr_p - stop_dist, decimals)
            else: # SELL
                recent_high = max(float(c["high"]) for c in prev_bars[-10:])
                stop_dist = max(min_stop, (recent_high - curr_p) + pad)
                sl_price = round(curr_p + stop_dist, decimals)

            # Solve lot size for strict fixed risk
            raw_lots = fixed_risk_usd / (stop_dist * c_val)
            lots = max(1, int(math.floor(raw_lots)))
            actual_risk = lots * c_val * stop_dist

            # Guard against excessive risk
            if actual_risk > (fixed_risk_usd * 1.35) and lots == 1:
                continue

            half_lots = max(1, lots // 2)

            active_pos = {
                "symbol": symbol,
                "side": sig_side,
                "entry_price": curr_p,
                "stop_loss": sl_price,
                "orig_stop_loss": sl_price,
                "dist": stop_dist,
                "lots": lots,
                "half_lots": half_lots,
                "remaining_lots": lots,
                "opened_at": time_str,
                "highest_price": curr_p,
                "lowest_price": curr_p,
                "tp1_hit": False,
                "partial_gross_pnl": 0.0,
                "partial_comm": 0.0,
                "partial_spread": 0.0
            }

        # Calculate performance statistics for this symbol
        wins = [t for t in trades if t["pnl_usd"] > 0]
        losses = [t for t in trades if t["pnl_usd"] < 0]
        even = [t for t in trades if t["pnl_usd"] == 0]
        total_trades = len(trades)
        win_rate = round((len(wins) / total_trades * 100), 1) if total_trades else 0.0

        gross_profit = round(sum(t["gross_pnl_usd"] for t in wins), 2)
        gross_loss = round(abs(sum(t["gross_pnl_usd"] for t in losses)), 2)
        net_profit = round(capital - self.initial_capital, 2)
        roi_pct = round((net_profit / self.initial_capital * 100), 1)
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        # Construct chronological equity curve
        eq_curve = [{"timestamp": candles_15m[0]["timestamp"], "equity": self.initial_capital, "net_pnl": 0.0}]
        running_eq = self.initial_capital
        for t in trades:
            running_eq += t["pnl_usd"]
            c_ts = int(datetime.strptime(t["closed_at"], "%Y-%m-%d %H:%M:%S").timestamp())
            eq_curve.append({
                "timestamp": c_ts,
                "equity": round(running_eq, 2),
                "net_pnl": t["pnl_usd"],
                "gross_pnl": t["gross_pnl_usd"]
            })

        return {
            "symbol": symbol,
            "strategy_name": f"Dynamic Execution V2 ({symbol})",
            "initial_capital": self.initial_capital,
            "final_capital": round(capital, 2),
            "net_pl": net_profit,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_commissions": round(total_commissions, 2),
            "total_spreads": round(total_spreads, 2),
            "total_funding": round(total_funding, 2),
            "total_fees": round(total_commissions + total_spreads + total_funding, 2),
            "roi_pct": roi_pct,
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "even": len(even),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_usd": round(max_drawdown, 2),
            "max_drawdown_pct": round((max_drawdown / peak_capital * 100), 1) if peak_capital > 0 else 0.0,
            "avg_trade_pnl": round(net_profit / total_trades, 2) if total_trades else 0.0,
            "trades": trades,
            "equity_curve": eq_curve
        }

    def run_joint_portfolio_backtest(
        self,
        symbols: List[str] = ["BTCUSD", "ETHUSD", "XAUTUSD", "SLVONUSD"]
    ) -> Dict[str, Any]:
        """
        Executes granular backtests for each asset, then builds the Joint Combined Portfolio
        with chronological trade ordering, multi-asset equity curve, daily calendar breakdown,
        and explicit fee transparency.
        """
        isolated_results: Dict[str, Any] = {}
        all_trades: List[Dict[str, Any]] = []

        print("\n================================================================================")
        print("  [BRAIN] RUNNING BACKTEST V2: CONTEXT-AWARE DYNAMIC EXECUTION & EXPLICIT FEES  ")
        print("================================================================================")

        for sym in symbols:
            candles = self.db.get_latest_candles(sym, "15m", limit=35000)
            print(f"[*] Processing {sym} ({len(candles):,} real historical 15m candles)...")
            res = self.symbol_backtest = self.run_symbol_backtest(sym, candles)
            isolated_results[sym] = res
            all_trades.extend(res["trades"])
            print(f"    -> {sym}: {res['total_trades']} trades | WR: {res['win_rate']}% | Gross: ${res['gross_profit'] - res['gross_loss']:+.2f} | Fees: -${res['total_fees']:.2f} | Net: ${res['net_pl']:+.2f} (PF: {res['profit_factor']})")

        # Sort all trades strictly chronologically across the entire portfolio
        all_trades.sort(key=lambda t: t["closed_at"])

        # Construct Combined Joint Portfolio Equity Curve
        combined_capital = self.initial_capital
        portfolio_peak = combined_capital
        portfolio_max_dd = 0.0
        combined_equity_curve = [{"timestamp": 0, "equity": combined_capital, "date": "Start"}]

        portfolio_gross_profit = 0.0
        portfolio_gross_loss = 0.0
        portfolio_commissions = 0.0
        portfolio_spreads = 0.0
        portfolio_funding = 0.0

        # Daily PnL Map for Calendar Heatmap
        daily_pnl_map: Dict[str, Dict[str, Any]] = {}

        for idx, t in enumerate(all_trades, 1):
            t["portfolio_trade_num"] = idx
            net_pnl = t["pnl_usd"]
            gross_pnl = t["gross_pnl_usd"]

            combined_capital += net_pnl
            t["portfolio_equity_after"] = round(combined_capital, 2)

            if combined_capital > portfolio_peak:
                portfolio_peak = combined_capital
            dd = portfolio_peak - combined_capital
            if dd > portfolio_max_dd:
                portfolio_max_dd = dd

            if gross_pnl > 0:
                portfolio_gross_profit += gross_pnl
            elif gross_pnl < 0:
                portfolio_gross_loss += abs(gross_pnl)

            portfolio_commissions += t["commission_usd"]
            portfolio_spreads += t["spread_cost_usd"]
            portfolio_funding += t["funding_cost_usd"]

            cl_time = t["closed_at"]
            try:
                c_ts = int(datetime.strptime(cl_time, "%Y-%m-%d %H:%M:%S").timestamp())
            except Exception:
                c_ts = 0

            combined_equity_curve.append({
                "timestamp": c_ts,
                "equity": round(combined_capital, 2),
                "date": cl_time,
                "symbol": t["symbol"],
                "pnl": net_pnl
            })

            # Calendar Daily Aggregation
            d_str = cl_time.split(" ")[0]
            if d_str not in daily_pnl_map:
                daily_pnl_map[d_str] = {
                    "date": d_str,
                    "net_pnl": 0.0,
                    "gross_pnl": 0.0,
                    "total_fees": 0.0,
                    "trades_count": 0,
                    "wins": 0,
                    "losses": 0,
                    "trades": []
                }
            daily_pnl_map[d_str]["net_pnl"] += net_pnl
            daily_pnl_map[d_str]["gross_pnl"] += gross_pnl
            daily_pnl_map[d_str]["total_fees"] += t["total_fees_usd"]
            daily_pnl_map[d_str]["trades_count"] += 1
            if net_pnl > 0:
                daily_pnl_map[d_str]["wins"] += 1
            elif net_pnl < 0:
                daily_pnl_map[d_str]["losses"] += 1
            daily_pnl_map[d_str]["trades"].append(t["id"])

        # Format Daily PnL List
        daily_pnl_list = []
        for d, item in sorted(daily_pnl_map.items()):
            daily_pnl_list.append({
                "date": d,
                "net_pnl": round(item["net_pnl"], 2),
                "gross_pnl": round(item["gross_pnl"], 2),
                "total_fees": round(item["total_fees"], 2),
                "trades_count": item["trades_count"],
                "wins": item["wins"],
                "losses": item["losses"],
                "is_profit": item["net_pnl"] > 0,
                "is_loss": item["net_pnl"] < 0
            })

        portfolio_wins = [t for t in all_trades if t["pnl_usd"] > 0]
        portfolio_losses = [t for t in all_trades if t["pnl_usd"] < 0]
        tot_trades = len(all_trades)
        overall_wr = round(len(portfolio_wins) / tot_trades * 100, 1) if tot_trades else 0.0
        portfolio_net = round(combined_capital - self.initial_capital, 2)
        portfolio_roi = round(portfolio_net / self.initial_capital * 100, 1)
        portfolio_total_fees = round(portfolio_commissions + portfolio_spreads + portfolio_funding, 2)
        portfolio_pf = round(portfolio_gross_profit / portfolio_gross_loss, 2) if portfolio_gross_loss > 0 else 99.0

        # Summary of Dynamic Rules triggered across portfolio
        dynamic_stats = {
            "sr_rejections": len([t for t in all_trades if t.get("partial_trigger") == "SR_REJECTION"]),
            "upcoming_sr_barriers": len([t for t in all_trades if t.get("partial_trigger") == "UPCOMING_SR_BARRIER"]),
            "orderflow_reversals": len([t for t in all_trades if t.get("partial_trigger") == "ORDERFLOW_REVERSAL"]),
            "target_2r_reached": len([t for t in all_trades if t.get("partial_trigger") == "TARGET_2R_REACHED"]),
            "runner_max_targets": len([t for t in all_trades if "RUNNER" in t.get("close_reason", "")]),
            "trailing_stops": len([t for t in all_trades if t.get("close_reason") == "TRAILING_STOP"]),
            "regular_stops": len([t for t in all_trades if t.get("close_reason") == "STOP_LOSS"])
        }

        joint_portfolio = {
            "strategy_name": "👑 4-Asset Apex Portfolio (Dynamic Execution V2)",
            "initial_capital": self.initial_capital,
            "final_capital": round(combined_capital, 2),
            "net_pl": portfolio_net,
            "gross_profit": round(portfolio_gross_profit, 2),
            "gross_loss": round(portfolio_gross_loss, 2),
            "total_commissions": round(portfolio_commissions, 2),
            "total_spreads": round(portfolio_spreads, 2),
            "total_funding": round(portfolio_funding, 2),
            "total_fees": portfolio_total_fees,
            "roi_pct": portfolio_roi,
            "total_trades": tot_trades,
            "wins": len(portfolio_wins),
            "losses": len(portfolio_losses),
            "win_rate": overall_wr,
            "profit_factor": portfolio_pf,
            "max_drawdown_usd": round(portfolio_max_dd, 2),
            "max_drawdown_pct": round(portfolio_max_dd / portfolio_peak * 100, 1) if portfolio_peak > 0 else 0.0,
            "avg_trade_pnl": round(portfolio_net / tot_trades, 2) if tot_trades else 0.0,
            "equity_curve": combined_equity_curve,
            "trades": all_trades,
            "daily_pnl": daily_pnl_list,
            "dynamic_stats": dynamic_stats
        }

        print("\n================================================================================")
        print("                 COMBINED JOINT PORTFOLIO SCORECARD ($50 BASE)                  ")
        print("================================================================================")
        print(f"Total Trades:           {tot_trades}")
        print(f"Overall Win Rate:       {overall_wr}% ({len(portfolio_wins)}W / {len(portfolio_losses)}L)")
        print(f"Gross Profit / Loss:    +${portfolio_gross_profit:.2f} / -${portfolio_gross_loss:.2f}")
        print(f"Explicit Fees Deducted: -${portfolio_total_fees:.2f} (Comm: ${portfolio_commissions:.2f}, Sprd: ${portfolio_spreads:.2f}, Fund: ${portfolio_funding:.2f})")
        print(f"Real Net Profit:        ${portfolio_net:+.2f} ({portfolio_roi:+.1f}% ROI)")
        print(f"Profit Factor:          {portfolio_pf}")
        print(f"Portfolio Max Drawdown: -${portfolio_max_dd:.2f}")
        print("================================================================================\n")

        return {
            "joint_portfolio": joint_portfolio,
            "per_pair": isolated_results
        }
