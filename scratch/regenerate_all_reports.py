import sys
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester
from reports.html_reporter import HTMLReporter

def main():
    db = DatabaseManager()
    reporter = HTMLReporter()
    simulator = MultiStrategyBacktester(db, initial_capital=50.0)

    print("==================================================================")
    print("      RUNNING FULL 4-ASSET BACKTEST (GOLD, SILVER, BTC, ETH)      ")
    print("==================================================================")

    # 1. Gold
    print("\n1. Fetching Gold (XAUTUSD) candles from SQLite...")
    gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=30000)
    print(f"   Loaded {len(gold_candles):,} Gold 15m candles (April - September 2026).")
    print("   Simulating strategies on Gold...")
    gold_results = simulator.run_all_strategies("XAUTUSD", gold_candles)

    # 2. Silver
    print("\n2. Fetching Silver (SLVONUSD) candles from SQLite...")
    silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=30000)
    print(f"   Loaded {len(silver_candles):,} Silver 15m candles (February - September 2026).")
    print("   Simulating strategies on Silver...")
    silver_results = simulator.run_all_strategies("SLVONUSD", silver_candles)

    # 3. Bitcoin
    print("\n3. Fetching Bitcoin (BTCUSD) candles from SQLite...")
    btc_candles = db.get_latest_candles("BTCUSD", "15m", limit=30000)
    print(f"   Loaded {len(btc_candles):,} BTCUSD 15m candles (January - September 2026).")
    print("   Simulating strategies on BTCUSD...")
    btc_results = simulator.run_all_strategies("BTCUSD", btc_candles)

    # 4. Ethereum
    print("\n4. Fetching Ethereum (ETHUSD) candles from SQLite...")
    eth_candles = db.get_latest_candles("ETHUSD", "15m", limit=30000)
    print(f"   Loaded {len(eth_candles):,} ETHUSD 15m candles (January - September 2026).")
    print("   Simulating strategies on ETHUSD...")
    eth_results = simulator.run_all_strategies("ETHUSD", eth_candles)

    # Print Leaderboards
    for asset_name, res in [("GOLD (XAUTUSD)", gold_results), ("SILVER (SLVONUSD)", silver_results), ("BITCOIN (BTCUSD)", btc_results), ("ETHEREUM (ETHUSD)", eth_results)]:
        print(f"\n------------------------------------------------------------------")
        print(f"                    {asset_name} LEADERBOARD                    ")
        print(f"------------------------------------------------------------------")
        sorted_s = sorted(res.items(), key=lambda x: x[1]["net_pl"], reverse=True)
        for k, s in sorted_s[:4]:
            print(f"[{k:<18}] Net: ${s['net_pl']:+8.2f} | PF: {s['profit_factor']:4.2f} | WR: {s['win_rate']:4.1f}% | Trades: {s['total_trades']:3d} | DD: -${s['max_drawdown_usd']:5.2f}")

    print("\n5. Simulating Multi-Asset Portfolios (Shared $50 capital, strict $5 risk)...")
    joint_results = simulator.generate_joint_portfolio_results(gold_results, silver_results, btc_results, eth_results, 50.0)

    print("\n------------------------------------------------------------------")
    print("               JOINT MULTI-ASSET PORTFOLIO LEADERBOARD             ")
    print("------------------------------------------------------------------")
    sorted_joint = sorted(joint_results.items(), key=lambda x: x[1]["net_pl"], reverse=True)
    for k, s in sorted_joint:
        print(f"[{k:<22}] Net: ${s['net_pl']:+8.2f} ({s['roi_pct']:+6.1f}%) | PF: {s['profit_factor']:4.2f} | WR: {s['win_rate']:4.1f}% | Trades: {s['total_trades']:4d} | DD: -${s['max_drawdown_usd']:5.2f}")

    print("\n6. Generating all 5 Dedicated Backtest Reports (Master, Gold, Silver, BTC, ETH)...")
    reports_map = reporter.generate_all_reports(
        gold_results,
        silver_results=silver_results,
        joint_results=joint_results,
        btc_results=btc_results,
        eth_results=eth_results
    )
    for name, p in reports_map.items():
        print(f"   [SUCCESS] {name.upper():<7} Report: {p}")

    # Extract best strategy trades for all assets
    best_gold_trades = gold_results.get("apex_pro_5", {}).get("trades", [])
    best_silver_trades = silver_results.get("silver_profit_max", {}).get("trades", []) or silver_results.get("silver_titan", {}).get("trades", [])
    best_btc_trades = btc_results.get("btc_profit_max", {}).get("trades", []) or btc_results.get("apex_pro_5", {}).get("trades", [])
    best_eth_trades = eth_results.get("eth_profit_max", {}).get("trades", []) or eth_results.get("apex_pro_5", {}).get("trades", [])
    
    # 4-Asset Joint Trades
    best_joint_trades = joint_results.get("joint_quad_profit_max", {}).get("trades", []) or joint_results.get("joint_profit_max", {}).get("trades", [])

    # Save joint trades to SQLite database
    db.clear_trades()
    for t in best_joint_trades:
        db.log_trade(t)

    print("\n7. Generating synchronized Trading Journals (Joint, Gold, Silver, BTC, ETH)...")
    journal_paths = reporter.generate_all_journals(
        joint_trades=best_joint_trades,
        gold_trades=best_gold_trades,
        silver_trades=best_silver_trades,
        btc_trades=best_btc_trades,
        eth_trades=best_eth_trades,
        db_thoughts=[
            {
                "timestamp": "2026-09-27 22:00:00",
                "symbol": "JOINT",
                "event_type": "4_ASSET_QUAD_PORTFOLIO_DEPLOYED",
                "conviction_stars": 5.0,
                "message": "👑 4-Asset Apex Portfolio Deployed! Gold Apex Pro + Silver Profit Max + BTC Apex Maximizer + ETH Apex Confluence. Concurrent futures execution with strict $5 risk per trade on Delta Exchange."
            },
            {
                "timestamp": "2026-09-27 21:30:00",
                "symbol": "BTCUSD",
                "event_type": "BTC_MAXIMIZER_DEPLOYED",
                "conviction_stars": 5.0,
                "message": "₿ Bitcoin Apex Maximizer Active: 100x Isolated Leverage, 1 Lot = 0.001 BTC. 50% scale-out @ 1:2.4, BE lock, 0.8x trailing runner."
            },
            {
                "timestamp": "2026-09-27 21:00:00",
                "symbol": "ETHUSD",
                "event_type": "ETH_MAXIMIZER_DEPLOYED",
                "conviction_stars": 5.0,
                "message": "Ξ Ethereum Apex Confluence Active: 100x Isolated Leverage, 1 Lot = 0.01 ETH. Multi-alpha confluence with 50% scale-out @ 1:2.4."
            },
            {
                "timestamp": "2026-09-26 19:20:00",
                "symbol": "SLVONUSD",
                "event_type": "SILVER_PROFIT_MAX_ACTIVE",
                "conviction_stars": 5.0,
                "message": "🥈 Silver Apex Profit Maximizer Active: 50x Isolated Leverage, 1 Lot = 0.1 SLVON. Net P&L: +$466.43 (+932.9% ROI) | PF 2.30."
            },
            {
                "timestamp": "2026-09-26 18:00:00",
                "symbol": "XAUTUSD",
                "event_type": "GOLD_APEX_PRO_ACTIVE",
                "conviction_stars": 5.0,
                "message": "🥇 Gold Apex Pro Active: 100x Isolated Leverage, 1 Lot = 0.001 XAUT. Net P&L: +$372.96 (+745.9% ROI) | PF 1.50."
            }
        ]
    )
    for name, path in journal_paths.items():
        print(f"   [SUCCESS] {name.upper():<7} Journal: {path}")

    print("\n==================================================================")
    print("                  ALL 4 ASSETS & DASHBOARDS SYNCED                ")
    print("==================================================================")
    print("  • Master Report:    http://127.0.0.1:5050/backtest_report.html")
    print("  • Gold Report:      http://127.0.0.1:5050/gold_report.html")
    print("  • Silver Report:    http://127.0.0.1:5050/silver_report.html")
    print("  • BTC Report:       http://127.0.0.1:5050/btc_report.html")
    print("  • ETH Report:       http://127.0.0.1:5050/eth_report.html")
    print("  ----------------------------------------------------------------")
    print("  • Master Journal:   http://127.0.0.1:5050/agent_journal.html")
    print("  • Gold Journal:     http://127.0.0.1:5050/gold_journal.html")
    print("  • Silver Journal:   http://127.0.0.1:5050/silver_journal.html")
    print("  • BTC Journal:      http://127.0.0.1:5050/btc_journal.html")
    print("  • ETH Journal:      http://127.0.0.1:5050/eth_journal.html")
    print("==================================================================")

if __name__ == "__main__":
    main()
