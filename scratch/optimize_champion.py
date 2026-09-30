import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

db = DatabaseManager()
sim = MultiStrategyBacktester(db)
btc_c = db.get_latest_candles("BTCUSD", "15m", limit=35000)
eth_c = db.get_latest_candles("ETHUSD", "15m", limit=35000)
gold_c = db.get_latest_candles("XAUTUSD", "15m", limit=35000)
silv_c = db.get_latest_candles("SLVONUSD", "15m", limit=35000)

g_res = sim.run_all_strategies("XAUTUSD", gold_c)
s_res = sim.run_all_strategies("SLVONUSD", silv_c)
b_res = sim.run_all_strategies("BTCUSD", btc_c)
e_res = sim.run_all_strategies("ETHUSD", eth_c)

# Let's test different ensemble configurations:
ensembles = [
    (
        "Stepped Compound Champion (Gold Stepped + Silver Stepped + BTC Stepped + ETH Balanced)",
        g_res["apex_stepped"], s_res["apex_stepped"], b_res["apex_stepped"], e_res["balanced_2_0"]
    ),
    (
        "Strict $5 Risk Alpha Apex (Gold Apex 5 + Silver Profit Max + BTC Apex 5 + ETH Balanced)",
        g_res["apex_pro_5"], s_res["silver_profit_max"], b_res["apex_pro_5"], e_res["balanced_2_0"]
    ),
    (
        "Strict $5 High PF Apex (Gold Apex 5 + Silver Apex 5 + BTC Apex 5 + ETH Scale-Out 2.0)",
        g_res["apex_pro_5"], s_res["apex_pro_5"], b_res["apex_pro_5"], e_res["scale_out_2_0"]
    ),
    (
        "Stepped Compound Hybrid (Gold Stepped + Silver Stepped + BTC Scale-Out 3.0 + ETH Balanced)",
        g_res["apex_stepped"], s_res["apex_stepped"], b_res["scale_out_3_0"], e_res["balanced_2_0"]
    ),
    (
        "Dynamic Multi-Alpha Ensemble (Gold Apex Master + Silver Apex Master + BTC Apex Master + ETH Adaptive)",
        g_res["apex_master"], s_res["apex_master"], b_res["apex_master"], e_res["adaptive_context"]
    )
]

for name, g, s, b, e in ensembles:
    merged = sim.generate_joint_portfolio_results(
        gold_results={"apex_pro_5": g},
        silver_results={"silver_profit_max": s},
        btc_results={"btc_profit_max": b},
        eth_results={"eth_profit_max": e}
    )["joint_quad_profit_max"]
    print(f"==================================================")
    print(f"ENSEMBLE: {name}")
    print(f"  Net P&L:       ${merged['net_pl']:,.2f}")
    print(f"  Win Rate:      {merged['win_rate']}%")
    print(f"  Profit Factor: {merged['profit_factor']}")
    print(f"  Total Trades:  {merged['total_trades']}")
    print(f"  Max Drawdown:  -${merged['max_drawdown_usd']:.2f}")
