import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from execution.multi_pair_trader import MultiPairLiveTrader

def test_multi_trader():
    print("==================================================================")
    print("      TESTING AUTONOMOUS MULTI-PAIR CONCURRENT TRADING ENGINE     ")
    print("==================================================================")
    
    trader = MultiPairLiveTrader(fixed_risk_usd=5.0)
    print(f"Trader Initialized with strict ${trader.fixed_risk_usd:.2f} risk per trade.")
    print(f"Supported Instruments: {list(trader.params.keys())}")
    
    # 1. Run live scan cycle
    print("\n1. Running live market scan cycle across all 4 instruments...")
    res = trader.scan_and_manage_all_pairs()
    print(f"Scan completed at {res['timestamp']}. Active positions: {res['active_positions_count']}")
    
    # 2. Simulate concurrent multi-pair execution:
    print("\n2. Testing concurrent trade management (BTC trade running while ETH and Gold take setups)...")
    
    # Open BTC trade
    btc_signal = {
        "symbol": "BTCUSD",
        "side": "BUY",
        "dist": 180.0,
        "lots": 28,
        "stop_loss": 89820.0,
        "take_profit": 90630.0
    }
    trader._execute_entry("BTCUSD", btc_signal, 90000.0)
    
    # Open ETH trade simultaneously
    eth_signal = {
        "symbol": "ETHUSD",
        "side": "BUY",
        "dist": 8.0,
        "lots": 62,
        "stop_loss": 3092.0,
        "take_profit": 3128.0
    }
    trader._execute_entry("ETHUSD", eth_signal, 3100.0)
    
    # Open Gold trade simultaneously
    gold_signal = {
        "symbol": "XAUTUSD",
        "side": "BUY",
        "dist": 10.0,
        "lots": 500,
        "stop_loss": 4740.0,
        "take_profit": 4800.0
    }
    trader._execute_entry("XAUTUSD", gold_signal, 4750.0)
    
    print(f"\nActive Concurrent Positions: {list(trader.active_positions.keys())}")
    assert len(trader.active_positions) == 3, "All 3 positions should be active simultaneously!"
    
    # 3. Simulate price movement:
    # BTC moves to +2.0R (90360) -> Scale out 50% and move SL to BE
    print("\n3. Testing BTC Scale-Out (Price rises to +2.0R = $90,360)...")
    trader._manage_active_position("BTCUSD", 90365.0)
    assert trader.active_positions["BTCUSD"]["tp1_hit"] == True, "BTC TP1 should be hit!"
    assert trader.active_positions["BTCUSD"]["stop_loss"] > 90000.0, "BTC SL should be moved above entry (Breakeven lock)!"
    
    # Meanwhile, ETH stays open and Gold stays open!
    assert "ETHUSD" in trader.active_positions, "ETH must still be active independently!"
    assert "XAUTUSD" in trader.active_positions, "Gold must still be active independently!"
    print(f"Verified: BTC is in Phase 3 (Risk-Free), while ETH & Gold remain active independently!")
    
    # 4. BTC hits runner target and exits cleanly
    print("\n4. Testing BTC Runner Target Exit (Price rises to +3.5R = $90,630)...")
    trader._manage_active_position("BTCUSD", 90635.0)
    assert "BTCUSD" not in trader.active_positions, "BTC should be closed after hitting runner target!"
    assert "ETHUSD" in trader.active_positions, "ETH must still be running after BTC closed!"
    assert "XAUTUSD" in trader.active_positions, "Gold must still be running after BTC closed!"
    print(f"Remaining active positions: {list(trader.active_positions.keys())}")
    
    # Clean up simulated ETH & Gold
    trader._close_position("ETHUSD", 3116.0, "TEST_CLEANUP")
    trader._close_position("XAUTUSD", 4775.0, "TEST_CLEANUP")
    
    print("\n==================================================================")
    print("      [SUCCESS] MULTI-PAIR CONCURRENT TRADER FULLY VERIFIED       ")
    print("==================================================================")

if __name__ == '__main__':
    test_multi_trader()
