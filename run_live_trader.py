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
    trader = MultiPairLiveTrader(fixed_risk_usd=5.0)

    print("=" * 80)
    print("🧠 AGENT BRAIN | AUTONOMOUS 24/7 LIVE TRADER")
    print("CHAMPION 3-PAIR MASTER PORTFOLIO ENGINE (Gold, BTC, ETH)")
    print("=" * 80)
    for sym, p in trader.params.items():
        wknd = "24/7 Continuous" if p.get("weekend_trading") else "Mon-Fri (Weekend Paused)"
        print(f"  • {sym:<8} | Strategy: {p['strategy_label']} | Mode: {p['mode']} | Risk: $5.00 | Trading: {wknd}")
    print("=" * 80)
    print(f"Risk Rules: Strictly $5.00 fixed risk per trade | Base Capital: $50.00")
    print(f"Trailing: Unified Ladder (+1R->+0.2R, +1.5R->+0.6R, +2R->+1R, +2.5R->+1.5R, +3R->+2R, +4R->+2.5R, +5R->+3.5R, +6R+ continuous 1.5R trail)")
    print(f"Reversal Guard: Active (-0.45R early cut / +0.8R peak profit lock)")
    print("=" * 80 + "\n")

    # Ensure sibling services (Dashboard & DOM Recorder) are synchronized
    import subprocess
    try:
        subprocess.run(["systemctl", "restart", "trading-dashboard"], capture_output=True, timeout=5)
    except Exception:
        pass

    print("[STARTING CONTINUOUS EXECUTION LOOP]")
    print("Press Ctrl+C to halt gracefully.\n")

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                print(f"\n--- [Cycle #{cycle_count} | {now_str}] Scanning 3 Champion Instruments & Managing Positions ---", flush=True)
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
            except Exception as e:
                import traceback
                print(f"❌ [UNHANDLED LOOP ERROR] {e}\n{traceback.format_exc()}", flush=True)

            # High-Frequency Real-Time Scan: 1 second tick for instant 1s L2 DOM execution & trailing management
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n🛑 [HALT] Autonomous Multi-Pair Live Trader stopped by user.")
        if trader.active_positions:
            print(f"⚠️ Notice: You still have active positions tracked: {list(trader.active_positions.keys())}")
        print("Agent Brain state is preserved in SQLite database.")

if __name__ == '__main__':
    main()
