import os
import sys
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")
from exchange.delta_client import DeltaExchangeClient

key = os.getenv("DELTA_API_KEY", "")
secret = os.getenv("DELTA_API_SECRET", "")
print(f"Key loaded: {key[:6]}... (length {len(key)})")
print(f"Secret loaded: {secret[:6]}... (length {len(secret)})")

for env in ["india", "global", "demo"]:
    client = DeltaExchangeClient(environment=env, api_key=key, api_secret=secret)
    print(f"\n--- Testing Environment: {env} ({client.base_url}) ---")
    try:
        products = client.get_products()
        print(f"  Products fetched: {len(products)}")
        wb = client.get_wallet_balances()
        print(f"  Wallet balances response: success={wb.get('success')}, error={wb.get('error')}, code={wb.get('status_code')}")
        if wb.get("success"):
            print(f"  Wallet result: {wb.get('result')}")
    except Exception as e:
        print(f"  Exception: {e}")
