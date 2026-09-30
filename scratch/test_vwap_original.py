import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("BTCUSD", "15m", limit=35000)

print(f"Loaded {len(candles)} BTC candles")

def run_pure_vwap_reversion(candles, sigma_entry=1.5, tp_vwap_rr=2.0, min_rr=2.0):
    c_val = 0.001
    decimals = 1
    min_scalp_dist = 220.0
    scalp_pad = 100.0
    capital = 50.0
    initial_capital = 50.0
    trades = []
    active = None
    last_close_ts = -999999999.0
    maker_fee = 0.0001

    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []

    for i in range(50, len(candles)):
        c = candles[i]
        curr = float(c["close"])
        ts = c["timestamp"]
        bt = datetime.fromtimestamp(ts)
        hm = bt.strftime("%H:%M")

        # Session filter
        if not ("12:30" <= hm <= "23:45"):
            continue

        d_str = bt.strftime("%Y-%m-%d")
        typ = (float(c["high"]) + float(c["low"]) + curr) / 3.0
        v = max(1.0, float(c.get("volume", 1.0)))

        if d_str != current_day:
            current_day = d_str
            day_cum_vol = 0.0
            day_cum_pv = 0.0
            day_prices = []

        day_cum_vol += v
        day_cum_pv += (typ * v)
        day_prices.append(typ)
        vwap = day_cum_pv / day_cum_vol
        stdev = max(40.0, (sum((x - (sum(day_prices)/len(day_prices)))**2 for x in day_prices)/len(day_prices))**0.5)

        upper_band = vwap + sigma_entry * stdev
        lower_band = vwap - sigma_entry * stdev

        if active:
            side = active["side"]
            entry = active["entry_price"]
            dist = active["dist"]
            lots = active["lots"]

            hit_sl = False
            hit_tp = False
            hit_vwap = False

            if side == "BUY":
                if float(c["low"]) <= active["sl"]:
                    hit_sl = True
                elif float(c["high"]) >= round(entry + min_rr * dist, decimals):
                    hit_tp = True
                elif float(c["high"]) >= vwap and vwap > entry:
                    hit_vwap = True
            else: # SELL
                if float(c["high"]) >= active["sl"]:
                    hit_sl = True
                elif float(c["low"]) <= round(entry - min_rr * dist, decimals):
                    hit_tp = True
                elif float(c["low"]) <= vwap and vwap < entry:
                    hit_vwap = True

            if hit_sl or hit_tp or hit_vwap:
                if hit_tp:
                    exit_p = round(entry + min_rr * dist if side == "BUY" else entry - min_rr * dist, decimals)
                    reason = "TAKE_PROFIT"
                elif hit_vwap:
                    exit_p = round(vwap, decimals)
                    reason = "VWAP REVERSION"
                else:
                    exit_p = active["sl"]
                    reason = "SL"

                diff = (exit_p - entry) if side == "BUY" else (entry - exit_p)
                pnl = round((lots * c_val * diff) - (lots * c_val * exit_p * maker_fee * 2), 2)
                capital += pnl
                rr = round(diff / dist, 1)

                active.update({
                    "exit_price": exit_p,
                    "pnl_usd": pnl,
                    "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S"),
                    "close_reason": reason,
                    "rr_achieved": rr
                })
                trades.append(active)
                active = None
                last_close_ts = float(c["timestamp"])
                continue

        # Check entry
        time_since_close = float(c["timestamp"]) - last_close_ts
        if not active and time_since_close >= 600.0 and len(day_prices) >= 8:
            delta = float(c.get("delta", 0.0))
            delta_ratio = delta / v

            p1 = candles[i-1]
            p2 = candles[i-2] if i >= 2 else p1
            prev_bear_cascade = (float(p1["close"]) < float(p1["open"])) and (float(p2["close"]) < float(p2["open"]))
            prev_bull_cascade = (float(p1["close"]) > float(p1["open"])) and (float(p2["close"]) > float(p2["open"]))

            bar_range = max(0.01, float(c["high"]) - float(c["low"]))
            lower_wick = (min(float(c["open"]), curr) - float(c["low"])) / bar_range
            upper_wick = (float(c["high"]) - max(float(c["open"]), curr)) / bar_range

            buy_confirmed = (curr > float(c["open"])) or (lower_wick >= 0.28 and curr >= float(c["low"]) + 0.40 * bar_range)
            buy_not_knife = not (prev_bear_cascade and curr < float(c["open"]) and lower_wick < 0.35)

            sell_confirmed = (curr < float(c["open"])) or (upper_wick >= 0.28 and curr <= float(c["high"]) - 0.40 * bar_range)
            sell_not_spike = not (prev_bull_cascade and curr > float(c["open"]) and upper_wick < 0.35)

            is_buy = (float(c["low"]) <= lower_band) and buy_confirmed and buy_not_knife and (delta_ratio >= -0.05)
            is_sell = (float(c["high"]) >= upper_band) and sell_confirmed and sell_not_spike and (delta_ratio <= 0.05)

            if is_buy or is_sell:
                sub = candles[max(0, i-8):i]
                side = "BUY" if is_buy else "SELL"
                if is_buy:
                    sw_low = min(float(x["low"]) for x in sub)
                    dist = max(min_scalp_dist, (curr - sw_low) + scalp_pad)
                    sl = round(curr - dist, decimals)
                else:
                    sw_high = max(float(x["high"]) for x in sub)
                    dist = max(min_scalp_dist, (sw_high - curr) + scalp_pad)
                    sl = round(curr + dist, decimals)

                trade_risk = 5.0
                lots = max(2, int(round(trade_risk / (dist * c_val))))
                active = {
                    "side": side,
                    "entry_price": curr,
                    "sl": sl,
                    "dist": dist,
                    "lots": lots,
                    "opened_at": bt.strftime("%Y-%m-%d %H:%M:%S")
                }

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    gp = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    net = round(capital - initial_capital, 2)
    pf = round(gp / gl, 2) if gl else 99.0
    print(f"RESULT: Trades: {len(trades)}, WR: {wr:.1f}%, GP: +${gp:,.2f}, GL: -${gl:,.2f}, NET: ${net:<+10.2f}, PF: {pf:.2f}")

run_pure_vwap_reversion(candles)
