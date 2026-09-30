import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from exchange.delta_client import DeltaExchangeClient

client = DeltaExchangeClient(environment="india")
products = client.get_products()
print(f"Total products on Delta India: {len(products)}")

matches = [p for p in products if any(k in p.get("symbol", "").upper() for k in ["XAUT", "GOLD", "SLV", "SILVER"])]
print(f"\nMatching Gold & Silver products ({len(matches)}):")
for m in matches:
    print(f"Symbol: {m.get('symbol'):<16} ID: {m.get('id'):<6} Underlying: {m.get('underlying_asset', {}).get('symbol')} Type: {m.get('contract_type')} SettledIn: {m.get('settling_asset', {}).get('symbol')}")
