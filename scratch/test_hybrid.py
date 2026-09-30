import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester

db = DatabaseManager()
sim = MultiStrategyBacktester(db, initial_capital=50.0)

print("[*] Ingesting candles...")
b_c = db.get_latest_candles("BTCUSD", "15m", limit=35000)
e_c = db.get_latest_candles("ETHUSD", "15m", limit=35000)
s_c = db.get_latest_candles("SLVONUSD", "15m", limit=35000)
g_c = db.get_latest_candles("XAUTUSD", "15m", limit=35000)

print("[*] Testing strategies...")
b_vwap = sim.run_session_vwap_bands_strategy("BTCUSD", b_c, sigma_entry=1.5, tp_vwap_rr=2.0, min_rr=2.0)
e_vwap = sim.run_session_vwap_bands_strategy("ETHUSD", e_c, sigma_entry=1.5, tp_vwap_rr=2.0, min_rr=2.0)
s_vwap = sim.run_session_vwap_bands_strategy("SLVONUSD", s_c, sigma_entry=1.8, tp_vwap_rr=1.6, min_rr=4.0)
g_apex = sim.run_apex_master_strategy("XAUTUSD", g_c, base_risk=5.0, tp1_high=2.5, min_rr_high=6.0, trail_high=1.0, del_th=0.03, filter_session_chop=True)

print(f"BTC VWAP:  {b_vwap['total_trades']:<5} trades | WR: {b_vwap['win_rate']:<5}% | Net: ${b_vwap['net_pl']:<+9.2f} | PF: {b_vwap['profit_factor']:<5.2f}")
print(f"ETH VWAP:  {e_vwap['total_trades']:<5} trades | WR: {e_vwap['win_rate']:<5}% | Net: ${e_vwap['net_pl']:<+9.2f} | PF: {e_vwap['profit_factor']:<5.2f}")
print(f"SLV VWAP:  {s_vwap['total_trades']:<5} trades | WR: {s_vwap['win_rate']:<5}% | Net: ${s_vwap['net_pl']:<+9.2f} | PF: {s_vwap['profit_factor']:<5.2f}")
print(f"XAUT APEX: {g_apex['total_trades']:<5} trades | WR: {g_apex['win_rate']:<5}% | Net: ${g_apex['net_pl']:<+9.2f} | PF: {g_apex['profit_factor']:<5.2f}")

tot_net = b_vwap['net_pl'] + e_vwap['net_pl'] + s_vwap['net_pl'] + g_apex['net_pl']
tot_trades = b_vwap['total_trades'] + e_vwap['total_trades'] + s_vwap['total_trades'] + g_apex['total_trades']
print(f"\nCOMBINED SUM NET: ${tot_net:,.2f} USD (+₹{tot_net*90:,.0f} INR) across {tot_trades} trades!")
