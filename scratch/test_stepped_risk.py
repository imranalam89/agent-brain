import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)

print(f"Total candles loaded for Tiered Risk research: {len(candles)}")

def test_stepped_risk(
    base_risk=4.0,
    base_capital=50.0,
    scale_factor=0.5, # 50% risk increase per 100% capital increase
    mode="continuous" # "continuous" or "tier_steps"
):
    capital = base_capital
    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_trade = None
    maker_fee = 0.0001
    
    current_day = None
    day_cum_vol = 0.0
    day_cum_pv = 0.0
    day_prices = []

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
        stdev = max(1.0, variance**0.5)

        upper_vwap = vwap + (1.8 * stdev)
        lower_vwap = vwap - (1.8 * stdev)

        # Manage active trade
        if active_trade:
            side = active_trade["side"]
            entry = active_trade["entry_price"]
            dist = active_trade["dist"]
            lots = active_trade["lots"]
            half_lots = max(1, lots // 2)
            tp1_target = active_trade["tp1_rr"]
            max_target = active_trade["max_rr"]
            trail_mult = active_trade["trail_mult"]

            if side == "BUY":
                if c["high"] > active_trade["highest"]:
                    active_trade["highest"] = c["high"]
                gain_r = (active_trade["highest"] - entry) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1_target:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + tp1_target * dist, 2)
                    pnl_half = (half_lots * 0.001 * (tp1_p - entry)) - (half_lots * 0.001 * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.15 * dist, 2))

                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["highest"] - (trail_mult * dist), 2)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["low"] <= active_trade["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_target * dist, 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_target * dist, 2) if hit_tp else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((exit_price - entry) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_target * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_target} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(active_trade)
                    active_trade = None
                    continue
            else: # SELL
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                if not active_trade["tp1_hit"] and gain_r >= tp1_target:
                    active_trade["tp1_hit"] = True
                    tp1_price = round(entry - tp1_target * dist, 2)
                    pnl_half = (half_lots * 0.001 * (entry - tp1_price)) - (half_lots * 0.001 * tp1_price * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.15 * dist, 2))

                if active_trade["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(active_trade["lowest"] + (trail_mult * dist), 2)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                hit_sl = c["high"] >= active_trade["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_target * dist, 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_target * dist, 2) if hit_tp else active_trade["stop_loss"]
                    remaining_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (remaining_lots * 0.001 * diff) - (remaining_lots * 0.001 * exit_price * maker_fee * 2)
                    total_pnl = round(active_trade["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((entry - exit_price) / dist, 1) if not active_trade["tp1_hit"] else round((tp1_target * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    active_trade.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_target} + TRAIL (+{rr_final}R)" if active_trade["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(active_trade)
                    active_trade = None
                    continue

        # Check Entry Signal
        if not active_trade:
            sub = candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            # Alpha 1: 8-bar Micro Liquidity Sweep
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= 0.04)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -0.04)

            # Alpha 2: Session VWAP Bands Reversion
            vwap_buy = (len(day_prices) >= 6) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= 0.04)
            vwap_sell = (len(day_prices) >= 6) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -0.04)

            # Alpha 3: Footprint Delta Absorption
            absorb_buy = (c["low"] <= lo12 * 1.0002) and (delta_ratio >= 0.03) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9998) and (delta_ratio <= -0.03) and (c["close"] < c["open"])

            if i >= 200:
                ema200 = sum(x["close"] for x in candles[i-200:i]) / 200.0
                macro_bull = (curr > ema200)
                macro_bear = (curr < ema200)
            else:
                macro_bull = True
                macro_bear = True

            buy_score = sum([sweep_buy, vwap_buy, absorb_buy, (macro_bull and sweep_buy)])
            sell_score = sum([sweep_sell, vwap_sell, absorb_sell, (macro_bear and sweep_sell)])

            is_buy = (buy_score >= 1) and (sell_score == 0)
            is_sell = (sell_score >= 1) and (buy_score == 0)

            if is_buy or is_sell:
                score = buy_score if is_buy else sell_score
                is_high_conv = (score >= 2)

                tp1_target = 2.5 if is_high_conv else 1.5
                max_target = 5.0 if is_high_conv else 2.5
                trail_mult = 1.5 if is_high_conv else 1.2

                dist = max(2.5, abs(curr - (c["low"] if is_buy else c["high"])) + 0.6)
                sl_price = round(curr - dist if is_buy else curr + dist, 2)
                
                # USER'S CAPITAL STEPPED RISK LOGIC:
                # Base Capital = $50 -> Base Risk = $4.00
                # When capital increases by 100% ($50 -> $100), risk increases by 50% (e.g. $4 -> $6, or if base is $5 -> $7.50)
                if mode == "continuous":
                    capital_gain_ratio = max(0.0, (capital - base_capital) / base_capital)
                    risk_mult = 1.0 + (scale_factor * capital_gain_ratio)
                    risk_usd = round(base_risk * risk_mult, 2)
                elif mode == "tier_steps":
                    # Stepped ladder:
                    # $50 - $99: $4.00 (or base)
                    # $100 - $149: +50% -> $6.00 (or $7.00)
                    # $150 - $199: +100% -> $8.00
                    # $200+: +150% -> $10.00
                    tier = int(capital // 50) # 1 for $50-$99, 2 for $100-$149, 3 for $150-$199, etc.
                    steps_above_base = max(0, tier - 1)
                    risk_mult = 1.0 + (scale_factor * steps_above_base)
                    risk_usd = round(base_risk * risk_mult, 2)
                elif mode == "user_exact":
                    # Exact user quote: "when 50 will be 100 than risk increase to 7-8 dollar"
                    # That means:
                    # At $50 capital: $4.00 risk
                    # At $100 capital: $7.50 risk (+87.5% risk on +100% capital)
                    # At $150 capital: $11.00 risk
                    tier = int(capital // 50)
                    steps_above_base = max(0, tier - 1)
                    risk_usd = base_risk + (steps_above_base * 3.50)

                # Cap maximum risk to protect account
                risk_usd = min(risk_usd, 35.0)

                lots = max(2, int(round(risk_usd / (dist * 0.001))))

                active_trade = {
                    "id": f"APEX_{c['timestamp']}",
                    "side": "BUY" if is_buy else "SELL",
                    "entry_price": curr,
                    "stop_loss": sl_price,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "risk_usd": risk_usd,
                    "tp1_rr": tp1_target,
                    "max_rr": max_target,
                    "trail_mult": trail_mult,
                    "tp1_hit": False,
                    "booked_pnl": 0.0
                }

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    total = len(trades)
    wr = round((len(wins) / total * 100), 1) if total > 0 else 0.0
    gw = sum(t["pnl_usd"] for t in wins)
    gl = abs(sum(t["pnl_usd"] for t in losses)) if losses else 1.0
    pf = round(gw / gl, 2) if gl > 0 else 0.0
    net = round(capital - base_capital, 2)
    roi = round((net / base_capital) * 100, 1)

    peak = base_capital
    max_dd = 0.0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = peak - pt["equity"]
        if dd > max_dd:
            max_dd = dd

    print(
        f"Mode:{mode:<11} BaseRisk:${base_risk:.1f} Scale:{scale_factor:.1f} | "
        f"Trades:{total:3d} | WR:{wr:4.1f}% | PF:{pf:4.2f} | Net:+${net:>7.2f} ({roi:>6.1f}%) | "
        f"EndCap:${capital:>7.2f} | MaxDD:-${max_dd:>5.2f}"
    )

print("=" * 105)
test_stepped_risk(base_risk=4.0, scale_factor=0.5, mode="continuous")
test_stepped_risk(base_risk=4.0, scale_factor=0.75, mode="continuous")
test_stepped_risk(base_risk=4.0, scale_factor=0.5, mode="tier_steps")
test_stepped_risk(base_risk=4.0, scale_factor=0.75, mode="tier_steps")
test_stepped_risk(base_risk=4.0, mode="user_exact")
test_stepped_risk(base_risk=4.5, mode="user_exact")
