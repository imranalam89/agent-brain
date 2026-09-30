import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

# Read original multi_strategy_backtester.py
with open("backtest/multi_strategy_backtester.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add _get_symbol_config helper
helper_code = '''
    def _get_symbol_config(self, symbol: str) -> Dict[str, Any]:
        is_silver = "SLV" in symbol.upper()
        return {
            "is_silver": is_silver,
            "contract_val": 1.0 if is_silver else 0.001,
            "min_swing_dist": 0.35 if is_silver else 3.5,
            "swing_pad": 0.10 if is_silver else 0.8,
            "min_scalp_dist": 0.30 if is_silver else 2.5,
            "scalp_pad": 0.06 if is_silver else 0.6,
            "price_decimals": 3 if is_silver else 2
        }
'''

print("Refactor test helper ready.")
