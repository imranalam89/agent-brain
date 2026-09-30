import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from data.database import DatabaseManager
from backtest.backtest_engine_v2 import BacktestEngineV2
from reports.backtest_v2_reporter import generate_backtest_v2_html

def main():
    print("================================================================================")
    print("  🧠 AGENT BRAIN | BACKTEST V2 GENERATOR (DYNAMIC EXECUTION & EXPLICIT FEES) 🧠 ")
    print("================================================================================")

    db = DatabaseManager()
    engine = BacktestEngineV2(db, initial_capital=50.0)

    symbols = ["BTCUSD", "ETHUSD", "XAUTUSD", "SLVONUSD"]
    results = engine.run_joint_portfolio_backtest(symbols)

    reports_dir = BASE_DIR / "reports"
    out_file = generate_backtest_v2_html(results, reports_dir, "backtest_v2.html")

    print("\n================================================================================")
    print(f"🎉 SUCCESS! Backtest V2 HTML Report is live at:")
    print(f"   Local file: file:///{out_file.as_posix()}")
    print(f"   Dashboard:  http://127.0.0.1:5050/backtest_v2.html")
    print("================================================================================")

if __name__ == "__main__":
    main()
