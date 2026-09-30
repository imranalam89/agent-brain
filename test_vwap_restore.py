import sys
from datetime import datetime
from data.database import DatabaseManager

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db = DatabaseManager()

def test_vwap_maximizer(symbol, candles, sigma=1.5, tp1_rr=2.0, trail_be_r=1.0):
    p = {
        "c_val": 0.001 if "BTC" in symbol else 0.01,
        "min_dist": 220.0 if "BTC" in symbol else 12.0,
        "pad": 100.0 if "BTC" in symbol else 5.0,
        "decimals": 1 if "BTC" in symbol else 2
    }
    c_val = p["c_val"]
    min_dist = p["min_dist"]
    pad = p["pad"]
    decimals = p["decimals"]

    capital = 50.0
    trades = []
    active = None
    last_close_ts = -999999999.0

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
        if not ("12:30" <= hm <= "23:45"):
            continue

        day_str = bt.strftime("%Y-%m-%d")
        typ_p = (float(c["high"]) + float(c["low"]) + curr) / 3.0
        v = max(1.0, float(c.get("volume", 1.0)))

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
        variance = sum((x - mean_p)**2 for x in day_prices) / len(day_prices)
        stdev = max(1.0, variance**0.5)

        upper_band = vwap + (sigma * stdev)
        lower_band = vwap - (sigma * stdev)

        if active:
            side = active["side"]
            entry = active["entry_price"]
            dist = active["dist"]
            lots = active["lots"]
            half = max(1, lots // 2)

            gain_r = (float(c["high"]) - entry) / dist if side == "BUY" else (entry - float(c["low"])) / dist

            # Partial cut @ tp1_rr + BE lock
            if not active["tp1_hit"] and gain_r >= tp1_rr:
                active["tp1_hit"] = True
                pnl_half = (half * c_val * tp1_rr * dist) - (half * c_val * (entry + tp1_rr*dist) * 0.0001 * 2)
                active["booked_pnl"] = pnl_half
                capital += pnl_half
                # Move SL to BE + 0.10R
                active["sl"] = round(entry + 0.10 * dist, decimals) if side == "BUY" else round(entry - 0.10 * dist, decimals)

            # Check VWAP Reversion Exit
            reverted_to_vwap = (float(c["high"]) >= vwap) if side == "BUY" else (float(c["low"]) <= vwap)
            hit_sl = (float(c["low"]) <= active["sl"]) if side == "BUY" else (float(c["high"]) >= active["sl"])

            if reverted_to_vwap or hit_sl:
                exit_price = vwap if reverted_to_vwap else active["sl"]
                rem_lots = (lots - half) if active["tp1_hit"] else lots
                gain = (exit_price - entry) if side == "BUY" else (entry - exit_price)
                rem_pnl = (rem_lots * c_val * gain) - (rem_lots * c_val * exit_price * 0.0001 * 2)
                total_pnl = round(active.get("booked_pnl", 0.0) + rem_pnl, 2)
                capital += rem_pnl

                reason = "VWAP REVERSION" if reverted_to_vwap else ("BE_LOCK" if active["tp1_hit"] else "SL")
                active.update({
                    "exit_price": exit_price,
                    "pnl_usd": total_pnl,
                    "close_reason": reason,
                    "closed_at": bt.strftime("%Y-%m-%d %H:%M:%S")
                })
                trades.append(active)
                active = None
                last_close_ts = float(c["timestamp"])
                continue

        # Entry logic
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
                recent = candles[max(0, i-8):i]
                if is_buy:
                    sw_low = min(float(x["low"]) for x in recent)
                    dist = max(min_dist, (curr - sw_low) + pad)
                    sl = round(curr - dist, decimals)
                else:
                    sw_high = max(float(x["high"]) for x in recent)
                    dist = max(min_dist, (sw_high - curr) + pad)
                    sl = round(curr + dist, decimals)

                side = "BUY" if is_buy else "SELL"
                lots = max(2, int(round(5.0 / (dist * c_val))))

                active = {
                    "id": f"VW_{ts}",
                    "symbol": symbol,
                    "side": side,
                    "entry_price": curr,
                    "dist": dist,
                    "sl": sl,
                    "orig_sl": sl,
                    "lots": lots,
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "opened_at": bt.strftime("%Y-%m-%d %H:%M:%S")
                }

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    gp = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses))
    pf = gp / gl if gl > 0 else 99.0
    net = round(capital - 50.0, 2)
    wr = len(wins) / len(trades) * 100 if trades else 0.0

    print(f"{symbol} (sigma={sigma}, tp1_rr={tp1_rr}):")
    print(f"  Net: +${net:.2f} | WR: {wr:.1f}% ({len(wins)}W / {len(losses)}L) | PF: {pf:.2f} | Trades: {len(trades)}")
    return net, wr, pf

b_c = db.get_latest_candles("BTCUSD", "15m", 35000)
e_c = db.get_latest_candles("ETHUSD", "15m", 35000)

for s in [1.5, 1.6, 1.7, 1.8]:
    test_vwap_maximizer("BTCUSD", b_c, sigma=s, tp1_rr=2.0)
for s in [1.5, 1.6, 1.7, 1.8]:
    test_vwap_maximizer("ETHUSD", e_c, sigma=s, tp1_rr=2.0)
