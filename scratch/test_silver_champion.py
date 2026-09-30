import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
silver_candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)

def test_silver_model(
    candles,
    tp1_rr=1.8,
    max_rr=4.5,
    trail_mult=1.1,
    del_th=0.035,
    min_dist=0.30,
    dist_pad=0.06,
    bad_hours=None,
    require_absorption=False
):
    if bad_hours is None:
        bad_hours = {16, 18, 19, 23}

    contract_val = 1.0
    maker_fee = 0.0001
    fixed_risk = 5.0
    capital = 50.0

    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trade = None

    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []
    day_trades_count = defaultdict(int)

    for i in range(50, len(candles)):
        c = candles[i]
        curr = c["close"]
        ts = c["timestamp"]
        bar_time = datetime.fromtimestamp(ts)

        if bar_time.weekday() in (5, 6):
            continue

        hm = bar_time.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue

        day_str = bar_time.strftime("%Y-%m-%d")
        typ_p = (c["high"] + c["low"] + c["close"]) / 3.0
        v = max(1.0, c.get("volume", 1.0))

        if day_str != current_day:
            current_day = day_str
            day_cum_vol = 0.0
            day_cum_pv = 0.0
            day_prices = []

        day_cum_vol += v
        day_cum_pv += (typ_p * v)
        day_prices.append(typ_p)
        vwap = day_cum_pv / day_cum_vol
        mean_p = sum(day_prices) / len(day_prices)
        variance = sum((p - mean_p)**2 for p in day_prices) / len(day_prices)
        stdev = max(0.1, variance**0.5)

        upper_vwap = vwap + (1.8 * stdev)
        lower_vwap = vwap - (1.8 * stdev)

        # Active trade management
        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half_lots = max(1, lots // 2)

            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist

                # Scale out 50%
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_rr * dist, 3)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven + buffer
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 3))

                # Dynamic Trailing
                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["highest"] - (trail_mult * dist), 3)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_rr * dist, 3)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_rr * dist, 3) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((exit_price - entry) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_rr * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(active_trade)
                    day_trades_count[day_str] += 1
                    active_trade = None
                    continue

            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                # Scale out 50%
                if not active_trade["tp1_hit"] and gain_r >= tp1_rr:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - tp1_rr * dist, 3)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 3))

                # Dynamic Trailing
                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["lowest"] + (trail_mult * dist), 3)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_rr * dist, 3)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_rr * dist, 3) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((entry - exit_price) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_rr * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_rr} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(active_trade)
                    day_trades_count[day_str] += 1
                    active_trade = None
                    continue

        # Entry logic
        if not active_trade and (bar_time.hour not in bad_hours):
            sub = candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            # Alpha 1: 8-bar Micro Sweep
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_th)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_th)

            # Alpha 2: VWAP Bands Reversion
            vwap_buy = (len(day_prices) >= 4) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= del_th)
            vwap_sell = (len(day_prices) >= 4) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -del_th)

            # Alpha 3: Footprint Delta Absorption
            absorb_buy = (c["low"] <= lo12 * 1.0003) and (delta_ratio >= del_th * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9997) and (delta_ratio <= -del_th * 0.8) and (c["close"] < c["open"])

            # 100 EMA
            if i >= 100:
                ema100 = sum(x["close"] for x in candles[i-100:i]) / 100.0
                macro_bull = (curr > ema100)
                macro_bear = (curr < ema100)
            else:
                macro_bull = macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and (sweep_buy or absorb_buy))])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and (sweep_sell or absorb_sell))])

            if require_absorption:
                is_buy = (absorb_buy or (sweep_buy and vwap_buy)) and (sell_score == 0)
                is_sell = (absorb_sell or (sweep_sell and vwap_sell)) and (buy_score == 0)
            else:
                is_buy = (buy_score >= 1) and (sell_score == 0)
                is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                side = "BUY" if is_buy else "SELL"
                dist = max(min_dist, abs(curr - (c["low"] if is_buy else c["high"])) + dist_pad)
                sl_price = round(curr - dist if is_buy else curr + dist, 3)
                lots = max(2, int(round(fixed_risk / (dist * contract_val))))
                notional = lots * contract_val * curr

                active_trade = {
                    "id": f"SLV_{c['timestamp']}",
                    "symbol": "SLVONUSD",
                    "side": side,
                    "entry_price": curr,
                    "stop_loss": sl_price,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "notional_usd": round(notional, 2),
                    "risk_usd": fixed_risk,
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S")
                }

    if not trades:
        return None

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    wr = len(wins) / len(trades) * 100
    net = capital - 50.0
    gp = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    pf = (gp / gl) if gl > 0 else float("inf")
    peak = 50.0
    dd = 0.0
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak: peak = eq
        if peak - eq > dd: dd = peak - eq

    return {
        "trades": len(trades),
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "net": round(net, 2),
        "dd": round(dd, 2)
    }

print("Running parameter tests for Silver Master Strategy...")
configs = [
    {"tp1": 1.5, "max_rr": 3.5, "trail": 1.0, "del": 0.03, "min_d": 0.30, "bad": {16, 18, 19, 23}, "abs": False},
    {"tp1": 1.8, "max_rr": 4.0, "trail": 1.1, "del": 0.03, "min_d": 0.30, "bad": {16, 18, 19, 23}, "abs": False},
    {"tp1": 2.0, "max_rr": 4.5, "trail": 1.1, "del": 0.03, "min_d": 0.30, "bad": {16, 18, 19, 23}, "abs": False},
    {"tp1": 2.0, "max_rr": 4.5, "trail": 1.1, "del": 0.03, "min_d": 0.35, "bad": {16, 18, 19, 23}, "abs": False},
    {"tp1": 1.8, "max_rr": 4.0, "trail": 1.1, "del": 0.03, "min_d": 0.30, "bad": {16, 18, 19, 23}, "abs": True},
    {"tp1": 2.0, "max_rr": 4.5, "trail": 1.2, "del": 0.03, "min_d": 0.30, "bad": {16, 18, 19, 23}, "abs": True},
    {"tp1": 2.0, "max_rr": 4.5, "trail": 1.2, "del": 0.03, "min_d": 0.35, "bad": {16, 18, 19, 23}, "abs": True},
    {"tp1": 2.0, "max_rr": 4.0, "trail": 1.0, "del": 0.035, "min_d": 0.30, "bad": {16, 18, 19, 23}, "abs": False},
    {"tp1": 2.2, "max_rr": 4.5, "trail": 1.1, "del": 0.035, "min_d": 0.30, "bad": {16, 18, 19, 23}, "abs": False},
    {"tp1": 2.5, "max_rr": 5.0, "trail": 1.2, "del": 0.035, "min_d": 0.30, "bad": {16, 18, 19, 23}, "abs": False},
]

for cfg in configs:
    r = test_silver_model(silver_candles, tp1_rr=cfg["tp1"], max_rr=cfg["max_rr"], trail_mult=cfg["trail"], del_th=cfg["del"], min_dist=cfg["min_d"], bad_hours=cfg["bad"], require_absorption=cfg["abs"])
    if r:
        print(f"TP1=1:{cfg['tp1']} Max={cfg['max_rr']}R Trail={cfg['trail']}x MinD=${cfg['min_d']} Abs={cfg['abs']} | Trades={r['trades']:3d} | WR={r['wr']:4.1f}% | PF={r['pf']:4.2f} | Net=${r['net']:+7.2f} | DD=-${r['dd']:5.2f}")
