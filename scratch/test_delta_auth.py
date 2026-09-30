import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import exchange.delta_client as d
client = d.DeltaExchangeClient()
res = client.get_wallet_balances()
print("DELTA_AUTH_RESULT:", res)
