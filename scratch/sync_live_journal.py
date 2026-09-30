import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from execution.multi_pair_trader import MultiPairLiveTrader

trader = MultiPairLiveTrader()
trader._sync_live_dashboards()
print("LIVE_DASHBOARDS_SYNCED_OK")
