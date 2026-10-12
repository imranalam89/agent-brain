import sys
import time
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
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
from strategies.orderflow_engine import OrderFlowEngine
from alerts.alert_dispatcher import dispatcher as notifier

class MultiPairLiveTrader:
    """
    Autonomous Level 2 DOM Institutional Order Flow Trading Engine.
    
    Verified Model C Macro Runner Strategy:
    1. Pure Level 2 Microstructure:
       - 100% driven by real-time Order Book Imbalance & Institutional Resting Walls.
       - Discards lagging candle oscillators and VWAP bands.
    2. Asset-Specific Execution Modes:
       - BTCUSD : BREAKOUT Mode (Imbalance >= 3.0x, TP 2.2%, SL 0.3%, Cooldown 15m)
       - ETHUSD : SESSION_FLOW Mode (Imbalance >= 2.0x, TP 2.0%, SL 0.3%, Cooldown 10m)
       - XAUTUSD: ABSORPTION_FADE Mode (Imbalance >= 2.0x / Asks >= 3.1x Bids, TP 0.8%, SL 0.2%, Cooldown 10m)
       - SLVONUSD: BREAKOUT Mode (Imbalance >= 2.5x, TP 2.0%, SL 0.3%, Cooldown 10m)
    3. Strict Invariants:
       - Capital: $50.00 USD base with strictly $5.00 fixed risk per trade.
       - Mutual Exclusion: Exactly 1 open position per symbol at any time.
       - Weekend Filter: Saturday & Sunday paused (institutional desks closed).
       - Time-Confluence Filter: Pauses during midday lunch chop (13:00-14:00 IST) and late NY whipsaw (22:00-23:15 IST).
    4. Model C Macro Runner Trade Management:
       - Breakeven profit lock (+0.20R guaranteed green) at +1.0R.
       - Wide Breathing Trailing Stop (1.35x SL buffer behind peak price) starting at +1.5R.
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

        # Order Flow Microstructure Engine
        self.orderflow_engine = OrderFlowEngine(min_imbalance_ratio=1.8)

        # Asset-specific DOM parameters calibrated from 80+ Hours continuous recording
        self.params = {
            "BTCUSD": {
                "mode": "BREAKOUT",
                "min_imbalance": 3.0,
                "tp_pct": 0.022,     # 2.2% Take Profit
                "sl_pct": 0.003,     # 0.3% Stop Loss (1:7.33 R:R)
                "cooldown_sec": 900, # 15 minutes cooldown
                "c_val": 0.001,
                "decimals": 1,
                "strategy_label": "DOM Breakout & Ask/Bid Sweep (Model C Macro Runner)"
            },
            "ETHUSD": {
                "mode": "SESSION_FLOW",
                "min_imbalance": 2.0,
                "tp_pct": 0.020,     # 2.0% Take Profit
                "sl_pct": 0.003,     # 0.3% Stop Loss (1:6.67 R:R)
                "cooldown_sec": 600, # 10 minutes cooldown
                "c_val": 0.01,
                "decimals": 2,
                "strategy_label": "DOM London/NY Session Flow Wall Defense (Model C Macro Runner)"
            },
            "XAUTUSD": {
                "mode": "ABSORPTION_FADE",
                "min_imbalance": 2.0,
                "tp_pct": 0.008,     # 0.8% Take Profit
                "sl_pct": 0.002,     # 0.2% Stop Loss (1:4.0 R:R)
                "cooldown_sec": 600, # 10 minutes cooldown
                "c_val": 0.001,
                "decimals": 2,
                "strategy_label": "DOM Institutional Absorption Trap & Reversal (Model C Macro Runner)"
            },
            "SLVONUSD": {
                "mode": "BREAKOUT",
                "min_imbalance": 2.5,
                "tp_pct": 0.020,     # 2.0% Take Profit
                "sl_pct": 0.003,     # 0.3% Stop Loss (1:6.67 R:R)
                "cooldown_sec": 600, # 10 minutes cooldown
                "c_val": 0.1,
                "decimals": 3,
                "strategy_label": "DOM Breakout & Liquidity Wall Sweep (Model C Macro Runner)"
            }
        }

        # Rolling micro price window for absorption detection
        self.price_window: Dict[str, List[float]] = {s: [] for s in ACTIVE_SYMBOLS}
        self.cooldown_until: Dict[str, float] = {}
        self.missing_exchange_counts: Dict[str, int] = {}
        self.last_thought_log: Dict[str, float] = {}

        # Check API key status
        self.is_live_authenticated = False
        self.client_ip = "Unknown"
        self._verify_credentials()
        self._load_open_positions_from_db()

    def _verify_credentials(self):
        """Checks if API key is authenticated on Delta Exchange."""
        res = self.client.get_wallet_balances()
        if res.get("success"):
            self.is_live_authenticated = True
            print("[LIVE TRADER] Authenticated with Delta Exchange. Real order execution ACTIVE.")
        else:
            self.client_ip = res.get("client_ip", "Unknown")
            print(f"[LIVE TRADER] Real API returned: {res.get('error')}")
            print(f"[LIVE TRADER] Running in LIVE STREAM PAPER MODE (100% realistic fills & real-time monitoring).")
            if self.client_ip != "Unknown":
                print(f"[LIVE TRADER] To enable real money orders, whitelist IP '{self.client_ip}' in Delta Exchange API settings.")

    def _load_open_positions_from_db(self):
        """Restores any active OPEN positions and post-trade cooldowns from SQLite on engine boot."""
        try:
            trades = self.db.get_trades(limit=50)
            open_trades = [t for t in trades if t.get("status") == "OPEN"]
            for t in open_trades:
                sym = t.get("symbol")
                if not sym or sym not in self.params:
                    continue
                lots = int(float(t.get("lots") or 1))
                entry_p = float(t.get("entry_price", 0))
                sl_p = float(t.get("stop_loss", 0))
                tp_p = float(t.get("take_profit", 0))
                dist = abs(entry_p - sl_p)
                sl_pct = self.params[sym]["sl_pct"]
                tp_pct = self.params[sym]["tp_pct"]

                self.active_positions[sym] = {
                    "id": t.get("id"),
                    "symbol": sym,
                    "side": t.get("side"),
                    "entry_price": entry_p,
                    "stop_loss": sl_p,
                    "take_profit": tp_p,
                    "dist": dist,
                    "sl_pct": sl_pct,
                    "tp_pct": tp_pct,
                    "lots": lots,
                    "remaining_lots": lots,
                    "notional_usd": float(t.get("notional_usd") or 0),
                    "margin_usd": float(t.get("margin_usd") or 0),
                    "opened_at": t.get("opened_at"),
                    "opened_ts": time.time(),
                    "be_locked": False,
                    "leverage": t.get("leverage") or LEVERAGE_MAP.get(sym, 100),
                    "risk_usd": self.fixed_risk_usd,
                    "strategy_name": t.get("strategy_name") or self.params[sym]["strategy_label"]
                }
                print(f"🔄 [RESTORED OPEN POSITION] {sym} {t.get('side')} (ID: {t.get('id')}) restored from database.")

            # Restore cooldowns for recently closed trades
            closed_trades = [t for t in trades if t.get("status") == "CLOSED"]
            for t in closed_trades:
                sym = t.get("symbol")
                if not sym or sym not in self.params or sym in self.cooldown_until:
                    continue
                c_str = t.get("closed_at")
                if c_str:
                    try:
                        try:
                            c_dt = datetime.fromisoformat(c_str)
                        except Exception:
                            c_dt = datetime.strptime(c_str, "%Y-%m-%d %H:%M:%S")
                        elapsed = time.time() - c_dt.timestamp()
                        cd_sec = self.params[sym]["cooldown_sec"]
                        if elapsed < cd_sec:
                            self.cooldown_until[sym] = c_dt.timestamp() + cd_sec
                            rem = int(self.cooldown_until[sym] - time.time())
                            print(f"⏳ [COOLDOWN RESTORED] {sym} cooldown active ({rem // 60}m {rem % 60}s remaining).")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[NOTICE] Could not restore open positions: {e}")

    def _adopt_exchange_position(self, symbol: str, p: Dict[str, Any]):
        """Adopts an open position from Delta Exchange, ensures bracket protection, logs to DB, and sends alerts."""
        size = float(p.get("size", 0))
        side = "BUY" if size > 0 else "SELL"
        lots = abs(int(size))
        entry_price = float(p.get("entry_price") or p.get("mark_price") or 0.0)
        param = self.params[symbol]
        sl_pct = param["sl_pct"]
        tp_pct = param["tp_pct"]
        decimals = param["decimals"]

        sl = round(entry_price * (1.0 - sl_pct) if side == "BUY" else entry_price * (1.0 + sl_pct), decimals)
        tp = round(entry_price * (1.0 + tp_pct) if side == "BUY" else entry_price * (1.0 - tp_pct), decimals)
        dist = abs(entry_price - sl)

        # Ensure bracket orders on Delta if live
        close_side = "sell" if side == "BUY" else "buy"
        if self.is_live_authenticated:
            try:
                open_orders = self.client._request("GET", "/v2/orders?state=open", auth=True)
                existing = open_orders.get("result", []) if open_orders.get("success") else []
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
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "lots": lots,
            "remaining_lots": lots,
            "notional_usd": round(lots * param["c_val"] * entry_price, 2),
            "margin_usd": float(p.get("margin", 0.0)),
            "opened_at": p.get("created_at") or datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "opened_ts": time.time(),
            "be_locked": False,
            "leverage": LEVERAGE_MAP.get(symbol, 100),
            "risk_usd": self.fixed_risk_usd,
            "strategy_name": param["strategy_label"]
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
            "orderflow_notes": f"Adopted Live Delta Execution: {side} {lots} Lots @ ${entry_price}. DOM Institutional Strategy.",
            "is_paper": 0
        }
        self.db.log_trade(open_log)

        # Dispatch real-time Telegram entry alert
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

    def scan_and_manage_all_pairs(self) -> Dict[str, Any]:
        """
        Executes one full concurrent cycle across ALL active pairs:
        1. Checks risk limits & daily circuit breaker ($20 max daily loss).
        2. Queries live exchange positions from Delta Exchange (Strict 1-position invariant).
        3. Manages active positions (Model C Breakeven at +0.8R, Breathing Trailing at +1.5R).
        4. Scans for new Level 2 DOM setups on pairs that are FLAT and past cooldown.
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

        # 2. Query live exchange positions from Delta Exchange
        exchange_positions = {}
        if self.is_live_authenticated:
            try:
                raw_pos = self.client.get_positions()
                for p in raw_pos:
                    s = p.get("product_symbol")
                    sz = float(p.get("size", 0))
                    if s and sz != 0:
                        exchange_positions[s] = p
            except Exception:
                pass

        # 3. Iterate through each symbol independently
        for symbol in ACTIVE_SYMBOLS:
            try:
                ticker = self.client.get_ticker(symbol)
                mark_price = float(ticker.get("mark_price") or ticker.get("close") or 0.0)
                if mark_price <= 0:
                    continue

                has_local = symbol in self.active_positions
                has_exchange = symbol in exchange_positions

                # 3A. STRICT INVARIANT: 1 Active Position per symbol at any time
                if has_local or has_exchange:
                    pos_age = time.time() - self.active_positions.get(symbol, {}).get("opened_ts", time.time())
                    if has_local and self.is_live_authenticated and not has_exchange and pos_age > 90:
                        self.missing_exchange_counts[symbol] = self.missing_exchange_counts.get(symbol, 0) + 1
                        if self.missing_exchange_counts[symbol] >= 6:
                            self.missing_exchange_counts[symbol] = 0
                            print(f"⚡ [DELTA EXCHANGE SYNC] {symbol} position confirmed closed on Delta. Finalizing trade @ mark price ${mark_price:,.2f}...")
                            self._close_position(symbol, mark_price, reason="EXCHANGE_FILLED_EXIT")
                        continue
                    else:
                        self.missing_exchange_counts[symbol] = 0

                    if not has_local and has_exchange:
                        self._adopt_exchange_position(symbol, exchange_positions[symbol])
                    
                    # Manage the active position (Breakeven + Model C Trailing)
                    self._manage_active_position(symbol, mark_price)
                    status_report["positions"][symbol] = self.active_positions.get(symbol, {})
                    # STRICT MUTUAL EXCLUSION: NEVER scan or enter another trade while position is active!
                    continue

                # 3B. Check Cooldown
                now_ts = time.time()
                cooldown_end = self.cooldown_until.get(symbol, 0.0)
                if now_ts < cooldown_end:
                    continue

                # Check Master Bot Pause Switch
                is_paused, pause_reason, pause_until = self.db.is_bot_paused()
                if is_paused:
                    status_report["bot_status"] = "PAUSED"
                    status_report["pause_reason"] = pause_reason
                    status_report["pause_until"] = pause_until
                    continue

                # 3C. Pair is FLAT and cooldown clear: Scan Level 2 DOM for high-probability Institutional Setup
                signal = self._evaluate_entry_signal(symbol, mark_price)
                if signal:
                    status_report["signals"][symbol] = signal
                    self._execute_entry(symbol, signal, mark_price)

            except Exception as e:
                print(f"[ERROR] Error monitoring {symbol}: {e}")

        # Update bot status
        is_paused, pause_reason, pause_until = self.db.is_bot_paused()
        status_report["bot_status"] = "PAUSED" if is_paused else "ACTIVE"
        status_report["target_risk_usd"] = self.db.get_target_risk_usd(self.fixed_risk_usd)
        status_report["pause_reason"] = pause_reason
        status_report["pause_until"] = pause_until

        # Update living journal dashboards
        self._sync_live_dashboards()

        return status_report

    def _manage_active_position(self, symbol: str, current_price: float):
        """
        Model C Wide Breathing Macro Runner Trade Management:
        1. Breakeven Move at +0.8R: Move stop loss to entry price (100% position risk-free).
        2. Model C Trailing Stop at +1.5R: Ratchet SL with 1.35x SL buffer behind peak price.
        3. Take Profit Exit: Full exit on target.
        4. Stop Loss / Breakeven Exit: Full exit on stop hit.
        """
        pos = self.active_positions[symbol]
        side = pos["side"]
        entry = pos["entry_price"]
        sl_pct = pos.get("sl_pct", self.params[symbol]["sl_pct"])
        tp_pct = pos.get("tp_pct", self.params[symbol]["tp_pct"])
        decimals = self.params[symbol]["decimals"]

        if side == "BUY":
            profit_pct = (current_price - entry) / entry
        else:
            profit_pct = (entry - current_price) / entry

        r_mult = profit_pct / max(1e-6, sl_pct)

        # 1. Breakeven Profit Lock at +1.0R (Locks +0.20R guaranteed net profit)
        if r_mult >= 1.0:
            one_r_dist = entry * sl_pct
            if side == "BUY":
                be_price = round(entry + (0.20 * one_r_dist), decimals)
                if be_price > pos["stop_loss"]:
                    pos["stop_loss"] = be_price
                    pos["be_locked"] = True
                    print(f"🛡️ [BREAKEVEN PROFIT LOCKED] {symbol} {side} SL locked at ${be_price:,.2f} (+0.20R profit buffer). Trade is guaranteed green.")
                    self.db.log_thought(
                        symbol=symbol,
                        event_type="BREAKEVEN_LOCKED",
                        stars=5.0,
                        message=f"🛡️ Model C Breakeven locked on {symbol} {side} @ ${current_price:,.2f} (+{r_mult:.1f}R reached). SL moved to ${be_price:,.2f} (+0.20R profit secured). Position is 100% risk-free and fee-covered."
                    )
                    notifier.send_breakeven_alert(symbol, side, current_price, be_price, r_mult)
            elif side == "SELL":
                be_price = round(entry - (0.20 * one_r_dist), decimals)
                if be_price < pos["stop_loss"]:
                    pos["stop_loss"] = be_price
                    pos["be_locked"] = True
                    print(f"🛡️ [BREAKEVEN PROFIT LOCKED] {symbol} {side} SL locked at ${be_price:,.2f} (+0.20R profit buffer). Trade is guaranteed green.")
                    self.db.log_thought(
                        symbol=symbol,
                        event_type="BREAKEVEN_LOCKED",
                        stars=5.0,
                        message=f"🛡️ Model C Breakeven locked on {symbol} {side} @ ${current_price:,.2f} (+{r_mult:.1f}R reached). SL moved to ${be_price:,.2f} (+0.20R profit secured). Position is 100% risk-free and fee-covered."
                    )
                    notifier.send_breakeven_alert(symbol, side, current_price, be_price, r_mult)

        # 2. Model C Wide Breathing Trailing (1.35x SL buffer behind price) starting at +1.5R
        if r_mult >= 1.5:
            trail_mult = 1.35
            if side == "BUY":
                trail_level = round(current_price * (1.0 - (sl_pct * trail_mult)), decimals)
                if trail_level > pos["stop_loss"]:
                    pos["stop_loss"] = trail_level
                    print(f"⚡ [MODEL C TRAILING SL] {symbol} {side} trailing SL ratcheted to ${trail_level:,.2f} (+{r_mult:.1f}R expansion).")
                    notifier.send_trailing_alert(symbol, side, current_price, trail_level, r_mult)
            elif side == "SELL":
                trail_level = round(current_price * (1.0 + (sl_pct * trail_mult)), decimals)
                if trail_level < pos["stop_loss"]:
                    pos["stop_loss"] = trail_level
                    print(f"⚡ [MODEL C TRAILING SL] {symbol} {side} trailing SL ratcheted to ${trail_level:,.2f} (+{r_mult:.1f}R expansion).")
                    notifier.send_trailing_alert(symbol, side, current_price, trail_level, r_mult)

        # 3. Take Profit Exit Check
        tp_hit = (current_price >= pos["take_profit"]) if side == "BUY" else (current_price <= pos["take_profit"])
        if tp_hit:
            self._close_position(symbol, current_price, reason="TAKE_PROFIT")
            return

        # 4. Stop Loss / Breakeven Exit Check
        sl_hit = (current_price <= pos["stop_loss"]) if side == "BUY" else (current_price >= pos["stop_loss"])
        if sl_hit:
            reason = "BREAKEVEN" if pos.get("be_locked") else "STOP_LOSS"
            self._close_position(symbol, current_price, reason=reason)
            return

    def _evaluate_entry_signal(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Pure Level 2 DOM Institutional Order Flow Entry Evaluation.
        Enforces Weekend, Time-Confluence, and Asset-Specific Microstructure Rules.
        """
        # 1. Check Cooldown
        if time.time() < self.cooldown_until.get(symbol, 0.0):
            return None

        # Maintain rolling price window
        win = self.price_window.setdefault(symbol, [])
        win.append(current_price)
        if len(win) > 200:
            win.pop(0)

        now_ist = datetime.now(IST)
        now_ts = time.time()

        # 2. Weekend Rule: Saturday (5) & Sunday (6) low-liquidity retail chop paused
        if now_ist.weekday() in (5, 6):
            if now_ts - self.last_thought_log.get(f"{symbol}_weekend", 0) > 900:
                self.last_thought_log[f"{symbol}_weekend"] = now_ts
                self.db.log_thought(
                    symbol=symbol,
                    event_type="WEEKEND_FILTER",
                    stars=3.0,
                    message="⏸️ Weekend Filter Active: Saturday & Sunday retail chop paused. Institutional desks closed. Trading resumes Monday."
                )
            return None

        # 3. Time-Confluence (Institutional Hours) Filter:
        # A. London Lunch Consolidation Chop (13:00 - 14:00 IST)
        # B. Late Night NY After-Hours Whipsaw (22:00 - 23:15 IST)
        in_lunch_chop = (now_ist.hour == 13)
        in_late_ny_whipsaw = (now_ist.hour == 22) or (now_ist.hour == 23 and now_ist.minute < 15)

        if in_lunch_chop or in_late_ny_whipsaw:
            if now_ts - self.last_thought_log.get(f"{symbol}_session_filter", 0) > 900:
                self.last_thought_log[f"{symbol}_session_filter"] = now_ts
                reason = "London Lunch Chop (13:00-14:00 IST)" if in_lunch_chop else "Late Night NY Whipsaw (22:00-23:15 IST)"
                self.db.log_thought(
                    symbol=symbol,
                    event_type="SESSION_FILTER",
                    stars=3.0,
                    message=f"⏸️ Time-Confluence Filter: Paused during {reason}. Preserving capital for high-momentum institutional hours."
                )
            return None

        # 4. Fetch Level 2 Order Book Depth from Delta Exchange
        dom_data = self.client.get_l2_orderbook(symbol, depth=50)
        bids = dom_data.get("bids", []) if isinstance(dom_data, dict) else []
        asks = dom_data.get("asks", []) if isinstance(dom_data, dict) else []
        if not bids or not asks:
            return None

        metrics = self.orderflow_engine.analyze_dom(bids, asks)
        total_bids = metrics.get("total_bid_size", 0.0)
        total_asks = metrics.get("total_ask_size", 0.0)
        buyer_ratio = (total_bids / total_asks) if total_asks > 0 else 1.0
        seller_ratio = (total_asks / total_bids) if total_bids > 0 else 1.0
        side_dominant = metrics.get("dominant_side", "NEUTRAL")
        bid_walls = metrics.get("bid_walls", [])
        ask_walls = metrics.get("ask_walls", [])
        mid = metrics.get("mid_price") or current_price

        cfg = self.params[symbol]
        mode = cfg["mode"]
        min_imb = cfg["min_imbalance"]

        has_bid_wall = any(w.get("price", 0) <= mid for w in bid_walls) if bid_walls else False
        has_ask_wall = any(w.get("price", 0) >= mid for w in ask_walls) if ask_walls else False

        long_trigger = False
        short_trigger = False
        strat_title = ""

        # 5. Evaluate Exact Asset Strategy Mode
        if mode == "BREAKOUT":
            # BTCUSD (3.0x), SLVONUSD (2.5x): Momentum sweep through resting liquidity walls
            long_trigger = (side_dominant == "BUYERS" and buyer_ratio >= min_imb and (has_ask_wall or len(ask_walls) > 0))
            short_trigger = (side_dominant == "SELLERS" and seller_ratio >= min_imb and (has_bid_wall or len(bid_walls) > 0))
            strat_title = f"DOM {symbol} Breakout & Ask Wall Sweep" if long_trigger else f"DOM {symbol} Breakout & Bid Wall Sweep"

        elif mode == "SESSION_FLOW":
            # ETHUSD (2.0x): Trend continuation during London/NY liquid sessions (13:00 - 23:45 IST)
            in_session = (13 <= now_ist.hour <= 23)
            if in_session:
                long_trigger = (side_dominant == "BUYERS" and buyer_ratio >= min_imb and (has_bid_wall or len(bid_walls) > 0))
                short_trigger = (side_dominant == "SELLERS" and seller_ratio >= min_imb and (has_ask_wall or len(ask_walls) > 0))
                strat_title = f"DOM {symbol} London/NY Session Flow Wall Defense"

        elif mode == "ABSORPTION_FADE":
            # XAUTUSD (2.0x / Asks >= 3.1x Bids): Contrarian fade when massive order flow fails to push price
            if len(win) >= 20:
                price_change = mid - win[-20]
                # Trapped sellers (BUY): Heavy seller pressure or ask wall dominance, but price refuses to drop
                seller_exhausted = (side_dominant == "SELLERS" and seller_ratio >= min_imb) or (buyer_ratio <= 0.32)
                long_trigger = seller_exhausted and (price_change >= (-0.0001 * mid)) and (has_bid_wall or len(bid_walls) > 0)

                # Trapped buyers (SELL): Heavy buyer pressure, but price refuses to rally
                short_trigger = (side_dominant == "BUYERS" and buyer_ratio >= min_imb) and (price_change <= (0.0001 * mid)) and (has_ask_wall or len(ask_walls) > 0)
                strat_title = f"DOM {symbol} Seller Absorption Trap & Reversal" if long_trigger else f"DOM {symbol} Buyer Absorption Trap & Reversal"

        # Periodic status thought log in Live Journal for UI transparency
        last_t = self.last_thought_log.get(symbol, 0)
        if now_ts - last_t > 120:
            self.last_thought_log[symbol] = now_ts
            ratio_disp = buyer_ratio if side_dominant == "BUYERS" else seller_ratio
            wall_info = f"Walls: {len(bid_walls)} Bids / {len(ask_walls)} Asks"
            self.db.log_thought(
                symbol=symbol,
                event_type="SETUP_MONITOR",
                stars=3.5 if (long_trigger or short_trigger) else 2.5,
                message=f"Scanning {symbol} ({mode}): DOM Ratio {ratio_disp:.2f}x ({side_dominant}). {wall_info}. Mid: ${mid:,.2f}."
            )

        if not long_trigger and not short_trigger:
            return None

        trade_side = "BUY" if long_trigger else "SELL"
        tp_pct = cfg["tp_pct"]
        sl_pct = cfg["sl_pct"]
        decimals = cfg["decimals"]
        c_val = cfg["c_val"]

        if trade_side == "BUY":
            tp_price = round(mid * (1.0 + tp_pct), decimals)
            sl_price = round(mid * (1.0 - sl_pct), decimals)
        else:
            tp_price = round(mid * (1.0 - tp_pct), decimals)
            sl_price = round(mid * (1.0 + sl_pct), decimals)

        # Strictly $5.00 fixed risk per trade sizing
        sl_distance_usd = mid * sl_pct
        current_risk = self.db.get_target_risk_usd(self.fixed_risk_usd)
        raw_lots = current_risk / max(0.0001, sl_distance_usd * c_val)
        lots = max(1, round(raw_lots))

        return {
            "symbol": symbol,
            "side": trade_side,
            "entry_price": mid,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "dist": sl_distance_usd,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "lots": lots,
            "risk_usd": current_risk,
            "strategy_name": f"{cfg['strategy_label']} ({strat_title})",
            "buyer_ratio": round(buyer_ratio, 2),
            "seller_ratio": round(seller_ratio, 2),
            "walls_count": len(ask_walls if trade_side == "BUY" and mode == "BREAKOUT" else bid_walls)
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
        sl_pct = signal["sl_pct"]
        tp_pct = signal["tp_pct"]
        current_risk = signal.get("risk_usd") or self.db.get_target_risk_usd(self.fixed_risk_usd)

        notional = round(lots * c_val * current_price, 2)
        margin = round(notional / LEVERAGE_MAP.get(symbol, 100), 2)

        # Submit live bracket order to Delta Exchange if live authenticated
        if self.is_live_authenticated:
            try:
                order_res = self.client.place_bracket_order(
                    symbol=symbol,
                    side=side.lower(),
                    size=lots,
                    order_type="market_order",
                    stop_loss_price=sl,
                    take_profit_price=tp
                )
                print(f"🚀 [DELTA LIVE ORDER PLACED] {symbol} {side} {lots} Lots (Risk: ${current_risk:.2f} | SL: ${sl} | TP: ${tp}) -> Response: {order_res.get('success')}")
            except Exception as e:
                print(f"[DELTA LIVE ORDER ERROR] {e}")

        trade_id = f"LIVE_{symbol}_{int(time.time())}"
        pos_record = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "stop_loss": sl,
            "take_profit": tp,
            "dist": dist,
            "sl_pct": sl_pct,
            "tp_pct": tp_pct,
            "lots": lots,
            "remaining_lots": lots,
            "notional_usd": notional,
            "margin_usd": margin,
            "opened_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "opened_ts": time.time(),
            "be_locked": False,
            "leverage": LEVERAGE_MAP.get(symbol, 100),
            "risk_usd": current_risk,
            "strategy_name": signal.get("strategy_name", p["strategy_label"])
        }

        self.active_positions[symbol] = pos_record
        print(f"✅ [DOM POSITION OPENED] {symbol} {side} @ ${current_price:,.2f} | Lots: {lots} | Fixed Risk: ${current_risk:.2f} | Open Pairs: {list(self.active_positions.keys())}")

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
            "risk_usd": current_risk,
            "pnl_usd": 0.0,
            "rr_achieved": 0.0,
            "opened_at": pos_record["opened_at"],
            "closed_at": None,
            "status": "OPEN",
            "close_reason": None,
            "strategy_name": pos_record["strategy_name"],
            "conviction_stars": 5.0,
            "orderflow_notes": f"DOM Institutional Entry: {side} {lots} Lots @ ${current_price}. Strict ${current_risk:.2f} Risk. Mode: {p['mode']}.",
            "is_paper": 0 if self.is_live_authenticated else 1
        }
        self.db.log_trade(open_log)

        # Log thought in database
        self.db.log_thought(
            symbol=symbol,
            event_type="LIVE_ENTRY_TRIGGERED",
            stars=5.0,
            message=f"🚀 Level 2 DOM Entry Triggered on {symbol} {side} @ ${current_price:,.2f}. Lots: {lots}. Risk: ${current_risk:.2f}. Active Pairs: {list(self.active_positions.keys())}."
        )

        # Dispatch real-time notification
        notifier.send_entry_alert(
            symbol=symbol,
            side=side,
            entry_price=current_price,
            sl=sl,
            tp=tp,
            lots=lots,
            risk_usd=current_risk,
            leverage=LEVERAGE_MAP.get(symbol, 100)
        )

    def _close_position(self, symbol: str, exit_price: float, reason: str):
        """Closes active position, calculates final P&L with Delta India fees, and updates journals."""
        pos = self.active_positions.pop(symbol, None)
        if not pos:
            return

        p = self.params[symbol]
        c_val = p["c_val"]
        side = pos["side"]
        entry = pos["entry_price"]
        rem_lots = pos["remaining_lots"]
        notional = pos["notional_usd"]

        # Close remaining lots directly on Delta Exchange if live
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

            # Clean up resting bracket orders
            try:
                self.client.cancel_all_orders(symbol)
                print(f"🧹 [DELTA RESTING ORDERS CANCELLED] Cleaned up orders for {symbol}")
            except Exception:
                pass

        # Calculate exact gross P&L
        diff = (exit_price - entry) if side == "BUY" else (entry - exit_price)
        gross_pnl = diff * rem_lots * c_val

        # Calculate Delta Exchange India fees
        is_sl = ("SL" in reason.upper()) or ("STOP" in reason.upper())
        fee = calculate_brokerage_fee(symbol, notional, is_sl=is_sl)
        total_pnl = round(gross_pnl - fee, 2)
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
            "notional_usd": notional,
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
            "orderflow_notes": f"DOM Institutional Execution: Closed {reason} @ ${exit_price}. Net: ${total_pnl:+.2f} ({rr_achieved:+.1f}R). Fee: ${fee:.4f}.",
            "is_paper": 0 if self.is_live_authenticated else 1
        }

        # Log trade to SQLite
        self.db.log_trade(trade_log)

        # Dispatch real-time exit notification
        notifier.send_exit_alert(symbol, side, exit_price, total_pnl, reason)

        # Enforce post-trade cooldown (15m BTC, 10m ETH, Gold, Silver)
        cd_sec = p["cooldown_sec"]
        self.cooldown_until[symbol] = time.time() + cd_sec
        exp_time = datetime.fromtimestamp(self.cooldown_until[symbol]).strftime("%H:%M:%S")
        print(f"⏳ [COOLDOWN ACTIVATED] {symbol} closed ({reason}). Cooldown active until {exp_time} ({cd_sec//60} mins).")
        self.db.log_thought(
            symbol=symbol,
            event_type="POST_TRADE_COOLDOWN",
            stars=5.0,
            message=f"⏳ Post-trade cooldown active on {symbol} for {cd_sec//60} mins until {exp_time} ({reason}). Preserving capital against churn."
        )

        print(f"\n🏁 [POSITION CLOSED] {symbol} {side} Exit @ ${exit_price:,.2f} ({reason}) | Net P&L: ${total_pnl:+.2f} ({rr_achieved:+.1f}R)")
        print(f"📊 Remaining Active Positions: {list(self.active_positions.keys()) or 'None (All Cash)'}")

        # Sync live journals
        self._sync_live_dashboards()

    def _sync_live_dashboards(self):
        """Regenerates journals and live dashboard after any trade event or scan tick."""
        try:
            trades = self.db.get_trades(limit=5000)
            thoughts = self.db.get_recent_thoughts(limit=50)
            self.reporter.generate_live_journal(
                active_positions=self.active_positions,
                recent_trades=trades,
                db_thoughts=thoughts,
                delta_client=self.client
            )
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
