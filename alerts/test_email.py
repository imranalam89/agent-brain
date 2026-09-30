"""
Quick verification script for email notifications.
Run this script to test if your email credentials can connect to SMTP and deliver an alert.
"""

import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alerts.email_notifier import notifier

def test_connection():
    print("==================================================")
    print("   📧 AGENT BRAIN EMAIL NOTIFICATION TESTER       ")
    print("==================================================")
    
    notifier._load_config()
    print(f"Enabled:          {notifier.enabled}")
    print(f"SMTP Host:        {notifier.smtp_host}:{notifier.smtp_port}")
    print(f"Sender Email:     {notifier.smtp_user}")
    print(f"Recipient Email:  {notifier.recipient_email}")
    print(f"Password Set:     {'YES (configured)' if notifier.smtp_password else 'NO (blank)'}")
    print("--------------------------------------------------")

    if not notifier.is_configured():
        print("❌ Email notifications are NOT fully configured in .env yet.")
        print("\nPlease add the following lines to your .env file:")
        print("ALERT_EMAIL_ENABLED=true")
        print("SMTP_HOST=smtp.gmail.com")
        print("SMTP_PORT=587")
        print("SMTP_USER=your_email@gmail.com")
        print("SMTP_PASSWORD=your_16_character_app_password")
        print("ALERT_RECIPIENT_EMAIL=your_email@gmail.com")
        print("\nNote for Gmail: Use an 'App Password' from https://myaccount.google.com/apppasswords")
        return False

    print("🚀 Sending test live trade alert...")
    notifier.send_entry_alert(
        symbol="BTCUSD",
        side="BUY",
        entry_price=82950.0,
        sl=82150.0,
        tp=84550.0,
        lots=6,
        risk_usd=5.00,
        leverage=100
    )
    print("✅ Dispatched! Check your inbox (and spam folder) in a few seconds.")
    return True

if __name__ == "__main__":
    test_connection()
