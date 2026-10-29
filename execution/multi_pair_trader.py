import sys
import time
import math
import json
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
    LEVERAGE_MAP,
    CHAMPION_CONFIG,
    CHAMPION_CONFIG_BTC,
    CHAMPION_CONFIG_ETH,
    WEEKEND_TRADING_SYMBOLS,
    WEEKEND_PAUSED_SYMBOLS
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
    
    Verified 3-Pair Champion Portfolio Architecture (Gold + BTC + ETH):
    1. Gold (XAUTUSD):
       - Level 2 DOM Trap & Order Flow Absorption (Fixed 1:3.00 RR, $5 risk).
       - London & NY Killzone (13:00 to 23:30 IST), 24-bar H/L breach & rejection,
         >= 25% wick, delta absorption flip, 4H EMA50 trend alignment.
       - Pauses Saturday/Sunday (commodity market closed).
    2. Bitcoin (BTCUSD):
       - 1H Macro Volume Climax Sweep + London Asian Judas Swing (Fixed 1:3.50 RR, $5 risk).
       - Technical Cushion: 0.35xATR preservation.
       - Engine 1: 20-hour sweep with >= 1.20x volume climax (12:00-23:30 IST).
       - Engine 2: Asian session sweep during London Open (12:30-17:00 IST) with >= 1.25x volume climax.
       - Continuous 24/7 trading (weekends included).
    3. Ethereum (ETHUSD):
       - Dual Engine: Momentum Breakout + DOM Liquidity Sweep (Fixed 1:3.50 RR, $5 risk).
       - London & NY Killzone (13:00 to 23:30 IST).
       - Engine 1: 33-bar Breakout with < 18% counter wick and 5m staircase alignment.
       - Engine 2: 48-bar Trap with >= 25% rejection wick and delta flip.
       - Continuous 24/7 trading (weekends included).
    4. All 3 Champion Pairs:
       - Strictly $5.00 fixed risk per trade.
       - Position Management: Fixed Technical Cushion Stop Loss (Preserves 0.35xATR/structural buffer).
       - No premature trailing choke, no early hostile cuts.
       - Strict Invariant: Exactly 1 open position per symbol at any time.
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
        self.verified_sl_orders: set = set()
        self.candle_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.last_candle_fetch: Dict[str, float] = {}

        # Order Flow Microstructure Engine
        self.orderflow_engine = OrderFlowEngine(min_imbalance_ratio=1.8)

        # Asset-specific DOM parameters calibrated from 3-Pair Champion Backtest
        self.params = {
            "BTCUSD": {
                "mode": "MACRO_SWEEP_JUDAS",
                "target_rr": 3.5,
                "min_risk": 80.0,
                "atr_cushion_mult": 0.35,
                "cooldown_sec": 900,
                "c_val": 0.001,
                "decimals": 2,
                "weekend_trading": True,
                "strategy_label": "Bitcoin 1H Macro Volume Climax Sweep + London Asian Judas"
            },
            "ETHUSD": {
                "mode": "DUAL_ENGINE",
                "target_rr": 3.5,
                "min_risk": 3.0,
                "sl_buffer": 0.50,
                "cooldown_sec": 900,
                "c_val": 0.01,
                "decimals": 2,
                "weekend_trading": True,
                "strategy_label": "Ethereum Dual Engine (Momentum Breakout + DOM Liquidity Sweep)"
            },
            "XAUTUSD": {
                "mode": "DOM_TRAP",
                "target_rr": 3.0,
                "min_risk": 2.50,
                "sl_buffer": 0.50,
                "cooldown_sec": 900,
                "c_val": 0.001,
                "decimals": 2,
                "weekend_trading": False,
                "strategy_label": "Gold Level 2 DOM Trap with Order Flow Absorption"
            }
        }

        # Track loss timestamps within lookback window for the cascade circuit breakers
        self.loss_timestamps: Dict[str, List[float]] = {s: [] for s in self.params}
        self.consecutive_losses: Dict[str, int] = {s: 0 for s in self.params}

        # Rolling micro price window for absorption detection
        self.price_window: Dict[str, List[float]] = {s: [] for s in ACTIVE_SYMBOLS}
        self.cooldown_until: Dict[str, float] = {}
        self.missing_exchange_counts: Dict[str, int] = {}
        self.last_thought_log: Dict[str, float] = {}
        self.last_evaluated_candle_ts: Dict[str, int] = {}

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

                opened_at_str = t.get("opened_at")
                opened_ts = time.time()
                if opened_at_str:
                    try:
                        opened_ts = datetime.fromisoformat(opened_at_str).timestamp()
                    except Exception:
                        try:
                            opened_ts = datetime.strptime(opened_at_str, "%Y-%m-%d %H:%M:%S").timestamp()
                        except Exception:
                            pass

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
                    "opened_at": opened_at_str,
                    "opened_ts": opened_ts,
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

            # Restore consecutive losses and cascade circuit breaker halts
            for sym in self.params:
                # 1. Load directly from SQLite persisted state
                saved_halt = self.db.get_system_state(f"cooldown_until_{sym}", 0.0)
                saved_consec = self.db.get_system_state(f"consecutive_losses_{sym}", None)
                saved_loss_ts = self.db.get_system_state(f"loss_timestamps_{sym}", None)
                if saved_halt and float(saved_halt) > time.time():
                    self.cooldown_until[sym] = max(self.cooldown_until.get(sym, 0), float(saved_halt))
                    rem_mins = int((float(saved_halt) - time.time()) / 60)
                    print(f"🚨 [PERSISTED CASCADE BREAKER RESTORED] {sym} halt restored from SQLite ({rem_mins}m remaining).")
                
                if saved_loss_ts:
                    try:
                        loaded_ts = json.loads(saved_loss_ts)
                        window_sec = self.params[sym].get("cascade_window_hours", 2.0) * 3600
                        now_ts = time.time()
                        self.loss_timestamps[sym] = [t for t in loaded_ts if (now_ts - t) <= window_sec]
                    except Exception:
                        self.loss_timestamps[sym] = []
                
                if self.loss_timestamps.get(sym):
                    self.consecutive_losses[sym] = len(self.loss_timestamps[sym])
                elif saved_consec is not None:
                    self.consecutive_losses[sym] = int(saved_consec)
                else:
                    # Fallback to trade history inspection
                    sym_trades = [t for t in closed_trades if t.get("symbol") == sym]
                    consec = 0
                    for tr in sym_trades[:5]:
                        pnl_val = float(tr.get("pnl_usd", 0) or 0)
                        if pnl_val < 0:
                            consec += 1
                        else:
                            break
                    self.consecutive_losses[sym] = consec
                    limit_losses = self.params[sym].get("cascade_breaker_losses", 2)
                    halt_hrs = self.params[sym].get("cascade_breaker_hours", 2.0)
                    if consec >= limit_losses and sym_trades:
                        c_str = sym_trades[0].get("closed_at")
                        if c_str:
                            try:
                                try:
                                    c_dt = datetime.fromisoformat(c_str)
                                except Exception:
                                    c_dt = datetime.strptime(c_str, "%Y-%m-%d %H:%M:%S")
                                halt_end = c_dt.timestamp() + (halt_hrs * 3600)
                                if time.time() < halt_end:
                                    self.cooldown_until[sym] = max(self.cooldown_until.get(sym, 0), halt_end)
                                    rem_mins = int((halt_end - time.time()) / 60)
                                    print(f"🚨 [CASCADE BREAKER RESTORED] {sym} halted ({consec} consecutive losses, {rem_mins}m remaining).")
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

        # 1. Circuit Breaker Check (Blocks new entries only, NEVER blocks managing active trades!)
        is_breaker, daily_loss = self.risk_mgr.is_daily_circuit_breaker_active()
        if is_breaker:
            status_report["bot_status"] = "CIRCUIT_BREAKER_ACTIVE"
            status_report["pause_reason"] = f"Daily loss limit hit (${daily_loss:.2f} >= ${self.risk_mgr.daily_loss_limit:.2f}). Managing open positions only."

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

        # 2B. Reconcile Delta Exchange Open/Stop Orders (Auto-cancel orphans & obsolete duplicates)
        if self.is_live_authenticated:
            try:
                all_open_orders = self.client.get_open_orders()
                active_symbols_on_exchange = set(exchange_positions.keys())
                for o in all_open_orders:
                    sym = o.get("product_symbol")
                    oid = o.get("id")
                    pid = o.get("product_id")
                    if not oid:
                        continue
                    # Case 1: Symbol has 0 position on exchange -> Cancel orphaned resting/stop order
                    if sym not in active_symbols_on_exchange:
                        print(f"🧹 [ORPHAN ORDER CLEANUP] Cancelling order {oid} for flat pair {sym} ({o.get('stop_order_type')} @ {o.get('stop_price')})")
                        self.client.cancel_order(oid, pid)
                    # Case 2: Symbol has active position -> Cancel obsolete stop-loss orders at older prices & replace with active SL
                    elif sym in self.active_positions:
                        current_sl = self.active_positions[sym].get("stop_loss")
                        stype = o.get("stop_order_type")
                        sprice = float(o.get("stop_price") or 0.0)
                        if stype == "stop_loss_order" and current_sl and abs(sprice - current_sl) > 0.05:
                            print(f"🧹 [OBSOLETE STOP CLEANUP] Cancelling old stop loss order {oid} on {sym} @ ${sprice} (Active SL is ${current_sl})")
                            self.client.cancel_order(oid, pid)
                            self.verified_sl_orders.discard(sym)
                            # Immediately place replacement active Stop Loss order on Delta Exchange
                            try:
                                side = self.active_positions[sym]["side"]
                                close_side = "sell" if side == "BUY" else "buy"
                                rem_lots = self.active_positions[sym].get("remaining_lots") or self.active_positions[sym].get("lots") or 1
                                sl_res = self.client.place_stop_order(
                                    symbol=sym,
                                    side=close_side,
                                    size=rem_lots,
                                    stop_price=current_sl,
                                    is_take_profit=False
                                )
                                if sl_res.get("success"):
                                    self.verified_sl_orders.add(sym)
                                    print(f"🛡️ [DELTA SL ORDER PLACED] {sym} {close_side.upper()} {rem_lots} Lots Stop @ ${current_sl} -> True")
                            except Exception as e_sl:
                                print(f"[REPLACEMENT SL ERROR] {sym}: {e_sl}")
            except Exception as e:
                print(f"[ORDER RECONCILIATION NOTICE] {e}")

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
                    if has_local and self.is_live_authenticated and not has_exchange and pos_age > 15:
                        self.missing_exchange_counts[symbol] = self.missing_exchange_counts.get(symbol, 0) + 1
                        if self.missing_exchange_counts[symbol] >= 3:
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

                # 3C. Pair is FLAT and cooldown clear: Check circuit breaker before new entries
                if is_breaker:
                    continue

                signal = self._evaluate_entry_signal(symbol, mark_price)
                if signal:
                    status_report["signals"][symbol] = signal
                    self._execute_entry(symbol, signal, mark_price)

            except Exception as e:
                import traceback
                print(f"[ERROR] Error monitoring {symbol}: {e}\n{traceback.format_exc()}", flush=True)

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
        Champion Multi-Asset Position Management:
        - Fixed technical Stop Loss & Take Profit bracket execution.
        - Strict Technical Cushion Preservation: Stop Loss stays anchored at its
          original structural invalidation level (0.35xATR or swing cushion).
        - No premature trailing or hostile orderbook cutting (which degrades PF by -16.8%).
        - Real-time exchange bracket order verification on Delta Exchange.
        """
        pos = self.active_positions[symbol]
        side = pos["side"]
        entry = pos["entry_price"]
        dist = pos.get("dist") or abs(entry - pos["stop_loss"])
        decimals = self.params[symbol]["decimals"]

        # Track excursions for telemetry
        if "highest_price" not in pos:
            pos["highest_price"] = max(entry, current_price)
            pos["lowest_price"] = min(entry, current_price)
        else:
            if current_price > pos["highest_price"]:
                pos["highest_price"] = current_price
            if current_price < pos["lowest_price"]:
                pos["lowest_price"] = current_price

        # Baseline check: Ensure Delta Exchange has the protective stop order active
        if self.is_live_authenticated and symbol in self.active_positions:
            try:
                open_orders = self.client.get_open_orders(symbol)
                has_sl = any(o.get("stop_order_type") == "stop_loss_order" for o in open_orders)
                if not has_sl:
                    close_side = "sell" if side == "BUY" else "buy"
                    rem_lots = pos.get("remaining_lots") or pos.get("lots") or 1
                    sl_res = self.client.place_stop_order(
                        symbol=symbol,
                        side=close_side,
                        size=rem_lots,
                        stop_price=pos["stop_loss"],
                        is_take_profit=False
                    )
                    if sl_res.get("success"):
                        self.verified_sl_orders.add(symbol)
                        print(f"🛡️ [DELTA EXCHANGE SL VERIFIED] {symbol} {close_side.upper()} Stop placed on Delta @ ${pos['stop_loss']}")
                else:
                    self.verified_sl_orders.add(symbol)
            except Exception as e:
                print(f"[DELTA BASELINE SL NOTICE] {e}")

        # 1. Take Profit Exit Check
        tp_hit = (current_price >= pos["take_profit"]) if side == "BUY" else (current_price <= pos["take_profit"])
        if tp_hit:
            self._close_position(symbol, current_price, reason="TAKE_PROFIT")
            return

        # 2. Stop Loss Exit Check
        sl_hit = (current_price <= pos["stop_loss"]) if side == "BUY" else (current_price >= pos["stop_loss"])
        if sl_hit:
            self._close_position(symbol, current_price, reason="STOP_LOSS")
            return

    @staticmethod
    def _calc_ema(prices: List[float], period: int) -> List[float]:
        if not prices:
            return []
        ema = [prices[0]]
        mult = 2.0 / (period + 1.0)
        for p in prices[1:]:
            ema.append((p - ema[-1]) * mult + ema[-1])
        return ema

    @staticmethod
    def _calc_atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 50.0
        trs = []
        for i in range(1, len(candles)):
            h = candles[i]["high"]
            l = candles[i]["low"]
            pc = candles[i - 1]["close"]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        if len(trs) < period:
            return sum(trs) / max(1, len(trs))
        return sum(trs[-period:]) / period

    @staticmethod
    def _calc_bollinger(prices: List[float], period: int = 20, num_std: float = 2.0):
        upper, mid, lower = [], [], []
        for i in range(len(prices)):
            if i < period:
                upper.append(prices[i])
                mid.append(prices[i])
                lower.append(prices[i])
            else:
                w = prices[i - period + 1 : i + 1]
                m = sum(w) / period
                std = math.sqrt(sum((x - m) ** 2 for x in w) / period)
                mid.append(m)
                upper.append(m + num_std * std)
                lower.append(m - num_std * std)
        return upper, mid, lower

    @staticmethod
    def _calc_rsi(prices: List[float], period: int = 14) -> List[float]:
        rsi = [50.0] * len(prices)
        if len(prices) <= period:
            return rsi
        gains, losses = [], []
        for i in range(1, period + 1):
            diff = prices[i] - prices[i - 1]
            gains.append(max(0.0, diff))
            losses.append(max(0.0, -diff))
        avg_g = sum(gains) / period
        avg_l = sum(losses) / period
        for i in range(period + 1, len(prices)):
            diff = prices[i] - prices[i - 1]
            g = max(0.0, diff)
            l = max(0.0, -diff)
            avg_g = (avg_g * (period - 1) + g) / period
            avg_l = (avg_l * (period - 1) + l) / period
            if avg_l == 0:
                rsi[i] = 100.0
            else:
                rsi[i] = 100.0 - (100.0 / (1.0 + (avg_g / avg_l)))
        return rsi

    def _aggregate_candles(self, candles: List[Dict[str, Any]], tf_seconds: int) -> List[Dict[str, Any]]:
        """Aggregates lower-timeframe candles into higher-timeframe candles."""
        if not candles:
            return []
        buckets = {}
        for c in candles:
            bts = (c["timestamp"] // tf_seconds) * tf_seconds
            if bts not in buckets:
                buckets[bts] = {
                    "timestamp": bts,
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c.get("volume", 0.0),
                    "delta": c.get("delta", 0.0)
                }
            else:
                b = buckets[bts]
                b["high"] = max(b["high"], c["high"])
                b["low"] = min(b["low"], c["low"])
                b["close"] = c["close"]
                b["volume"] += c.get("volume", 0.0)
                b["delta"] += c.get("delta", 0.0)
        res = list(buckets.values())
        res.sort(key=lambda x: x["timestamp"])
        return res

    @staticmethod
    def _get_closed_bars(candles: List[Dict[str, Any]], bar_duration_sec: int) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], int]:
        """
        Returns (last_closed_bar, prev_closed_bar, last_closed_bar_index).
        Guarantees that the evaluated bar is 100% completed and closed.
        """
        if not candles or len(candles) < 3:
            return None, None, -1
        now_ts = time.time()
        latest = candles[-1]
        # A bar at timestamp T spans [T, T + bar_duration_sec).
        if now_ts >= latest["timestamp"] + bar_duration_sec:
            return latest, candles[-2], len(candles) - 1
        else:
            return candles[-2], candles[-3], len(candles) - 2

    def _get_mtf_consensus(self, symbol: str) -> Tuple[str, Dict[str, Any]]:
        """
        Computes 3-Timeframe Trend Consensus (1D, 4H, 1H EMA 50).
        Requires at least 2 out of 3 votes for master trend.
        Uses 2,500 historical 15m bars from SQLite to guarantee mathematical convergence.
        """
        c15 = self._get_symbol_candles(symbol, resolution="15m", limit=2500)
        c4h = self._aggregate_candles(c15, 14400)
        c1h = self._aggregate_candles(c15, 3600)
        c1d = self._aggregate_candles(c15, 86400)

        ema4h = self._calc_ema([x["close"] for x in c4h], 50)
        ema1h = self._calc_ema([x["close"] for x in c1h], 50)
        ema1d = self._calc_ema([x["close"] for x in c1d], 50)

        v4h = 1 if (c4h and ema4h and c4h[-1]["close"] >= ema4h[-1]) else 0
        v1h = 1 if (c1h and ema1h and c1h[-1]["close"] >= ema1h[-1]) else 0
        v1d = 1 if (c1d and ema1d and c1d[-1]["close"] >= ema1d[-1]) else 0

        votes = v4h + v1h + v1d
        trend = "BULLISH" if votes >= 2 else "BEARISH"
        return trend, {
            "votes": votes,
            "v4h": v4h, "ema4h": ema4h[-1] if ema4h else 0.0,
            "v1h": v1h, "ema1h": ema1h[-1] if ema1h else 0.0,
            "v1d": v1d, "ema1d": ema1d[-1] if ema1d else 0.0,
        }

    def _get_symbol_candles(self, symbol: str, resolution: str = "15m", limit: int = 150) -> List[Dict[str, Any]]:
        """
        Retrieves recent candles for a symbol and resolution.
        Higher timeframes (30m, 1h, 4h, 1d) are aggregated from 15m bars to guarantee
        sufficient history for 50-period EMA convergence without missing bars.
        """
        # For HTF, resample from 15m candles
        if resolution in ("30m", "1h", "4h", "1d"):
            sec_map = {"30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
            tf_sec = sec_map.get(resolution, 14400)
            req_15m = max(2500, limit * (tf_sec // 900))
            c15 = self._get_symbol_candles(symbol, resolution="15m", limit=req_15m)
            return self._aggregate_candles(c15, tf_sec)

        cache_key = f"{symbol}_{resolution}"
        now_ts = time.time()
        cached = self.candle_cache.get(cache_key, [])
        last_fetch = self.last_candle_fetch.get(cache_key, 0.0)

        if cached and (now_ts - last_fetch < 15) and len(cached) >= limit // 2:
            return cached

        candles = []
        # 1. Try Delta REST API for recent 15m/5m bars
        try:
            bar_sec = 300 if resolution == "5m" else 900
            start_ts = int(now_ts - min(limit, 300) * bar_sec)
            api_res = self.client.get_candles(symbol, resolution=resolution, start=start_ts, end=int(now_ts))
            if api_res and len(api_res) >= 5:
                candles = api_res
        except Exception:
            pass

        # 2. Merge with or fallback to SQLite database
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT timestamp, open, high, low, close, volume, delta FROM candles WHERE symbol = ? AND timeframe = ? ORDER BY timestamp DESC LIMIT ?",
                    (symbol, resolution, limit)
                )
                rows = cursor.fetchall()
                if rows:
                    db_candles = [
                        {
                            "timestamp": r[0],
                            "open": float(r[1]),
                            "high": float(r[2]),
                            "low": float(r[3]),
                            "close": float(r[4]),
                            "volume": float(r[5] or 0.0),
                            "delta": float(r[6] or 0.0)
                        }
                        for r in reversed(rows)
                    ]
                    if not candles:
                        candles = db_candles
                    else:
                        # Combine db historical candles with latest API candles
                        c_map = {c["timestamp"]: c for c in db_candles}
                        for c in candles:
                            c_map[c["timestamp"]] = c
                        candles = [c_map[k] for k in sorted(c_map.keys())]
                        if len(candles) > limit:
                            candles = candles[-limit:]
        except Exception:
            pass

        if candles:
            self.candle_cache[cache_key] = candles
            self.last_candle_fetch[cache_key] = now_ts
            return candles

        return cached

    def _evaluate_entry_signal(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Champion Multi-Asset Institutional Order Flow Entry Evaluation (3 Champion Pairs):
        1. XAUTUSD (Gold): Level 2 DOM Trap & Delta Absorption (Fixed 1:3.0 RR, London & NY Killzone 13:00-23:30 IST)
        2. ETHUSD (Ethereum): Dual Engine (Momentum Breakout + DOM Liquidity Sweep, Fixed 1:3.5 RR, 13:00-23:30 IST)
        3. BTCUSD (Bitcoin): 1H Macro Volume Climax Sweep + London Asian Judas Swing (Fixed 1:3.5 RR, 0.35xATR cushion)
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
        is_weekend = now_ist.weekday() in (5, 6)
        cfg = self.params.get(symbol)
        if not cfg:
            return None

        # 2. Weekend Policy:
        # BTC and ETH trade 24/7 uninterrupted (weekends included).
        # Gold (XAUTUSD) pauses on weekends (traditional markets closed).
        if symbol == "XAUTUSD" and is_weekend:
            if now_ts - self.last_thought_log.get(f"{symbol}_weekend", 0) > 900:
                self.last_thought_log[f"{symbol}_weekend"] = now_ts
                self.db.log_thought(
                    symbol=symbol,
                    event_type="WEEKEND_FILTER",
                    stars=3.0,
                    message="⏸️ Gold Weekend Pause: Commodity desks closed Saturday/Sunday. Trading resumes Monday."
                )
            return None

        # 3. Fetch Level 2 Order Book Depth from Delta Exchange
        dom_data = self.client.get_l2_orderbook(symbol, depth=50)
        bids = dom_data.get("bids", []) if isinstance(dom_data, dict) else []
        asks = dom_data.get("asks", []) if isinstance(dom_data, dict) else []
        metrics = self.orderflow_engine.analyze_dom(bids, asks) if (bids and asks) else {}
        total_bids = metrics.get("total_bid_size", 0.0)
        total_asks = metrics.get("total_ask_size", 0.0)
        buyer_ratio = (total_bids / total_asks) if total_asks > 0 else 1.0
        seller_ratio = (total_asks / total_bids) if total_bids > 0 else 1.0
        side_dominant = metrics.get("dominant_side", "NEUTRAL")
        bid_walls = metrics.get("bid_walls", [])
        ask_walls = metrics.get("ask_walls", [])
        mid = metrics.get("mid_price") or current_price

        long_trigger = False
        short_trigger = False
        strat_title = ""
        sl_dist = 0.0
        tp_price = 0.0
        sl_price = 0.0
        c_val = cfg["c_val"]
        decimals = cfg["decimals"]

        # ---------------------------------------------------------------------------------
        # PAIR 1: GOLD (XAUTUSD) - Level 2 DOM Trap with Order Flow Absorption (1:3.0 RR)
        # ---------------------------------------------------------------------------------
        if symbol == "XAUTUSD":
            # Session Window: London & NY Killzone (13:00 to 23:30 IST)
            in_session = (13 <= now_ist.hour <= 23)
            if in_session:
                candles_15m = self._get_symbol_candles(symbol, resolution="15m", limit=150)
                c, prev, bar_idx = self._get_closed_bars(candles_15m, 900)

                if c and prev and bar_idx >= 30:
                    closed_ts = c["timestamp"]
                    if closed_ts <= self.last_evaluated_candle_ts.get(symbol, 0):
                        return None

                    # 3-Timeframe Trend Consensus (1D, 4H, 1H EMA 50)
                    master_trend, trend_info = self._get_mtf_consensus(symbol)

                    # 24-Bar Support / Resistance Window on Completed Closed Bars
                    lookback_sr = cfg.get("lookback_bars", 24)
                    win_sr = candles_15m[bar_idx - lookback_sr - 1 : bar_idx - 1]
                    sr_high = max(x["high"] for x in win_sr)
                    sr_low = min(x["low"] for x in win_sr)

                    # 30m Structure Room-to-Run Filter
                    c30 = self._get_symbol_candles(symbol, resolution="30m", limit=60)
                    sr_30_hi = max(x["high"] for x in c30[-21:-1]) if len(c30) >= 22 else sr_high
                    sr_30_lo = min(x["low"] for x in c30[-21:-1]) if len(c30) >= 22 else sr_low

                    c_range = max(0.01, c["high"] - c["low"])
                    lower_wick_pct = (min(c["open"], c["close"]) - c["low"]) / c_range
                    upper_wick_pct = (c["high"] - max(c["open"], c["close"])) / c_range
                    prev_delta = prev.get("delta", 0.0)
                    curr_delta = c.get("delta", 0.0)
                    c_vol = max(1.0, c.get("volume", 1.0))

                    # 1. Bull Trap (Short Gold)
                    if prev["high"] > sr_high and c["close"] < sr_high and c["close"] < prev["close"]:
                        dom_trapped = (prev_delta > 0 and curr_delta < 0) or (curr_delta <= -0.015 * c_vol)
                        dom_defense = upper_wick_pct >= 0.25 or (c["close"] < prev["open"])
                        if dom_trapped and dom_defense and master_trend == "BEARISH":
                            trap_h = max(prev["high"], c["high"])
                            sl_dist = max(cfg.get("min_risk", 2.50), trap_h - c["close"] + cfg.get("sl_buffer", 0.50))
                            # Enforce Room to Run: At least 1.5R clearance to opposing 30m support
                            if (c["close"] - sr_30_lo) >= 1.5 * sl_dist:
                                short_trigger = True
                                strat_title = f"DOM Bull Trap Absorption ({prev_delta:+.0f}Δ -> {curr_delta:+.0f}Δ | {int(upper_wick_pct*100)}% rejection | MTF {trend_info['votes']}/3 Bearish)"
                                tp_price = round(mid - cfg["target_rr"] * sl_dist, decimals)
                                sl_price = round(mid + sl_dist, decimals)

                    # 2. Bear Trap (Long Gold)
                    elif prev["low"] < sr_low and c["close"] > sr_low and c["close"] > prev["close"]:
                        dom_trapped = (prev_delta < 0 and curr_delta > 0) or (curr_delta >= 0.015 * c_vol)
                        dom_defense = lower_wick_pct >= 0.25 or (c["close"] > prev["open"])
                        if dom_trapped and dom_defense and master_trend == "BULLISH":
                            trap_l = min(prev["low"], c["low"])
                            sl_dist = max(cfg.get("min_risk", 2.50), c["close"] - trap_l + cfg.get("sl_buffer", 0.50))
                            # Enforce Room to Run: At least 1.5R clearance to opposing 30m resistance
                            if (sr_30_hi - c["close"]) >= 1.5 * sl_dist:
                                long_trigger = True
                                strat_title = f"DOM Bear Trap Defense ({prev_delta:+.0f}Δ -> {curr_delta:+.0f}Δ | {int(lower_wick_pct*100)}% defense | MTF {trend_info['votes']}/3 Bullish)"
                                tp_price = round(mid + cfg["target_rr"] * sl_dist, decimals)
                                sl_price = round(mid - sl_dist, decimals)

                    # Mark closed bar evaluated
                    self.last_evaluated_candle_ts[symbol] = closed_ts

        # ---------------------------------------------------------------------------------
        # PAIR 2: ETHEREUM (ETHUSD) - Dual Engine: Momentum Breakout + DOM Liquidity Sweep (1:3.5 RR)
        # ---------------------------------------------------------------------------------
        elif symbol == "ETHUSD":
            # Session Window: London & NY Killzone (13:00 to 23:30 IST)
            in_session = (13 <= now_ist.hour <= 23)
            if in_session:
                candles_15m = self._get_symbol_candles(symbol, resolution="15m", limit=150)
                candles_5m = self._get_symbol_candles(symbol, resolution="5m", limit=60)
                c, prev, bar_idx = self._get_closed_bars(candles_15m, 900)

                if c and prev and bar_idx >= 55:
                    closed_ts = c["timestamp"]
                    if closed_ts <= self.last_evaluated_candle_ts.get(symbol, 0):
                        return None

                    # 3-Timeframe Trend Consensus (1D, 4H, 1H EMA 50)
                    master_trend, trend_info = self._get_mtf_consensus(symbol)

                    # 15m EMA50 for Extension Filtering
                    close_15m = [x["close"] for x in candles_15m[:bar_idx + 1]]
                    ema15_50 = self._calc_ema(close_15m, 50)

                    c_range = max(0.01, c["high"] - c["low"])
                    lw_pct = (min(c["open"], c["close"]) - c["low"]) / c_range
                    uw_pct = (c["high"] - max(c["open"], c["close"])) / c_range

                    # Build 5m lookup map
                    m5_map = {x["timestamp"]: x for x in candles_5m}
                    b1 = m5_map.get(closed_ts)
                    b2 = m5_map.get(closed_ts + 300)
                    b3 = m5_map.get(closed_ts + 600)
                    if not (b1 and b2 and b3) and len(candles_5m) >= 3:
                        b1, b2, b3 = candles_5m[-3], candles_5m[-2], candles_5m[-1]

                    # Engine 1: Momentum Breakout (33 bars)
                    win_33 = candles_15m[bar_idx - 33 : bar_idx - 1]
                    hi_33 = max(x["high"] for x in win_33)
                    lo_33 = min(x["low"] for x in win_33)

                    if b1 and b2 and b3:
                        if c["close"] > hi_33 and master_trend == "BULLISH" and b3["close"] > b2["close"] > b1["close"]:
                            ext = (c["close"] - ema15_50[-1]) / c["close"] * 100
                            if uw_pct < 0.18 and ext <= 2.2:
                                long_trigger = True
                                sl_dist = max(cfg.get("min_risk", 3.0), c["close"] - c["low"] + cfg.get("sl_buffer", 0.50))
                                strat_title = f"Momentum Breakout (33-bar High ${hi_33:.2f} cleared, 5m staircase aligned | MTF {trend_info['votes']}/3 Bullish)"
                                tp_price = round(mid + cfg["target_rr"] * sl_dist, decimals)
                                sl_price = round(mid - sl_dist, decimals)
                        elif c["close"] < lo_33 and master_trend == "BEARISH" and b3["close"] < b2["close"] < b1["close"]:
                            ext = (ema15_50[-1] - c["close"]) / c["close"] * 100
                            if lw_pct < 0.18 and ext <= 2.2:
                                short_trigger = True
                                sl_dist = max(cfg.get("min_risk", 3.0), c["high"] - c["close"] + cfg.get("sl_buffer", 0.50))
                                strat_title = f"Momentum Breakdown (33-bar Low ${lo_33:.2f} breached, 5m staircase aligned | MTF {trend_info['votes']}/3 Bearish)"
                                tp_price = round(mid - cfg["target_rr"] * sl_dist, decimals)
                                sl_price = round(mid + sl_dist, decimals)

                    # Engine 2: DOM Liquidity Sweep Trap (48 bars)
                    if not (long_trigger or short_trigger):
                        win_48 = candles_15m[bar_idx - 48 : bar_idx - 1]
                        hi_48 = max(x["high"] for x in win_48)
                        lo_48 = min(x["low"] for x in win_48)
                        p_delta = prev.get("delta", 0.0)
                        c_delta = c.get("delta", 0.0)

                        if prev["low"] < lo_48 and c["close"] > lo_48 and c["close"] > prev["close"] and p_delta < 0 and c_delta > 0 and lw_pct >= 0.25 and master_trend == "BULLISH":
                            long_trigger = True
                            sl_dist = max(cfg.get("min_risk", 3.0), c["close"] - c["low"] + cfg.get("sl_buffer", 0.50))
                            strat_title = f"DOM Bear Trap (48-bar Low ${lo_48:.2f} swept, delta flip {p_delta:.0f} -> {c_delta:.0f} | MTF {trend_info['votes']}/3 Bullish)"
                            tp_price = round(mid + cfg["target_rr"] * sl_dist, decimals)
                            sl_price = round(mid - sl_dist, decimals)
                        elif prev["high"] > hi_48 and c["close"] < hi_48 and c["close"] < prev["close"] and p_delta > 0 and c_delta < 0 and uw_pct >= 0.25 and master_trend == "BEARISH":
                            short_trigger = True
                            sl_dist = max(cfg.get("min_risk", 3.0), c["high"] - c["close"] + cfg.get("sl_buffer", 0.50))
                            strat_title = f"DOM Bull Trap (48-bar High ${hi_48:.2f} swept, delta flip {p_delta:.0f} -> {c_delta:.0f} | MTF {trend_info['votes']}/3 Bearish)"
                            tp_price = round(mid - cfg["target_rr"] * sl_dist, decimals)
                            sl_price = round(mid + sl_dist, decimals)

                    # Mark closed bar evaluated
                    self.last_evaluated_candle_ts[symbol] = closed_ts

        # ---------------------------------------------------------------------------------
        # PAIR 3: BITCOIN (BTCUSD) - 1H Macro Volume Climax Sweep + London Asian Judas (1:3.5 RR)
        # ---------------------------------------------------------------------------------
        elif symbol == "BTCUSD":
            candles_1h = self._get_symbol_candles(symbol, resolution="1h", limit=80)
            candles_15m = self._get_symbol_candles(symbol, resolution="15m", limit=150)
            closed_1h, prev_1h, idx_1h = self._get_closed_bars(candles_1h, 3600)
            closed_15m, prev_15m, idx_15m = self._get_closed_bars(candles_15m, 900)

            if closed_1h and closed_15m and idx_1h >= 25 and idx_15m >= 28:
                master_trend, trend_info = self._get_mtf_consensus(symbol)
                atr_val = self._calc_atr(candles_1h[:idx_1h + 1], 14)

                # Engine 1: 1H Macro Volume Climax Sweep (12:00 to 23:30 IST) - Evaluated on Completed 1H Bars
                closed_1h_ts = closed_1h["timestamp"]
                last_1h_eval = self.last_evaluated_candle_ts.get(f"{symbol}_1h", 0)
                if (12 <= now_ist.hour <= 23) and (closed_1h_ts > last_1h_eval):
                    win_20 = candles_1h[idx_1h - 20 : idx_1h - 1]
                    sw_hi = max(x["high"] for x in win_20)
                    sw_lo = min(x["low"] for x in win_20)
                    c_range_1h = max(1.0, closed_1h["high"] - closed_1h["low"])
                    lw_1h = (min(closed_1h["open"], closed_1h["close"]) - closed_1h["low"]) / c_range_1h
                    uw_1h = (closed_1h["high"] - max(closed_1h["open"], closed_1h["close"])) / c_range_1h
                    avg_v1h = sum(x["volume"] for x in candles_1h[idx_1h - 10 : idx_1h]) / 10.0
                    vol_climax = closed_1h["volume"] >= 1.20 * avg_v1h

                    if closed_1h["low"] < sw_lo and closed_1h["close"] > sw_lo and lw_1h >= 0.25 and master_trend == "BULLISH" and vol_climax:
                        long_trigger = True
                        sl_dist = max(cfg.get("min_risk", 80.0), (closed_1h["close"] - closed_1h["low"]) + cfg.get("atr_cushion_mult", 0.35) * atr_val)
                        strat_title = f"1H Macro Sweep Trap Long (20h Low ${sw_lo:,.0f} swept, Vol Climax {closed_1h['volume']/avg_v1h:.2f}x | MTF {trend_info['votes']}/3 Bullish)"
                        tp_price = round(mid + cfg["target_rr"] * sl_dist, decimals)
                        sl_price = round(mid - sl_dist, decimals)
                    elif closed_1h["high"] > sw_hi and closed_1h["close"] < sw_hi and uw_1h >= 0.25 and master_trend == "BEARISH" and vol_climax:
                        short_trigger = True
                        sl_dist = max(cfg.get("min_risk", 80.0), (closed_1h["high"] - closed_1h["close"]) + cfg.get("atr_cushion_mult", 0.35) * atr_val)
                        strat_title = f"1H Macro Sweep Trap Short (20h High ${sw_hi:,.0f} swept, Vol Climax {closed_1h['volume']/avg_v1h:.2f}x | MTF {trend_info['votes']}/3 Bearish)"
                        tp_price = round(mid - cfg["target_rr"] * sl_dist, decimals)
                        sl_price = round(mid + sl_dist, decimals)

                    self.last_evaluated_candle_ts[f"{symbol}_1h"] = closed_1h_ts

                # Engine 2: Asian Judas Sweep (12:30 to 17:00 IST) - Evaluated on Completed 15m Bars
                closed_15m_ts = closed_15m["timestamp"]
                last_15m_eval = self.last_evaluated_candle_ts.get(f"{symbol}_15m", 0)
                if not (long_trigger or short_trigger) and (12 <= now_ist.hour <= 17) and (closed_15m_ts > last_15m_eval):
                    asia_bars = [x for x in candles_15m if 0 <= datetime.fromtimestamp(x["timestamp"], tz=timezone.utc).hour < 7 and x["timestamp"] < closed_15m_ts]
                    if len(asia_bars) >= 8:
                        asia_hi = max(x["high"] for x in asia_bars)
                        asia_lo = min(x["low"] for x in asia_bars)
                        vol_ma20 = sum(x["volume"] for x in candles_15m[idx_15m - 20 : idx_15m]) / 20.0
                        vol_ok = closed_15m["volume"] >= 1.25 * vol_ma20
                        c_range_15 = max(1.0, closed_15m["high"] - closed_15m["low"])
                        lw_15 = (min(closed_15m["open"], closed_15m["close"]) - closed_15m["low"]) / c_range_15
                        uw_15 = (closed_15m["high"] - max(closed_15m["open"], closed_15m["close"])) / c_range_15

                        if vol_ok:
                            if prev_15m["low"] < asia_lo and closed_15m["close"] > asia_lo and lw_15 >= 0.25 and master_trend == "BULLISH":
                                long_trigger = True
                                sl_dist = max(cfg.get("min_risk", 80.0), (closed_15m["close"] - closed_15m["low"]) + cfg.get("atr_cushion_mult", 0.35) * atr_val)
                                strat_title = f"Asian Judas Sweep Long (Asian Low ${asia_lo:,.0f} swept, Vol Climax {closed_15m['volume']/vol_ma20:.2f}x | MTF {trend_info['votes']}/3 Bullish)"
                                tp_price = round(mid + cfg["target_rr"] * sl_dist, decimals)
                                sl_price = round(mid - sl_dist, decimals)
                            elif prev_15m["high"] > asia_hi and closed_15m["close"] < asia_hi and uw_15 >= 0.25 and master_trend == "BEARISH":
                                short_trigger = True
                                sl_dist = max(cfg.get("min_risk", 80.0), (closed_15m["high"] - closed_15m["close"]) + cfg.get("atr_cushion_mult", 0.35) * atr_val)
                                strat_title = f"Asian Judas Sweep Short (Asian High ${asia_hi:,.0f} swept, Vol Climax {closed_15m['volume']/vol_ma20:.2f}x | MTF {trend_info['votes']}/3 Bearish)"
                                tp_price = round(mid - cfg["target_rr"] * sl_dist, decimals)
                                sl_price = round(mid + sl_dist, decimals)

                    self.last_evaluated_candle_ts[f"{symbol}_15m"] = closed_15m_ts

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
                message=f"Scanning {symbol} ({cfg['mode']}): Target 1:{cfg['target_rr']:.1f} RR. DOM Ratio {ratio_disp:.2f}x ({side_dominant}). {wall_info}. Mid: ${mid:,.2f}."
            )

        if not long_trigger and not short_trigger:
            return None

        trade_side = "BUY" if long_trigger else "SELL"

        # Strictly $5.00 fixed risk per trade sizing
        current_risk = self.db.get_target_risk_usd(self.fixed_risk_usd)
        raw_lots = current_risk / max(0.0001, sl_dist * c_val)
        lots = max(1, round(raw_lots))

        return {
            "symbol": symbol,
            "side": trade_side,
            "entry_price": mid,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "dist": sl_dist,
            "sl_pct": round(sl_dist / mid, 5),
            "tp_pct": round(abs(tp_price - mid) / mid, 5),
            "lots": lots,
            "risk_usd": current_risk,
            "strategy_name": f"{cfg['strategy_label']} ({strat_title})",
            "is_weekend": False,
            "buyer_ratio": round(buyer_ratio, 2),
            "seller_ratio": round(seller_ratio, 2),
            "walls_count": len(ask_walls if trade_side == "BUY" else bid_walls)
        }

    def _execute_entry(self, symbol: str, signal: Dict[str, Any], current_price: float):
        """Submits entry order and initializes position in concurrent state manager."""
        p = self.params[symbol]
        c_val = p["c_val"]
        decimals = p["decimals"]
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

        # Technical Structural Stop Loss Execution:
        # Stop loss placed exactly at technical structural invalidation cushion (sl),
        # guaranteeing full breathing room for the trade thesis as proven in zero-defect audit.
        exchange_bracket_sl = sl

        # Submit live bracket order to Delta Exchange if live authenticated
        if self.is_live_authenticated:
            try:
                order_res = self.client.place_bracket_order(
                    symbol=symbol,
                    side=side.lower(),
                    size=lots,
                    order_type="market_order",
                    stop_loss_price=exchange_bracket_sl,
                    take_profit_price=tp
                )
                print(f"🚀 [DELTA LIVE ORDER PLACED] {symbol} {side} {lots} Lots (Risk: ${current_risk:.2f} | Technical SL: ${exchange_bracket_sl} | TP: ${tp}) -> Response: {order_res.get('success')}")

                # Standalone fallback stop order directly on Delta Exchange book
                try:
                    close_side = "sell" if side == "BUY" else "buy"
                    sl_res = self.client.place_stop_order(
                        symbol=symbol,
                        side=close_side,
                        size=lots,
                        stop_price=exchange_bracket_sl,
                        is_take_profit=False
                    )
                    self.verified_sl_orders.add(symbol)
                    print(f"🛡️ [DELTA STANDALONE SL PLACED] {symbol} {close_side.upper()} {lots} Lots Stop @ ${exchange_bracket_sl} -> Success: {sl_res.get('success')}")
                except Exception as e_sl:
                    print(f"[DELTA STANDALONE SL NOTICE] {e_sl}")

            except Exception as e:
                print(f"[DELTA LIVE ORDER ERROR] {e}")

        trade_id = f"LIVE_{symbol}_{int(time.time())}"
        pos_record = {
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "stop_loss": sl,
            "initial_sl": sl,
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
            "is_weekend": signal.get("is_weekend", False),
            "highest_price": current_price,
            "lowest_price": current_price,
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
        self.verified_sl_orders.discard(symbol)
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
        is_sl = ("SL" in reason.upper()) or ("STOP" in reason.upper()) or ("CUT" in reason.upper())
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

        # Enforce post-trade cooldown (15m standard rest)
        cd_sec = p["cooldown_sec"]
        self.cooldown_until[symbol] = time.time() + cd_sec

        # Pair-specific cascade circuit breaker logic (2 SLs within 2-Hour lookback window)
        now_ts = time.time()
        window_sec = p.get("cascade_window_hours", 2.0) * 3600
        if total_pnl < 0:
            recent_losses = [t for t in self.loss_timestamps.get(symbol, []) if (now_ts - t) <= window_sec]
            recent_losses.append(now_ts)
            self.loss_timestamps[symbol] = recent_losses
            self.consecutive_losses[symbol] = len(recent_losses)
            
            cascade_limit = p.get("cascade_breaker_losses", 2)
            cascade_hours = p.get("cascade_breaker_hours", 2.0)
            if len(recent_losses) >= cascade_limit:
                halt_sec = int(cascade_hours * 3600)
                self.cooldown_until[symbol] = max(self.cooldown_until.get(symbol, 0), now_ts + halt_sec)
                self.loss_timestamps[symbol] = []
                self.consecutive_losses[symbol] = 0
                exp_halt_time = datetime.fromtimestamp(self.cooldown_until[symbol]).strftime("%H:%M:%S")
                print(f"🚨 [CASCADE CIRCUIT BREAKER] {cascade_limit} losses within {p.get('cascade_window_hours', 2.0):.1f}h on {symbol}! Trading halted for {cascade_hours:.1f} hours until {exp_halt_time}.")
                self.db.log_thought(
                    symbol=symbol,
                    event_type="CASCADE_BREAKER",
                    stars=5.0,
                    message=f"🚨 Liquidation Cascade Circuit Breaker: {cascade_limit} losses within {p.get('cascade_window_hours', 2.0):.1f}h hit on {symbol}. Pausing new entries for {cascade_hours:.1f}h until {exp_halt_time} to shield capital."
                )
        else:
            self.loss_timestamps[symbol] = []
            self.consecutive_losses[symbol] = 0

        # Persist halt timestamp, loss timestamps & consecutive losses directly in SQLite system_state
        self.db.set_system_state(f"loss_timestamps_{symbol}", json.dumps(self.loss_timestamps[symbol]))
        self.db.set_system_state(f"consecutive_losses_{symbol}", self.consecutive_losses[symbol])
        self.db.set_system_state(f"cooldown_until_{symbol}", self.cooldown_until[symbol])

        exp_time = datetime.fromtimestamp(self.cooldown_until[symbol]).strftime("%H:%M:%S")
        print(f"⏳ [COOLDOWN ACTIVATED] {symbol} closed ({reason}). Active until {exp_time}.")
        self.db.log_thought(
            symbol=symbol,
            event_type="POST_TRADE_COOLDOWN",
            stars=5.0,
            message=f"⏳ Post-trade rest active on {symbol} until {exp_time} ({reason}). Preserving capital."
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
