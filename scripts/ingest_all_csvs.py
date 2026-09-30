import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from data.historical_loader import HistoricalDataLoader

def main():
    db = DatabaseManager()
    loader = HistoricalDataLoader(db)

    csv_dir = Path("data/csv_imports")
    
    # Target files in chronological order: April -> September 2026
    months = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
    
    for m in months:
        # Find file matching month
        matched_file = None
        for root, dirs, files in os.walk(csv_dir):
            for f in files:
                if m in f and f.endswith(".csv"):
                    candidate = Path(root) / f
                    # Ensure it's a file, not a folder
                    if candidate.is_file():
                        matched_file = candidate
                        break
            if matched_file:
                break

        if matched_file:
            print(f"\n==========================================")
            print(f"Processing Month {m}: {matched_file.name} ({matched_file.stat().st_size / (1024*1024):.1f} MB)...")
            loader.process_delta_csv_file(matched_file, timeframe_minutes=15)
        else:
            print(f"Warning: File for month {m} not found in {csv_dir}")

    total_candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)
    print(f"\n==========================================")
    print(f"Ingestion Complete! Total 15m candles in SQLite: {len(total_candles):,}")

if __name__ == "__main__":
    main()
