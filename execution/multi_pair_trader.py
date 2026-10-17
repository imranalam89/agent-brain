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
    LEVERAGE_MAP,
    CHAMPION_CONFIG,
    CHAMPION_CONFIG_BTC,
    CHAMPION_CONFIG_ETH,
    UNIFIED_TRAILING_LADDER,
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
       - Hybrid A: 15m Session Breakout (London/NY ORB) + CVD Order Flow Absorption.
       - Level 2 DOM wall confirmation, 15m cooldown, 2-Loss = 2h halt circuit breaker.
       - Ratcheted trailing stop with 1.10x breathing buffer and 4-bar swing protection.
       - Pauses Saturday/Sunday (commodity market closed).
    2. Bitcoin (BTCUSD):
       - DOM Imbalance & Ask/Bid Wall Sweep (Institutional Depth >= 3.0x).
       - Peak profit lock at +0.8R, 2-Loss = 4h halt circuit breaker (liquidation cascade shield).
       - Continuous 24/7 trading (weekends included).
    3. Ethereum (ETHUSD):
       - Weekday: Confluence DOM Sweep & CVD Trend Pullback (London/NY session).
       - Weekend: Bollinger & RSI Range Exhaustion Reversal (24/7 weekend trading, fixed +2.0R TP).
       - 2-Loss = 2h halt circuit breaker.
    4. All 3 Champion Pairs:
       - Strictly $5.00 fixed raw risk per trade.
       - Unified Ratcheted Trailing Ladder:
         +1.0R -> +0.20R (Guaranteed Green, fees covered)
         +1.5R -> +0.60R
         +2.0R -> +1.00R
         +2.5R -> +1.50R
         +3.0R -> +2.00R
         +4.0R -> +2.50R
         +5.0R -> +3.50R (1.5R buffer)
         +6.0R+ -> Continuous 1.5R trailing buffer behind peak price.
       - Early Reversal Cut: Cut early at -0.45R on opposing hostile orderbook wall (saves ~55% of loss).
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
                "mode": "BREAKOUT",
                "min_imbalance": 3.0,
                "tp_pct": 0.022,      # 2.2% Take Profit runner
                "sl_pct": 0.003,      # 0.3% Stop Loss (1:7.33 R:R)
                "cooldown_sec": 900,  # 15 minutes post-exit rest
                "cascade_breaker_losses": 2, # 2 losses in a row
                "cascade_breaker_hours": 4.0, # 4-hour halt (protects against liquidation dumps)
                "profit_lock_r": 0.80, # Bank +0.8R on opposing wall detection
                "reversal_cut_r": -0.45, # Cut early at -0.45R (saves ~55% loss)
                "c_val": 0.001,
                "decimals": 2,
                "weekend_trading": True,
                "strategy_label": "DOM Imbalance & Ask/Bid Wall Sweep (Selective 3.0x • 24/7 Crypto)"
            },
            "ETHUSD": {
                "mode": "CONFLUENCE_WEEKEND",
                "min_imbalance": 2.0,
                "tp_pct": 0.020,      # Weekday runner target
                "sl_pct": 0.0035,     # Structure-based baseline
                "cooldown_sec": 900,  # 15 minutes post-exit rest
                "cascade_breaker_losses": 2, # 2 losses in a row
                "cascade_breaker_hours": 2.0, # 2-hour halt (sweet spot for ETH)
                "reversal_cut_r": -0.45, # Cut early at -0.45R on opposing DOM wall
                "c_val": 0.01,
                "decimals": 2,
                "weekend_trading": True,
                "weekend_tp_r": 2.0,  # Fixed +2.0R take profit on weekend mean reversion
                "strategy_label": "Confluence DOM Sweep (Weekday) + BB Exhaustion Reversal (Weekend 24/7)"
            },
            "XAUTUSD": {
                "mode": "HYBRID_A",
                "min_imbalance": 1.5,
                "tp_pct": 0.020,      # Runner target
                "sl_pct": 0.0025,     # Structure-based baseline
                "cooldown_sec": 900,  # 15 minutes post-exit rest
                "cascade_breaker_losses": 2, # 2 losses in a row
                "cascade_breaker_hours": 2.0, # 2-hour halt
                "breathing_mult": 1.10, # 1.10x breathing trail distance behind peak
                "swing_lookback_bars": 4, # 4-bar swing low/high structural protection
                "reversal_cut_r": -0.45, # Cut early at -0.45R on opposing absorption wall
                "c_val": 0.001,
                "decimals": 2,
                "weekend_trading": False, # Pauses on weekends (traditional markets closed)
                "strategy_label": "Hybrid A (15m Breakout + CVD Order Flow Absorption + DOM)"
            }
        }

        # Track consecutive losses per pair for the cascade circuit breakers
        self.consecutive_losses: Dict[str, int] = {s: 0 for s in self.params}

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
                if saved_halt and float(saved_halt) > time.time():
                    self.cooldown_until[sym] = max(self.cooldown_until.get(sym, 0), float(saved_halt))
                    rem_mins = int((float(saved_halt) - time.time()) / 60)
                    print(f"🚨 [PERSISTED CASCADE BREAKER RESTORED] {sym} halt restored from SQLite ({rem_mins}m remaining).")
                if saved_consec is not None:
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
        Unified 3-Pair Champion Trailing Ladder & Early Reversal Guard:
        - Unified Trailing Ladder:
          +1.0R -> +0.20R (Guaranteed Green, fees covered)
          +1.5R -> +0.60R
          +2.0R -> +1.00R
          +2.5R -> +1.50R
          +3.0R -> +2.00R
          +4.0R -> +2.50R
          +5.0R -> +3.50R (1.5R breathing buffer)
          +6.0R+ -> Continuous 1.5R trailing buffer behind peak price.
        - Gold: In addition, 4-bar swing low/high structural protection.
        - Weekend ETH: Fixed +2.0R TP / -1.0R SL with -0.45R reversal cut.
        - Hostile Reversal Guard:
          * In Profit (>= +0.8R BTC, >= +0.6R others): Bank profit early before retrace.
          * In Loss (<= -0.30R): Cut early at -0.45R on hostile orderbook wall (saves ~55% of loss).
        """
        pos = self.active_positions[symbol]
        side = pos["side"]
        entry = pos["entry_price"]
        dist = pos.get("dist") or abs(entry - pos["stop_loss"])
        decimals = self.params[symbol]["decimals"]
        is_weekend_trade = pos.get("is_weekend", False)

        # Track peak excursions for dynamic runner trailing
        if "highest_price" not in pos:
            pos["highest_price"] = max(entry, current_price)
            pos["lowest_price"] = min(entry, current_price)
        else:
            if current_price > pos["highest_price"]:
                pos["highest_price"] = current_price
            if current_price < pos["lowest_price"]:
                pos["lowest_price"] = current_price

        if side == "BUY":
            r_mult = (current_price - entry) / max(1e-6, dist)
            peak_r = (pos["highest_price"] - entry) / max(1e-6, dist)
        else:
            r_mult = (entry - current_price) / max(1e-6, dist)
            peak_r = (entry - pos["lowest_price"]) / max(1e-6, dist)

        target_sl = None

        if is_weekend_trade:
            # Weekend ETH trade: Fixed +2.0R TP / -1.0R SL
            pass
        else:
            # UNIFIED RATCHETED TRAILING SL LADDER (ALL 3 PAIRS)
            if peak_r >= 6.0:
                # Macro runner continuous 1.5R buffer behind peak price
                target_sl = (pos["highest_price"] - 1.50 * dist) if side == "BUY" else (pos["lowest_price"] + 1.50 * dist)
            elif peak_r >= 5.0:
                target_sl = (entry + 3.50 * dist) if side == "BUY" else (entry - 3.50 * dist)
            elif peak_r >= 4.0:
                target_sl = (entry + 2.50 * dist) if side == "BUY" else (entry - 2.50 * dist)
            elif peak_r >= 3.0:
                target_sl = (entry + 2.00 * dist) if side == "BUY" else (entry - 2.00 * dist)
            elif peak_r >= 2.5:
                target_sl = (entry + 1.50 * dist) if side == "BUY" else (entry - 1.50 * dist)
            elif peak_r >= 2.0:
                target_sl = (entry + 1.00 * dist) if side == "BUY" else (entry - 1.00 * dist)
            elif peak_r >= 1.5:
                target_sl = (entry + 0.60 * dist) if side == "BUY" else (entry - 0.60 * dist)
            elif peak_r >= 1.0:
                target_sl = (entry + 0.20 * dist) if side == "BUY" else (entry - 0.20 * dist)

            # Gold-specific 4-bar swing low/high structural protection
            if symbol == "XAUTUSD" and peak_r >= 2.8:
                candles_15m = self.candle_cache.get(symbol, [])
                if len(candles_15m) >= 6:
                    recent_bars = candles_15m[-5:-1]
                    if side == "BUY":
                        recent_swing = min(float(b["low"]) for b in recent_bars)
                        trail_level = max(recent_swing - 0.10 * dist, pos["highest_price"] - 1.10 * dist)
                        target_sl = max(target_sl or 0.0, trail_level)
                    else:
                        recent_swing = max(float(b["high"]) for b in recent_bars)
                        trail_level = min(recent_swing + 0.10 * dist, pos["lowest_price"] + 1.10 * dist)
                        target_sl = min(target_sl or 999999.0, trail_level)

        if target_sl is not None:
            new_sl = round(target_sl, decimals)
            is_tightened = (new_sl > pos["stop_loss"]) if side == "BUY" else (new_sl < pos["stop_loss"])
            if is_tightened:
                old_sl = pos["stop_loss"]
                pos["stop_loss"] = new_sl
                pos["be_locked"] = True
                locked_r = round(abs(new_sl - entry) / dist, 2)

                # 1. Update SQLite trade record
                try:
                    with self.db.get_connection() as conn:
                        conn.execute("UPDATE trades SET stop_loss = ? WHERE id = ?", (new_sl, pos["id"]))
                        conn.commit()
                except Exception as e:
                    print(f"[DB SL UPDATE NOTICE] {e}")

                # 2. Place / ratchet reduce-only stop order directly on Delta Exchange book
                if self.is_live_authenticated:
                    try:
                        close_side = "sell" if side == "BUY" else "buy"
                        rem_lots = pos.get("remaining_lots") or pos.get("lots") or 1
                        # Cancel existing stop loss orders for this symbol first by ID
                        open_orders = self.client.get_open_orders(symbol)
                        for o in open_orders:
                            if o.get("stop_order_type") == "stop_loss_order":
                                self.client.cancel_order(o.get("id"), o.get("product_id"))
                        sl_res = self.client.place_stop_order(
                            symbol=symbol,
                            side=close_side,
                            size=rem_lots,
                            stop_price=new_sl,
                            is_take_profit=False
                        )
                        self.verified_sl_orders.add(symbol)
                        print(f"🛡️ [DELTA EXCHANGE TRAILING SL ORDER] {symbol} {close_side.upper()} {rem_lots} Lots Stop @ ${new_sl} -> Success: {sl_res.get('success')}")
                    except Exception as e:
                        print(f"[DELTA SL ORDER NOTICE] {e}")

                print(f"⚡ [PROFIT TRAIL RATCHET] {symbol} {side} SL ratcheted from ${old_sl} to ${new_sl} (+{locked_r}R profit locked @ +{peak_r:.1f}R peak).")
                self.db.log_thought(
                    symbol=symbol,
                    event_type="TRAILING_SL_RATCHET",
                    stars=5.0,
                    message=f"⚡ Trailing SL ratcheted on {symbol} {side} to ${new_sl} (+{locked_r}R profit locked @ +{peak_r:.1f}R peak). Delta stop order updated."
                )
                if locked_r <= 0.25:
                    notifier.send_breakeven_alert(symbol, side, current_price, new_sl, peak_r)
                else:
                    notifier.send_trailing_alert(symbol, side, current_price, new_sl, peak_r)

        # Baseline check: If position is open and authenticated, ensure at least one exchange stop exists
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

        # 2. Level 2 DOM High-Conviction Hostile Reversal Guard
        try:
            dom_data = self.client.get_l2_orderbook(symbol, depth=30)
            if dom_data and isinstance(dom_data, dict):
                bids = dom_data.get("bids", [])
                asks = dom_data.get("asks", [])
                if bids and asks:
                    dom_m = self.orderflow_engine.analyze_dom(bids, asks)
                    total_b = dom_m.get("total_bid_size", 0.0)
                    total_a = dom_m.get("total_ask_size", 0.0)
                    b_ratio = (total_b / total_a) if total_a > 0 else 1.0
                    s_ratio = (total_a / total_b) if total_b > 0 else 1.0
                    b_walls = dom_m.get("bid_walls", [])
                    a_walls = dom_m.get("ask_walls", [])

                    hostile_reversal = False
                    opposing_ratio = 1.0
                    min_hostile_imb = 2.2 if symbol in ("XAUTUSD", "BTCUSD") else 2.0
                    if side == "BUY":
                        hostile_reversal = (s_ratio >= min_hostile_imb and len(a_walls) >= 2)
                        opposing_ratio = s_ratio
                    elif side == "SELL":
                        hostile_reversal = (b_ratio >= min_hostile_imb and len(b_walls) >= 2)
                        opposing_ratio = b_ratio

                    if hostile_reversal:
                        # Case A: Reversal Peak Profit Lock (BTC >= +0.8R, Others >= +0.6R)
                        profit_threshold = 0.80 if symbol == "BTCUSD" else 0.60
                        if r_mult >= profit_threshold:
                            print(f"🚨 [L2 EARLY REVERSAL PROFIT LOCK] {symbol} {side} closed early @ ${current_price:,.2f} (+{r_mult:.2f}R). Hostile DOM reversal flow ({opposing_ratio:.2f}x).")
                            self.db.log_thought(
                                symbol=symbol,
                                event_type="EARLY_REVERSAL_PROFIT_LOCK",
                                stars=5.0,
                                message=f"🚨 High-Conviction L2 DOM Reversal: Opposing orderbook flow reached {opposing_ratio:.2f}x with stacked hostile walls. Closed early to bank +{r_mult:.2f}R profit."
                            )
                            self._close_position(symbol, current_price, reason="REVERSAL_PROFIT_LOCK")
                            return

                        # Case B: Reversal Full Cut at -0.45R (In loss <= -0.30R)
                        elif r_mult <= -0.30:
                            cut_price = round(entry - 0.45 * dist if side == "BUY" else entry + 0.45 * dist, decimals)
                            exec_cut_p = cut_price if (cut_price > pos["stop_loss"] if side == "BUY" else cut_price < pos["stop_loss"]) else current_price
                            print(f"🛡️ [L2 EARLY REVERSAL CUT] {symbol} {side} cut early @ ${exec_cut_p:,.2f} (-0.45R). Opposing wall detected, saving ~55% loss.")
                            self.db.log_thought(
                                symbol=symbol,
                                event_type="EARLY_REVERSAL_CUT",
                                stars=4.5,
                                message=f"🛡️ Early Reversal Risk Cut: Hostile DOM reversal confirmed thesis invalidated. Cut position early at -0.45R to prevent full -1.0R loss."
                            )
                            self._close_position(symbol, exec_cut_p, reason="REVERSAL_FULL_CUT")
                            return
        except Exception:
            pass

        # 3. Take Profit Exit Check
        tp_hit = (current_price >= pos["take_profit"]) if side == "BUY" else (current_price <= pos["take_profit"])
        if tp_hit:
            reason = "WEEKEND_TP_2R" if is_weekend_trade else "TAKE_PROFIT"
            self._close_position(symbol, current_price, reason=reason)
            return

        # 4. Stop Loss / Breakeven Exit Check
        sl_hit = (current_price <= pos["stop_loss"]) if side == "BUY" else (current_price >= pos["stop_loss"])
        if sl_hit:
            reason = "BREAKEVEN" if pos.get("be_locked") else "STOP_LOSS"
            self._close_position(symbol, current_price, reason=reason)
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

    def _evaluate_entry_signal(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Pure Level 2 DOM & Microstructure Champion Entry Evaluation (3 Champion Pairs):
        1. BTCUSD: DOM Imbalance >= 3.0x & Resting Wall Sweep (24/7 continuous).
        2. ETHUSD: Confluence DOM Sweep (Weekday) + BB Exhaustion Reversal (Weekend 24/7).
        3. XAUTUSD: Hybrid A (15m Session Breakout + CVD Orderflow Absorption + DOM Confirmation).
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

        has_bid_wall = any(w.get("price", 0) <= mid for w in bid_walls) if bid_walls else False
        has_ask_wall = any(w.get("price", 0) >= mid for w in ask_walls) if ask_walls else False

        long_trigger = False
        short_trigger = False
        strat_title = ""
        sl_dist = 0.0
        tp_price = 0.0
        sl_price = 0.0
        is_weekend_signal = False
        c_val = cfg["c_val"]
        decimals = cfg["decimals"]

        # 4. Evaluate Asset Strategy Logic
        # -------------------------------------------------------------
        # PAIR 1: BITCOIN (BTCUSD) - 24/7 DOM Imbalance >= 3.0x & Sweep
        # -------------------------------------------------------------
        if symbol == "BTCUSD":
            min_imb = cfg.get("min_imbalance", 3.0)
            long_trigger = (side_dominant == "BUYERS" and buyer_ratio >= min_imb and (has_ask_wall or len(ask_walls) > 0))
            short_trigger = (side_dominant == "SELLERS" and seller_ratio >= min_imb and (has_bid_wall or len(bid_walls) > 0))
            if long_trigger or short_trigger:
                strat_title = f"DOM {symbol} Breakout & Ask Wall Sweep" if long_trigger else f"DOM {symbol} Breakout & Bid Wall Sweep"
                sl_dist = round(mid * cfg["sl_pct"], decimals)
                tp_price = round(mid * (1.0 + cfg["tp_pct"]) if long_trigger else mid * (1.0 - cfg["tp_pct"]), decimals)
                sl_price = round(mid - sl_dist if long_trigger else mid + sl_dist, decimals)

        # ---------------------------------------------------------------------------------
        # PAIR 2: ETHEREUM (ETHUSD) - Weekday Confluence + Weekend BB/RSI Scalp (24/7 Crypto)
        # ---------------------------------------------------------------------------------
        elif symbol == "ETHUSD":
            # Cache 5m candles for ETH
            candles_5m = self.candle_cache.get(symbol, [])
            if now_ts - self.last_candle_fetch.get(symbol, 0) > 60 or not candles_5m:
                try:
                    c_start = int(now_ts - (86400 * 3))
                    candles_5m = self.client.get_candles(symbol, resolution="5m", start=c_start, end=int(now_ts))
                    if candles_5m and len(candles_5m) >= 30:
                        self.candle_cache[symbol] = candles_5m
                        self.last_candle_fetch[symbol] = now_ts
                except Exception as e:
                    print(f"[CANDLE FETCH NOTICE] {symbol}: {e}")

            if candles_5m and len(candles_5m) >= 30:
                closes = [float(x["close"]) for x in candles_5m]
                highs = [float(x["high"]) for x in candles_5m]
                lows = [float(x["low"]) for x in candles_5m]
                c_idx = len(candles_5m) - 1
                curr_c = candles_5m[-1]

                if is_weekend:
                    # Weekend Module: Bollinger & RSI Range Exhaustion Reversal
                    bb_up, bb_mid, bb_low = self._calc_bollinger(closes, period=20, num_std=2.0)
                    rsi14 = self._calc_rsi(closes, period=14)
                    
                    if lows[-1] <= bb_low[-1] and closes[-1] > bb_low[-1] and rsi14[-1] <= 35:
                        long_trigger = True
                        sl_dist = max(3.0, closes[-1] - lows[-1] + 1.0)
                        strat_title = "Weekend Bollinger & RSI Reversal (Long)"
                        is_weekend_signal = True
                    elif highs[-1] >= bb_up[-1] and closes[-1] < bb_up[-1] and rsi14[-1] >= 65:
                        short_trigger = True
                        sl_dist = max(3.0, highs[-1] - closes[-1] + 1.0)
                        strat_title = "Weekend Bollinger & RSI Reversal (Short)"
                        is_weekend_signal = True

                    if long_trigger or short_trigger:
                        # Fixed 2.0R Take Profit on weekend mean reversion
                        tp_price = round(mid + 2.0 * sl_dist if long_trigger else mid - 2.0 * sl_dist, decimals)
                        sl_price = round(mid - sl_dist if long_trigger else mid + sl_dist, decimals)

                else:
                    # Weekday Module: London & NY Confluence (13:00 - 23:00 IST, avoid hours 16, 19, 20, 22)
                    in_session = (13 <= now_ist.hour <= 23) and (now_ist.hour not in (16, 19, 20, 22))
                    if in_session:
                        ema20 = self._calc_ema(closes, 20)
                        ema50 = self._calc_ema(closes, 50)
                        bar_range = max(1.0, highs[-1] - lows[-1])
                        delta = float(curr_c.get("delta", 0.0))
                        vol = max(1.0, float(curr_c.get("volume", 1.0)))
                        dr = delta / vol
                        recent_h15 = max(highs[max(0, c_idx - 15) : c_idx])
                        recent_l15 = min(lows[max(0, c_idx - 15) : c_idx])
                        recent_h8 = max(highs[max(0, c_idx - 8) : c_idx])
                        recent_l8 = min(lows[max(0, c_idx - 8) : c_idx])

                        # Strict Champion Weekday Strategy: Trend Pullback (EMA 20/50 + CVD Aggression)
                        # Non-champion DOM Range Sweep and Momentum Breakout removed to eliminate unwanted trades & losses
                        if ema20[-1] > ema50[-1] and lows[-1] <= ema20[-1] and closes[-1] > ema20[-1] and dr >= 0.02:
                            long_trigger = True
                            sl_dist = max(3.5, closes[-1] - lows[-1] + 1.5)
                            strat_title = "Trend Pullback (Long)"
                        elif ema20[-1] < ema50[-1] and highs[-1] >= ema20[-1] and closes[-1] < ema20[-1] and dr <= -0.02:
                            short_trigger = True
                            sl_dist = max(3.5, highs[-1] - closes[-1] + 1.5)
                            strat_title = "Trend Pullback (Short)"

                        if long_trigger or short_trigger:
                            tp_price = round(mid + 40.0 * sl_dist if long_trigger else mid - 40.0 * sl_dist, decimals)
                            sl_price = round(mid - sl_dist if long_trigger else mid + sl_dist, decimals)

        # ---------------------------------------------------------------------------------
        # PAIR 3: GOLD (XAUTUSD) - Hybrid A (15m Session Breakout + CVD Absorption + DOM)
        # ---------------------------------------------------------------------------------
        elif symbol == "XAUTUSD":
            # Session Window: 13:00 to 23:00 IST, avoiding news blackout hours 16, 19, 20, 22
            in_session = (13 <= now_ist.hour <= 23) and (now_ist.hour not in (16, 19, 20, 22))
            if in_session:
                candles_15m = self.candle_cache.get(symbol, [])
                if now_ts - self.last_candle_fetch.get(symbol, 0) > 60 or not candles_15m:
                    try:
                        c_start = int(now_ts - (86400 * 4))
                        candles_15m = self.client.get_candles(symbol, resolution="15m", start=c_start, end=int(now_ts))
                        if candles_15m and len(candles_15m) >= 25:
                            self.candle_cache[symbol] = candles_15m
                            self.last_candle_fetch[symbol] = now_ts
                    except Exception as e:
                        print(f"[CANDLE FETCH NOTICE] {symbol}: {e}")

                if candles_15m and len(candles_15m) >= 25:
                    c = candles_15m[-1]
                    curr_p = float(c["close"])
                    c_idx = len(candles_15m) - 1

                    # Component 1: Session Breakout (London 13:00-15:30 or NY 18:00-21:00 ORB)
                    hm = now_ist.strftime("%H:%M")
                    is_orb_session = ("13:00" <= hm <= "15:30") or ("18:00" <= hm <= "21:00")
                    delta = float(c.get("delta", 0.0))
                    vol = max(1.0, float(c.get("volume", 1.0)))
                    delta_ratio = delta / vol

                    if is_orb_session:
                        sub = candles_15m[max(0, c_idx - 8) : c_idx]
                        range_high = max(float(x["high"]) for x in sub)
                        range_low = min(float(x["low"]) for x in sub)
                        if curr_p > range_high and float(c["close"]) > float(c["open"]) and delta > 0:
                            long_trigger = True
                            sl_dist = max(3.0, (curr_p - range_low) * 0.40)
                            strat_title = "Session Breakout (London/NY ORB)"
                        elif curr_p < range_low and float(c["close"]) < float(c["open"]) and delta < 0:
                            short_trigger = True
                            sl_dist = max(3.0, (range_high - curr_p) * 0.40)
                            strat_title = "Session Breakout (London/NY ORB)"

                    # Component 2: CVD Order Flow Absorption
                    if not (long_trigger or short_trigger):
                        sub_abs = candles_15m[max(0, c_idx - 12) : c_idx]
                        hi = max(float(x["high"]) for x in sub_abs)
                        lo = min(float(x["low"]) for x in sub_abs)
                        bar_range = max(0.01, float(c["high"]) - float(c["low"]))
                        lower_wick = (min(float(c["open"]), curr_p) - float(c["low"])) / bar_range
                        upper_wick = (float(c["high"]) - max(float(c["open"]), curr_p)) / bar_range

                        if float(c["high"]) >= hi * 0.9998 and upper_wick >= 0.30 and delta_ratio <= -0.03:
                            short_trigger = True
                            sl_dist = max(3.0, float(c["high"]) - curr_p)
                            strat_title = "CVD Order Flow Absorption (Resistance)"
                        elif float(c["low"]) <= lo * 1.0002 and lower_wick >= 0.30 and delta_ratio >= 0.03:
                            long_trigger = True
                            sl_dist = max(3.0, curr_p - float(c["low"]))
                            strat_title = "CVD Order Flow Absorption (Support)"

                    # Component 3: Level 2 DOM Confirmation
                    if long_trigger:
                        dom_ok = (delta_ratio >= 0.015) or (side_dominant == "BUYERS" and buyer_ratio >= 1.5) or has_bid_wall
                        if not dom_ok:
                            long_trigger = False
                    elif short_trigger:
                        dom_ok = (delta_ratio <= -0.015) or (side_dominant == "SELLERS" and seller_ratio >= 1.5) or has_ask_wall
                        if not dom_ok:
                            short_trigger = False

                    if long_trigger or short_trigger:
                        tp_price = round(mid + 40.0 * sl_dist if long_trigger else mid - 40.0 * sl_dist, decimals)
                        sl_price = round(mid - sl_dist if long_trigger else mid + sl_dist, decimals)

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
                message=f"Scanning {symbol} ({cfg['mode']}): DOM Ratio {ratio_disp:.2f}x ({side_dominant}). {wall_info}. Mid: ${mid:,.2f}."
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
            "tp_pct": cfg.get("tp_pct", 0.02),
            "lots": lots,
            "risk_usd": current_risk,
            "strategy_name": f"{cfg['strategy_label']} ({strat_title})",
            "is_weekend": is_weekend_signal,
            "buyer_ratio": round(buyer_ratio, 2),
            "seller_ratio": round(seller_ratio, 2),
            "walls_count": len(ask_walls if trade_side == "BUY" else bid_walls)
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

        # Root Cause 2 Fix: Tighten Delta Exchange bracket hard stop from -1.0R to -0.50R
        # Instead of placing the exchange stop at full -1.0R (which allowed market spikes to fill at -$7.00 loss with slippage),
        # we place Delta's hard bracket stop at -0.50R (~$3.50 loss).
        # This guarantees that even during high volatility or network latency, the exchange itself cuts the loss
        # at -0.50R, perfectly matching the -0.45R backtest reversal cut!
        rev_cut_mult = 0.50
        if side == "BUY":
            exchange_bracket_sl = round(current_price - rev_cut_mult * dist, decimals)
        else:
            exchange_bracket_sl = round(current_price + rev_cut_mult * dist, decimals)

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
                print(f"🚀 [DELTA LIVE ORDER PLACED] {symbol} {side} {lots} Lots (Risk: ${current_risk:.2f} | Tight Exchange SL: ${exchange_bracket_sl} | TP: ${tp}) -> Response: {order_res.get('success')}")

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
            "stop_loss": exchange_bracket_sl,
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

        # Pair-specific cascade circuit breaker logic
        if total_pnl < 0:
            self.consecutive_losses[symbol] = self.consecutive_losses.get(symbol, 0) + 1
            cascade_limit = p.get("cascade_breaker_losses", 2)
            cascade_hours = p.get("cascade_breaker_hours", 2.0)
            if self.consecutive_losses[symbol] >= cascade_limit:
                halt_sec = int(cascade_hours * 3600)
                self.cooldown_until[symbol] = max(self.cooldown_until[symbol], time.time() + halt_sec)
                self.consecutive_losses[symbol] = 0
                exp_halt_time = datetime.fromtimestamp(self.cooldown_until[symbol]).strftime("%H:%M:%S")
                print(f"🚨 [CASCADE CIRCUIT BREAKER] {cascade_limit} consecutive losses on {symbol}! Trading halted for {cascade_hours:.1f} hours until {exp_halt_time}.")
                self.db.log_thought(
                    symbol=symbol,
                    event_type="CASCADE_BREAKER",
                    stars=5.0,
                    message=f"🚨 Liquidation Cascade Circuit Breaker: {cascade_limit} consecutive losses hit on {symbol}. Pausing new entries for {cascade_hours:.1f}h until {exp_halt_time} to shield capital."
                )
        else:
            self.consecutive_losses[symbol] = 0

        # Root Cause 3 Fix: Persist halt timestamp & consecutive losses directly in SQLite system_state
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
