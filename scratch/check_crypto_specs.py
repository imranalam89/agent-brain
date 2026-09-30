import requests
import json
from pathlib import Path

def main():
    try:
        r = requests.get('https://api.india.delta.exchange/v2/products', timeout=10)
        data = r.json()
        target_symbols = ['BTCUSD', 'ETHUSD', 'XAUTUSD', 'SLVONUSD']
        for p in data.get('result', []):
            sym = p.get('symbol')
            if sym in target_symbols:
                print(f"SYMBOL: {sym}")
                print(f"  id: {p.get('id')}")
                print(f"  Contract Value: {p.get('contract_value')}")
                print(f"  Tick Size:      {p.get('tick_size')}")
                print(f"  maker_commission_rate: {p.get('maker_commission_rate')}")
                print(f"  taker_commission_rate: {p.get('taker_commission_rate')}")
                print(f"  initial_margin: {p.get('initial_margin')}")
                print(f"  maintenance_margin: {p.get('maintenance_margin')}")
    except Exception as e:
        print("API Query failed:", e)

    csv_dir = Path("data/csv_imports")
    for sym in ["BTCUSD", "ETHUSD"]:
        print(f"\nScanning files for {sym}...")
        found = [p for p in csv_dir.rglob("*.csv") if p.is_file() and sym in p.name]
        print(f"Found {len(found)} actual CSV files for {sym}:")
        for f in sorted(found):
            print(f"  {f.name} ({f.stat().st_size / 1024 / 1024:.2f} MB)")
            with open(f, "r", encoding="utf-8") as file:
                header = file.readline().strip()
                row1 = file.readline().strip()
                print(f"    Header: {header}")
                print(f"    Sample: {row1[:100]}...")

if __name__ == '__main__':
    main()
