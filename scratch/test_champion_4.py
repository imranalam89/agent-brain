import os
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

def test_champion_4_portfolio():
    db = DatabaseManager()
    
    # 1. Fetch Gold & Silver
    gold_candles = db.get_latest_candles("XAUTUSD", "15m", limit=30000)
    silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=30000)
    btc_candles = db.get_latest_candles("BTCUSD", "15m", limit=30000)
    eth_candles = db.get_latest_candles("ETHUSD", "15m", limit=30000)
    
    bt = MultiStrategyBacktester(db, initial_capital=50.0)
    
    # Gold Apex Pro
    gold_res = bt.run_apex_master_strategy(
        "XAUTUSD", gold_candles,
        name="🥇 Gold Apex Pro",
        use_stepped_risk=False,
        base_risk=5.0,
        tp1_high=2.5,
        min_rr_high=6.0,
        trail_high=1.0,
        del_th=0.03,
        filter_session_chop=True,
        trail_mod=1.2
    )
    
    # Silver Profit Maximizer
    silver_res = bt.run_silver_apex_titan_strategy(
        "SLVONUSD", silver_candles,
        tp1_rr=2.4, max_rr=6.0, trail_mult=0.8, min_dist=0.30, dist_pad=0.06,
        name="🥈 Silver Apex Profit Maximizer"
    )
    
    print(f"Gold:   Net ${gold_res['net_pl']:+7.2f} | PF: {gold_res['profit_factor']:.2f} | WR: {gold_res['win_rate_pct']:.1f}% | Trades: {gold_res['total_trades']}")
    print(f"Silver: Net ${silver_res['net_pl']:+7.2f} | PF: {silver_res['profit_factor']:.2f} | WR: {silver_res['win_rate_pct']:.1f}% | Trades: {silver_res['total_trades']}")

if __name__ == '__main__':
    test_champion_4_portfolio()
