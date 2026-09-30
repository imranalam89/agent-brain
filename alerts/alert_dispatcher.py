"""
Unified Alert Dispatcher for Agent Brain.
Simultaneously dispatches alerts to Email (SMTP) and Telegram Bot.
"""

from alerts.email_notifier import notifier as email_notifier
from alerts.telegram_notifier import telegram_notifier


class AlertDispatcher:
    def send_entry_alert(self, symbol: str, side: str, entry_price: float, sl: float, tp: float, lots: int, risk_usd: float = 5.00, leverage: int = 100):
        # Email
        email_notifier.send_entry_alert(symbol, side, entry_price, sl, tp, lots, risk_usd, leverage)
        # Telegram
        telegram_notifier.send_entry_alert(symbol, side, entry_price, sl, tp, lots, risk_usd, leverage)

    def send_scale_out_alert(self, symbol: str, side: str, price: float, booked_gain: float, new_sl: float):
        # Email
        email_notifier.send_scale_out_alert(symbol, side, price, booked_gain, new_sl)
        # Telegram
        telegram_notifier.send_scale_out_alert(symbol, side, price, booked_gain, new_sl)

    def send_exit_alert(self, symbol: str, side: str, exit_price: float, net_pnl: float, reason: str):
        # Email
        email_notifier.send_exit_alert(symbol, side, exit_price, net_pnl, reason)
        # Telegram
        telegram_notifier.send_exit_alert(symbol, side, exit_price, net_pnl, reason)


dispatcher = AlertDispatcher()
