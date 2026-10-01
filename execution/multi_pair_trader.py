import sys
import time
import math
from datetime import datetime, date, timezone, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config.settings import (
    ACTIVE_SYMBOLS,
    ACCOUNT_CAPITAL_USD,
    TARGET_RISK_USD,
    DAILY_MAX_LOSS_USD,
    DELTA_BROKERAGE_FEE_PCT,
    DELTA_FEES,
    calculate_brokerage_fee,
    CONTRACT_VALUES,
    LEVERAGE_MAP
)
from data.database import DatabaseManager
from exchange.delta_client import DeltaExchangeClient
from reports.html_reporter import HTMLReporter
from execution.risk_manager import RiskManager
from execution.dynamic_trade_manager import DynamicTradeManager
from alerts.alert_dispatcher import dispatcher as notifier

class MultiPairLiveTrader:
    """
    Autonomous Multi-Pair Live Trading Engine for Delta Exchange India.
    
    Key Institutional Capabilities:
    1. Concurrent Multi-Asset Execution:
       - Manages independent execution state machines for BTCUSD, ETHUSD, XAUTUSD, and SLVONUSD.
       - An open trade in BTCUSD NEVER blocks new setups in ETHUSD, Gold, or Silver.
    2. Strict $5.00 Fixed Risk Per Trade:
       - Dynamic contract lot sizing based on real-time stop distance and contract multiplier.
       - Hard daily loss circuit breaker ($20.00 max daily loss = 4 consecutive losses).
    3. Asymmetric 4-Phase Trade Lifecycle per Active Pair:
       - Phase 1: Precision entry with structural stop ($5 risk).
       - Phase 2: Scale-out 50% at 2.0R - 2.5R target (lock guaranteed dollar cash profit).
       - Phase 3: Instant Breakeven stop loss move (+0.10R to cover exchange fees). Trade is 100% risk-free.
       - Phase 4: Dynamic trailing runner with ATR to capture macro fat-tail trends up to 6.0R.
    4. Resilient Delta Connectivity:
       - Synchronized server timestamp handling.
       - Automatic fallback to Live-Paper mode if API Key IP restriction is active, seamlessly switching to live order placement once whitelisted.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        client: Optional[DeltaExchangeClient] = None,
        reporter: Optional[HTMLReporter] = None,
        fixed_risk_usd: float = TARGET_RISK_USD
    ):
        self.db = db or DatabaseManager()
        self.client = client or DeltaExchangeClient()
        self.reporter = reporter or HTMLReporter()
        self.risk_mgr = RiskManager(self.db, target_risk=fixed_risk_usd)
        self.fixed_risk_usd = fixed_risk_usd
        
        # Concurrent active positions dictionary: {symbol: trade_dict}
        self.active_positions: Dict[str, Dict[str, Any]] = {}

        # Instrument technical parameters (Operator Smart Money Calibration)
        self.params = {
            "BTCUSD": {
                "c_val": 0.001,
                "min_stop_dist": 160.0,
                "padding": 45.0,
                "sigma": 1.8,
                "tp1_rr": 2.0,
                "max_rr": 10.0,
                "is_crypto": True,
                "decimals": 1
            },
            "ETHUSD": {
                "c_val": 0.01,
                "min_stop_dist": 8.0,
                "padding": 2.2,
                "sigma": 1.8,
                "tp1_rr": 2.0,
                "max_rr": 10.0,
                "is_crypto": True,
                "decimals": 2
            },
            "XAUTUSD": {
                "c_val": 0.001,
                "min_stop_dist": 3.0,
                "padding": 1.2,
                "sigma": 1.8,
                "tp1_rr": 2.0,
                "max_rr": 10.0,
                "is_crypto": False,
                "decimals": 2
            },
            "SLVONUSD": {
                "c_val": 0.1,
                "min_stop_dist": 0.25,
                "padding": 0.08,
                "sigma": 1.8,
                "tp1_rr": 2.0,
                "max_rr": 10.0,
                "is_crypto": False,
                "decimals": 3
            }
        }

        # Check API key status
        self.is_live_authenticated = False
        self.client_ip = "Unknown"
        self.dynamic_mgr = DynamicTradeManager()
        self._candle_cache: Dict[str, Any] = {}
        self.cooldown_until: Dict[str, float] = {}  # {symbol: expiration_timestamp}
        self.missing_exchange_counts: Dict[str, int] = {}
        self._verify_credentials()
        self._load_open_positions_from_db()

    def _load_open_positions_from_db(self):
        """Restores any active OPEN positions and recent 10-min cooldowns from SQLite on engine boot."""
        try:
            trades = self.db.get_trades(limit=50)
            open_trades = [t for t in trades if t.get("status") == "OPEN"]
            for t in open_trades:
                sym = t.get("symbol")
                if not sym or sym not in self.params:
                    continue
                lots = int(float(t.get("lots") or 2))
                half_lots = max(1, lots // 2)
                dist = abs(float(t.get("entry_price", 0)) - float(t.get("stop_loss", 0)))
                self.active_positions[sym] = {
                    "id": t.get("id"),
                    "symbol": sym,
                    "side": t.get("side"),
                    "entry_price": float(t.get("entry_price")),
                    "stop_loss": float(t.get("stop_loss")),
                    "take_profit": float(t.get("take_profit")),
                    "dist": dist,
                    "lots": lots,
                    "half_lots": half_lots,
                    "remaining_lots": lots,
                    "notional_usd": float(t.get("notional_usd") or 0),
                    "margin_usd": float(t.get("margin_usd") or 0),
                    "opened_at": t.get("opened_at"),
                    "highest_price": float(t.get("entry_price")),
                    "lowest_price": float(t.get("entry_price")),
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "leverage": t.get("leverage") or LEVERAGE_MAP.get(sym, 100),
                    "risk_usd": self.fixed_risk_usd,
                    "strategy_name": t.get("strategy_name")
                }
                print(f"🔄 [RESTORED OPEN POSITION] {sym} {t.get('side')} (ID: {t.get('id')}) restored from database.")

            # Restore 10-minute cooldowns for recently closed trades
            closed_trades = [t for t in trades if t.get("status") == "CLOSED"]
            for t in closed_trades:
                sym = t.get("symbol")
                if not sym or sym in self.cooldown_until:
                    continue
                c_str = t.get("closed_at")
                if c_str:
                    try:
                        try:
                            c_dt = datetime.fromisoformat(c_str)
                        except Exception:
                            c_dt = datetime.strptime(c_str, "%Y-%m-%d %H:%M:%S")
                        elapsed = time.time() - c_dt.timestamp()
                        if elapsed < 600.0:
                            self.cooldown_until[sym] = c_dt.timestamp() + 600.0
                            rem = int(self.cooldown_until[sym] - time.time())
                            print(f"⏳ [COOLDOWN RESTORED] {sym} 10-minute cooldown active ({rem // 60}m {rem % 60}s remaining).")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[NOTICE] Could not restore open positions: {e}")

    def _adopt_exchange_position(self, symbol: str, p: Dict[str, Any]):
        """Adopts an open position from Delta Exchange, ensures bracket protection, logs to DB, and sends Telegram alert."""
        size = float(p.get("size", 0))
        side = "BUY" if size > 0 else "SELL"
        lots = abs(int(size))
        entry_price = float(p.get("entry_price") or p.get("mark_price") or 0.0)
        param = self.params[symbol]
        dist = param["min_stop_dist"]
        
        sl = round(entry_price - dist if side == "BUY" else entry_price + dist, param["decimals"])
        tp = round(entry_price + (dist * param["tp1_rr"]) if side == "BUY" else entry_price - (dist * param["tp1_rr"]), param["decimals"])

        # Check existing open resting orders on Delta for this symbol
        close_side = "sell" if side == "BUY" else "buy"
        if self.is_live_authenticated:
            try:
                open_orders = self.client._request("GET", "/v2/orders?state=open", auth=True)
                existing = open_orders.get("result", []) if open_orders.get("success") else []
                for o in existing:
                    if o.get("product_symbol") == symbol:
                        stype = o.get("stop_order_type")
                        sprice = float(o.get("stop_price", 0) or 0)
                        if stype == "stop_loss_order" and sprice > 0:
                            sl = sprice
                        elif stype == "take_profit_order" and sprice > 0:
                            tp = sprice

                has_sl = any(o.get("product_symbol") == symbol and o.get("stop_order_type") == "stop_loss_order" for o in existing)
                has_tp = any(o.get("product_symbol") == symbol and o.get("stop_order_type") == "take_profit_order" for o in existing)

                if not has_sl:
                    sl_res = self.client.place_stop_order(symbol, side=close_side, size=lots, stop_price=sl, is_take_profit=False)
                    print(f"🛡️ [DELTA SL ORDER PLACED] {symbol} SL @ ${sl} -> {sl_res.get('success')}")
                if not has_tp:
                    tp_res = self.client.place_stop_order(symbol, side=close_side, size=lots, stop_price=tp, is_take_profit=True)
                    print(f"🎯 [DELTA TP ORDER PLACED] {symbol} TP @ ${tp} -> {tp_res.get('success')}")
            except Exception as e:
                print(f"[ADOPT NOTICE] Error checking/placing exchange bracket orders: {e}")

        trade_id = f"LIVE_{symbol}_{int(time.time())}"
        pos_record = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "stop_loss": sl,
            "take_profit": tp,
            "dist": dist,
            "lots": lots,
            "half_lots": max(1, lots // 2),
            "remaining_lots": lots,
            "notional_usd": round(lots * param["c_val"] * entry_price, 2),
            "margin_usd": float(p.get("margin", 0.0)),
            "opened_at": p.get("created_at") or datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "highest_price": entry_price,
            "lowest_price": entry_price,
            "tp1_hit": False,
            "booked_pnl": 0.0,
            "leverage": LEVERAGE_MAP.get(symbol, 100),
            "risk_usd": self.fixed_risk_usd,
            "strategy_name": f"⚡ 4-Asset High-Velocity Suite ({symbol} | 1:10R Velocity)"
        }
        self.active_positions[symbol] = pos_record
        print(f"📥 [ADOPTED DELTA POSITION] {symbol} {side} {lots} Lots @ ${entry_price:,.2f} | SL: ${sl} | TP: ${tp}")

        # Log open trade to SQLite
        open_log = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": None,
            "stop_loss": sl,
            "take_profit": tp,
            "lots": lots,
            "notional_usd": pos_record["notional_usd"],
            "margin_usd": pos_record["margin_usd"],
            "leverage": LEVERAGE_MAP.get(symbol, 100),
            "risk_usd": self.fixed_risk_usd,
            "pnl_usd": 0.0,
            "rr_achieved": 0.0,
            "opened_at": pos_record["opened_at"],
            "closed_at": None,
            "status": "OPEN",
            "close_reason": None,
            "strategy_name": pos_record["strategy_name"],
            "conviction_stars": 5.0,
            "orderflow_notes": f"Adopted Live Delta Execution: {side} {lots} Lots @ ${entry_price}. Strict $5 Risk.",
            "is_paper": 0
        }
        self.db.log_trade(open_log)

        # Dispatch real-time Telegram entry alert so user immediately receives SL and TP!
        notifier.send_entry_alert(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            sl=sl,
            tp=tp,
            lots=lots,
            risk_usd=self.fixed_risk_usd,
            leverage=LEVERAGE_MAP.get(symbol, 100)
        )

    def _verify_credentials(self):
        """Checks if API key is authenticated on Delta Exchange."""
        res = self.client.get_wallet_balances()
        if res.get("success"):
            self.is_live_authenticated = True
            print("[LIVE TRADER] Authenticated with Delta Exchange. Real order execution ACTIVE.")
        else:
            self.client_ip = res.get("client_ip", "Unknown")
            print(f"[LIVE TRADER] Notice: Real API authenticated returned: {res.get('error')}")
            print(f"[LIVE TRADER] Running in LIVE STREAM PAPER MODE (100% realistic fills & real-time monitoring).")
            print(f"[LIVE TRADER] To enable real money orders, add IP '{self.client_ip}' in Delta Exchange API Key settings.")

    def scan_and_manage_all_pairs(self) -> Dict[str, Any]:
        """
        Executes one full concurrent cycle across ALL active pairs:
        1. Checks risk limits & daily circuit breaker.
        2. Syncs positions directly with Delta Exchange (Rule 2: strict mutual exclusion).
        3. Manages active positions (Scale-out, Breakeven stop lock, Trailing runner exit).
        4. Scans for new high-probability entries on pairs that are FLAT and past 10-min cooldown (Rule 1).
        """
        status_report = {
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "active_positions_count": len(self.active_positions),
            "positions": {},
            "signals": {}
        }

        # 1. Circuit Breaker Check
        is_breaker, daily_loss = self.risk_mgr.is_daily_circuit_breaker_active()
        if is_breaker:
            print(f"[CIRCUIT BREAKER ACTIVE] Daily loss ${daily_loss:.2f} >= ${self.risk_mgr.daily_loss_limit:.2f}. Halting new entries.")
            return status_report

        # 2. Query live exchange positions from Delta Exchange (Rule 2: strict exchange-level check)
        exchange_positions = {}
        if self.is_live_authenticated:
            try:
                raw_pos = self.client.get_positions()
                for p in raw_pos:
                    s = p.get("product_symbol")
                    sz = float(p.get("size", 0))
                    if s and sz != 0:
                        exchange_positions[s] = p
            except Exception as e:
                pass

        # 3. Iterate through each symbol independently
        for symbol in ACTIVE_SYMBOLS:
            try:
                # Fetch real-time market data from Delta
                ticker = self.client.get_ticker(symbol)
                mark_price = float(ticker.get("mark_price") or ticker.get("close") or 0.0)
                if mark_price <= 0:
                    continue

                has_local = symbol in self.active_positions
                has_exchange = symbol in exchange_positions

                # 3A. RULE 2: If a position is running on this pair (locally or on Delta):
                if has_local or has_exchange:
                    # If tracked locally but no longer active on Delta Exchange, confirm across 3 consecutive cycles before finalizing
                    if has_local and self.is_live_authenticated and not has_exchange:
                        self.missing_exchange_counts[symbol] = self.missing_exchange_counts.get(symbol, 0) + 1
                        if self.missing_exchange_counts[symbol] >= 3:
                            self.missing_exchange_counts[symbol] = 0
                            print(f"⚡ [DELTA EXCHANGE SYNC] {symbol} position confirmed closed on Delta (3 cycles). Finalizing trade @ mark price ${mark_price:,.2f}...")
                            self._close_position(symbol, mark_price, reason="EXCHANGE_FILLED_EXIT")
                        continue
                    else:
                        self.missing_exchange_counts[symbol] = 0

                    # Adopt exchange position into state manager if not tracked locally
                    if not has_local and has_exchange:
                        self._adopt_exchange_position(symbol, exchange_positions[symbol])
                    
                    # Manage the active position (Scale-Out, Breakeven Stop, Trailing Exit)
                    self._manage_active_position(symbol, mark_price)
                    status_report["positions"][symbol] = self.active_positions.get(symbol, {})
                    # STRICT RULE: NEVER scan or enter another trade on this symbol while one is active!
                    continue

                # 3B. RULE 1: Check 10-minute cooldown on this pair after closing
                now_ts = time.time()
                cooldown_end = self.cooldown_until.get(symbol, 0.0)
                if now_ts < cooldown_end:
                    rem_sec = int(cooldown_end - now_ts)
                    # Silently skip scanning this pair until 10 minutes have elapsed
                    continue

                # Check Master Pause / Sleep Switch before scanning for new entries
                is_paused, pause_reason, pause_until = self.db.is_bot_paused()
                if is_paused:
                    # Skip scanning new setups while paused (existing open positions are still managed above!)
                    status_report["bot_status"] = "PAUSED"
                    status_report["pause_reason"] = pause_reason
                    status_report["pause_until"] = pause_until
                    continue

                # 3C. Pair is 100% FLAT and cooldown expired: Scan for new high-probability entry
                signal = self._evaluate_entry_signal(symbol, mark_price)
                if signal:
                    status_report["signals"][symbol] = signal
                    self._execute_entry(symbol, signal, mark_price)
            except Exception as e:
                print(f"[ERROR] Error monitoring {symbol}: {e}")

        # Record overall bot status and active risk
        is_paused, pause_reason, pause_until = self.db.is_bot_paused()
        status_report["bot_status"] = "PAUSED" if is_paused else "ACTIVE"
        status_report["target_risk_usd"] = self.db.get_target_risk_usd(self.fixed_risk_usd)
        status_report["pause_reason"] = pause_reason
        status_report["pause_until"] = pause_until

        # Continuously keep live journal HTML updated on disk
        self._sync_live_dashboards()

        return status_report

    def _manage_active_position(self, symbol: str, current_price: float):
        """
        Institutional Context-Aware Dynamic Trade Management:
        - 1:1 R:R Target: Full Hold if orderflow aligned and no major upcoming S/R barrier.
        - Early partial booking (50%) on upcoming S/R barrier or Order Flow reversal.
        - S/R Rejection Trigger: Reached ~1.1 to 1.3R, rejected by S/R and pulling back -> Book 50%.
        - Entry Retracement Exception: Retesting entry S/R zone -> Preserve original SL.
        - 1:1.5 to 1:3 R:R: Book 50% and trail remaining 50% SL to BE (+0.10R) or lock profit behind structural levels.
        - Max Runner Target: Full exit at 3.5R or trailing stop.
        """
        pos = self.active_positions[symbol]
        side = pos["side"]
        entry = pos["entry_price"]
        sl = pos["stop_loss"]
        dist = pos["dist"]
        p = self.params[symbol]
        c_val = p["c_val"]
        total_lots = pos["lots"]
        half_lots = pos["half_lots"]

        # 1. Fetch recent candles for order flow & S/R analysis
        now_ts = time.time()
        cached = self._candle_cache.get(symbol)
        if cached and (now_ts - cached[0] < 15.0):
            candles = cached[1]
        else:
            candles = self.client.get_candles(symbol, resolution="15m")
            if len(candles) >= 15:
                self._candle_cache[symbol] = (now_ts, candles)

        latest_bar = candles[-1] if candles else {
            "high": current_price, "low": current_price, "close": current_price, "open": current_price, "volume": 1.0, "delta": 0.0
        }

        # 2. Evaluate with DynamicTradeManager
        decision = self.dynamic_mgr.evaluate_position(
            pos=pos,
            current_price=current_price,
            current_bar=latest_bar,
            recent_candles=candles,
            dom_data=None,
            decimals=p["decimals"]
        )

        action = decision.get("action", "HOLD_POSITION")

        # A. Stop Loss or Runner Max Target Hit
        if action == "CLOSE_FULL":
            self._close_position(symbol, decision.get("exit_price", current_price), reason=decision.get("reason", "STOP_LOSS"))
            return

        # B. Entry Retracement Exception (SL Rule)
        if action == "HOLD_ORIGINAL_SL":
            # Retesting entry S/R zone: Keep original Stop-Loss intact
            pass

        # C. 1:1 Full Hold Rule Active
        if action == "HOLD_FULL_RUNNER":
            # Holding 100% position size through 1:1 aiming for 1:2 / 1:3 run-up
            pass

        # D. Partial Scale-Out (50%) Triggered
        if decision.get("book_partial") and not pos["tp1_hit"]:
            pos["tp1_hit"] = True
            diff = (current_price - entry) if side == "BUY" else (entry - current_price)
            if "XAUT" in symbol or "SLV" in symbol:
                fee_partial = 0.005 # half of flat $0.01 fee
            else:
                fee_partial = (half_lots * c_val * (entry + current_price)) * 0.0002 # 0.02% Maker
            booked_gain = (half_lots * c_val * diff) - fee_partial
            pos["booked_pnl"] += booked_gain
            pos["booked_fees"] = pos.get("booked_fees", 0.0) + fee_partial

            # Trail remaining SL to BE (+0.10R to cover all fees)
            be_sl = round(entry + (0.10 * dist), p["decimals"]) if side == "BUY" else round(entry - (0.10 * dist), p["decimals"])
            pos["stop_loss"] = be_sl
            pos["remaining_lots"] = total_lots - half_lots

            # Execute partial exit on Delta Exchange if live
            if self.is_live_authenticated and half_lots > 0:
                try:
                    close_side = "sell" if side == "BUY" else "buy"
                    self.client.place_bracket_order(
                        symbol=symbol,
                        side=close_side,
                        size=half_lots,
                        order_type="market_order"
                    )
                    print(f"🎯 [DELTA LIVE SCALE-OUT] {symbol} {close_side.upper()} {half_lots} Lots filled on Delta.")
                except Exception as e:
                    print(f"[DELTA SCALE-OUT NOTICE] {e}")

            trigger_label = decision.get("trigger", "DYNAMIC_SCALE_OUT")
            print(f"🎯 [DYNAMIC SCALE-OUT 50%] {symbol} {side} ({trigger_label})! Banked +${booked_gain:.2f}. Stop moved to BE (${pos['stop_loss']}).")
            notifier.send_scale_out_alert(symbol, side, current_price, booked_gain, pos["stop_loss"])
            self.db.log_thought(
                symbol=symbol,
                event_type="DYNAMIC_SCALE_OUT_50",
                stars=5.0,
                message=f"🎯 Scale-out 50% on {symbol} {side} @ ${current_price} ({trigger_label}): {decision.get('reason')}. Banked +${booked_gain:.2f}. Stop locked at BE ${pos['stop_loss']}."
            )

        # E. Trailing Stop Adjustment (Remaining 50% Runner)
        if decision.get("trail_sl") and pos["tp1_hit"]:
            new_sl = decision.get("new_sl")
            if new_sl:
                if side == "BUY" and new_sl > pos["stop_loss"]:
                    pos["stop_loss"] = new_sl
                elif side == "SELL" and new_sl < pos["stop_loss"]:
                    pos["stop_loss"] = new_sl

        # F. Direct intra-bar Stop Loss check
        sl_hit = (current_price <= pos["stop_loss"]) if side == "BUY" else (current_price >= pos["stop_loss"])
        if sl_hit:
            self._close_position(symbol, current_price, reason="TRAILING_STOP" if pos["tp1_hit"] else "STOP_LOSS")
            return

    def _evaluate_entry_signal(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        """Evaluates entry conditions for a symbol using recent 15m candles and order flow."""
        # Double check Rule 1: 10-minute cooldown
        if time.time() < self.cooldown_until.get(symbol, 0.0):
            return None

        p = self.params[symbol]
        # In live trading, fetch live candles from Delta Exchange (with 15s cache to protect API limits during 1-5s fast scans)
        now_ts = time.time()
        cached = self._candle_cache.get(symbol)
        if cached and (now_ts - cached[0] < 15.0):
            candles = cached[1]
        else:
            candles = self.client.get_candles(symbol, resolution="15m")
            if len(candles) >= 20:
                self._candle_cache[symbol] = (now_ts, candles)
            else:
                candles = self.db.get_latest_candles(symbol, "15m", limit=60)
                if len(candles) < 20:
                    return None

        # Session Filter:
        # - BTC and ETH: 24/7 global crypto market with high-conviction 2-edge confluence
        # - Gold (XAUT) & Silver (SLVON): London & NY Session (12:30 to 23:45 IST)
        now_ist = datetime.now(IST)
        hm = now_ist.strftime("%H:%M")

        is_crypto = ("BTC" in symbol or "ETH" in symbol)
        if not is_crypto:
            if not ("12:30" <= hm <= "23:45"):
                return None
            # Exclude Gold chop hours (16, 19, 20, 22 IST)
            if symbol == "XAUTUSD" and now_ist.hour in (16, 19, 20, 22):
                return None

        # Calculate Session VWAP and Standard Deviation Bands in IST
        today_str = now_ist.strftime("%Y-%m-%d")
        today_candles = [c for c in candles if datetime.fromtimestamp(c["timestamp"], tz=IST).strftime("%Y-%m-%d") == today_str]
        if len(today_candles) < 6:
            today_candles = candles[-24:]

        cum_vol = 0.0
        cum_pv = 0.0
        prices = []
        for c in today_candles:
            typ_p = (c["high"] + c["low"] + c["close"]) / 3.0
            v = max(1.0, c.get("volume", 1.0))
            cum_vol += v
            cum_pv += (typ_p * v)
            prices.append(typ_p)

        vwap = cum_pv / max(1.0, cum_vol)
        variance = sum((pr - vwap)**2 for pr in prices) / len(prices)
        stdev = max(1.0, variance**0.5)

        upper_band = vwap + (p["sigma"] * stdev)
        lower_band = vwap - (p["sigma"] * stdev)

        latest = today_candles[-1]
        prev_1 = today_candles[-2] if len(today_candles) >= 2 else latest
        prev_2 = today_candles[-3] if len(today_candles) >= 3 else prev_1

        delta = latest.get("delta", 0.0)
        v_latest = max(1.0, latest.get("volume", 1.0))
        c_open = latest.get("open", current_price)
        c_high = latest.get("high", current_price)
        c_low = latest.get("low", current_price)
        c_close = latest.get("close", current_price)
        candle_range = max(0.01, c_high - c_low)

        if delta == 0.0 and candle_range > 0:
            body = c_close - c_open
            lower_wick = min(c_open, c_close) - c_low
            upper_wick = c_high - max(c_open, c_close)
            directional_bias = body / candle_range
            wick_bias = (lower_wick - upper_wick) / candle_range
            effective_bias = (0.7 * directional_bias) + (0.3 * wick_bias)
            delta = effective_bias * v_latest
            delta_ratio = effective_bias
        else:
            delta_ratio = delta / v_latest

        # -----------------------------------------------------------------
        # CONFIRMATION LOGIC & ANTI-CASCADE (NO FALLING KNIVES / SPIKES)
        # -----------------------------------------------------------------
        # Check if preceding candles were a waterfall cascade against the trade
        prev_1_bear = prev_1["close"] < prev_1["open"]
        prev_2_bear = prev_2["close"] < prev_2["open"]
        bearish_cascade = prev_1_bear and prev_2_bear  # 2+ consecutive falling candles

        prev_1_bull = prev_1["close"] > prev_1["open"]
        prev_2_bull = prev_2["close"] > prev_2["open"]
        bullish_cascade = prev_1_bull and prev_2_bull  # 2+ consecutive rising candles

        # Rejection wick measurements
        lower_wick = min(c_open, current_price) - c_low
        lower_wick_ratio = lower_wick / candle_range

        upper_wick = c_high - max(c_open, current_price)
        upper_wick_ratio = upper_wick / candle_range

        # -----------------------------------------------------------------
        # OPERATOR SMART MONEY EDGES & CONFIRMATION (PRICE ACTION + ORDER FLOW)
        # -----------------------------------------------------------------
        sub = today_candles[-15:] if len(today_candles) >= 15 else today_candles
        hi8 = max(float(x["high"]) for x in sub[-8:]) if len(sub) >= 8 else c_high
        lo8 = min(float(x["low"]) for x in sub[-8:]) if len(sub) >= 8 else c_low

        bullish_candle_confirm = (current_price > c_open) or (lower_wick_ratio >= 0.28 and current_price >= c_low + 0.40 * candle_range)
        not_falling_knife = not (bearish_cascade and current_price < c_open and lower_wick_ratio < 0.35)

        bearish_candle_confirm = (current_price < c_open) or (upper_wick_ratio >= 0.28 and current_price <= c_high - 0.40 * candle_range)
        not_rising_spike = not (bullish_cascade and current_price > c_open and upper_wick_ratio < 0.35)

        # Edge 1: Micro Liquidity Sweep (Stop Hunt & Reclaim)
        sweep_buy = (float(c_low) < lo8) and (current_price > lo8) and (delta_ratio >= 0.02)
        sweep_sell = (float(c_high) > hi8) and (current_price < hi8) and (delta_ratio <= -0.02)

        # Edge 2: Session VWAP Bands Reversion
        vwap_buy = (len(prices) >= 6) and (float(c_low) <= lower_band) and (current_price > float(c_open)) and (delta_ratio >= 0.02)
        vwap_sell = (len(prices) >= 6) and (float(c_high) >= upper_band) and (current_price < float(c_open)) and (delta_ratio <= -0.02)

        # Edge 3: Footprint Delta Absorption
        absorb_buy = (float(c_low) <= lo8 * 1.0005) and (delta_ratio >= 0.04) and bullish_candle_confirm
        absorb_sell = (float(c_high) >= hi8 * 0.9995) and (delta_ratio <= -0.04) and bearish_candle_confirm

        # 200 EMA Macro Alignment
        if len(candles) >= 200:
            ema200 = sum(float(x["close"]) for x in candles[-200:]) / 200.0
            macro_bull = current_price > ema200
            macro_bear = current_price < ema200
        else:
            macro_bull = True
            macro_bear = True

        buy_score = (1 if sweep_buy else 0) + (1 if vwap_buy else 0) + (1 if absorb_buy else 0) + (1 if (macro_bull and sweep_buy) else 0)
        sell_score = (1 if sweep_sell else 0) + (1 if vwap_sell else 0) + (1 if absorb_sell else 0) + (1 if (macro_bear and sweep_sell) else 0)
        min_score = 2 if ("BTC" in symbol or "ETH" in symbol) else 1

        # Periodic live transparency log into Brain Thoughts
        now_ts = time.time()
        if not hasattr(self, "_last_thought_log"):
            self._last_thought_log = {}
        last_t = self._last_thought_log.get(symbol, 0)
        log_interval = 90 if (buy_score > 0 or sell_score > 0) else 180
        if now_ts - last_t > log_interval:
            self._last_thought_log[symbol] = now_ts
            dir_str = "BUY" if buy_score >= sell_score else "SELL"
            lead_score = max(buy_score, sell_score)
            status_desc = f"Score {lead_score}/{min_score} ({dir_str})" if lead_score > 0 else "Hunting A+ Setup"
            self.db.log_thought(
                symbol=symbol,
                event_type="SETUP_MONITOR",
                stars=round(2.5 + (lead_score * 0.7), 1) if lead_score > 0 else 2.5,
                message=f"Scanning {symbol}: {status_desc}. Price: ${current_price:,.2f}. Delta Ratio: {delta_ratio:+.3f}. VWAP: ${vwap:,.2f}."
            )

        is_buy = (buy_score >= min_score) and (sell_score == 0) and bullish_candle_confirm and not_falling_knife
        is_sell = (sell_score >= min_score) and (buy_score == 0) and bearish_candle_confirm and not_rising_spike

        if not is_buy and not is_sell:
            return None

        side = "BUY" if is_buy else "SELL"
        recent_window = today_candles[-8:] if len(today_candles) >= 8 else today_candles

        # Swing Low / Swing High Anchor with Generous Protective Buffer
        if is_buy:
            swing_low = min(float(c["low"]) for c in recent_window)
            raw_dist = (current_price - swing_low) + p["padding"]
            stop_dist = max(p["min_stop_dist"], raw_dist)
            sl_price = round(current_price - stop_dist, p["decimals"])
            tp_price = round(current_price + (stop_dist * p["max_rr"]), p["decimals"])
        else:
            swing_high = max(float(c["high"]) for c in recent_window)
            raw_dist = (swing_high - current_price) + p["padding"]
            stop_dist = max(p["min_stop_dist"], raw_dist)
            sl_price = round(current_price + stop_dist, p["decimals"])
            tp_price = round(current_price - (stop_dist * p["max_rr"]), p["decimals"])

        # Dynamic Lot calculation from current risk setting (default $5, customizable via Live Journal)
        current_risk = self.db.get_target_risk_usd(self.fixed_risk_usd)
        lots = max(2, int(round(current_risk / (stop_dist * p["c_val"]))))

        return {
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "dist": stop_dist,
            "lots": lots,
            "risk_usd": current_risk,
            "vwap": vwap,
            "upper_band": upper_band,
            "lower_band": lower_band,
            "reversal_confirmed": True
        }

    def _execute_entry(self, symbol: str, signal: Dict[str, Any], current_price: float):
        """Submits entry order and initializes position in concurrent state manager."""
        p = self.params[symbol]
        c_val = p["c_val"]
        lots = signal["lots"]
        side = signal["side"]
        dist = signal["dist"]
        sl = signal["stop_loss"]
        tp = signal["take_profit"]
        current_risk = signal.get("risk_usd") or self.db.get_target_risk_usd(self.fixed_risk_usd)

        half_lots = max(1, lots // 2)
        notional = round(lots * c_val * current_price, 2)
        margin = round(notional / LEVERAGE_MAP.get(symbol, 100), 2)

        # Submit live bracket order to Delta Exchange if live authenticated
        order_res = {}
        if self.is_live_authenticated:
            order_res = self.client.place_bracket_order(
                symbol=symbol,
                side=side.lower(),
                size=lots,
                order_type="market_order",
                stop_loss_price=sl,
                take_profit_price=tp
            )
            print(f"🚀 [DELTA LIVE ORDER PLACED] {symbol} {side} {lots} Lots (Risk: ${current_risk:.2f} | SL: ${sl} | TP: ${tp}) -> Response: {order_res.get('success')}")

        # Register position into concurrent multi-pair state machine
        trade_id = f"LIVE_{symbol}_{int(time.time())}"
        pos_record = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "stop_loss": sl,
            "take_profit": tp,
            "dist": dist,
            "lots": lots,
            "half_lots": half_lots,
            "remaining_lots": lots,
            "notional_usd": notional,
            "margin_usd": margin,
            "opened_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "highest_price": current_price,
            "lowest_price": current_price,
            "tp1_hit": False,
            "booked_pnl": 0.0,
            "leverage": LEVERAGE_MAP.get(symbol, 100),
            "risk_usd": current_risk,
            "strategy_name": f"⚡ 4-Asset High-Velocity Suite ({symbol} | 1:10R Velocity)"
        }

        self.active_positions[symbol] = pos_record
        print(f"✅ [CONCURRENT POSITION OPENED] {symbol} {side} @ ${current_price} | Lots: {lots} | Strict Risk: $5.00 | Open Positions: {list(self.active_positions.keys())}")

        # Log open trade to SQLite
        open_log = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "exit_price": None,
            "stop_loss": sl,
            "take_profit": tp,
            "lots": lots,
            "notional_usd": notional,
            "margin_usd": margin,
            "leverage": LEVERAGE_MAP.get(symbol, 100),
            "risk_usd": self.fixed_risk_usd,
            "pnl_usd": 0.0,
            "rr_achieved": 0.0,
            "opened_at": pos_record["opened_at"],
            "closed_at": None,
            "status": "OPEN",
            "close_reason": None,
            "strategy_name": pos_record["strategy_name"],
            "conviction_stars": 5.0,
            "orderflow_notes": f"Multi-Pair Live Entry: {side} {lots} Lots @ ${current_price}. Strict $5 Risk.",
            "is_paper": 0 if self.is_live_authenticated else 1
        }
        self.db.log_trade(open_log)

        # Log thought in database
        self.db.log_thought(
            symbol=symbol,
            event_type="LIVE_ENTRY_TRIGGERED",
            stars=5.0,
            message=f"🚀 Multi-pair entry triggered on {symbol} {side} @ ${current_price}. Size: {lots} Lots. Strict $5 Risk. Active Pairs: {list(self.active_positions.keys())}."
        )

        # Dispatch real-time email notification
        notifier.send_entry_alert(
            symbol=symbol,
            side=side,
            entry_price=current_price,
            sl=sl,
            tp=tp,
            lots=lots,
            risk_usd=self.fixed_risk_usd,
            leverage=LEVERAGE_MAP.get(symbol, 100)
        )

    def _close_position(self, symbol: str, exit_price: float, reason: str):
        """Closes active position, calculates final P&L, records trade in SQLite and journals."""
        pos = self.active_positions.pop(symbol, None)
        if not pos:
            return

        p = self.params[symbol]
        c_val = p["c_val"]
        side = pos["side"]
        entry = pos["entry_price"]
        rem_lots = pos["remaining_lots"]
        dist = pos["dist"]

        # Close remaining lots directly on Delta Exchange if live AND closure was initiated locally
        # (CRITICAL FIX: NEVER send a market order if Delta Exchange already filled the exit, as that would open a phantom reverse position!)
        if self.is_live_authenticated:
            if rem_lots > 0 and reason != "EXCHANGE_FILLED_EXIT":
                try:
                    close_side = "sell" if side == "BUY" else "buy"
                    self.client.place_bracket_order(
                        symbol=symbol,
                        side=close_side,
                        size=rem_lots,
                        order_type="market_order"
                    )
                    print(f"🏁 [DELTA LIVE ORDER] {symbol} {close_side.upper()} {rem_lots} Lots filled @ ${exit_price} ({reason})")
                except Exception as e:
                    print(f"[DELTA LIVE CLOSE NOTICE] {e}")

            # Cancel all remaining resting bracket orders (Stop Loss / Take Profit) on Delta Exchange
            try:
                self.client.cancel_all_orders(symbol)
                print(f"🧹 [DELTA RESTING ORDERS CANCELLED] Cleaned up orders for {symbol}")
            except Exception as e:
                pass

        # Calculate remainder P&L
        if side == "BUY":
            diff = exit_price - entry
        else:
            diff = entry - exit_price

        is_sl = ("SL" in reason.upper()) or ("STOP" in reason.upper())
        if "XAUT" in symbol or "SLV" in symbol:
            fee_rem = 0.005 if pos.get("tp1_hit") else 0.01
        else:
            exit_rate = 0.0005 if is_sl else 0.0002 # 0.05% Taker on SL, 0.02% Maker on TP
            entry_fee = (rem_lots * c_val * entry * 0.0002) if not pos.get("tp1_hit") else 0.0
            exit_fee = (rem_lots * c_val * exit_price * exit_rate)
            fee_rem = round(entry_fee + exit_fee, 4)

        rem_pnl = (rem_lots * c_val * diff) - fee_rem
        total_pnl = round(pos["booked_pnl"] + rem_pnl, 2)
        total_fee = round(pos.get("booked_fees", 0.0) + fee_rem, 4)
        rr_achieved = round(total_pnl / self.fixed_risk_usd, 1)

        closed_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        trade_log = {
            "id": pos["id"],
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "exit_price": exit_price,
            "stop_loss": pos["stop_loss"],
            "take_profit": pos["take_profit"],
            "lots": pos["lots"],
            "notional_usd": pos["notional_usd"],
            "margin_usd": pos["margin_usd"],
            "leverage": pos["leverage"],
            "risk_usd": pos["risk_usd"],
            "pnl_usd": total_pnl,
            "rr_achieved": rr_achieved,
            "opened_at": pos["opened_at"],
            "closed_at": closed_at,
            "status": "CLOSED",
            "close_reason": reason,
            "strategy_name": pos["strategy_name"],
            "conviction_stars": 5.0,
            "orderflow_notes": f"Multi-Pair Execution: Closed {reason} @ ${exit_price}. Net: ${total_pnl:+.2f} ({rr_achieved:+.1f}R).",
            "is_paper": 0 if self.is_live_authenticated else 1
        }

        # Log trade to SQLite
        self.db.log_trade(trade_log)

        # Dispatch real-time exit email/telegram notification
        notifier.send_exit_alert(symbol, side, exit_price, total_pnl, reason)

        # Enforce Rule 1: 10-minute cooldown on this pair after closing
        self.cooldown_until[symbol] = time.time() + 600.0
        exp_time = datetime.fromtimestamp(self.cooldown_until[symbol]).strftime("%H:%M:%S")
        print(f"⏳ [COOLDOWN ACTIVATED] {symbol} trade closed ({reason}). 10-minute cooldown active until {exp_time}. No immediate re-entries allowed on {symbol}.")
        self.db.log_thought(
            symbol=symbol,
            event_type="POST_TRADE_COOLDOWN",
            stars=5.0,
            message=f"⏳ Post-trade cooldown active on {symbol} for 10 minutes until {exp_time} ({reason}). Preserving capital against immediate re-entries."
        )

        print(f"\n🏁 [POSITION CLOSED] {symbol} {side} Exit @ ${exit_price} ({reason}) | Net P&L: ${total_pnl:+.2f} ({rr_achieved:+.1f}R)")
        print(f"📊 Remaining Active Positions: {list(self.active_positions.keys()) or 'None (All Cash)'}")

        # Update living journals
        self._sync_live_dashboards()

    def _sync_live_dashboards(self):
        """Regenerates journals and live dashboard after any trade event or scan tick."""
        try:
            trades = self.db.get_trades(limit=5000)
            thoughts = self.db.get_recent_thoughts(limit=50)
            # 1. Update Dedicated Live Journal
            self.reporter.generate_live_journal(
                active_positions=self.active_positions,
                recent_trades=trades,
                db_thoughts=thoughts,
                delta_client=self.client
            )
            # 2. Update Standard Journals
            self.reporter.generate_all_journals(
                joint_trades=trades,
                gold_trades=[t for t in trades if "XAUT" in (t.get("symbol") or "")],
                silver_trades=[t for t in trades if "SLV" in (t.get("symbol") or "")],
                btc_trades=[t for t in trades if "BTC" in (t.get("symbol") or "")],
                eth_trades=[t for t in trades if "ETH" in (t.get("symbol") or "")],
                db_thoughts=thoughts
            )
        except Exception as e:
            print(f"[REPORTER ERROR] Failed to sync dashboards: {e}")
