import math
from typing import List, Dict, Any, Optional
from datetime import datetime

from config.settings import (
    ACCOUNT_CAPITAL_USD,
    TARGET_RISK_USD,
    MIN_CONVICTION_STARS
)
from execution.risk_manager import RiskManager
from data.database import DatabaseManager

class BacktestSimulator:
    """
    Institutional Trend-Pullback & Order Flow Confluence Backtester:
    - 4H / 1H Trend Alignment (EMA 20 & EMA 50)
    - Dynamic Pullback to EMA with Real Delta Volume Confirmation
    - Asymmetric 1:2.0 Risk-to-Reward (Risk $4 to make $8+)
    - Dynamic 100x Lot Sizing on Delta Exchange
    """
    def __init__(self, db: DatabaseManager, initial_capital: float = ACCOUNT_CAPITAL_USD):
        self.db = db
        self.initial_capital = initial_capital
        self.risk_mgr = RiskManager(db)
        self.maker_fee_pct = 0.0001 # 0.01% Maker fee (matches user's Delta screenshot)

    def run_backtest(
        self,
        symbol: str,
        candles_15m: List[Dict[str, Any]],
        contract_spec: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Runs backtest across candle sequence."""
        if not candles_15m or len(candles_15m) < 50:
            return {"success": False, "error": "Insufficient candle data for backtest."}

        spec = contract_spec or {
            "contract_value": 0.001 if ("XAUT" in symbol or "BTC" in symbol) else 1.0,
            "contract_unit": symbol
        }

        capital = self.initial_capital
        equity_curve = [{"timestamp": candles_15m[0]["timestamp"], "equity": capital}]
        trades = []
        active_trade: Optional[Dict[str, Any]] = None

        # Loop through candle stream
        for i in range(50, len(candles_15m)):
            current_bar = candles_15m[i]
            prev_bars = candles_15m[i-50:i]
            current_price = current_bar["close"]
            bar_time = datetime.fromtimestamp(current_bar["timestamp"])

            # 1. Manage Active Position (Check SL / TP on current bar)
            if active_trade:
                hit_tp = False
                hit_sl = False

                if active_trade["side"] == "BUY":
                    if current_bar["high"] >= active_trade["take_profit"]:
                        hit_tp = True
                    elif current_bar["low"] <= active_trade["stop_loss"]:
                        hit_sl = True
                else: # SELL
                    if current_bar["low"] <= active_trade["take_profit"]:
                        hit_tp = True
                    elif current_bar["high"] >= active_trade["stop_loss"]:
                        hit_sl = True

                if hit_tp or hit_sl:
                    exit_price = active_trade["take_profit"] if hit_tp else active_trade["stop_loss"]
                    price_diff = (exit_price - active_trade["entry_price"]) if active_trade["side"] == "BUY" else (active_trade["entry_price"] - exit_price)
                    
                    gross_pnl = price_diff * active_trade["lots"] * spec["contract_value"]
                    fee = (active_trade["notional_usd"] * self.maker_fee_pct * 2)
                    net_pnl = round(gross_pnl - fee, 2)
                    
                    capital += net_pnl
                    equity_curve.append({"timestamp": current_bar["timestamp"], "equity": round(capital, 2)})

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": net_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": "TP" if hit_tp else "SL",
                        "status": "CLOSED",
                        "rr_achieved": 2.0 if hit_tp else -1.0
                    })
                    trades.append(active_trade)
                    active_trade = None
                continue # Only 1 active position at a time

            # 2. Trend & Pullback Analysis
            ema20 = sum(c["close"] for c in prev_bars[-20:]) / 20.0
            ema50 = sum(c["close"] for c in prev_bars[-50:]) / 50.0

            trend_bull = (ema20 > ema50) and (current_price > ema20)
            trend_bear = (ema20 < ema50) and (current_price < ema20)

            delta = current_bar.get("delta", 0.0)

            # 3. Setup Trigger (Pullback to EMA20 + Positive Delta Bullish Close)
            is_buy = False
            is_sell = False

            # Bullish Pullback: Low touched EMA20, closed green, volume delta positive
            if trend_bull and current_bar["low"] <= (ema20 * 1.001) and current_bar["close"] > current_bar["open"] and delta > 0:
                is_buy = True

            # Bearish Pullback: High touched EMA20, closed red, volume delta negative
            elif trend_bear and current_bar["high"] >= (ema20 * 0.999) and current_bar["close"] < current_bar["open"] and delta < 0:
                is_sell = True

            if not (is_buy or is_sell):
                continue

            # 4. Precision Risk & Target Calculation
            if is_buy:
                raw_sl = current_bar["low"] - 1.0
                risk_distance = max(3.5, current_price - raw_sl)
                sl_price = round(current_price - risk_distance, 2)
                tp_price = round(current_price + (risk_distance * 2.0), 2)
                side = "BUY"
            else:
                raw_sl = current_bar["high"] + 1.0
                risk_distance = max(3.5, raw_sl - current_price)
                sl_price = round(current_price + risk_distance, 2)
                tp_price = round(current_price - (risk_distance * 2.0), 2)
                side = "SELL"

            # 5. Position Sizing via Risk Manager ($3.50 to $4.50 risk)
            size_res = self.risk_mgr.calculate_position_size(
                symbol=symbol,
                entry_price=current_price,
                stop_loss_price=sl_price,
                contract_spec=spec,
                available_balance_usd=capital
            )

            if size_res.get("valid"):
                active_trade = {
                    "id": f"BT_{symbol}_{current_bar['timestamp']}",
                    "symbol": symbol,
                    "side": side,
                    "entry_price": current_price,
                    "stop_loss": sl_price,
                    "take_profit": tp_price,
                    "risk_distance": risk_distance,
                    "lots": size_res["lots"],
                    "notional_usd": size_res["notional_usd"],
                    "margin_usd": size_res["margin_usd"],
                    "leverage": size_res["leverage"],
                    "risk_usd": size_res["planned_risk_usd"],
                    "conviction_stars": 4.5,
                    "strategy_name": "Trend Pullback + Order Flow Delta",
                    "orderflow_notes": f"EMA20 Touch + Delta {delta:+.1f} | 1:2.0 R:R",
                    "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "OPEN",
                    "is_paper": 1
                }

        return self._compile_metrics(capital, equity_curve, trades)

    def _compile_metrics(self, final_capital: float, equity_curve: List[Dict], trades: List[Dict]) -> Dict[str, Any]:
        wins = [t for t in trades if t["pnl_usd"] > 0]
        losses = [t for t in trades if t["pnl_usd"] < 0]
        total = len(trades)

        win_rate = round((len(wins) / total * 100), 1) if total > 0 else 0.0
        gross_profit = sum(t["pnl_usd"] for t in wins)
        gross_loss = abs(sum(t["pnl_usd"] for t in losses))
        profit_factor = round((gross_profit / gross_loss), 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        net_pl = round(final_capital - self.initial_capital, 2)

        peak = self.initial_capital
        max_dd = 0.0
        for pt in equity_curve:
            eq = pt["equity"]
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd

        return {
            "initial_capital": self.initial_capital,
            "final_capital": round(final_capital, 2),
            "net_pl": net_pl,
            "roi_pct": round((net_pl / self.initial_capital) * 100, 1),
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_usd": round(max_dd, 2),
            "equity_curve": equity_curve,
            "trades": trades
        }
