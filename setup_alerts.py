"""
Interactive Alert Setup Wizard for Agent Brain.
Quickly configures Telegram Bot and/or Email alerts in .env.
"""

import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from pathlib import Path
from dotenv import set_key, load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"

def main():
    print("==================================================")
    print("      🚀 AGENT BRAIN NOTIFICATION SETUP WIZARD    ")
    print("==================================================")
    print("Choose an option:")
    print("  1. Configure Telegram Bot Alerts (Instant Phone Push)")
    print("  2. Configure Email Alerts (Gmail / SMTP)")
    print("  3. Test Telegram Alert")
    print("  4. Test Email Alert")
    print("  5. Exit")
    print("--------------------------------------------------")

    choice = input("Enter choice [1-5]: ").strip()

    if choice == "1":
        configure_telegram()
    elif choice == "2":
        configure_email()
    elif choice == "3":
        test_telegram()
    elif choice == "4":
        test_email()
    else:
        print("Exiting.")

def configure_telegram():
    print("\n--- TELEGRAM BOT CONFIGURATION ---")
    print("1. Open Telegram and search for @BotFather")
    print("2. Send '/newbot' and follow instructions to name your bot.")
    print("3. Copy the HTTP API token provided by BotFather.")
    print("   Example: 7891234567:AAF_example_token_here")
    token = input("\nEnter your Telegram Bot Token: ").strip()
    if not token:
        print("❌ Token cannot be empty.")
        return

    print("\nNext, open your new bot on Telegram and click 'Start' (or send 'hello').")
    input("Press Enter after you have pressed 'Start' on your bot...")

    from alerts.telegram_notifier import TelegramNotifier
    updates = TelegramNotifier.get_updates(token)
    chat_id = ""
    if updates.get("ok") and updates.get("result"):
        last_msg = updates["result"][-1]
        chat_id = str(last_msg.get("message", {}).get("chat", {}).get("id", ""))

    if chat_id:
        print(f"🎉 Auto-detected Chat ID: {chat_id}")
    else:
        print("⚠️ Could not auto-detect. (You can also find your chat ID by messaging @userinfobot on Telegram)")
        chat_id = input("Enter your Chat ID manually: ").strip()

    if not chat_id:
        print("❌ Chat ID is required.")
        return

    set_key(str(ENV_PATH), "TELEGRAM_ENABLED", "true")
    set_key(str(ENV_PATH), "TELEGRAM_BOT_TOKEN", token)
    set_key(str(ENV_PATH), "TELEGRAM_CHAT_ID", chat_id)
    print("\n✅ Telegram Bot settings successfully saved to .env!")
    
    # Test alert
    print("Sending test notification...")
    test_telegram()

def configure_email():
    print("\n--- EMAIL (SMTP) CONFIGURATION ---")
    email = input("Enter your sender email (e.g. your_email@gmail.com): ").strip()
    print("\nFor Gmail:")
    print("Generate a 16-character App Password at: https://myaccount.google.com/apppasswords")
    pwd = input("Enter your App Password / SMTP Password: ").strip()
    recipient = input(f"Enter recipient email (Press Enter to use '{email}'): ").strip()
    if not recipient:
        recipient = email

    set_key(str(ENV_PATH), "ALERT_EMAIL_ENABLED", "true")
    set_key(str(ENV_PATH), "SMTP_HOST", "smtp.gmail.com")
    set_key(str(ENV_PATH), "SMTP_PORT", "587")
    set_key(str(ENV_PATH), "SMTP_USER", email)
    set_key(str(ENV_PATH), "SMTP_PASSWORD", pwd)
    set_key(str(ENV_PATH), "ALERT_RECIPIENT_EMAIL", recipient)
    print("\n✅ Email settings successfully saved to .env!")

    print("Sending test email...")
    test_email()

def test_telegram():
    load_dotenv(str(ENV_PATH), override=True)
    from alerts.telegram_notifier import telegram_notifier
    telegram_notifier._load_config()
    if not telegram_notifier.is_configured():
        print("❌ Telegram is not configured yet. Run Option 1 first.")
        return
    print("🚀 Dispatching Telegram test notification...")
    telegram_notifier.send_entry_alert(
        symbol="BTCUSD",
        side="BUY",
        entry_price=82950.0,
        sl=82150.0,
        tp=84550.0,
        lots=6,
        risk_usd=5.00,
        leverage=100
    )
    print("✅ Telegram notification dispatched! Check your phone/app.")

def test_email():
    load_dotenv(str(ENV_PATH), override=True)
    from alerts.email_notifier import notifier
    notifier._load_config()
    if not notifier.is_configured():
        print("❌ Email is not configured yet. Run Option 2 first.")
        return
    print("🚀 Dispatching Email test notification...")
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
    print("✅ Email dispatched! Check your inbox.")

if __name__ == "__main__":
    main()
