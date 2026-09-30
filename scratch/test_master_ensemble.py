import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("XAUTUSD", "15m", limit=20000)

print(f"Total candles loaded for Master Ensemble research: {len(candles)}")

def run_master_ensemble_experiment(
    max_concurrent_slots=2,
    base_risk_usd=4.0,
    del_thresh=0.04,
    use_compounding=False,
    compound_pct=0.04
):
    capital = 50.0
    trades = []
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    active_positions = [] # list of active trade dicts
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

        # 1. Weekend Lock
        if bar_time.weekday() in (5, 6):
            continue

        # 2. Active Session Window (London + NY: 12:30 - 23:45 IST)
        hm = bar_time.strftime("%H:%M")
        if not ("12:30" <= hm <= "23:45"):
            continue

        # VWAP calculation
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

        upper_vwap_band = vwap + (1.8 * stdev)
        lower_vwap_band = vwap - (1.8 * stdev)

        # 3. Manage All Active Positions in Parallel
        remaining_positions = []
        for pos in active_positions:
            side = pos["side"]
            entry = pos["entry_price"]
            dist = pos["dist"]
            lots = pos["lots"]
            half_lots = max(1, lots // 2)
            tp1_target = pos["tp1_rr"]
            max_target = pos["max_rr"]
            trail_mult = pos["trail_mult"]

            if side == "BUY":
                if c["high"] > pos["highest"]:
                    pos["highest"] = c["high"]
                gain_r = (pos["highest"] - entry) / dist

                # Scale out 50% at TP1
                if not pos["tp1_hit"] and gain_r >= tp1_target:
                    pos["tp1_hit"] = True
                    tp1_p = round(entry + tp1_target * dist, 2)
                    pnl_half = (half_lots * 0.001 * (tp1_p - entry)) - (half_lots * 0.001 * tp1_p * maker_fee * 2)
                    pos["booked_pnl"] = pnl_half
                    capital += pnl_half
                    # Move SL to Breakeven (+0.1R buffer)
                    pos["stop_loss"] = max(pos["stop_loss"], round(entry + 0.1 * dist, 2))

                # Dynamic Runner Trailing
                if pos["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(pos["highest"] - (trail_mult * dist), 2)
                    if new_sl > pos["stop_loss"]:
                        pos["stop_loss"] = new_sl

                hit_sl = c["low"] <= pos["stop_loss"]
                hit_tp = c["high"] >= round(entry + max_target * dist, 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry + max_target * dist, 2) if hit_tp else pos["stop_loss"]
                    rem_lots = (lots - half_lots) if pos["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_price * maker_fee * 2)
                    total_pnl = round(pos["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((exit_price - entry) / dist, 1) if not pos["tp1_hit"] else round((tp1_target * 0.5) + (((exit_price - entry) / dist) * 0.5), 1)

                    pos.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_target} + TRAIL (+{rr_final}R)" if pos["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(pos)
                    continue
                else:
                    remaining_positions.append(pos)

            else: # SELL
                if c["low"] < pos["lowest"]:
                    pos["lowest"] = c["low"]
                gain_r = (entry - pos["lowest"]) / dist

                if not pos["tp1_hit"] and gain_r >= tp1_target:
                    pos["tp1_hit"] = True
                    tp1_p = round(entry - tp1_target * dist, 2)
                    pnl_half = (half_lots * 0.001 * (entry - tp1_p)) - (half_lots * 0.001 * tp1_p * maker_fee * 2)
                    pos["booked_pnl"] = pnl_half
                    capital += pnl_half
                    pos["stop_loss"] = min(pos["stop_loss"], round(entry - 0.1 * dist, 2))

                if pos["tp1_hit"] and gain_r >= 2.0:
                    new_sl = round(pos["lowest"] + (trail_mult * dist), 2)
                    if new_sl < pos["stop_loss"]:
                        pos["stop_loss"] = new_sl

                hit_sl = c["high"] >= pos["stop_loss"]
                hit_tp = c["low"] <= round(entry - max_target * dist, 2)

                if hit_sl or hit_tp:
                    exit_price = round(entry - max_target * dist, 2) if hit_tp else pos["stop_loss"]
                    rem_lots = (lots - half_lots) if pos["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * 0.001 * diff) - (rem_lots * 0.001 * exit_price * maker_fee * 2)
                    total_pnl = round(pos["booked_pnl"] + rem_pnl, 2)
                    capital += rem_pnl
                    equity_curve.append({"timestamp": ts, "equity": round(capital, 2)})

                    rr_final = round((entry - exit_price) / dist, 1) if not pos["tp1_hit"] else round((tp1_target * 0.5) + (((entry - exit_price) / dist) * 0.5), 1)

                    pos.update({
                        "exit_price": exit_price,
                        "pnl_usd": total_pnl,
                        "closed_at": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "close_reason": f"HALF @ 1:{tp1_target} + TRAIL (+{rr_final}R)" if pos["tp1_hit"] else "SL",
                        "status": "CLOSED",
                        "rr_achieved": rr_final
                    })
                    trades.append(pos)
                    continue
                else:
                    remaining_positions.append(pos)

        active_positions = remaining_positions

        # 4. Check New Signal Entries if slots available
        if len(active_positions) < max_concurrent_slots:
            sub = candles[i-20:i]
            hi8 = max(x["high"] for x in sub[-8:])
            lo8 = min(x["low"] for x in sub[-8:])
            hi12 = max(x["high"] for x in sub[-12:])
            lo12 = min(x["low"] for x in sub[-12:])

            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            ema20 = sum(x["close"] for x in sub[-20:]) / 20.0

            # Signal 1: 8-bar Micro Liquidity Sweep
            sweep_buy = (c["low"] < lo8) and (c["close"] > lo8) and (delta_ratio >= del_thresh)
            sweep_sell = (c["high"] > hi8) and (c["close"] < hi8) and (delta_ratio <= -del_thresh)

            # Signal 2: Session VWAP Bands Reversion
            vwap_buy = (len(day_prices) >= 6) and (c["low"] <= lower_vwap_band) and (c["close"] > c["open"]) and (delta_ratio >= del_thresh)
            vwap_sell = (len(day_prices) >= 6) and (c["high"] >= upper_vwap_band) and (c["close"] < c["open"]) and (delta_ratio <= -del_thresh)

            # Signal 3: Footprint Absorption Divergence
            absorb_buy = (c["low"] <= lo12 * 1.0002) and (delta_ratio >= del_thresh * 0.8) and (c["close"] > c["open"])
            absorb_sell = (c["high"] >= hi12 * 0.9998) and (delta_ratio <= -del_thresh * 0.8) and (c["close"] < c["open"])

            # Confluence scoring
            buy_signals = sum([sweep_buy, vwap_buy, absorb_buy])
            sell_signals = sum([sweep_sell, vwap_sell, absorb_sell])

            is_buy = (buy_signals > 0) and (sell_signals == 0)
            is_sell = (sell_signals > 0) and (buy_signals == 0)

            # Avoid opening opposite positions simultaneously
            has_buy = any(p["side"] == "BUY" for p in active_positions)
            has_sell = any(p["side"] == "SELL" for p in active_positions)

            if is_buy and not has_sell and not has_buy:
                confluence_score = buy_signals
                # 5-star confluence setup gets higher target + wider runner
                is_high_conviction = (confluence_score >= 2)
                tp1_rr = 2.5 if is_high_conviction else 2.0
                max_rr = 4.0 if is_high_conviction else 2.5
                trail_mult = 1.5 if is_high_conviction else 1.2

                dist = max(2.5, abs(curr - c["low"]) + 0.6)
                sl_price = round(curr - dist, 2)
                
                if use_compounding:
                    risk_usd = max(2.0, min(capital * compound_pct, 25.0))
                else:
                    risk_usd = base_risk_usd

                lots = max(2, int(round(risk_usd / (dist * 0.001))))

                active_positions.append({
                    "id": f"MASTER_{c['timestamp']}",
                    "side": "BUY",
                    "entry_price": curr,
                    "stop_loss": sl_price,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "risk_usd": risk_usd,
                    "tp1_rr": tp1_rr,
                    "max_rr": max_rr,
                    "trail_mult": trail_mult,
                    "conviction_stars": 5.0 if is_high_conviction else 4.0,
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S")
                })

            elif is_sell and not has_buy and not has_sell:
                confluence_score = sell_signals
                is_high_conviction = (confluence_score >= 2)
                tp1_rr = 2.5 if is_high_conviction else 2.0
                max_rr = 4.0 if is_high_conviction else 2.5
                trail_mult = 1.5 if is_high_conviction else 1.2

                dist = max(2.5, abs(c["high"] - curr) + 0.6)
                sl_price = round(curr + dist, 2)

                if use_compounding:
                    risk_usd = max(2.0, min(capital * compound_pct, 25.0))
                else:
                    risk_usd = base_risk_usd

                lots = max(2, int(round(risk_usd / (dist * 0.001))))

                active_positions.append({
                    "id": f"MASTER_{c['timestamp']}",
                    "side": "SELL",
                    "entry_price": curr,
                    "stop_loss": sl_price,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "risk_usd": risk_usd,
                    "tp1_rr": tp1_rr,
                    "max_rr": max_rr,
                    "trail_mult": trail_mult,
                    "conviction_stars": 5.0 if is_high_conviction else 4.0,
                    "tp1_hit": False,
                    "booked_pnl": 0.0,
                    "opened_at": bar_time.strftime("%Y-%m-%d %H:%M:%S")
                })

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] < 0]
    total = len(trades)
    wr = round((len(wins) / total * 100), 1) if total > 0 else 0.0
    gross_win = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses)) if losses else 1.0
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0.0
    net = round(capital - 50.0, 2)
    roi = round((net / 50.0) * 100, 1)

    peak = 50.0
    max_dd = 0.0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        dd = peak - pt["equity"]
        if dd > max_dd:
            max_dd = dd

    print(
        f"Slots:{max_concurrent_slots} Comp:{str(use_compounding):<5} Del:{del_thresh:.2f} | "
        f"Trades:{total:3d} | WR:{wr:4.1f}% | PF:{pf:4.2f} | Net:+${net:>7.2f} ({roi:>6.1f}%) | "
        f"EndCap:${capital:>7.2f} | MaxDD:-${max_dd:>5.2f}"
    )

print("=" * 105)
for comp in [False, True]:
    for d in [0.03, 0.04, 0.05]:
        for slots in [1, 2]:
            run_master_ensemble_experiment(max_concurrent_slots=slots, del_thresh=d, use_compounding=comp)
