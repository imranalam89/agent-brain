"""
Professional Real-Time Email Notifier for Agent Brain.
Dispatches asynchronous, non-blocking HTML alerts for trade entries, scale-outs, and exits.
"""

import os
import sys
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure latest .env values are loaded
load_dotenv(override=True)


class EmailNotifier:
    def __init__(self):
        self._load_config()

    def _load_config(self):
        load_dotenv(override=True)
        self.enabled = os.getenv("ALERT_EMAIL_ENABLED", "false").strip().lower() in ("true", "1", "yes")
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "").strip()
        self.smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
        self.recipient_email = os.getenv("ALERT_RECIPIENT_EMAIL", self.smtp_user).strip()

    def is_configured(self) -> bool:
        self._load_config()
        return bool(self.enabled and self.smtp_host and self.smtp_user and self.smtp_password and self.recipient_email)

    def _send_email_thread(self, subject: str, html_body: str, plain_body: str):
        """Worker thread to send email without delaying the trading loop."""
        if not self.is_configured():
            return

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Agent Brain Trader <{self.smtp_user}>"
            msg["To"] = self.recipient_email

            part1 = MIMEText(plain_body, "plain")
            part2 = MIMEText(html_body, "html")
            msg.attach(part1)
            msg.attach(part2)

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.ehlo()
                if self.smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, [self.recipient_email], msg.as_string())

            print(f"📧 [EMAIL DISPATCHED] Alert successfully sent to {self.recipient_email}: '{subject}'")
        except Exception as e:
            print(f"⚠️ [EMAIL FAILED] Could not send alert: {e}")

    def _dispatch_async(self, subject: str, html_body: str, plain_body: str):
        """Fires sending in a detached background thread."""
        thread = threading.Thread(
            target=self._send_email_thread,
            args=(subject, html_body, plain_body),
            daemon=True
        )
        thread.start()

    def send_entry_alert(self, symbol: str, side: str, entry_price: float, sl: float, tp: float, lots: int, risk_usd: float = 5.00, leverage: int = 100):
        """Sends an instant alert when a trade is entered on Delta Exchange."""
        self._load_config()
        if not self.is_configured():
            return

        side_upper = side.upper()
        badge_color = "#10b981" if side_upper == "BUY" else "#ef4444"
        side_icon = "🟢" if side_upper == "BUY" else "🔴"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC+5:30")
        subject = f"{side_icon} [DELTA LIVE ENTRY] {symbol} {side_upper} @ ${entry_price:,.2f}"

        plain_text = f"""
Agent Brain Live Trade Entry
Symbol: {symbol}
Side: {side_upper}
Entry Price: ${entry_price:,.2f}
Stop Loss: ${sl:,.2f}
Take Profit: ${tp:,.2f}
Position Size: {lots} Lots
Risk per Trade: ${risk_usd:.2f}
Leverage: {leverage}x Isolated
Timestamp: {now_str}
Live Journal: http://127.0.0.1:5050/live_journal.html
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #f3f4f6; margin: 0; padding: 20px; }}
  .card {{ max-width: 560px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 14px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
  .header {{ background: linear-gradient(135deg, #1e1b4b, #0f172a); padding: 24px; border-bottom: 1px solid #1f2937; text-align: center; }}
  .title {{ font-size: 20px; font-weight: 800; color: #f8fafc; margin: 0; letter-spacing: 0.5px; }}
  .subtitle {{ font-size: 13px; color: #94a3b8; margin-top: 6px; }}
  .badge {{ display: inline-block; padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 14px; color: #ffffff; background-color: {badge_color}; margin-top: 12px; }}
  .content {{ padding: 24px; }}
  .table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  .table td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; font-size: 14px; }}
  .table td.label {{ color: #94a3b8; font-weight: 500; width: 45%; }}
  .table td.val {{ color: #f1f5f9; font-weight: 700; text-align: right; }}
  .risk-badge {{ color: #fbbf24; font-weight: 800; }}
  .footer {{ padding: 18px 24px; background: #0b0f19; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #1f2937; }}
  .btn {{ display: inline-block; padding: 10px 20px; background: #3b82f6; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 13px; margin-top: 16px; }}
</style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="title">🧠 AGENT BRAIN | DELTA LIVE ORDER</div>
      <div class="subtitle">Champion Ensemble Autonomous Execution</div>
      <div class="badge">{side_icon} {side_upper} {symbol}</div>
    </div>
    <div class="content">
      <table class="table">
        <tr>
          <td class="label">Asset Symbol</td>
          <td class="val">{symbol}</td>
        </tr>
        <tr>
          <td class="label">Order Direction</td>
          <td class="val" style="color: {badge_color};">{side_upper}</td>
        </tr>
        <tr>
          <td class="label">Entry Price</td>
          <td class="val">${entry_price:,.2f}</td>
        </tr>
        <tr>
          <td class="label">Stop Loss</td>
          <td class="val" style="color: #ef4444;">${sl:,.2f}</td>
        </tr>
        <tr>
          <td class="label">Take Profit (Target)</td>
          <td class="val" style="color: #10b981;">${tp:,.2f}</td>
        </tr>
        <tr>
          <td class="label">Position Size</td>
          <td class="val">{lots:,} Lots</td>
        </tr>
        <tr>
          <td class="label">Leverage Mode</td>
          <td class="val">{leverage}x Isolated</td>
        </tr>
        <tr>
          <td class="label">Risk Enforced</td>
          <td class="val risk-badge">${risk_usd:.2f} Fixed</td>
        </tr>
        <tr>
          <td class="label">Execution Time</td>
          <td class="val">{now_str}</td>
        </tr>
      </table>

      <div style="text-align: center;">
        <a href="http://127.0.0.1:5050/live_journal.html" class="btn">View Live Trading Journal</a>
      </div>
    </div>
    <div class="footer">
      Automated alert sent by Agent Brain AI Engine &bull; Delta Exchange India
    </div>
  </div>
</body>
</html>
"""
        self._dispatch_async(subject, html_body, plain_text)

    def send_scale_out_alert(self, symbol: str, side: str, price: float, booked_gain: float, new_sl: float):
        """Sends an alert when 50% lots are scaled out and stop is moved to breakeven."""
        self._load_config()
        if not self.is_configured():
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC+5:30")
        subject = f"🎯 [DELTA PROFIT LOCKED] {symbol} {side} +${booked_gain:.2f} Banked (BE Locked)"

        plain_text = f"""
Agent Brain Profit Scale-Out & Breakeven Lock
Symbol: {symbol} ({side})
Trigger Price: ${price:,.2f}
Profit Banked (50%): +${booked_gain:.2f}
New Stop Loss: ${new_sl:,.2f} (100% Risk-Free Breakeven)
Timestamp: {now_str}
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b0f19; color: #f3f4f6; padding: 20px; }}
  .card {{ max-width: 560px; margin: 0 auto; background: #111827; border: 1px solid #10b981; border-radius: 14px; overflow: hidden; }}
  .header {{ background: #064e3b; padding: 20px; text-align: center; }}
  .title {{ font-size: 18px; font-weight: 800; color: #34d399; margin: 0; }}
  .content {{ padding: 20px; }}
  .table {{ width: 100%; border-collapse: collapse; }}
  .table td {{ padding: 8px 10px; border-bottom: 1px solid #1e293b; font-size: 14px; }}
</style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="title">🎯 50% PROFIT LOCKED & BREAKEVEN SECURED</div>
      <div style="color: #a7f3d0; font-size: 13px; margin-top: 4px;">{symbol} {side} &bull; Trade is now 100% Risk-Free</div>
    </div>
    <div class="content">
      <table class="table">
        <tr><td style="color:#94a3b8;">Asset</td><td style="text-align:right; font-weight:bold;">{symbol}</td></tr>
        <tr><td style="color:#94a3b8;">Banked Profit</td><td style="text-align:right; font-weight:bold; color:#10b981;">+${booked_gain:.2f}</td></tr>
        <tr><td style="color:#94a3b8;">New Stop Loss</td><td style="text-align:right; font-weight:bold; color:#38bdf8;">${new_sl:,.2f} (BE)</td></tr>
        <tr><td style="color:#94a3b8;">Runner Position</td><td style="text-align:right; font-weight:bold; color:#fbbf24;">50% Riding Target</td></tr>
        <tr><td style="color:#94a3b8;">Time</td><td style="text-align:right;">{now_str}</td></tr>
      </table>
    </div>
  </div>
</body>
</html>
"""
        self._dispatch_async(subject, html_body, plain_text)

    def send_exit_alert(self, symbol: str, side: str, exit_price: float, net_pnl: float, reason: str):
        """Sends an alert when a trade is completely closed."""
        self._load_config()
        if not self.is_configured():
            return

        is_win = net_pnl > 0
        icon = "🏆" if is_win else "🛑"
        color = "#10b981" if is_win else "#ef4444"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC+5:30")
        pnl_str = f"+${net_pnl:.2f}" if is_win else f"-${abs(net_pnl):.2f}"
        subject = f"{icon} [DELTA POSITION CLOSED] {symbol} {side} | Net P&L: {pnl_str} ({reason})"

        plain_text = f"""
Agent Brain Position Closed
Symbol: {symbol} ({side})
Exit Price: ${exit_price:,.2f}
Net Realized P&L: {pnl_str}
Close Reason: {reason}
Timestamp: {now_str}
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b0f19; color: #f3f4f6; padding: 20px; }}
  .card {{ max-width: 560px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 14px; overflow: hidden; }}
  .header {{ background: #1f2937; padding: 20px; text-align: center; }}
  .pnl {{ font-size: 24px; font-weight: 800; color: {color}; margin-top: 6px; }}
  .content {{ padding: 20px; }}
  .table {{ width: 100%; border-collapse: collapse; }}
  .table td {{ padding: 8px 10px; border-bottom: 1px solid #1e293b; font-size: 14px; }}
</style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div style="font-size: 14px; color: #94a3b8; font-weight: 600;">{icon} TRADE COMPLETED</div>
      <div class="pnl">{pnl_str}</div>
      <div style="color: #cbd5e1; font-size: 13px;">{symbol} &bull; {side} &bull; Reason: {reason}</div>
    </div>
    <div class="content">
      <table class="table">
        <tr><td style="color:#94a3b8;">Exit Price</td><td style="text-align:right; font-weight:bold;">${exit_price:,.2f}</td></tr>
        <tr><td style="color:#94a3b8;">Net P&L</td><td style="text-align:right; font-weight:bold; color:{color};">{pnl_str}</td></tr>
        <tr><td style="color:#94a3b8;">Reason</td><td style="text-align:right; font-weight:bold;">{reason}</td></tr>
        <tr><td style="color:#94a3b8;">Time</td><td style="text-align:right;">{now_str}</td></tr>
      </table>
    </div>
  </div>
</body>
</html>
"""
        self._dispatch_async(subject, html_body, plain_text)


# Global singleton
notifier = EmailNotifier()
