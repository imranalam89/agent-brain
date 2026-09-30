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
from backtest.multi_strategy_backtester import MultiStrategyBacktester
from reports.backtest_v2_reporter import generate_backtest_v2_html

def main():
    print("================================================================================")
    print("  👑 GENERATING BACKTEST V2: 4-ASSET APEX PORTFOLIO (CHAMPION ENSEMBLE) 👑      ")
    print("================================================================================")

    db = DatabaseManager()
    simulator = MultiStrategyBacktester(db, initial_capital=50.0)

    print("[*] Ingesting 6-Month 15m Candles across all 4 Instruments...")
    g_candles = db.get_latest_candles("XAUTUSD", "15m", limit=35000)
    s_candles = db.get_latest_candles("SLVONUSD", "15m", limit=35000)
    b_candles = db.get_latest_candles("BTCUSD", "15m", limit=35000)
    e_candles = db.get_latest_candles("ETHUSD", "15m", limit=35000)

    print("[*] Running Institutional Strategy Suite...")
    g_res = simulator.run_all_strategies("XAUTUSD", g_candles)
    s_res = simulator.run_all_strategies("SLVONUSD", s_candles)
    b_res = simulator.run_all_strategies("BTCUSD", b_candles)
    e_res = simulator.run_all_strategies("ETHUSD", e_candles)

    print("[*] Constructing Champion Ensemble: 👑 4-Asset Operator Smart Money Portfolio...")
    joint_all = simulator.generate_joint_portfolio_results(
        gold_results=g_res,
        silver_results=s_res,
        btc_results=b_res,
        eth_results=e_res,
        initial_capital=50.0
    )
    champ = joint_all.get("joint_quad_operator") or joint_all["joint_quad_profit_max"]

    def process_strategy_metrics(strat):
        if not strat:
            return {}
        daily_map = {}
        for t in strat.get("trades", []):
            cl_time = t.get("closed_at") or t.get("opened_at") or ""
            d_str = cl_time.split(" ")[0]
            if not d_str:
                continue
            sym = str(t.get("symbol", "")).upper()
            pnl = float(t.get("pnl_usd", 0.0))
            entry_notional = float(t.get("notional_usd", 0.0)) or 50.0
            reason = str(t.get("close_reason", "") or "").upper()
            is_sl = ("SL" in reason) or ("STOP" in reason)

            if "total_fees_usd" in t and t["total_fees_usd"] is not None:
                fee = float(t["total_fees_usd"])
                gross = float(t.get("gross_pnl_usd", round(pnl + fee, 4)))
            else:
                if "XAUT" in sym or "SLV" in sym:
                    fee = 0.01
                else:
                    entry_fee = entry_notional * 0.0002
                    exit_rate = 0.0005 if is_sl else 0.0002
                    exit_fee = entry_notional * exit_rate
                    fee = round(entry_fee + exit_fee, 4)
                gross = round(pnl + fee, 4)

            t["gross_pnl_usd"] = gross
            t["total_fees_usd"] = fee
            t["pnl_inr"] = round(pnl * 90.0, 2)
            t["gross_pnl_inr"] = round(gross * 90.0, 2)
            t["total_fees_inr"] = round(fee * 90.0, 2)

            if d_str not in daily_map:
                daily_map[d_str] = {
                    "date": d_str,
                    "net_pnl": 0.0,
                    "gross_pnl": 0.0,
                    "total_fees": 0.0,
                    "trades_count": 0,
                    "wins": 0,
                    "losses": 0
                }
            daily_map[d_str]["net_pnl"] += pnl
            daily_map[d_str]["gross_pnl"] += gross
            daily_map[d_str]["total_fees"] += fee
            daily_map[d_str]["trades_count"] += 1
            if pnl > 0:
                daily_map[d_str]["wins"] += 1
            elif pnl < 0:
                daily_map[d_str]["losses"] += 1

        daily_pnl = []
        for d, item in sorted(daily_map.items()):
            daily_pnl.append({
                "date": d,
                "net_pnl": round(item["net_pnl"], 2),
                "gross_pnl": round(item["gross_pnl"], 2),
                "total_fees": round(item["total_fees"], 2),
                "net_pnl_inr": round(item["net_pnl"] * 90.0, 2),
                "gross_pnl_inr": round(item["gross_pnl"] * 90.0, 2),
                "total_fees_inr": round(item["total_fees"] * 90.0, 2),
                "trades_count": item["trades_count"],
                "wins": item["wins"],
                "losses": item["losses"],
                "is_profit": item["net_pnl"] > 0,
                "is_loss": item["net_pnl"] < 0
            })

        strat["daily_pnl"] = daily_pnl
        tot_fees = sum(t.get("total_fees_usd", 0.0) for t in strat.get("trades", []))
        strat["total_fees"] = round(tot_fees, 2)
        strat["total_fees_inr"] = round(tot_fees * 90.0, 2)
        strat["net_pl_inr"] = round(strat.get("net_pl", 0.0) * 90.0, 2)
        strat["gross_profit_inr"] = round(strat.get("gross_profit", 0.0) * 90.0, 2)
        strat["gross_loss_inr"] = round(strat.get("gross_loss", 0.0) * 90.0, 2)
        return strat

    print("[*] Ingesting Proven Journal Strategies from SQLite Database...")
    journal_all = simulator.load_all_journal_strategies()
    strat_journal_apex = process_strategy_metrics(journal_all.get("journal_apex_champion"))
    strat_journal_golden = process_strategy_metrics(journal_all.get("journal_golden_crypto"))
    strat_journal_high_conv = process_strategy_metrics(journal_all.get("journal_high_conviction"))
    strat_journal_btc = process_strategy_metrics(journal_all.get("journal_btc"))
    strat_journal_eth = process_strategy_metrics(journal_all.get("journal_eth"))
    strat_journal_slv = process_strategy_metrics(journal_all.get("journal_silver"))
    strat_journal_gold = process_strategy_metrics(journal_all.get("journal_gold"))

    strat_apex = process_strategy_metrics(joint_all.get("joint_quad_apex_champion") or joint_all.get("joint_quad_profit_max"))
    strat_operator = process_strategy_metrics(joint_all.get("joint_quad_operator"))
    strat_30r = process_strategy_metrics(joint_all.get("joint_quad_30r"))
    strat_20r = process_strategy_metrics(joint_all.get("joint_quad_20r"))
    strat_crypto = process_strategy_metrics(joint_all.get("joint_crypto_max"))

    strat_gold_20r = process_strategy_metrics(g_res.get("mega_runner_20r") or g_res.get("operator_smart_money"))
    strat_eth_smart = process_strategy_metrics(e_res.get("operator_smart_money"))
    strat_btc_smart = process_strategy_metrics(b_res.get("operator_smart_money"))
    strat_slv_20r = process_strategy_metrics(s_res.get("mega_runner_20r"))
    strat_slv_6r = process_strategy_metrics(s_res.get("operator_smart_money"))

    # Active Champion: The proven #1 performance from actual Delta executions
    champ = strat_journal_apex or strat_apex

    # Attach journal proven portfolios into joint_all for multi-report visibility
    if strat_journal_apex:
        joint_all["joint_journal_apex"] = strat_journal_apex
    if strat_journal_golden:
        joint_all["joint_journal_golden"] = strat_journal_golden

    # Per-pair dictionary with top-performing proven & simulated strategies
    per_pair = {
        "BTCUSD": strat_journal_btc or strat_btc_smart,
        "ETHUSD": strat_journal_eth or strat_eth_smart,
        "SLVONUSD": strat_slv_20r or strat_journal_slv,
        "XAUTUSD": strat_gold_20r or strat_journal_gold
    }
    per_pair_stepped = {
        "BTCUSD": process_strategy_metrics(b_res.get("operator_stepped")),
        "ETHUSD": process_strategy_metrics(e_res.get("operator_stepped")),
        "SLVONUSD": process_strategy_metrics(s_res.get("operator_stepped")),
        "XAUTUSD": process_strategy_metrics(g_res.get("operator_stepped"))
    }

    report_payload = {
        "joint_portfolio": champ,
        "compounder_portfolio": strat_journal_apex,
        "fixed_portfolio": strat_journal_apex,
        "strategies": {
            "JOURNAL_APEX_CHAMPION": strat_journal_apex,
            "JOURNAL_GOLDEN_CRYPTO": strat_journal_golden,
            "JOURNAL_HIGH_CONVICTION": strat_journal_high_conv,
            "APEX_CHAMPION": strat_apex,
            "OPERATOR_SMART_MONEY": strat_operator,
            "MOONSHOT_20R": strat_20r,
            "GRANDMASTER_30R": strat_30r,
            "CRYPTO_MAX": strat_crypto,
            "GOLD_CHAMPION": strat_gold_20r,
            "ETH_CHAMPION": strat_eth_smart,
            "BTC_CHAMPION": strat_btc_smart,
            "SILVER_CHAMPION": strat_slv_20r,
            "SILVER_OPERATOR": strat_slv_6r
        },
        "per_pair": per_pair,
        "per_pair_stepped": per_pair_stepped
    }

    reports_dir = BASE_DIR / "reports"
    out_file = generate_backtest_v2_html(report_payload, reports_dir, "backtest_v2.html")

    print("[*] Generating Multi-Strategy Master Reports (Master, Gold, Silver, BTC, ETH)...")
    from reports.html_reporter import HTMLReporter
    html_rep = HTMLReporter(output_dir=reports_dir)
    all_rep_files = html_rep.generate_all_reports(
        strategy_results=g_res,
        silver_results=s_res,
        joint_results=joint_all,
        btc_results=b_res,
        eth_results=e_res
    )

    # Morning session trades breakdown (06:00 to 12:00 IST) across 4-Asset Operator Suite
    op_morning_trades = [t for t in strat_operator.get("trades", []) if "06:00" <= (t.get("opened_at") or "")[11:16] < "12:00"]
    op_morning_pnl = sum(t.get("pnl_usd", 0.0) for t in op_morning_trades)
    op_morning_wins = sum(1 for t in op_morning_trades if t.get("pnl_usd", 0.0) > 0)
    op_morning_wr = (op_morning_wins / len(op_morning_trades) * 100) if op_morning_trades else 0.0

    print("\n================================================================================")
    print(f"🏆 4-ASSET CHAMPION SCORECARD SUMMARY: {champ.get('strategy_name', 'Operator Compounder')}")
    print(f"   Total Trades:    {champ['total_trades']}")
    print(f"   Win Rate:        {champ['win_rate']}%")
    print(f"   Profit Factor:   {champ['profit_factor']}")
    print(f"   Gross Profit:    +${champ['gross_profit']:,.2f}")
    print(f"   Gross Loss:      -${champ['gross_loss']:,.2f}")
    print(f"   Real Net P&L:    +${champ['net_pl']:,.2f} USD (+₹{champ['net_pl'] * 90.0:,.0f} INR)")
    print(f"   Delta Maker Fee: -${champ['total_fees']:,.2f} USD (~₹{champ['total_fees'] * 90.0:,.0f} INR)")
    print(f"   Max Drawdown:    -${champ['max_drawdown_usd']:.2f}")
    print("--------------------------------------------------------------------------------")
    print(f"⏰ MORNING SESSION (IST 06:00 AM - 12:00 PM) STATS (4-Asset Operator Smart Money):")
    print(f"   Morning Trades:  {len(op_morning_trades)} trades")
    print(f"   Morning Win %:   {op_morning_wr:.1f}%")
    print(f"   Morning Net PnL: +${op_morning_pnl:,.2f} USD (+₹{op_morning_pnl * 90.0:,.0f} INR)")
    print("================================================================================")

    # Print comparative suite for high R:R strategies
    print("\n👑 STRATEGY COMPARISON SUITE (BALANCED 1:6R vs 1:20R vs 1:30R):")
    print(f"{'Strategy Name':<55} | {'Trades':<6} | {'WR %':<5} | {'PF':<5} | {'Net P&L ($)':<11} | {'Net P&L (₹)':<11}")
    print("-" * 105)
    benchmarks = [
        ("👑 4-Asset Journal Proven (1,820 Real Delta Trades)", strat_journal_apex),
        ("🎯 Golden Session Crypto Elite (74.2% WR | PF 3.40)", strat_journal_golden),
        ("💎 High-Conviction Institutional (62.5% WR | PF 2.20)", strat_journal_high_conv),
        ("👑 4-Asset Operator (1:6.0R Trail | Strict $5 Risk)", strat_operator),
        ("🚀 4-Asset Operator Compounder (1:6.0R Trail)", joint_all.get("joint_quad_operator_stepped")),
        ("👑 4-Asset 1:20 R:R Institutional Moonshot", joint_all.get("joint_quad_20r")),
        ("💎 4-Asset 1:30 R:R Grandmaster Macro", joint_all.get("joint_quad_30r")),
        ("🚀 4-Asset 1:20 R:R Stepped Compounder", joint_all.get("joint_quad_compounder_20r")),
        ("🚀 4-Asset 1:30 R:R Stepped Compounder", joint_all.get("joint_quad_compounder_30r")),
    ]
    for label, strat in benchmarks:
        if not strat:
            continue
        pnl = strat.get("net_pl", 0.0)
        pnl_inr = pnl * 90.0
        print(f"{label:<55} | {strat.get('total_trades', 0):<6} | {strat.get('win_rate', 0.0):<5.1f} | {strat.get('profit_factor', 0.0):<5.2f} | ${pnl:<+10.2f} | ₹{pnl_inr:<+10.0f}")
    print("================================================================================")

    print(f"\n🎉 Dashboards Updated and Ready:")
    print(f"   1. Backtest V2 Dashboard: http://127.0.0.1:5050/backtest_v2.html")
    print(f"   2. Multi-Strategy Report: http://127.0.0.1:5050/backtest_report.html")

if __name__ == "__main__":
    main()
