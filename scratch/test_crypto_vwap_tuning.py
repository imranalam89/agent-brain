import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

def main():
    db = DatabaseManager()
    bt = MultiStrategyBacktester(db, initial_capital=50.0)
    btc_c = db.get_latest_candles('BTCUSD', '15m', limit=30000)
    eth_c = db.get_latest_candles('ETHUSD', '15m', limit=30000)

    for sym, c in [('BTCUSD', btc_c), ('ETHUSD', eth_c)]:
        print(f"\n=================== Testing {sym} ===================")
        for sig in [1.5, 1.7, 1.8, 2.0]:
            for tp_rr in [1.0, 1.2, 1.5, 2.0]:
                for min_rr in [2.0, 2.5, 3.5, 5.0]:
                    res = bt.run_session_vwap_bands_strategy(sym, c, sigma_entry=sig, tp_vwap_rr=tp_rr, min_rr=min_rr)
                    if res['win_rate'] >= 65.0 and res['profit_factor'] >= 1.7:
                        print(f"Sig: {sig:3.1f} | TP_RR: {tp_rr:3.1f} | Min_RR: {min_rr:3.1f} -> Net: ${res['net_pl']:+8.2f} ({res['roi_pct']:+6.1f}%) | WR: {res['win_rate']:4.1f}% | PF: {res['profit_factor']:4.2f} | Trades: {res['total_trades']:3d} | DD: -${res['max_drawdown_usd']:.2f}")

if __name__ == '__main__':
    main()
