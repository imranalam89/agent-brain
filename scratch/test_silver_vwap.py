import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.database import DatabaseManager

db = DatabaseManager()
candles = db.get_latest_candles("SLVONUSD", "15m", limit=25000)

def test_silver_vwap(candles):
    capital = 50.0
    equity_curve = [{"timestamp": candles[50]["timestamp"], "equity": capital}]
    trades = []
    active_trade = None
    maker_fee = 0.0001
    contract_val = 1.0

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
        stdev = max(0.1, variance**0.5)

        upper_vwap = vwap + (1.8 * stdev)
        lower_vwap = vwap - (1.8 * stdev)

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

                if not active_trade["tp1_hit"] and gain_r >= 2.0:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry + 2.0 * dist, 3)
                    pnl_half = (half_lots * contract_val * (tp1_p - entry)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = max(active_trade["stop_loss"], round(entry + 0.1 * dist, 3))

                if active_trade["tp1_hit"] and gain_r >= 2.5:
                    new_sl = round(active_trade["highest"] - (1.2 * dist), 3)
                    if new_sl > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                if c["low"] <= active_trade["stop_loss"] or c["high"] >= round(entry + 4.0 * dist, 3):
                    exit_price = round(entry + 4.0 * dist, 3) if c["high"] >= round(entry + 4.0 * dist, 3) else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = exit_price - entry
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    capital += rem_pnl
                    trades.append({"pnl_usd": active_trade["booked_pnl"] + rem_pnl})
                    active_trade = None
                    continue
            else:
                if c["low"] < active_trade["lowest"]:
                    active_trade["lowest"] = c["low"]
                gain_r = (entry - active_trade["lowest"]) / dist

                if not active_trade["tp1_hit"] and gain_r >= 2.0:
                    active_trade["tp1_hit"] = True
                    tp1_p = round(entry - 2.0 * dist, 3)
                    pnl_half = (half_lots * contract_val * (entry - tp1_p)) - (half_lots * contract_val * tp1_p * maker_fee * 2)
                    active_trade["booked_pnl"] = pnl_half
                    capital += pnl_half
                    active_trade["stop_loss"] = min(active_trade["stop_loss"], round(entry - 0.1 * dist, 3))

                if active_trade["tp1_hit"] and gain_r >= 2.5:
                    new_sl = round(active_trade["lowest"] + (1.2 * dist), 3)
                    if new_sl < active_trade["stop_loss"]:
                        active_trade["stop_loss"] = new_sl

                if c["high"] >= active_trade["stop_loss"] or c["low"] <= round(entry - 4.0 * dist, 3):
                    exit_price = round(entry - 4.0 * dist, 3) if c["low"] <= round(entry - 4.0 * dist, 3) else active_trade["stop_loss"]
                    rem_lots = (lots - half_lots) if active_trade["tp1_hit"] else lots
                    diff = entry - exit_price
                    rem_pnl = (rem_lots * contract_val * diff) - (rem_lots * contract_val * exit_price * maker_fee * 2)
                    capital += rem_pnl
                    trades.append({"pnl_usd": active_trade["booked_pnl"] + rem_pnl})
                    active_trade = None
                    continue

        if not active_trade:
            delta = c.get("delta", 0.0)
            vol = max(1.0, c.get("volume", 1.0))
            delta_ratio = delta / vol

            # VWAP Reversion entry
            vwap_buy = (len(day_prices) >= 6) and (c["low"] <= lower_vwap) and (c["close"] > c["open"]) and (delta_ratio >= 0.03)
            vwap_sell = (len(day_prices) >= 6) and (c["high"] >= upper_vwap) and (c["close"] < c["open"]) and (delta_ratio <= -0.03)

            if vwap_buy or vwap_sell:
                dist = max(0.20, abs(curr - (c["low"] if vwap_buy else c["high"])) + 0.05)
                sl = round(curr - dist if vwap_buy else curr + dist, 3)
                lots = max(2, int(round(5.0 / (dist * contract_val))))
                active_trade = {
                    "side": "BUY" if vwap_buy else "SELL",
                    "entry_price": curr,
                    "stop_loss": sl,
                    "dist": dist,
                    "highest": curr,
                    "lowest": curr,
                    "lots": lots,
                    "tp1_hit": False,
                    "booked_pnl": 0.0
                }

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    total_trades = len(trades)
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    net_pl = capital - 50.0
    gross_profit = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    print(f"VWAP Reversion Silver: Trades={total_trades}, WinRate={win_rate:.1f}%, PF={pf:.2f}, Net=${net_pl:+.2f}")

test_silver_vwap(candles)
