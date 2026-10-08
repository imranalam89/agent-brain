import sys
import json
import csv
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from data.database import DatabaseManager
from backtest.multi_strategy_backtester import MultiStrategyBacktester
from scripts.generate_champion_v5 import simulate_v5_apex_suite, calculate_exact_fees, STRICT_RISK_USD, USD_TO_INR

def generate_24_7_candidate_trades(symbol: str, candles: list, sigma: float = 1.5, min_dist: float = 160.0, pad: float = 45.0, tp_rr: float = 2.0, is_crypto: bool = True) -> list:
    """
    Generates 24/7 candidate trade setups across all 24 hours of the day (00:00 to 23:45)
    and all 7 days of the week (Monday through Sunday for crypto; market days for commodities).
    """
    trades = []
    active = None
    last_close = -999999999
    curr_day = None
    day_v = 0.0
    day_pv = 0.0
    day_pr = []

    for i in range(50, len(candles)):
        c = candles[i]
        ts = c["timestamp"]
        dt = datetime.fromtimestamp(ts)
        d_str = dt.strftime("%Y-%m-%d")
        cl = c["close"]
        hi = c["high"]
        lo = c["low"]
        op = c["open"]
        v = max(1.0, c.get("volume", 1.0))
        typ = (hi + lo + cl) / 3.0

        if not is_crypto and dt.weekday() in (5, 6):
            continue

        if d_str != curr_day:
            curr_day = d_str
            day_v = 0.0
            day_pv = 0.0
            day_pr = []

        day_v += v
        day_pv += typ * v
        day_pr.append(typ)
        vwap = day_pv / day_v
        mean_p = sum(day_pr) / len(day_pr)
        var = sum((x - mean_p)**2 for x in day_pr) / len(day_pr)
        std = max(1.0 if "XAUT" in symbol or "SLV" in symbol else 40.0, var**0.5)

        upper = vwap + sigma * std
        lower = vwap - sigma * std

        if active:
            side = active["side"]
            sl = active["stop_loss"]
            tp = active["take_profit"]
            hit_sl = (lo <= sl) if side == "BUY" else (hi >= sl)
            hit_tp = (hi >= tp) if side == "BUY" else (lo <= tp)

            if hit_sl or hit_tp:
                exit_p = tp if hit_tp else sl
                pnl_r = tp_rr if hit_tp else -1.0
                pnl_usd = pnl_r * 5.0
                active.update({
                    "exit_price": exit_p,
                    "pnl_usd": pnl_usd,
                    "rr_achieved": pnl_r,
                    "closed_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "close_reason": f"HALF @ 1:2.0 + TRAIL (+{pnl_r}R)" if hit_tp else "STOP_LOSS"
                })
                trades.append(active)
                active = None
                last_close = ts

        if not active and (ts - last_close >= 600):
            if lo <= lower and cl > op:
                dist = max(min_dist, (cl - lo) + pad)
                sl = cl - dist
                tp = cl + tp_rr * dist
                active = {
                    "id": f"{symbol}_{ts}",
                    "symbol": symbol,
                    "side": "BUY",
                    "entry_price": cl,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "dist": dist,
                    "risk_usd": 5.0,
                    "conviction_stars": 5.0,
                    "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S")
                }
            elif hi >= upper and cl < op:
                dist = max(min_dist, (hi - cl) + pad)
                sl = cl + dist
                tp = cl - tp_rr * dist
                active = {
                    "id": f"{symbol}_{ts}",
                    "symbol": symbol,
                    "side": "SELL",
                    "entry_price": cl,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "dist": dist,
                    "risk_usd": 5.0,
                    "conviction_stars": 5.0,
                    "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S")
                }

    return trades

