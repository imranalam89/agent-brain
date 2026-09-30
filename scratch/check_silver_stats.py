import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from datetime import datetime

db = DatabaseManager()
candles = db.get_latest_candles('SLVONUSD', '15m', limit=25000)
print(f'SLVONUSD candles count: {len(candles)}')
if candles:
    start_dt = datetime.fromtimestamp(candles[0]['timestamp']).strftime('%Y-%m-%d %H:%M')
    end_dt = datetime.fromtimestamp(candles[-1]['timestamp']).strftime('%Y-%m-%d %H:%M')
    print(f'Date range: {start_dt} to {end_dt}')
    lows = [c['low'] for c in candles]
    highs = [c['high'] for c in candles]
    ranges = [c['high'] - c['low'] for c in candles]
    print(f'Price range: min=${min(lows):.2f}, max=${max(highs):.2f}')
    print(f'Average 15m candle range (High - Low): ${sum(ranges)/len(ranges):.4f}')
    print(f'Median 15m candle range: ${sorted(ranges)[len(ranges)//2]:.4f}')
