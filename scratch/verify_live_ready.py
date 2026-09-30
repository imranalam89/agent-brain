import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from execution.multi_pair_trader import MultiPairLiveTrader

trader = MultiPairLiveTrader()
print("LIVE_TRADER_AUTHENTICATED:", trader.is_live_authenticated)
res = trader.scan_and_manage_all_pairs()
print("SCAN_RESULT:", res)
