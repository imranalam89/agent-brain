"""
Telegram Bot Instant Push Notifier for Agent Brain.
Sends instantaneous mobile push alerts for trade entries, 50% scale-outs, and trade exits.
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


class TelegramNotifier:
    def __init__(self):
        self._load_config()

    def _load_config(self):
        load_dotenv(override=True)
        self.enabled = os.getenv("TELEGRAM_ENABLED", "false").strip().lower() in ("true", "1", "yes")
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

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
            f"🔗 <a href='http://127.0.0.1:5050/live_journal.html'>Open Live Trading Journal</a>"
        )
        self._dispatch_async(msg)

    def send_scale_out_alert(self, symbol: str, side: str, price: float, booked_gain: float, new_sl: float):
        """Sends instant push notification when 50% profit is secured & breakeven locked."""
        self._load_config()
        if not self.is_configured():
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = (
            f"🎯 <b>PROFIT BANKED & BREAKEVEN LOCKED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Asset:</b> <code>{symbol}</code> ({side})\n"
            f"💰 <b>Banked Profit (50%):</b> <b>+${booked_gain:.2f}</b>\n"
            f"🛡️ <b>New Stop Loss:</b> <code>${new_sl:,.2f}</code> (Risk-Free Breakeven)\n"
            f"🏃 <b>Runner:</b> 50% remaining lots targeting extended trend\n"
            f"🕒 <b>Time:</b> <code>{now_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        self._dispatch_async(msg)

    def send_exit_alert(self, symbol: str, side: str, exit_price: float, net_pnl: float, reason: str):
        """Sends instant push notification when a trade is closed."""
        self._load_config()
        if not self.is_configured():
            return

        is_win = net_pnl > 0
        icon = "🏆 <b>TRADE CLOSED (WIN)</b>" if is_win else "🛑 <b>TRADE CLOSED (LOSS)</b>"
        pnl_str = f"+${net_pnl:.2f}" if is_win else f"-${abs(net_pnl):.2f}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        msg = (
            f"{icon}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Asset:</b> <code>{symbol}</code> ({side})\n"
            f"💵 <b>Exit Price:</b> <code>${exit_price:,.2f}</code>\n"
            f"📊 <b>Net Realized P&L:</b> <b>{pnl_str}</b>\n"
            f"📝 <b>Reason:</b> <code>{reason}</code>\n"
            f"🕒 <b>Time:</b> <code>{now_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
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
