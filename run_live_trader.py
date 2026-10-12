import sys
import time
import os
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from execution.multi_pair_trader import MultiPairLiveTrader

def main():
    print("""
================================================================================
     🧠 AGENT BRAIN | AUTONOMOUS DELTA LIVE TRADER (MODEL C MACRO RUNNER) 🧠     
   Strategy: 🏛️ Verified Level 2 DOM Institutional Order Flow Strategy
   Microstructure: Real-Time L2 Book Imbalance & Resting Wall Exploitation
   Instruments: BTCUSD (Breakout 3.0x), ETHUSD (Session 2.0x), XAUTUSD (Absorption 2.0x), SLVONUSD (Breakout 2.5x)
   Trade Management: Model C Breathing Trail (1.35x @ +1.5R) • Breakeven @ +0.8R
   Risk Base: Strictly $5.00 Fixed Risk Per Trade ($50 Capital Base)
================================================================================
    """)

    # Ensure sibling services (Dashboard & DOM Recorder) are synchronized
    import subprocess
    try:
        subprocess.run(["systemctl", "restart", "trading-dashboard"], capture_output=True, timeout=5)
    except Exception:
        pass

    trader = MultiPairLiveTrader(fixed_risk_usd=5.0)

    print("\n[STARTING CONTINUOUS EXECUTION LOOP]")
    print("Press Ctrl+C to halt gracefully.\n")

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n--- [Cycle #{cycle_count} | {now_str}] Scanning 4 Instruments & Managing Positions ---", flush=True)
            
            status = trader.scan_and_manage_all_pairs()
            active_count = status.get("active_positions_count", 0)
            bot_status = status.get("bot_status", "ACTIVE")
            target_risk = status.get("target_risk_usd", 5.0)

            if bot_status == "PAUSED":
                pause_reason = status.get("pause_reason", "News / Manual Pause")
                pause_until = status.get("pause_until")
                time_str = f" until {pause_until}" if pause_until else ""
                print(f"⏸️ [PAUSE / SLEEP MODE ACTIVE] New entries paused ({pause_reason}{time_str}). Risk: ${target_risk:.2f}/trade.", flush=True)
            elif active_count > 0:
                print(f"⚡ Currently Managing {active_count} Active Position(s): {list(trader.active_positions.keys())} | Risk: ${target_risk:.2f}", flush=True)
            else:
                print(f"💤 No active positions. Scanning for A+ setups... [Status: ACTIVE | Risk: ${target_risk:.2f}/trade]", flush=True)

            # High-Frequency Scan: 3 seconds tick for instant execution & management
            time.sleep(3)

    except KeyboardInterrupt:
        print("\n\n🛑 [HALT] Autonomous Multi-Pair Live Trader stopped by user.")
        if trader.active_positions:
            print(f"⚠️ Notice: You still have active positions tracked: {list(trader.active_positions.keys())}")
        print("Agent Brain state is preserved in SQLite database.")

if __name__ == '__main__':
    main()
