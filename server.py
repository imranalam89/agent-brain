import sys
import json
import webbrowser
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester
from reports.html_reporter import HTMLReporter
from exchange.delta_client import DeltaExchangeClient
from strategies.orderflow_engine import OrderFlowEngine
from config.settings import ACTIVE_SYMBOLS, ACCOUNT_CAPITAL_USD, calculate_brokerage_fee

PORT = 5050

class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve files from the reports directory
        super().__init__(*args, directory=str(BASE_DIR / "reports"), **kwargs)

    def end_headers(self):
        # Enable CORS so browser requests from file:/// also work seamlessly
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/live-status"):
            self._handle_live_status()
            return
        if self.path in ("/", "/index.html"):
            self.path = "/live_journal.html"
        elif self.path == "/live":
            self.path = "/live_journal.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/run-backtest":
            self._handle_run_backtest()
        elif self.path == "/api/paper-scan":
            self._handle_paper_scan()
        elif self.path == "/api/set-risk":
            self._handle_set_risk()
        elif self.path == "/api/toggle-bot-status":
            self._handle_toggle_bot_status()
        else:
            self.send_error(404, "Endpoint not found")

    def _handle_run_backtest(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                body = json.loads(post_data.decode("utf-8"))
            except Exception:
                body = {}
            target_symbol = body.get("symbol", "ALL")

            db = DatabaseManager()
            reporter = HTMLReporter()
            simulator = MultiStrategyBacktester(db, initial_capital=ACCOUNT_CAPITAL_USD)

            gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=30000)
            silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=30000)
            btc_candles = db.get_latest_candles("BTCUSD", "15m", limit=30000)
            eth_candles = db.get_latest_candles("ETHUSD", "15m", limit=30000)

            gold_results = simulator.run_all_strategies("XAUTUSD", gold_candles) if gold_candles else {}
            silver_results = simulator.run_all_strategies("SLVONUSD", silver_candles) if silver_candles else {}
            btc_results = simulator.run_all_strategies("BTCUSD", btc_candles) if btc_candles else {}
            eth_results = simulator.run_all_strategies("ETHUSD", eth_candles) if eth_candles else {}

            joint_results = simulator.generate_joint_portfolio_results(gold_results, silver_results, btc_results, eth_results, ACCOUNT_CAPITAL_USD)

            # Determine best strategy per asset and joint
            best_gold_key = max(gold_results.keys(), key=lambda k: gold_results[k]["net_pl"]) if gold_results else None
            best_silver_key = max(silver_results.keys(), key=lambda k: silver_results[k]["net_pl"]) if silver_results else None
            best_btc_key = max(btc_results.keys(), key=lambda k: btc_results[k]["net_pl"]) if btc_results else None
            best_eth_key = max(eth_results.keys(), key=lambda k: eth_results[k]["net_pl"]) if eth_results else None
            best_joint_key = max(joint_results.keys(), key=lambda k: joint_results[k]["net_pl"]) if joint_results else None

            best_gold_trades = gold_results[best_gold_key]["trades"] if best_gold_key else []
            best_silver_trades = silver_results[best_silver_key]["trades"] if best_silver_key else []
            best_btc_trades = btc_results[best_btc_key]["trades"] if best_btc_key else []
            best_eth_trades = eth_results[best_eth_key]["trades"] if best_eth_key else []
            best_joint_trades = joint_results[best_joint_key]["trades"] if best_joint_key else (best_gold_trades + best_silver_trades)

            # Active selection
            if target_symbol == "SLVONUSD":
                active_strat = silver_results.get(best_silver_key, {})
            elif target_symbol == "BTCUSD":
                active_strat = btc_results.get(best_btc_key, {})
            elif target_symbol == "ETHUSD":
                active_strat = eth_results.get(best_eth_key, {})
            elif target_symbol == "JOINT":
                active_strat = joint_results.get(best_joint_key, {})
            else:
                active_strat = gold_results.get(best_gold_key, {})

            db.clear_trades()
            for t in active_strat.get("trades", []):
                db.log_trade(t)

            # Regenerate reports on disk with Joint, Gold, Silver, BTC, and ETH
            report_path = reporter.generate_multi_strategy_backtest_report(
                gold_results,
                "Multi-Asset (Gold, Silver, BTC, ETH)",
                silver_results=silver_results,
                joint_results=joint_results,
                btc_results=btc_results,
                eth_results=eth_results
            )
            reporter.generate_all_journals(
                joint_trades=best_joint_trades,
                gold_trades=best_gold_trades,
                silver_trades=best_silver_trades,
                btc_trades=best_btc_trades,
                eth_trades=best_eth_trades,
                db_thoughts=[
                    {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "symbol": target_symbol,
                        "event_type": "1_CLICK_WEB_BACKTEST",
                        "conviction_stars": 5.0,
                        "message": f"4-Asset Backtest Completed across Gold, Silver, BTC, and ETH. Best Strategy: {active_strat.get('strategy_name', 'Unknown')} with Net P&L ${active_strat.get('net_pl', 0.0):+.2f}, Win Rate: {active_strat.get('win_rate', 0)}%, PF: {active_strat.get('profit_factor', 0)}."
                    }
                ]
            )

            self._send_json({
                "success": True,
                "best_strategy": active_strat.get("strategy_name", "Portfolio Champion"),
                "results": {
                    "JOINT": joint_results,
                    "XAUTUSD": gold_results,
                    "SLVONUSD": silver_results,
                    "BTCUSD": btc_results,
                    "ETHUSD": eth_results
                }
            })
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_paper_scan(self):
        try:
            db = DatabaseManager()
            client = DeltaExchangeClient()
            of = OrderFlowEngine()
            reporter = HTMLReporter()

            scan_results = []
            for symbol in ACTIVE_SYMBOLS:
                dom = client.get_l2_orderbook(symbol)
                ticker = client.get_ticker(symbol)
                current_price = ticker.get("mark_price", 0.0)

                bids = dom.get("bids", [])
                asks = dom.get("asks", [])
                dom_analysis = of.analyze_dom(bids, asks)

                recent_candles = db.get_latest_candles(symbol, "15m", limit=30)
                is_sweep = False
                sweep_type = "NONE"
                if len(recent_candles) >= 20:
                    is_sweep, sweep_type, _ = of.detect_liquidity_sweep(recent_candles[-1], recent_candles[:-1])

                thought_msg = f"Web Scan: {symbol} at ${current_price}. DOM: {dom_analysis['dominant_side']} (Ratio: {dom_analysis['bid_imbalance_ratio']}x). Sweep: {sweep_type}."
                db.log_thought(
                    symbol=symbol,
                    event_type="WEB_SCAN",
                    stars=4.2 if is_sweep else 3.5,
                    message=thought_msg,
                    metrics={"dom": dom_analysis, "price": current_price, "sweep": sweep_type}
                )

                scan_results.append({
                    "symbol": symbol,
                    "price": current_price,
                    "dominant_side": dom_analysis["dominant_side"],
                    "sweep": sweep_type
                })

            reporter.generate_agent_journal(db.get_trades(), db.get_recent_thoughts())
            self._send_json({"success": True, "scan": scan_results})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_set_risk(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
            new_risk = float(body.get("risk_usd", 5.0))
            if new_risk < 1.0 or new_risk > 100.0:
                self._send_json({"success": False, "error": "Risk must be between $1.00 and $100.00 USD"})
                return

            db = DatabaseManager()
            db.set_target_risk_usd(new_risk)
            db.log_thought(
                symbol="SYSTEM",
                event_type="CONFIG_UPDATE",
                stars=5.0,
                message=f"Risk Per Trade dynamically updated to ${new_risk:.2f} USD by operator via Live Journal."
            )
            self._send_json({"success": True, "target_risk_usd": new_risk})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_toggle_bot_status(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
            new_status = str(body.get("status", "ACTIVE")).upper()
            duration_minutes = int(body.get("duration_minutes", 0))
            reason = str(body.get("reason", "News / Event Pause"))

            db = DatabaseManager()
            db.set_bot_status(new_status, duration_minutes=duration_minutes, reason=reason)

            dur_text = f" for {duration_minutes} minutes" if duration_minutes > 0 else " indefinitely"
            action_text = f"Bot trading paused ({reason}{dur_text})" if new_status == "PAUSED" else "Bot trading resumed ACTIVE"
            db.log_thought(
                symbol="SYSTEM",
                event_type="STATUS_CHANGE",
                stars=5.0,
                message=f"Operator Switch: {action_text}."
            )

            is_paused, reason_str, pause_until = db.is_bot_paused()
            self._send_json({
                "success": True,
                "bot_status": "PAUSED" if is_paused else "ACTIVE",
                "pause_reason": reason_str,
                "pause_until": pause_until
            })
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_live_status(self):
        try:
            db = DatabaseManager()
            client = DeltaExchangeClient()

            # Bot master state & risk settings
            is_paused, pause_reason, pause_until = db.is_bot_paused()
            target_risk = db.get_target_risk_usd(5.0)

            # Wallet balances from Delta India
            bal_res = client.get_wallet_balances()
            balances = bal_res.get("result", []) if bal_res.get("success") else []
            usd_bal = "0.00"
            inr_bal = "0.00"
            for b in balances:
                if b.get("asset_symbol") == "USD":
                    usd_bal = f"{float(b.get('balance', 0)):.2f}"
                elif b.get("asset_symbol") == "INR":
                    inr_bal = f"{float(b.get('balance', 0)):.2f}"

            # Delta positions
            delta_pos = client.get_positions()

            # DB trades
            db_trades = db.get_trades(limit=500)
            # Filter strictly for real live trades (is_paper == 0 and starts with LIVE_)
            open_trades = [t for t in db_trades if t.get("status") == "OPEN" and t.get("is_paper") == 0 and str(t.get("id", "")).startswith("LIVE_")]
            closed_trades = [t for t in db_trades if t.get("status") == "CLOSED" and t.get("is_paper") == 0 and str(t.get("id", "")).startswith("LIVE_")]

            for t in closed_trades:
                sym = str(t.get("symbol", "")).upper()
                notional = float(t.get("notional_usd") or 0.0)
                reason = str(t.get("close_reason") or "").upper()
                is_sl = "SL" in reason or "STOP" in reason or "CIRCUIT" in reason
                fee_usd = calculate_brokerage_fee(sym, notional, is_sl)
                net_pnl = float(t.get("pnl_usd") or 0.0)
                gross_pnl = round(net_pnl + fee_usd, 2)
                t["fee_usd"] = fee_usd
                t["fee_inr"] = round(fee_usd * 90.0, 2)
                t["gross_pnl_usd"] = gross_pnl
                t["pnl_inr"] = round(net_pnl * 90.0, 2)

            # Live tickers
            tickers = {}
            for s in ACTIVE_SYMBOLS:
                try:
                    t = client.get_ticker(s)
                    tickers[s] = float(t.get("mark_price") or t.get("close") or 0.0)
                except Exception:
                    tickers[s] = 0.0

            # Recent AI thoughts
            thoughts = db.get_recent_thoughts(limit=25)

            self._send_json({
                "success": True,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "connected": bal_res.get("success", False),
                "account_id": "74634658",
                "bot_status": "PAUSED" if is_paused else "ACTIVE",
                "target_risk_usd": target_risk,
                "pause_reason": pause_reason,
                "pause_until": pause_until,
                "wallet": {
                    "usd": usd_bal,
                    "inr": inr_bal
                },
                "tickers": tickers,
                "open_trades": open_trades,
                "delta_positions": delta_pos,
                "closed_trades": closed_trades,
                "thoughts": thoughts
            })
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _send_json(self, data: Dict[str, Any]):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

def run_server():
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    server_address = (host, PORT)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)
    url = f"http://127.0.0.1:{PORT}/live_journal.html"
    print("=" * 70)
    print("  [BRAIN] AGENT BRAIN | INTERACTIVE WEB DASHBOARD & ENGINE SERVER")
    print(f"  Listening on: http://{host}:{PORT}")
    print(f"  Opening:      {url}")
    print("=" * 70)
    print("Press Ctrl+C to stop the dashboard server.\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server. Goodbye!")

if __name__ == "__main__":
    run_server()