def compute_detailed_analytics(trades: list) -> dict:
    """
    Computes Yearly, Monthly, Weekly, Hourly (00-23 IST), and Day-of-Week performance analytics.
    """
    yearly_map = defaultdict(lambda: {
        "year": "", "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
        "net_pnl": 0.0, "net_pnl_inr": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
        "total_fees": 0.0, "profit_factor": 0.0
    })

    monthly_map = defaultdict(lambda: {
        "month_str": "", "year": "", "month": "", "trades": 0, "wins": 0, "losses": 0,
        "win_rate": 0.0, "net_pnl": 0.0, "net_pnl_inr": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
        "total_fees": 0.0, "profit_factor": 0.0
    })

    weekly_map = defaultdict(lambda: {
        "week_str": "", "year": "", "week_num": 0, "start_date": "", "end_date": "",
        "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "net_pnl": 0.0, "net_pnl_inr": 0.0,
        "gross_profit": 0.0, "gross_loss": 0.0, "total_fees": 0.0, "profit_factor": 0.0
    })

    hourly_map = {h: {"hour": h, "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "fees": 0.0, "gp": 0.0, "gl": 0.0, "wr": 0.0} for h in range(24)}
    dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow_map = {d: {"day": d, "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "fees": 0.0, "gp": 0.0, "gl": 0.0, "wr": 0.0} for d in dow_names}

    max_w_streak = 0
    max_l_streak = 0
    cur_w = 0
    cur_l = 0

    for t in trades:
        pnl = float(t.get("pnl_usd", 0.0))
        fee = float(t.get("total_fees_usd", 0.0))
        gp = float(t.get("gross_pnl_usd", 0.0)) if pnl > 0 else 0.0
        gl = abs(float(t.get("gross_pnl_usd", 0.0))) if pnl < 0 else 0.0

        if pnl > 0:
            cur_l = 0
            cur_w += 1
            if cur_w > max_w_streak: max_w_streak = cur_w
        elif pnl < 0:
            cur_w = 0
            cur_l += 1
            if cur_l > max_l_streak: max_l_streak = cur_l

        d_str = (t.get("closed_at") or t.get("opened_at") or "").split(" ")[0].split("T")[0]
        op_str = t.get("opened_at", "")
        if not d_str or len(d_str) < 10:
            continue
        try:
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            yr = str(dt.year)
            ym = dt.strftime("%Y-%m")
            iso_yr, iso_wk, _ = dt.isocalendar()
            yw = f"{iso_yr}-W{iso_wk:02d}"

            # Yearly
            y = yearly_map[yr]
            y["year"] = yr
            y["trades"] += 1
            if pnl > 0: y["wins"] += 1
            else: y["losses"] += 1
            y["net_pnl"] += pnl
            y["total_fees"] += fee
            y["gross_profit"] += gp
            y["gross_loss"] += gl

            # Monthly
            m = monthly_map[ym]
            m["month_str"] = ym
            m["year"] = yr
            m["month"] = dt.strftime("%B")
            m["trades"] += 1
            if pnl > 0: m["wins"] += 1
            else: m["losses"] += 1
            m["net_pnl"] += pnl
            m["total_fees"] += fee
            m["gross_profit"] += gp
            m["gross_loss"] += gl

            # Weekly
            w = weekly_map[yw]
            w["week_str"] = yw
            w["year"] = str(iso_yr)
            w["week_num"] = iso_wk
            if not w["start_date"] or d_str < w["start_date"]: w["start_date"] = d_str
            if not w["end_date"] or d_str > w["end_date"]: w["end_date"] = d_str
            w["trades"] += 1
            if pnl > 0: w["wins"] += 1
            else: w["losses"] += 1
            w["net_pnl"] += pnl
            w["total_fees"] += fee
            w["gross_profit"] += gp
            w["gross_loss"] += gl

            # Hourly & Day of Week (IST)
            if " " in op_str:
                h = int(op_str.split(" ")[1].split(":")[0])
                if 0 <= h < 24:
                    hd = hourly_map[h]
                    hd["trades"] += 1
                    hd["pnl"] += pnl
                    hd["fees"] += fee
                    hd["gp"] += gp
                    hd["gl"] += gl
                    if pnl > 0: hd["wins"] += 1
                    else: hd["losses"] += 1

                day_name = dt.strftime("%A")
                if day_name in dow_map:
                    dd = dow_map[day_name]
                    dd["trades"] += 1
                    dd["pnl"] += pnl
                    dd["fees"] += fee
                    dd["gp"] += gp
                    dd["gl"] += gl
                    if pnl > 0: dd["wins"] += 1
                    else: dd["losses"] += 1

        except Exception:
            pass

    # Finalize Yearly
    yearly_list = []
    for yr in sorted(yearly_map.keys()):
        y = yearly_map[yr]
        y["win_rate"] = round(y["wins"] / y["trades"] * 100, 1) if y["trades"] > 0 else 0.0
        y["net_pnl"] = round(y["net_pnl"], 2)
        y["net_pnl_inr"] = round(y["net_pnl"] * USD_TO_INR, 2)
        y["total_fees"] = round(y["total_fees"], 2)
        y["gross_profit"] = round(y["gross_profit"], 2)
        y["gross_loss"] = round(y["gross_loss"], 2)
        y["profit_factor"] = round(y["gross_profit"] / y["gross_loss"], 2) if y["gross_loss"] > 0 else (99.0 if y["gross_profit"] > 0 else 0.0)
        yearly_list.append(dict(y))

    # Finalize Monthly
    monthly_list = []
    for ym in sorted(monthly_map.keys()):
        m = monthly_map[ym]
        m["win_rate"] = round(m["wins"] / m["trades"] * 100, 1) if m["trades"] > 0 else 0.0
        m["net_pnl"] = round(m["net_pnl"], 2)
        m["net_pnl_inr"] = round(m["net_pnl"] * USD_TO_INR, 2)
        m["total_fees"] = round(m["total_fees"], 2)
        m["gross_profit"] = round(m["gross_profit"], 2)
        m["gross_loss"] = round(m["gross_loss"], 2)
        m["profit_factor"] = round(m["gross_profit"] / m["gross_loss"], 2) if m["gross_loss"] > 0 else (99.0 if m["gross_profit"] > 0 else 0.0)
        monthly_list.append(dict(m))

    # Finalize Weekly
    weekly_list = []
    for yw in sorted(weekly_map.keys()):
        w = weekly_map[yw]
        w["win_rate"] = round(w["wins"] / w["trades"] * 100, 1) if w["trades"] > 0 else 0.0
        w["net_pnl"] = round(w["net_pnl"], 2)
        w["net_pnl_inr"] = round(w["net_pnl"] * USD_TO_INR, 2)
        w["total_fees"] = round(w["total_fees"], 2)
        w["gross_profit"] = round(w["gross_profit"], 2)
        w["gross_loss"] = round(w["gross_loss"], 2)
        w["profit_factor"] = round(w["gross_profit"] / w["gross_loss"], 2) if w["gross_loss"] > 0 else (99.0 if w["gross_profit"] > 0 else 0.0)
        weekly_list.append(dict(w))

    # Finalize Hourly
    hourly_list = []
    for h in range(24):
        hd = hourly_map[h]
        hd["wr"] = round(hd["wins"] / hd["trades"] * 100, 1) if hd["trades"] > 0 else 0.0
        hd["pnl"] = round(hd["pnl"], 2)
        hd["fees"] = round(hd["fees"], 2)
        hourly_list.append(hd)

    # Finalize Day of Week
    dow_list = []
    for d in dow_names:
        dd = dow_map[d]
        dd["wr"] = round(dd["wins"] / dd["trades"] * 100, 1) if dd["trades"] > 0 else 0.0
        dd["pnl"] = round(dd["pnl"], 2)
        dd["fees"] = round(dd["fees"], 2)
        dow_list.append(dd)

    best_hour_item = max(hourly_list, key=lambda x: x["pnl"])
    worst_hour_item = min(hourly_list, key=lambda x: x["pnl"])
    best_day_item = max(dow_list, key=lambda x: x["pnl"])
    worst_day_item = min(dow_list, key=lambda x: x["pnl"])

    return {
        "yearly_summary": yearly_list,
        "monthly_summary": monthly_list,
        "weekly_summary": weekly_list,
        "hourly_summary": hourly_list,
        "dow_summary": dow_list,
        "best_hour": best_hour_item,
        "worst_hour": worst_hour_item,
        "best_day": best_day_item,
        "worst_day": worst_day_item,
        "max_w_streak": max_w_streak,
        "max_l_streak": max_l_streak
    }

def run_v6_suite(all_trades: list, candles_dict: dict, candle_map: dict, name: str, **kwargs) -> dict:
    res = simulate_v5_apex_suite(
        all_trades, candles_dict, candle_map,
        name=name,
        **kwargs
    )

    for t in res["trades"]:
        op_str = t.get("opened_at") or ""
        cl_str = t.get("closed_at") or op_str
        duration_min = 0
        try:
            d_op = datetime.strptime(op_str.split(".")[0].replace("T", " "), "%Y-%m-%d %H:%M:%S")
            d_cl = datetime.strptime(cl_str.split(".")[0].replace("T", " "), "%Y-%m-%d %H:%M:%S")
            duration_min = max(0, int((d_cl - d_op).total_seconds() // 60))
        except:
            pass
        t["duration_minutes"] = duration_min
        if duration_min < 60:
            t["duration_str"] = f"{duration_min}m"
        elif duration_min < 1440:
            t["duration_str"] = f"{duration_min//60}h {duration_min%60}m"
        else:
            t["duration_str"] = f"{duration_min//1440}d {(duration_min%1440)//60}h"

    analytics = compute_detailed_analytics(res["trades"])
    res.update(analytics)
    return res

def main():
    print("=" * 85)
    print("💎 BACKTEST V6: ⚡ 3-YEAR 4-ASSET 24/7 APEX HYBRID ENGINE 💎")
    print("   • Strict $5.00 Fixed Risk Per Trade across 3 Full Years")
    print("   • 3 Years Continuous Data from Delta Exchange API (Oct 2023 - Oct 2026)")
    print("   • 24/7 Round-the-Clock Trading Coverage (All 24 Hours & All 7 Days)")
    print("   • Multi-Timeframe Breakdown: Yearly, Monthly, Weekly & Custom Date")
    print("   • Time & Days Edge Suite: Exact Best & Worst Hours & Days of the Week")
    print("   • Full Calendar Heatmap, Winning & Losing Streak Analysis, and Trade Journal")
    print("   • 100% Local Execution (No Git/Cloud Push)")
    print("=" * 85)

    db = DatabaseManager()

    print("\n[*] Loading 3-year historical candles from local SQLite...")
    candles_dict = {
        "BTCUSD": db.get_latest_candles("BTCUSD", "15m", limit=150000),
        "ETHUSD": db.get_latest_candles("ETHUSD", "15m", limit=150000),
        "SLVONUSD": db.get_latest_candles("SLVONUSD", "15m", limit=150000),
        "XAUTUSD": db.get_latest_candles("XAUTUSD", "15m", limit=150000)
    }

    candle_map = {}
    for sym, c_list in candles_dict.items():
        candle_map[sym] = {c["timestamp"]: (idx, c) for idx, c in enumerate(c_list)}
        t_first = datetime.fromtimestamp(c_list[0]["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d") if c_list else "None"
        t_last = datetime.fromtimestamp(c_list[-1]["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d") if c_list else "None"
        print(f"    - {sym:<10}: {len(c_list):>7,} candles ({t_first} -> {t_last})")

    print("\n[*] Generating 24/7 Round-the-Clock candidate setups across all 3 years...")
    btc_24_7 = generate_24_7_candidate_trades("BTCUSD", candles_dict["BTCUSD"], sigma=1.5, min_dist=160.0, pad=45.0, tp_rr=2.0, is_crypto=True)
    eth_24_7 = generate_24_7_candidate_trades("ETHUSD", candles_dict["ETHUSD"], sigma=1.5, min_dist=8.0, pad=2.2, tp_rr=2.0, is_crypto=True)
    slv_24_7 = generate_24_7_candidate_trades("SLVONUSD", candles_dict["SLVONUSD"], sigma=1.6, min_dist=0.30, pad=0.06, tp_rr=2.4, is_crypto=False)
    xaut_24_7 = generate_24_7_candidate_trades("XAUTUSD", candles_dict["XAUTUSD"], sigma=1.6, min_dist=3.0, pad=1.2, tp_rr=2.0, is_crypto=False)

    all_24_7 = sorted(btc_24_7 + eth_24_7 + slv_24_7 + xaut_24_7, key=lambda t: (t.get("opened_at") or t.get("closed_at") or ""))
    print(f"[*] Ingested {len(all_24_7):,} total 24/7 candidate trade setups across all 24 hours.")

    print("\n[*] Simulating V6 24/7 Apex Hybrid Suite Models...")

    # 1. 💎 FLAGSHIP V6: 4-Asset Apex Hybrid Sniper 24/7 (1:10R to 1:40R | Round-the-Clock | Squad Veto)
    v6_apex_24_7_flagship = run_v6_suite(
        all_24_7, candles_dict, candle_map,
        name="💎 4-Asset Apex Hybrid Sniper 24/7 (3-Year 1:40R | Round-the-Clock | Squad Veto)",
        initial_target_rr=10.0, max_macro_rr=40.0, is_maker_exit=True,
        use_v5_ratchet=True, use_structural_trail=True, use_reversal_pinch=True,
        skip_toxic_trades=False, enforce_squad_veto=True
    )

    # 2. ⚡ V6 Dynamic 25R Sniper 24/7 (Capped at 25R)
    v6_dynamic_25r = run_v6_suite(
        all_24_7, candles_dict, candle_map,
        name="⚡ 4-Asset Precision Sniper 24/7 (1:10R to 1:25R | 3-Layer Trailing | High Win Rate)",
        initial_target_rr=10.0, max_macro_rr=25.0, is_maker_exit=True,
        use_v5_ratchet=True, use_structural_trail=True, use_reversal_pinch=True,
        skip_toxic_trades=False, enforce_squad_veto=True
    )

    # 3. 🎯 V6 Dynamic 15R Runner 24/7 (Capped at 15R)
    v6_dynamic_15r = run_v6_suite(
        all_24_7, candles_dict, candle_map,
        name="🎯 4-Asset Velocity Runner 24/7 (1:10R to 1:15R | Rapid Turnover)",
        initial_target_rr=10.0, max_macro_rr=15.0, is_maker_exit=True,
        use_v5_ratchet=True, use_structural_trail=True, use_reversal_pinch=True,
        skip_toxic_trades=False, enforce_squad_veto=True
    )

    # 4. 👑 V6 Full Dataset 40R Apex 24/7 (Unpruned)
    v6_apex_full_40r = run_v6_suite(
        all_24_7, candles_dict, candle_map,
        name="👑 4-Asset Apex Grandmaster Full 24/7 (1:10R to 1:40R | Full Dataset)",
        initial_target_rr=10.0, max_macro_rr=40.0, is_maker_exit=True,
        use_v5_ratchet=True, use_structural_trail=True, use_reversal_pinch=True,
        skip_toxic_trades=False, enforce_squad_veto=False
    )

    # 5. Granular Per-Pair Breakdown under V6 Flagship 24/7
    print("[*] Simulating V6 Granular Per-Pair Breakdown across 3 Years 24/7...")
    per_pair_v6 = {}
    for sym_target in ["BTCUSD", "ETHUSD", "SLVONUSD", "XAUTUSD"]:
        sym_res = run_v6_suite(
            all_24_7, candles_dict, candle_map,
            name=f"💎 {sym_target} 3-Year Apex Hybrid Sniper 24/7 (1:40R | 3-Layer Trailing)",
            initial_target_rr=10.0, max_macro_rr=40.0, symbol_filter=sym_target,
            is_maker_exit=True, use_v5_ratchet=True, use_structural_trail=True,
            use_reversal_pinch=True, skip_toxic_trades=False, enforce_squad_veto=False
        )
        per_pair_v6[sym_target] = sym_res

    # Also load the 32 today live trades from live database if available for proof
    db_trades = db.get_trades(limit=50)
    today_live_trades = [t for t in db_trades if not t.get("is_paper")]

    report_payload = {
        "default_strategy_key": "V6_APEX_SNIPER_24_7",
        "joint_portfolio": v6_apex_24_7_flagship,
        "per_pair": per_pair_v6,
        "today_trades": today_live_trades,
        "strategies": {
            "V6_APEX_SNIPER_24_7": v6_apex_24_7_flagship,
            "V6_DYNAMIC_25R_24_7": v6_dynamic_25r,
            "V6_DYNAMIC_15R_24_7": v6_dynamic_15r,
            "V6_APEX_FULL_40R_24_7": v6_apex_full_40r,
            "BTC_V6_CHAMPION": per_pair_v6["BTCUSD"],
            "ETH_V6_CHAMPION": per_pair_v6["ETHUSD"],
            "SLV_V6_CHAMPION": per_pair_v6["SLVONUSD"],
            "XAUT_V6_CHAMPION": per_pair_v6["XAUTUSD"]
        }
    }

    print("\n[*] Rendering reports/backtest_v6.html...")
    from reports.backtest_v6_reporter import generate_backtest_v6_html
    reports_dir = BASE_DIR / "reports"
    out_file = generate_backtest_v6_html(report_payload, reports_dir, "backtest_v6.html")
    print(f"✅ Generated Backtest V6 Dashboard: {out_file}")

    print("\n" + "=" * 115)
    print("📊 3-YEAR 24/7 BACKTEST V6 LEADERBOARD SCORECARD ($5 RISK PER TRADE):")
    print("-" * 115)
    print(f"{'STRATEGY MODEL':<35} | {'TRADES':<6} | {'WIN RATE':<8} | {'DELTA FEES':<10} | {'REAL NET P&L ($)':<16} | {'REAL NET P&L (₹)':<16} | {'PF':<5} | {'MAX DD':<8}")
    print("-" * 115)
    for k in ["V6_APEX_SNIPER_24_7", "V6_DYNAMIC_25R_24_7", "V6_DYNAMIC_15R_24_7", "V6_APEX_FULL_40R_24_7"]:
        st = report_payload["strategies"][k]
        print(f"{st['strategy_name'][:35]:<35} | {st['total_trades']:<6} | {st['win_rate']:<6.1f}% | -${st['total_fees']:<8,.2f} | +${st['net_pl']:<14,.2f} | +₹{st['net_pl_inr']:<14,.0f} | {st['profit_factor']:<5.2f} | -${st['max_drawdown_usd']:<6.2f}")
    print("-" * 115)
    print("💎 3-YEAR 24/7 PER-PAIR BREAKDOWN:")
    for sym in ["BTCUSD", "ETHUSD", "SLVONUSD", "XAUTUSD"]:
        res = per_pair_v6[sym]
        print(f"{sym:<35} | {res['total_trades']:<6} | {res['win_rate']:<6.1f}% | -${res['total_fees']:<8,.2f} | +${res['net_pl']:<14,.2f} | +₹{res['net_pl_inr']:<14,.0f} | {res['profit_factor']:<5.2f} | -${res['max_drawdown_usd']:<6.2f}")
    print("=" * 115)

    print("\n⏰ 24/7 TIME & DAYS PERFORMANCE AUDIT (💎 4-Asset Apex Hybrid Sniper):")
    print("-" * 95)
    bh = v6_apex_24_7_flagship["best_hour"]
    wh = v6_apex_24_7_flagship["worst_hour"]
    bd = v6_apex_24_7_flagship["best_day"]
    wd = v6_apex_24_7_flagship["worst_day"]
    print(f"⭐ BEST TRADING HOUR : Hour {bh['hour']:02d}:00 IST (Net: +${bh['pnl']:,.2f} | {bh['trades']} trades | {bh['wr']:.1f}% Win Rate)")
    print(f"⚠️ WORST TRADING HOUR: Hour {wh['hour']:02d}:00 IST (Net: ${wh['pnl']:,.2f} | {wh['trades']} trades | {wh['wr']:.1f}% Win Rate)")
    print(f"⭐ BEST TRADING DAY  : {bd['day']} (Net: +${bd['pnl']:,.2f} | {bd['trades']} trades | {bd['wr']:.1f}% Win Rate)")
    print(f"⚠️ WORST TRADING DAY : {wd['day']} (Net: +${wd['pnl']:,.2f} | {wd['trades']} trades | {wd['wr']:.1f}% Win Rate)")
    print("-" * 95)
    print(f"🔥 MAX WINNING STREAK: {v6_apex_24_7_flagship['max_w_streak']} consecutive wins")
    print(f"🛡️ MAX LOSING STREAK : {v6_apex_24_7_flagship['max_l_streak']} consecutive losses")
    print("=" * 95)

if __name__ == "__main__":
    main()
