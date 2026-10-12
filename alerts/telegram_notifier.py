"""
Telegram Bot Instant Push Notifier for Agent Brain.
Sends instantaneous mobile push alerts for trade entries, breakeven stop locks, and trade exits.
Zero-delay, non-blocking background thread execution.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import threading
from datetime import datetime
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv(override=True)

DEFAULT_BOT_TOKEN = "8668687479:AAH-kAPQYfZGCGEDXHhEfvbrPEM_BmG2j-Y"
DEFAULT_CHAT_ID = "8953069874"

class TelegramNotifier:
    def __init__(self):
        self._load_config()

    def _load_config(self):
        load_dotenv(override=True)
        # Default enabled to True with configured credentials fallback
        self.enabled = os.getenv("TELEGRAM_ENABLED", "true").strip().lower() in ("true", "1", "yes")
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or DEFAULT_BOT_TOKEN
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or DEFAULT_CHAT_ID

    def is_configured(self) -> bool:
        self._load_config()
        return bool(self.enabled and self.bot_token and self.chat_id)

    def _send_request(self, text: str, parse_mode: str = "HTML"):
        if not self.is_configured():
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "AgentBrainNotifier/1.0"}
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res.get("ok"):
                    print(f"📱 [TELEGRAM ALERT SENT] Push notification delivered to Chat ID: {self.chat_id}")
                else:
                    print(f"⚠️ [TELEGRAM ERROR] API returned: {res}")
        except Exception as e:
            print(f"⚠️ [TELEGRAM NOTICE] Failed to send push alert: {e}")

    def _dispatch_async(self, text: str):
        thread = threading.Thread(target=self._send_request, args=(text,), daemon=True)
        thread.start()

    def send_entry_alert(self, symbol: str, side: str, entry_price: float, sl: float, tp: float, lots: int, risk_usd: float = 5.00, leverage: int = 100):
        """Sends instant push notification when a trade enters."""
        self._load_config()
        if not self.is_configured():
            return

        side_upper = side.upper()
        icon = "🟢 <b>BUY ORDER EXECUTED</b>" if side_upper == "BUY" else "🔴 <b>SELL ORDER EXECUTED</b>"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        msg = (
            f"🧠 <b>AGENT BRAIN &bull; DELTA LIVE ORDER</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{icon}\n\n"
            f"📌 <b>Asset:</b> <code>{symbol}</code>\n"
            f"🎯 <b>Direction:</b> <b>{side_upper}</b>\n"
            f"💵 <b>Entry Price:</b> <code>${entry_price:,.2f}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>${sl:,.2f}</code>\n"
            f"🎯 <b>Take Profit:</b> <code>${tp:,.2f}</code>\n"
            f"📦 <b>Lots:</b> <code>{lots:,} Lots</code>\n"
            f"⚡ <b>Leverage:</b> <code>{leverage}x Isolated</code>\n"
            f"🛡️ <b>Strict Risk:</b> <code>${risk_usd:.2f}</code>\n"
            f"🕒 <b>Time:</b> <code>{now_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <a href='http://62.72.31.29:5050/live_journal.html'>Open Live Trading Journal</a>"
        )
        self._dispatch_async(msg)

    def send_breakeven_alert(self, symbol: str, side: str, current_price: float, be_sl: float, r_mult: float = 1.0):
        """Sends instant push notification when Breakeven profit is locked at +1.0R."""
        self._load_config()
        if not self.is_configured():
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = (
            f"🛡️ <b>BREAKEVEN PROFIT LOCKED (+0.20R)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Asset:</b> <code>{symbol}</code> ({side.upper()})\n"
            f"💵 <b>Current Price:</b> <code>${current_price:,.2f}</code> (+{r_mult:.1f}R reached)\n"
            f"🛡️ <b>New Stop Loss:</b> <code>${be_sl:,.2f}</code> (+0.20R in profit)\n"
            f"💰 <b>Guaranteed Outcome:</b> Fees fully covered + profit locked if reversed!\n"
            f"🏃 <b>Macro Runner:</b> 100% position running towards full Take Profit\n"
            f"🕒 <b>Time:</b> <code>{now_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <a href='http://62.72.31.29:5050/live_journal.html'>Open Live Trading Journal</a>"
        )
        self._dispatch_async(msg)

    def send_trailing_alert(self, symbol: str, side: str, current_price: float, new_sl: float, r_mult: float):
        """Sends instant push notification when Model C breathing trailing ratchets."""
        self._load_config()
        if not self.is_configured():
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = (
            f"⚡ <b>MODEL C TRAILING STOP RATCHETED (+{r_mult:.1f}R)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Asset:</b> <code>{symbol}</code> ({side.upper()})\n"
            f"💵 <b>Current Price:</b> <code>${current_price:,.2f}</code>\n"
            f"🛡️ <b>Trailing Stop:</b> <code>${new_sl:,.2f}</code> (Profit Protected)\n"
            f"🏃 <b>Macro Runner:</b> 1.35x breathing buffer active\n"
            f"🕒 <b>Time:</b> <code>{now_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <a href='http://62.72.31.29:5050/live_journal.html'>Open Live Trading Journal</a>"
        )
        self._dispatch_async(msg)

    def send_exit_alert(self, symbol: str, side: str, exit_price: float, net_pnl: float, reason: str):
        """Sends instant push notification when a trade is closed."""
        self._load_config()
        if not self.is_configured():
            return

        is_win = net_pnl > 0
        is_be = "BREAKEVEN" in reason.upper() or abs(net_pnl) < 1.0
        if is_win:
            icon = "🏆 <b>TRADE CLOSED (WIN)</b>"
        elif is_be:
            icon = "🛡️ <b>TRADE CLOSED (BREAKEVEN)</b>"
        else:
            icon = "🛑 <b>TRADE CLOSED (STOP LOSS)</b>"

        pnl_str = f"+${net_pnl:.2f}" if net_pnl >= 0 else f"-${abs(net_pnl):.2f}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        msg = (
            f"{icon}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Asset:</b> <code>{symbol}</code> ({side.upper()})\n"
            f"💵 <b>Exit Price:</b> <code>${exit_price:,.2f}</code>\n"
            f"📊 <b>Net Realized P&L:</b> <b>{pnl_str} USD</b> (₹{net_pnl*90:+,.2f} INR)\n"
            f"📝 <b>Reason:</b> <code>{reason}</code>\n"
            f"🕒 <b>Time:</b> <code>{now_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <a href='http://62.72.31.29:5050/live_journal.html'>Open Live Trading Journal</a>"
        )
        self._dispatch_async(msg)

    @staticmethod
    def get_updates(bot_token: str):
        """Helper to fetch recent messages and auto-detect chat_id."""
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AgentBrainNotifier/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": str(e)}


telegram_notifier = TelegramNotifier()
