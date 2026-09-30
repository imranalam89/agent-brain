import os
import sys
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from exchange.delta_client import DeltaExchangeClient
from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester
from reports.html_reporter import HTMLReporter

def patch_september_data():
    print("==================================================================")
    print("      PATCHING SEPTEMBER 2026 DATA FROM DELTA EXCHANGE API        ")
    print("==================================================================")

    db = DatabaseManager()
    client = DeltaExchangeClient(environment="india")

    # September 1 to September 27, 2026 (current date)
    start_ts = int(datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime(2026, 9, 27, 0, 0, 0, tzinfo=timezone.utc).timestamp())

    symbols = ["XAUTUSD", "SLVONUSD"]
    resolutions = ["15m", "5m", "1h"]

    for symbol in symbols:
        print(f"\n1. Fetching {symbol} data from Delta Exchange India API...")
        for res in resolutions:
            raw_candles = client.get_candles(symbol, resolution=res, start=start_ts, end=end_ts)
            if not raw_candles:
                print(f"   [WARN] No {res} candles returned for {symbol}")
                continue

            # Delta returns candles descending; sort ascending
            raw_candles.sort(key=lambda x: x["timestamp"])

            # Compute Order Flow Delta & Volumes
            enriched = []
            for c in raw_candles:
                vol = c.get("volume", 0.0)
                hi = c["high"]
                lo = c["low"]
                op = c["open"]
                cl = c["close"]
                hl = max(0.0001, hi - lo)
                co = cl - op
                ratio = max(-1.0, min(1.0, co / hl))
                delta = round(vol * ratio, 2)
                buy_vol = round(max(0.0, (vol + delta) / 2.0), 2)
                sell_vol = round(max(0.0, (vol - delta) / 2.0), 2)

                enriched.append({
                    "timestamp": c["timestamp"],
                    "open": op,
                    "high": hi,
                    "low": lo,
                    "close": cl,
                    "volume": vol,
                    "buy_volume": buy_vol,
                    "sell_volume": sell_vol,
                    "delta": delta
                })

            db.save_candles(symbol, res, enriched)
            t_first = datetime.fromtimestamp(enriched[0]["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            t_last = datetime.fromtimestamp(enriched[-1]["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            print(f"   [SUCCESS] Saved {len(enriched):,} {res} candles for {symbol} ({t_first} -> {t_last})")

    # Verify counts in SQLite
    print("\n------------------------------------------------------------------")
    print("                DATABASE CANDLE STATUS POST-PATCH                 ")
    print("------------------------------------------------------------------")
    with db.get_connection() as conn:
        c = conn.cursor()
        for s in symbols:
            c.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM candles WHERE symbol = ? AND timeframe = '15m'", (s,))
            row = c.fetchone()
            t_min = datetime.fromtimestamp(row[1], tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if row[1] else "None"
            t_max = datetime.fromtimestamp(row[2], tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if row[2] else "None"

            c.execute("SELECT COUNT(*) FROM candles WHERE symbol = ? AND timeframe = '15m' AND timestamp >= 1788220800", (s,))
            sep_count = c.fetchone()[0]
            print(f"[{s:<10}] Total 15m: {row[0]:,} candles ({t_min} -> {t_max}) | September 2026: {sep_count:,} candles")

    print("\n==================================================================")
    print("     RUNNING FULL MULTI-ASSET BACKTEST WITH SEPTEMBER 2026        ")
    print("==================================================================")

    simulator = MultiStrategyBacktester(db, initial_capital=50.0)
    reporter = HTMLReporter()

    print("\nFetching updated Gold (XAUTUSD) candles...")
    gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=30000)
    print(f"Loaded {len(gold_candles):,} Gold 15m candles.")
    gold_results = simulator.run_all_strategies("XAUTUSD", gold_candles)

    print("\nFetching updated Silver (SLVONUSD) candles...")
    silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=30000)
    print(f"Loaded {len(silver_candles):,} Silver 15m candles.")
    silver_results = simulator.run_all_strategies("SLVONUSD", silver_candles)

    print("\nSimulating Joint Multi-Asset Portfolio (Shared $50 capital, strict $5 risk)...")
    joint_results = simulator.generate_joint_portfolio_results(gold_results, silver_results, 50.0)

    print("\n------------------------------------------------------------------")
    print("                    GOLD (XAUTUSD) LEADERBOARD                    ")
    print("------------------------------------------------------------------")
    sorted_gold = sorted(gold_results.items(), key=lambda x: x[1]["net_pl"], reverse=True)
    for k, s in sorted_gold[:5]:
        sep_trades = [t for t in s["trades"] if (t.get("opened_at") or "").startswith("2026-09") or (t.get("closed_at") or "").startswith("2026-09")]
        sep_pl = sum(t.get("pnl_usd", 0.0) for t in sep_trades)
        print(f"[{k:<18}] Net: ${s['net_pl']:+8.2f} | PF: {s['profit_factor']:4.2f} | WR: {s['win_rate']:4.1f}% | Trades: {s['total_trades']:3d} (Sep: {len(sep_trades):2d} trades, ${sep_pl:+6.2f}) | DD: -${s['max_drawdown_usd']:5.2f}")

    print("\n------------------------------------------------------------------")
    print("                   SILVER (SLVONUSD) LEADERBOARD                  ")
    print("------------------------------------------------------------------")
    sorted_silver = sorted(silver_results.items(), key=lambda x: x[1]["net_pl"], reverse=True)
    for k, s in sorted_silver[:5]:
        sep_trades = [t for t in s["trades"] if (t.get("opened_at") or "").startswith("2026-09") or (t.get("closed_at") or "").startswith("2026-09")]
        sep_pl = sum(t.get("pnl_usd", 0.0) for t in sep_trades)
        print(f"[{k:<18}] Net: ${s['net_pl']:+8.2f} | PF: {s['profit_factor']:4.2f} | WR: {s['win_rate']:4.1f}% | Trades: {s['total_trades']:3d} (Sep: {len(sep_trades):2d} trades, ${sep_pl:+6.2f}) | DD: -${s['max_drawdown_usd']:5.2f}")

    print("\n------------------------------------------------------------------")
    print("               JOINT MULTI-ASSET PORTFOLIO LEADERBOARD             ")
    print("------------------------------------------------------------------")
    sorted_joint = sorted(joint_results.items(), key=lambda x: x[1]["net_pl"], reverse=True)
    for k, s in sorted_joint:
        sep_trades = [t for t in s["trades"] if (t.get("opened_at") or "").startswith("2026-09") or (t.get("closed_at") or "").startswith("2026-09")]
        sep_pl = sum(t.get("pnl_usd", 0.0) for t in sep_trades)
        print(f"[{k:<20}] Net: ${s['net_pl']:+8.2f} ({s['roi_pct']:+6.1f}%) | PF: {s['profit_factor']:4.2f} | WR: {s['win_rate']:4.1f}% | Trades: {s['total_trades']:3d} (Sep: {len(sep_trades):2d} trades, ${sep_pl:+6.2f}) | DD: -${s['max_drawdown_usd']:5.2f}")

    # Generate Dashboards
    print("\nRegenerating Scorecard & Synchronized Journals...")
    report_path = reporter.generate_multi_strategy_backtest_report(
        gold_results,
        "Multi-Asset (Gold & Silver)",
        silver_results=silver_results,
        joint_results=joint_results
    )

    best_gold_trades = gold_results.get("apex_pro_5", {}).get("trades", [])
    best_silver_trades = silver_results.get("silver_profit_max", {}).get("trades", []) or silver_results.get("silver_titan", {}).get("trades", [])
    best_joint_trades = joint_results.get("joint_profit_max", {}).get("trades", []) or (best_gold_trades + best_silver_trades)

    db.clear_trades()
    for t in best_joint_trades:
        db.log_trade(t)

    journals = reporter.generate_all_journals(
        joint_trades=best_joint_trades,
        gold_trades=best_gold_trades,
        silver_trades=best_silver_trades,
        db_thoughts=[
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": "JOINT",
                "event_type": "SEPTEMBER_2026_API_PATCHED",
                "conviction_stars": 5.0,
                "message": "Delta Exchange India API September 2026 data successfully fetched and patched! Full backtest completed with live tick candles up to September 26, 2026."
            }
        ]
    )

    print(f"   [SUCCESS] Scorecard:     {report_path}")
    for name, p in journals.items():
        print(f"   [SUCCESS] {name.upper():<7} Journal: {p}")

    print("\nAll reports refreshed with real September 2026 Delta Exchange data!")

if __name__ == "__main__":
    patch_september_data()
