import sys
import json
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from data.database import DatabaseManager
from reports.backtest_v5_reporter import generate_backtest_v5_html

IST = timezone(timedelta(hours=5, minutes=30))  # Delta Exchange India IST Timezone (UTC+5:30)
STRICT_RISK_USD = 5.00  # Strict $5.00 Fixed Risk Per Trade
USD_TO_INR = 90.0       # Delta Exchange India conversion rate

def calculate_exact_fees(symbol: str, entry: float, sl: float, is_maker: bool = True) -> float:
    """
    Calibrated directly from live Delta Exchange India fee schedule:
    - Commodity Contracts (XAUTUSD, SLVONUSD):
      Taker/Market fee: 0.009% base + 18% GST = 0.01062% per leg.
      Round trip: 0.02124% (0.0002124).
    """
    dist = abs(entry - sl)
    notional = (STRICT_RISK_USD / dist) * entry if dist > 0 and entry > 0 else 1000.0
    return round(notional * 0.0002124, 4)

def calc_delta_lots(symbol: str, entry: float, sl: float, risk: float = STRICT_RISK_USD) -> int:
    """
    Computes exact integer contract lot size based on strict USD risk and Delta Exchange contract multipliers:
    - XAUTUSD: 1 Lot = 0.001 XAUT (Gold oz)
    """
    dist = abs(entry - sl)
    if dist <= 0 or entry <= 0:
        return 1
    coins = risk / dist
    lots = int(round(coins / 0.001))
    return max(1, lots)

def get_symbol_params(symbol: str = "XAUTUSD"):
    return {"min_dist": 3.5, "pad": 0.9}

def resample_htf(candles_15m: list, target_minutes: int):
    """Resamples 15m candles into Higher Timeframe (4H = 240m, 1H = 60m)."""
    target_sec = target_minutes * 60
    htf = []
    curr = None
    b_o = b_h = b_l = b_c = b_v = b_d = 0.0

    for c in candles_15m:
        ts = c["timestamp"]
        bts = (ts // target_sec) * target_sec
        if curr is None or bts != curr:
            if curr is not None:
                htf.append({"timestamp": curr, "open": b_o, "high": b_h, "low": b_l, "close": b_c, "volume": b_v, "delta": b_d})
            curr = bts
            b_o = c["open"]
            b_h = c["high"]
            b_l = c["low"]
            b_c = c["close"]
            b_v = c.get("volume", 0.0)
            b_d = c.get("delta", 0.0)
        else:
            if c["high"] > b_h: b_h = c["high"]
            if c["low"] < b_l: b_l = c["low"]
            b_c = c["close"]
            b_v += c.get("volume", 0.0)
            b_d += c.get("delta", 0.0)

    if curr is not None:
        htf.append({"timestamp": curr, "open": b_o, "high": b_h, "low": b_l, "close": b_c, "volume": b_v, "delta": b_d})

    n = len(htf)
    closes = [c["close"] for c in htf]
    highs = [c["high"] for c in htf]
    lows = [c["low"] for c in htf]

    def calc_ema(p):
        res = [0.0] * n
        if n < p: return res
        k = 2.0 / (p + 1.0)
        res[p - 1] = sum(closes[:p]) / p
        for i in range(p, n):
            res[i] = closes[i] * k + res[i - 1] * (1.0 - k)
        return res

    ema20 = calc_ema(20)
    ema50 = calc_ema(50)
    ema200 = calc_ema(200)

    for i in range(n):
        htf[i]["ema20"] = ema20[i]
        htf[i]["ema50"] = ema50[i]
        htf[i]["ema200"] = ema200[i]
        st = max(0, i - 24)
        htf[i]["swing_hi"] = max(highs[st:i]) if i > 0 else highs[0]
        htf[i]["swing_lo"] = min(lows[st:i]) if i > 0 else lows[0]

    htf_map = {}
    h_idx = 0
    for c in candles_15m:
        ts = c["timestamp"]
        bts = (ts // target_sec) * target_sec
        while h_idx < len(htf) and htf[h_idx]["timestamp"] < bts:
            h_idx += 1
        htf_map[ts] = htf[h_idx - 1] if h_idx > 0 else None

    return htf, htf_map

def prepare_15m_data(candles: list):
    """Calculates EMA, ATR, Session VWAP, and RSI on 15m candles."""
    n = len(candles)
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [max(1.0, c.get("volume", 1.0)) for c in candles]

    def calc_ema(p):
        res = [0.0] * n
        if n < p: return res
        k = 2.0 / (p + 1.0)
        res[p - 1] = sum(closes[:p]) / p
        for i in range(p, n):
            res[i] = closes[i] * k + res[i - 1] * (1.0 - k)
        return res

    ema20 = calc_ema(20)
    ema50 = calc_ema(50)

    atr14 = [0.0] * n
    if n >= 15:
        tr = [0.0] * n
        for i in range(1, n):
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        atr14[14] = sum(tr[1:15]) / 14.0
        for i in range(15, n):
            atr14[i] = (atr14[i - 1] * 13.0 + tr[i]) / 14.0

    curr_day = None
    day_v = 0.0
    day_pv = 0.0
    day_pr = []
    vwap_arr = [0.0] * n
    vwap_std_arr = [0.0] * n

    for i in range(n):
        c = candles[i]
        dt = datetime.fromtimestamp(c["timestamp"], tz=IST)
        d_str = dt.strftime("%Y-%m-%d")
        typ = (c["high"] + c["low"] + c["close"]) / 3.0
        v = vols[i]

        if d_str != curr_day:
            curr_day = d_str
            day_v = 0.0
            day_pv = 0.0
            day_pr = []

        day_v += v
        day_pv += typ * v
        day_pr.append(typ)
        vw = day_pv / day_v
        vwap_arr[i] = vw

        if len(day_pr) > 1:
            mean_p = sum(day_pr) / len(day_pr)
            var = sum((x - mean_p)**2 for x in day_pr) / len(day_pr)
            vwap_std_arr[i] = max(0.2, var**0.5)
        else:
            vwap_std_arr[i] = 1.0

    # RSI 14
    rsi = [50.0] * n
    if n > 14:
        gains = [0.0] * n
        losses = [0.0] * n
        for i in range(1, n):
            chg = closes[i] - closes[i-1]
            if chg > 0: gains[i] = chg
            else: losses[i] = abs(chg)
        avg_g = sum(gains[1:15]) / 14.0
        avg_l = sum(losses[1:15]) / 14.0
        if avg_l == 0: rsi[14] = 100.0
        else: rsi[14] = 100.0 - (100.0 / (1.0 + avg_g / avg_l))

        for i in range(15, n):
            avg_g = (avg_g * 13.0 + gains[i]) / 14.0
            avg_l = (avg_l * 13.0 + losses[i]) / 14.0
            if avg_l == 0: rsi[i] = 100.0
            else: rsi[i] = 100.0 - (100.0 / (1.0 + avg_g / avg_l))

    for i in range(n):
        candles[i]["ema20"] = ema20[i]
        candles[i]["ema50"] = ema50[i]
        candles[i]["atr14"] = max(0.01, atr14[i])
        candles[i]["vwap"] = vwap_arr[i]
        candles[i]["vwap_std"] = vwap_std_arr[i]
        candles[i]["rsi14"] = rsi[i]

# =========================================================================================
# 5 DISTINCT SPECIALIZED GOLD (XAUTUSD) STRATEGIES
# =========================================================================================

# 1. Gold Apex Grandmaster Confluence (4H BOS + 1H Momentum + 30m Wave + 15m Value Retest)
def generate_gold_apex_confluence(c15: list, h4_map: dict, h1_map: dict, m30_map: dict = None):
    trades = []
    min_dist = 3.5
    last_ts = 0
    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 4: continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        m30 = m30_map.get(ts) if m30_map else None
        if not h4 or not h1 or h4.get("ema50", 0.0) <= 0 or h1.get("ema20", 0.0) <= 0: continue
        if m30 and m30.get("ema20", 0.0) <= 0: continue
        atr = c.get("atr14", 3.0)
        delta = c.get("delta", 0.0)
        dt = datetime.fromtimestamp(ts, tz=IST)

        rng = max(0.1, c["high"] - c["low"])
        l_wick = (min(c["open"], c["close"]) - c["low"]) / rng
        u_wick = (c["high"] - max(c["open"], c["close"])) / rng

        m30_bull = (m30["close"] > m30["ema20"]) if m30 else True
        m30_bear = (m30["close"] < m30["ema20"]) if m30 else True

        if h4["close"] > h4["ema50"] and h4["ema50"] > h4.get("ema200", 0.0) and h1["close"] > h1["ema20"] and m30_bull and c["close"] > c["open"] and delta > 0 and l_wick >= 0.20:
            if c["low"] <= c.get("ema20", c["close"]):
                dist = max(min_dist, 1.4 * atr)
                sl = c["close"] - dist
                trades.append({
                    "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": sl,
                    "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "conviction_stars": 5.0, "notes": "Gold 4H Bull Structure + 1H Momentum + 30m Wave + 15m Value Retest"
                })
                last_ts = ts
        elif h4["close"] < h4["ema50"] and h4["ema50"] < h4.get("ema200", 0.0) and h1["close"] < h1["ema20"] and m30_bear and c["close"] < c["open"] and delta < 0 and u_wick >= 0.20:
            if c["high"] >= c.get("ema20", c["close"]):
                dist = max(min_dist, 1.4 * atr)
                sl = c["close"] + dist
                trades.append({
                    "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": sl,
                    "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "conviction_stars": 5.0, "notes": "Gold 4H Bear Structure + 1H Momentum + 30m Wave + 15m Premium Retest"
                })
                last_ts = ts
    return trades

# 2. Gold London & NY Session Institutional Flow (13:00 to 22:00 IST)
def generate_gold_session_momentum(c15: list, h4_map: dict, h1_map: dict):
    trades = []
    min_dist = 3.5
    last_ts = 0
    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 5: continue
        dt = datetime.fromtimestamp(ts, tz=IST)
        if not (13 <= dt.hour <= 22): continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        if not h4 or not h1 or h4.get("ema50", 0.0) <= 0: continue
        atr = c.get("atr14", 3.0)
        delta = c.get("delta", 0.0)

        if h4["close"] > h4["ema50"] and h1["close"] > h1["ema20"] and c["close"] > c["open"] and delta > 0:
            if c["low"] <= c.get("ema20", c["close"]):
                dist = max(min_dist, 1.3 * atr)
                sl = c["close"] - dist
                trades.append({
                    "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": sl,
                    "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "conviction_stars": 5.0, "notes": "Gold London/NY Session Momentum Retest"
                })
                last_ts = ts
        elif h4["close"] < h4["ema50"] and h1["close"] < h1["ema20"] and c["close"] < c["open"] and delta < 0:
            if c["high"] >= c.get("ema20", c["close"]):
                dist = max(min_dist, 1.3 * atr)
                sl = c["close"] + dist
                trades.append({
                    "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": sl,
                    "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "conviction_stars": 5.0, "notes": "Gold London/NY Session Momentum Retest"
                })
                last_ts = ts
    return trades

# 2B. Gold Dual-Engine Titan (Apex Confluence + Session Momentum Combination)
def generate_gold_dual_engine(c15: list, h4_map: dict, h1_map: dict):
    t1 = generate_gold_apex_confluence(c15, h4_map, h1_map)
    t2 = generate_gold_session_momentum(c15, h4_map, h1_map)
    seen = set()
    combined = []
    for t in t1 + t2:
        if t["timestamp"] not in seen:
            seen.add(t["timestamp"])
            combined.append(t)
    combined.sort(key=lambda t: t["timestamp"])
    return combined

# 3. Gold Multi-Timeframe 5-Tier Master Confluence (4H + 1H + 30m + 15m + 5m)
def generate_gold_multi_tf_cascade(c15: list, h4_map: dict, h1_map: dict, m30_map: dict, c5: list = None):
    trades = []
    min_dist = 3.5
    last_ts = 0
    c5_by_ts = {c["timestamp"]: c for c in c5} if c5 else {}

    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 3: continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        m30 = m30_map.get(ts)
        if not h4 or not h1 or not m30 or h4.get("ema50", 0) <= 0 or h1.get("ema20", 0) <= 0 or m30.get("ema20", 0) <= 0: continue
        
        atr = c.get("atr14", 3.0)
        delta = c.get("delta", 0.0)
        rng = max(0.1, c["high"] - c["low"])
        l_wick = (min(c["open"], c["close"]) - c["low"]) / rng
        u_wick = (c["high"] - max(c["open"], c["close"])) / rng

        # Setup A: Apex Retest (4H + 1H + 30m + 15m EMA Value Retest with Wick Rejection)
        is_apex_buy = (h4["close"] > h4["ema50"] and h4["ema50"] > h4.get("ema200", 0.0) and 
                       h1["close"] > h1["ema20"] and m30["close"] > m30["ema20"] and 
                       c["close"] > c["open"] and delta > 0 and c["low"] <= c.get("ema20", c["close"]) and l_wick >= 0.20)
                       
        is_apex_sell = (h4["close"] < h4["ema50"] and h4["ema50"] < h4.get("ema200", 0.0) and 
                        h1["close"] < h1["ema20"] and m30["close"] < m30["ema20"] and 
                        c["close"] < c["open"] and delta < 0 and c["high"] >= c.get("ema20", c["close"]) and u_wick >= 0.20)

        # Setup B: Order Block Liquidity Sweep Retest
        prev_low = min(c15[j]["low"] for j in range(i-3, i))
        prev_high = max(c15[j]["high"] for j in range(i-3, i))
        
        is_ob_buy = (h4["close"] > h4["ema50"] and h1["close"] > h1["ema20"] and m30["close"] > m30["ema20"] and
                     c["low"] <= prev_low and c["close"] > c["open"] and delta > 0 and l_wick >= 0.20)
                     
        is_ob_sell = (h4["close"] < h4["ema50"] and h1["close"] < h1["ema20"] and m30["close"] < m30["ema20"] and
                      c["high"] >= prev_high and c["close"] < c["open"] and delta < 0 and u_wick >= 0.20)

        # 5m Trigger refinement when 5m candle exists
        sub_5m = c5_by_ts.get(ts + 600)
        if sub_5m is not None:
            if (is_apex_buy or is_ob_buy) and (sub_5m["delta"] <= 0 or sub_5m["close"] < sub_5m["open"]): continue
            if (is_apex_sell or is_ob_sell) and (sub_5m["delta"] >= 0 or sub_5m["close"] > sub_5m["open"]): continue

        dt = datetime.fromtimestamp(ts, tz=IST)
        if is_apex_buy or is_ob_buy:
            dist = max(min_dist, 1.4 * atr)
            note = "Multi-TF 5-Tier Apex Retest" if is_apex_buy else "Multi-TF 5-Tier Order Block Sweep"
            trades.append({
                "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": c["close"] - dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": note
            })
            last_ts = ts
        elif is_apex_sell or is_ob_sell:
            dist = max(min_dist, 1.4 * atr)
            note = "Multi-TF 5-Tier Apex Retest" if is_apex_sell else "Multi-TF 5-Tier Order Block Sweep"
            trades.append({
                "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": c["close"] + dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": note
            })
            last_ts = ts
    return trades

# 4. Gold Institutional Order Block Retest
def generate_gold_order_block(c15: list, h4_map: dict, h1_map: dict):
    trades = []
    min_dist = 3.5
    last_ts = 0
    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 4: continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        if not h4 or not h1 or h4.get("ema50", 0.0) <= 0: continue
        atr = c.get("atr14", 3.0)
        delta = c.get("delta", 0.0)
        dt = datetime.fromtimestamp(ts, tz=IST)

        prev_low = min(c15[j]["low"] for j in range(i-3, i))
        if h4["close"] > h4["ema50"] and h1["close"] > h1["ema20"] and c["low"] <= prev_low and c["close"] > c["open"] and delta > 0:
            dist = max(min_dist, 1.3 * atr)
            sl = c["close"] - dist
            trades.append({
                "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": sl,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Gold 4H Trend + 15m Order Block Liquidity Retest"
            })
            last_ts = ts
        elif h4["close"] < h4["ema50"] and h1["close"] < h1["ema20"] and c["high"] >= max(c15[j]["high"] for j in range(i-3, i)) and c["close"] < c["open"] and delta < 0:
            dist = max(min_dist, 1.3 * atr)
            sl = c["close"] + dist
            trades.append({
                "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": sl,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Gold 4H Trend + 15m Order Block Liquidity Retest"
            })
            last_ts = ts
    return trades

# 5. Gold Volume Expansion Breakout (High-Volatility Runner)
def generate_gold_vol_expansion(c15: list, h4_map: dict, h1_map: dict):
    trades = []
    min_dist = 3.5
    last_ts = 0
    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 5: continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        if not h4 or not h1 or h4.get("ema50", 0.0) <= 0: continue
        atr = c.get("atr14", 3.0)
        delta = c.get("delta", 0.0)
        c_range = max(0.01, c["high"] - c["low"])
        dt = datetime.fromtimestamp(ts, tz=IST)

        # Expansion candle >= 1.6x ATR with volume surge and delta
        if c_range >= 1.6 * atr and delta > 0 and h4["close"] > h4["ema50"] and h1["close"] > h1["ema20"] and c["close"] > c["open"]:
            dist = max(min_dist, 1.2 * atr)
            sl = c["close"] - dist
            trades.append({
                "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": sl,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Gold Institutional Volatility Expansion Breakout"
            })
            last_ts = ts
        elif c_range >= 1.6 * atr and delta < 0 and h4["close"] < h4["ema50"] and h1["close"] < h1["ema20"] and c["close"] < c["open"]:
            dist = max(min_dist, 1.2 * atr)
            sl = c["close"] + dist
            trades.append({
                "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": sl,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Gold Institutional Volatility Expansion Breakout"
            })
            last_ts = ts
    return trades

# 6. Gold Price Action: Fair Value Gap (FVG) Imbalance Retest
def generate_gold_fvg_imbalance(c15: list, h4_map: dict, h1_map: dict, m30_map: dict):
    trades = []
    min_dist = 3.5
    last_ts = 0
    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 3: continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        m30 = m30_map.get(ts)
        if not h4 or not h1 or not m30 or h4.get("ema50", 0) <= 0 or h1.get("ema20", 0) <= 0 or m30.get("ema20", 0) <= 0: continue
        atr = c.get("atr14", 3.0)
        dt = datetime.fromtimestamp(ts, tz=IST)

        bull_htf = (h4["close"] > h4["ema50"] and h4["ema50"] > h4.get("ema200", 0.0) and h1["close"] > h1["ema20"] and m30["close"] > m30["ema20"])
        bear_htf = (h4["close"] < h4["ema50"] and h4["ema50"] < h4.get("ema200", 0.0) and h1["close"] < h1["ema20"] and m30["close"] < m30["ema20"])

        fvg_bull_gap = c15[i-2]["low"] - c15[i-4]["high"]
        fvg_bear_gap = c15[i-4]["low"] - c15[i-2]["high"]

        if bull_htf and fvg_bull_gap > 0.5 and c["low"] <= c15[i-2]["low"] and c["low"] >= c15[i-4]["high"] and c["close"] > c["open"]:
            dist = max(min_dist, 1.4 * atr)
            trades.append({
                "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": c["close"] - dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Price Action FVG Imbalance Retest"
            })
            last_ts = ts
        elif bear_htf and fvg_bear_gap > 0.5 and c["high"] >= c15[i-2]["high"] and c["high"] <= c15[i-4]["low"] and c["close"] < c["open"]:
            dist = max(min_dist, 1.4 * atr)
            trades.append({
                "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": c["close"] + dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Price Action FVG Imbalance Retest"
            })
            last_ts = ts
    return trades

# 7. Gold Price Action: Inside Bar False Breakout Trap (Hikkake Reversal)
def generate_gold_inside_bar_trap(c15: list, h4_map: dict, h1_map: dict, m30_map: dict):
    trades = []
    min_dist = 3.5
    last_ts = 0
    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 3: continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        m30 = m30_map.get(ts)
        if not h4 or not h1 or not m30 or h4.get("ema50", 0) <= 0 or h1.get("ema20", 0) <= 0 or m30.get("ema20", 0) <= 0: continue
        atr = c.get("atr14", 3.0)
        dt = datetime.fromtimestamp(ts, tz=IST)

        bull_htf = (h4["close"] > h4["ema50"] and h4["ema50"] > h4.get("ema200", 0.0) and h1["close"] > h1["ema20"] and m30["close"] > m30["ema20"])
        bear_htf = (h4["close"] < h4["ema50"] and h4["ema50"] < h4.get("ema200", 0.0) and h1["close"] < h1["ema20"] and m30["close"] < m30["ema20"])

        mother = c15[i-3]
        inside = c15[i-2]
        is_inside = (inside["high"] <= mother["high"] and inside["low"] >= mother["low"])
        if not is_inside: continue

        if bull_htf and c15[i-1]["low"] < inside["low"] and c["close"] > inside["high"]:
            dist = max(min_dist, 1.4 * atr)
            trades.append({
                "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": c["close"] - dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Price Action Inside Bar False Breakout Trap"
            })
            last_ts = ts
        elif bear_htf and c15[i-1]["high"] > inside["high"] and c["close"] < inside["low"]:
            dist = max(min_dist, 1.4 * atr)
            trades.append({
                "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": c["close"] + dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Price Action Inside Bar False Breakout Trap"
            })
            last_ts = ts
    return trades

# 8. Gold Price Action: Swing Break & Retest
def generate_gold_break_retest(c15: list, h4_map: dict, h1_map: dict, m30_map: dict):
    trades = []
    min_dist = 3.5
    last_ts = 0
    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 3: continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        m30 = m30_map.get(ts)
        if not h4 or not h1 or not m30 or h4.get("ema50", 0) <= 0 or h1.get("ema20", 0) <= 0 or m30.get("ema20", 0) <= 0: continue
        atr = c.get("atr14", 3.0)
        dt = datetime.fromtimestamp(ts, tz=IST)

        bull_htf = (h4["close"] > h4["ema50"] and h4["ema50"] > h4.get("ema200", 0.0) and h1["close"] > h1["ema20"] and m30["close"] > m30["ema20"])
        bear_htf = (h4["close"] < h4["ema50"] and h4["ema50"] < h4.get("ema200", 0.0) and h1["close"] < h1["ema20"] and m30["close"] < m30["ema20"])

        swing_h = max(c15[j]["high"] for j in range(i-20, i-3))
        swing_l = min(c15[j]["low"] for j in range(i-20, i-3))
        prev_c = c15[i-1]

        if bull_htf and prev_c["close"] > swing_h and c["low"] <= swing_h + 0.5 * atr and c["close"] > c["open"]:
            dist = max(min_dist, 1.4 * atr)
            trades.append({
                "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": c["close"] - dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Price Action Swing Break & Retest"
            })
            last_ts = ts
        elif bear_htf and prev_c["close"] < swing_l and c["high"] >= swing_l - 0.5 * atr and c["close"] < c["open"]:
            dist = max(min_dist, 1.4 * atr)
            trades.append({
                "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": c["close"] + dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "Price Action Swing Break & Retest"
            })
            last_ts = ts
    return trades

# 9. Gold Price Action + Dual Order Flow Fusion (Delta Initiative & CVD Trend)
def generate_gold_pa_orderflow_fusion(c15: list, h4_map: dict, h1_map: dict, m30_map: dict, c5: list = None):
    trades = []
    min_dist = 3.5
    last_ts = 0
    c5_by_ts = {c["timestamp"]: c for c in c5} if c5 else {}

    cvd = 0.0
    for i in range(len(c15)):
        d = c15[i].get("delta", 0.0)
        cvd += d
        c15[i]["cvd"] = cvd

    for i in range(50, len(c15) - 10):
        c = c15[i]
        ts = c["timestamp"]
        if ts - last_ts < 3600 * 3: continue
        h4 = h4_map.get(ts)
        h1 = h1_map.get(ts)
        m30 = m30_map.get(ts)
        if not h4 or not h1 or not m30 or h4.get("ema50", 0) <= 0 or h1.get("ema20", 0) <= 0 or m30.get("ema20", 0) <= 0: continue
        
        atr = c.get("atr14", 3.0)
        rng = max(0.1, c["high"] - c["low"])
        l_wick = (min(c["open"], c["close"]) - c["low"]) / rng
        u_wick = (c["high"] - max(c["open"], c["close"])) / rng
        delta = c.get("delta", 0.0)

        bull_htf = (h4["close"] > h4["ema50"] and h4["ema50"] > h4.get("ema200", 0.0) and h1["close"] > h1["ema20"] and m30["close"] > m30["ema20"])
        bear_htf = (h4["close"] < h4["ema50"] and h4["ema50"] < h4.get("ema200", 0.0) and h1["close"] < h1["ema20"] and m30["close"] < m30["ema20"])

        prev_l = min(c15[j]["low"] for j in range(i-3, i))
        prev_h = max(c15[j]["high"] for j in range(i-3, i))

        # Price Action Retest:
        is_pa_b = (bull_htf and c["close"] > c["open"] and (c["low"] <= c.get("ema20", c["close"]) or c["low"] <= prev_l) and l_wick >= 0.20)
        is_pa_s = (bear_htf and c["close"] < c["open"] and (c["high"] >= c.get("ema20", c["close"]) or c["high"] >= prev_h) and u_wick >= 0.20)

        # Dual Order Flow Confirmation: Delta initiative + CVD slope alignment
        cvd_prev = c15[i-5]["cvd"]
        is_of_b = (delta > 0 and c["cvd"] > cvd_prev)
        is_of_s = (delta < 0 and c["cvd"] < cvd_prev)

        sub_5m = c5_by_ts.get(ts + 600)
        if sub_5m is not None:
            if is_pa_b and is_of_b and (sub_5m["delta"] <= 0 or sub_5m["close"] < sub_5m["open"]): continue
            if is_pa_s and is_of_s and (sub_5m["delta"] >= 0 or sub_5m["close"] > sub_5m["open"]): continue

        dt = datetime.fromtimestamp(ts, tz=IST)
        if is_pa_b and is_of_b:
            dist = max(min_dist, 1.4 * atr)
            trades.append({
                "symbol": "XAUTUSD", "side": "BUY", "entry_price": c["close"], "stop_loss": c["close"] - dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "PA + Dual Order Flow Fusion (Delta & CVD)"
            })
            last_ts = ts
        elif is_pa_s and is_of_s:
            dist = max(min_dist, 1.4 * atr)
            trades.append({
                "symbol": "XAUTUSD", "side": "SELL", "entry_price": c["close"], "stop_loss": c["close"] + dist,
                "timestamp": ts, "opened_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "conviction_stars": 5.0, "notes": "PA + Dual Order Flow Fusion (Delta & CVD)"
            })
            last_ts = ts
    return trades

# =========================================================================================
# V5 3-LAYER TRAILING & SIMULATION ENGINE FOR GOLD
# =========================================================================================

def apply_desk_journal_filters(signals: list, is_btc: bool = False) -> list:
    """
    Forensic Journal Audit Filters:
    1. Blocks toxic rollover/chop hours (06:00, 07:00, 14:00, 23:00 IST).
    2. Friday Institutional De-risking (No new entries after 16:00 IST).
    3. Blocks weekend BTC Long traps (Saturday & Sunday).
    """
    approved = []
    for s in signals:
        dt = datetime.fromtimestamp(s["timestamp"], tz=IST)
        if dt.hour in [6, 7, 14, 23]: continue
        if dt.weekday() == 4 and dt.hour >= 16: continue
        if is_btc and s.get("side") == "BUY" and dt.weekday() in [5, 6]: continue
        approved.append(s)
    return approved

def simulate_v5_strategy(trades: list, candles_dict: dict, name: str, max_macro_rr: float = 40.0, be_trigger: float = 1.6, be_lock: float = 0.30) -> dict:
    processed = []
    capital = 50.0
    peak = 50.0
    max_dd = 0.0
    total_fees = 0.0
    equity_curve = [{"timestamp": 0, "equity": 50.0, "date": "Start"}]
    daily_map = defaultdict(lambda: {
        "date": "", "net_pnl": 0.0, "gross_pnl": 0.0, "gross_profit": 0.0, "gross_loss": 0.0, "total_fees": 0.0,
        "trades_count": 0, "wins": 0, "losses": 0
    })

    clist = candles_dict.get("XAUTUSD", [])
    cmap = {c["timestamp"]: (idx, c) for idx, c in enumerate(clist)}
    last_exit_ts = 0

    for idx, t in enumerate(trades, 1):
        sym = "XAUTUSD"
        side = t["side"]
        entry = t["entry_price"]
        sl = t["stop_loss"]
        dist = abs(entry - sl)
        op_ts = t["timestamp"]

        if op_ts < last_exit_ts: continue  # Strict Single-Position (FIFO): Do not open new trade until previous trade closes!
        if op_ts not in cmap: continue
        start_idx, entry_candle = cmap[op_ts]
        if start_idx >= len(clist) - 1: continue

        # Strictly enforce entry within candle [low, high]
        entry = max(entry_candle["low"], min(entry_candle["high"], entry))

        highest = entry
        lowest = entry
        current_sl = sl
        final_r = -1.0
        exit_price = sl
        final_reason = "STOP_LOSS (-1.0R)"
        closed_at_ts = op_ts
        closed_candle = entry_candle
        hit_exit = False

        for fi in range(start_idx + 1, min(len(clist), start_idx + 400)):
            fc = clist[fi]
            c_range = max(0.01, fc["high"] - fc["low"])
            closed_at_ts = fc["timestamp"]
            closed_candle = fc

            if side == "BUY":
                if fc["low"] <= current_sl:
                    hit_exit = True
                    exit_price = min(fc["high"], max(fc["low"], fc["open"] if fc["open"] <= current_sl else current_sl))
                    if current_sl <= sl + 0.01 * dist:
                        final_r = -1.0
                        final_reason = "STOP_LOSS (-1.0R)"
                    else:
                        final_r = max(be_lock, round((exit_price - entry) / dist, 2))
                        final_reason = f"V5_TRAIL_STOP (+{final_r:.1f}R)"
                    break

                tp_price = round(entry + max_macro_rr * dist, 2)
                if fc["high"] >= tp_price:
                    hit_exit = True
                    exit_price = max(fc["low"], min(fc["high"], fc["open"] if fc["open"] >= tp_price else tp_price))
                    final_r = max_macro_rr
                    final_reason = f"V5_MAX_TARGET (+{max_macro_rr:.0f}R)"
                    break

                if fc["high"] > highest: highest = fc["high"]
                gain_r = (highest - entry) / dist

                # Enhanced Dynamic Breathing-Room Ratchet (Desk Audit Fix)
                if gain_r >= be_trigger: current_sl = max(current_sl, round(entry + be_lock * dist, 2))
                if gain_r >= 2.5: current_sl = max(current_sl, round(entry + 1.00 * dist, 2))
                if gain_r >= 5.0: current_sl = max(current_sl, round(entry + 2.50 * dist, 2))
                if gain_r >= 8.0: current_sl = max(current_sl, round(entry + 5.00 * dist, 2))
                if gain_r >= 12.0: current_sl = max(current_sl, round(entry + 8.00 * dist, 2))
                if gain_r >= 18.0: current_sl = max(current_sl, round(entry + 13.00 * dist, 2))
                if gain_r >= 25.0: current_sl = max(current_sl, round(entry + 19.00 * dist, 2))
                if gain_r >= 32.0: current_sl = max(current_sl, round(entry + 25.00 * dist, 2))

            else: # SELL
                if fc["high"] >= current_sl:
                    hit_exit = True
                    exit_price = max(fc["low"], min(fc["high"], fc["open"] if fc["open"] >= current_sl else current_sl))
                    if current_sl >= sl - 0.01 * dist:
                        final_r = -1.0
                        final_reason = "STOP_LOSS (-1.0R)"
                    else:
                        final_r = max(be_lock, round((entry - exit_price) / dist, 2))
                        final_reason = f"V5_TRAIL_STOP (+{final_r:.1f}R)"
                    break

                tp_price = round(entry - max_macro_rr * dist, 2)
                if fc["low"] <= tp_price:
                    hit_exit = True
                    exit_price = max(fc["low"], min(fc["high"], fc["open"] if fc["open"] <= tp_price else tp_price))
                    final_r = max_macro_rr
                    final_reason = f"V5_MAX_TARGET (+{max_macro_rr:.0f}R)"
                    break

                if fc["low"] < lowest: lowest = fc["low"]
                gain_r = (entry - lowest) / dist

                # Enhanced Dynamic Breathing-Room Ratchet (Desk Audit Fix)
                if gain_r >= be_trigger: current_sl = min(current_sl, round(entry - be_lock * dist, 2))
                if gain_r >= 2.5: current_sl = min(current_sl, round(entry - 1.00 * dist, 2))
                if gain_r >= 5.0: current_sl = min(current_sl, round(entry - 2.50 * dist, 2))
                if gain_r >= 8.0: current_sl = min(current_sl, round(entry - 5.00 * dist, 2))
                if gain_r >= 12.0: current_sl = min(current_sl, round(entry - 8.00 * dist, 2))
                if gain_r >= 18.0: current_sl = min(current_sl, round(entry - 13.00 * dist, 2))
                if gain_r >= 25.0: current_sl = min(current_sl, round(entry - 19.00 * dist, 2))
                if gain_r >= 32.0: current_sl = min(current_sl, round(entry - 25.00 * dist, 2))

        if not hit_exit:
            exit_price = closed_candle["close"]
            final_r = round((exit_price - entry) / dist, 1) if side == "BUY" else round((entry - exit_price) / dist, 1)
            final_reason = f"V5_HORIZON_CLOSE ({final_r:+.1f}R)"

        exit_price = max(closed_candle["low"], min(closed_candle["high"], exit_price))
        last_exit_ts = closed_at_ts
        opened_at_str = datetime.fromtimestamp(op_ts, tz=IST).strftime("%Y-%m-%d %H:%M:%S")
        closed_at_str = datetime.fromtimestamp(closed_at_ts, tz=IST).strftime("%Y-%m-%d %H:%M:%S")

        fee = calculate_exact_fees("XAUTUSD", entry, sl, is_maker=(final_r >= 0.0))
        gross = round(final_r * STRICT_RISK_USD, 2)
        net_pnl = round(gross - fee, 2)
        total_fees += fee

        capital += net_pnl
        if capital > peak: peak = capital
        if (peak - capital) > max_dd: max_dd = peak - capital

        d_str = closed_at_str.split(" ")[0] if " " in closed_at_str else "Unknown"
        dm = daily_map[d_str]
        dm["date"] = d_str
        dm["net_pnl"] += net_pnl
        dm["gross_pnl"] += gross
        dm["total_fees"] += fee
        dm["trades_count"] += 1
        if gross > 0: dm["gross_profit"] += gross
        elif gross < 0: dm["gross_loss"] += abs(gross)
        if net_pnl > 0: dm["wins"] += 1
        else: dm["losses"] += 1

        trade_record = {
            "trade_num": idx,
            "symbol": "XAUTUSD",
            "side": side,
            "lots": calc_delta_lots("XAUTUSD", entry, sl, STRICT_RISK_USD),
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": round(entry + max_macro_rr * dist, 2) if side == "BUY" else round(entry - max_macro_rr * dist, 2),
            "exit_price": exit_price,
            "risk_usd": STRICT_RISK_USD,
            "gross_pnl_usd": gross,
            "total_fees_usd": fee,
            "fee_usd": fee,
            "pnl_usd": net_pnl,
            "rr_achieved": final_r,
            "close_reason": final_reason,
            "opened_at": opened_at_str,
            "closed_at": closed_at_str,
            "entry_ts": op_ts,
            "exit_ts": closed_at_ts,
            "conviction_stars": t.get("conviction_stars", 5.0),
            "strategy_name": name,
            "orderflow_notes": t.get("notes", "")
        }
        processed.append(trade_record)
        equity_curve.append({
            "timestamp": op_ts,
            "equity": round(capital, 2),
            "date": d_str
        })

    wins = [tr for tr in processed if tr["pnl_usd"] > 0]
    losses = [tr for tr in processed if tr["pnl_usd"] <= 0]
    win_rate = (len(wins) / len(processed) * 100) if processed else 0.0
    gross_profit = sum(tr["gross_pnl_usd"] for tr in wins)
    gross_loss = abs(sum(tr["gross_pnl_usd"] for tr in losses))
    net_pl = sum(tr["pnl_usd"] for tr in processed)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.0

    daily_pnl = []
    for d, item in sorted(daily_map.items()):
        if not d or d == "Unknown": continue
        d_gp = round(item["gross_profit"], 2)
        d_gl = round(item["gross_loss"], 2)
        d_fees = round(item["total_fees"], 2)
        d_net = round(d_gp - d_gl - d_fees, 2)
        daily_pnl.append({
            "date": d, "net_pnl": d_net, "gross_pnl": round(d_gp - d_gl, 2),
            "gross_profit": d_gp, "gross_loss": d_gl, "total_fees": d_fees,
            "net_pnl_inr": round(d_net * USD_TO_INR, 2),
            "trades_count": item["trades_count"], "wins": item["wins"], "losses": item["losses"]
        })

    return {
        "strategy_name": name,
        "initial_capital": 50.0,
        "final_capital": round(capital, 2),
        "total_trades": len(processed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "total_fees": round(total_fees, 2),
        "net_pl": round(net_pl, 2),
        "net_pl_inr": round(net_pl * USD_TO_INR, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_usd": round(max_dd, 2),
        "max_drawdown_pct": round((max_dd / max(50.0, peak)) * 100, 2),
        "equity_curve": equity_curve,
        "daily_pnl": daily_pnl,
        "daily_calendar": daily_pnl,
        "trades": processed
    }

def main():
    print("=" * 115)
    print("👑 BACKTEST V5: ⚡ XAUTUSD (GOLD) INSTITUTIONAL MULTI-STRATEGY SPECIALIZATION 👑")
    print("   • Dedicated 100% to Gold (XAUTUSD) with Ultra-Low Delta Commodity Fees (0.02124%)")
    print("   • Strict $5.00 Fixed Risk Per Trade • Dynamic Delta Exchange India Lot Calculation")
    print("   • 100% Local Simulation & Interactive HTML Dashboard Generation")
    print("=" * 115)

    db = DatabaseManager()
    c15 = db.get_latest_candles("XAUTUSD", "15m", limit=150000)
    c5 = db.get_latest_candles("XAUTUSD", "5m", limit=150000)
    prepare_15m_data(c15)
    _, h4_map = resample_htf(c15, 240)
    _, h1_map = resample_htf(c15, 60)
    _, m30_map = resample_htf(c15, 30)

    t_first = datetime.fromtimestamp(c15[0]["timestamp"], tz=IST).strftime("%Y-%m-%d") if c15 else "None"
    t_last = datetime.fromtimestamp(c15[-1]["timestamp"], tz=IST).strftime("%Y-%m-%d") if c15 else "None"
    print(f"[*] Loaded XAUTUSD: {len(c15):,} 15m candles, {len(c5):,} 5m candles ({t_first} -> {t_last})\n")

    print("[*] Generating signals for dedicated Multi-Timeframe, Price Action & Order Flow strategies...")
    t_multi_tf = generate_gold_multi_tf_cascade(c15, h4_map, h1_map, m30_map, c5)
    t_of_fusion = generate_gold_pa_orderflow_fusion(c15, h4_map, h1_map, m30_map, c5)
    t_ob = generate_gold_order_block(c15, h4_map, h1_map)
    t_ib = generate_gold_inside_bar_trap(c15, h4_map, h1_map, m30_map)
    t_fvg = generate_gold_fvg_imbalance(c15, h4_map, h1_map, m30_map)
    t_apex = generate_gold_apex_confluence(c15, h4_map, h1_map, m30_map)
    t_br = generate_gold_break_retest(c15, h4_map, h1_map, m30_map)

    print("[*] Applying Desk Journal Filters (06, 07, 14, 23 IST & Friday post-16:00)...")
    t_multi_tf = apply_desk_journal_filters(t_multi_tf)
    t_of_fusion = apply_desk_journal_filters(t_of_fusion)
    t_ob = apply_desk_journal_filters(t_ob)
    t_ib = apply_desk_journal_filters(t_ib)
    t_fvg = apply_desk_journal_filters(t_fvg)
    t_apex = apply_desk_journal_filters(t_apex)
    t_br = apply_desk_journal_filters(t_br)

    print(f"  ✓ 1. Multi-TF 5-Tier Master Confluence : {len(t_multi_tf):,} signals")
    print(f"  ✓ 2. PA + Dual Order Flow (Delta & CVD): {len(t_of_fusion):,} signals")
    print(f"  ✓ 3. PA Order Block Liquidity Retest    : {len(t_ob):,} signals")
    print(f"  ✓ 4. PA Inside Bar False Breakout Trap  : {len(t_ib):,} signals")
    print(f"  ✓ 5. PA Fair Value Gap (FVG) Imbalance  : {len(t_fvg):,} signals")
    print(f"  ✓ 6. Gold Apex Grandmaster Confluence  : {len(t_apex):,} signals")
    print(f"  ✓ 7. PA Swing Break & Retest           : {len(t_br):,} signals")

    print("\n[*] Simulating all Price Action & Order Flow strategies on V5 Trailing Engine...")
    candles_dict = {"XAUTUSD": c15}
    res_multi_tf = simulate_v5_strategy(t_multi_tf, candles_dict, "🏆 1. Multi-TF 5-Tier Master Confluence (4H+1H+30m+15m+5m)", max_macro_rr=40.0, be_trigger=1.6, be_lock=0.30)
    res_of_fusion = simulate_v5_strategy(t_of_fusion, candles_dict, "🌊 2. PA + Dual Order Flow Fusion (Delta & CVD Trend)", max_macro_rr=40.0, be_trigger=1.6, be_lock=0.30)
    res_ob = simulate_v5_strategy(t_ob, candles_dict, "💎 3. PA Order Block Liquidity Retest (ICT S/R)", max_macro_rr=40.0, be_trigger=1.6, be_lock=0.30)
    res_apex = simulate_v5_strategy(t_apex, candles_dict, "👑 4. Gold Apex Grandmaster Confluence (4H+1H+30m+15m)", max_macro_rr=40.0, be_trigger=1.6, be_lock=0.30)
    res_ib = simulate_v5_strategy(t_ib, candles_dict, "⚡ 5. PA Inside Bar False Breakout Trap (Hikkake)", max_macro_rr=40.0, be_trigger=1.6, be_lock=0.30)
    res_fvg = simulate_v5_strategy(t_fvg, candles_dict, "🎯 6. PA Fair Value Gap (FVG) Imbalance Retest", max_macro_rr=40.0, be_trigger=1.6, be_lock=0.30)
    res_br = simulate_v5_strategy(t_br, candles_dict, "🔄 7. PA Swing Break & Retest (Dow Theory)", max_macro_rr=40.0, be_trigger=1.6, be_lock=0.30)

    report_payload = {
        "default_strategy_key": "XAUT_MULTI_TF_MASTER",
        "joint_portfolio": res_multi_tf,
        "per_pair": {"XAUTUSD": res_multi_tf},
        "strategies": {
            "XAUT_MULTI_TF_MASTER": res_multi_tf,
            "XAUT_PA_OF_FUSION": res_of_fusion,
            "XAUT_ORDER_BLOCK": res_ob,
            "XAUT_APEX_CONFLUENCE": res_apex,
            "XAUT_INSIDE_BAR_TRAP": res_ib,
            "XAUT_FVG_IMBALANCE": res_fvg,
            "XAUT_BREAK_RETEST": res_br
        }
    }

    print("\n[*] Rendering reports/backtest_v5.html...")
    reports_dir = BASE_DIR / "reports"
    out_file = generate_backtest_v5_html(report_payload, reports_dir, "backtest_v5.html")
    print(f"✅ Generated Backtest V5 Dashboard for XAUTUSD: {out_file}")

    print("\n" + "=" * 125)
    print("📊 XAUTUSD (GOLD) PRICE ACTION & ORDER FLOW QUANTITATIVE LEADERBOARD SCORECARD (STRICT $5 RISK PER TRADE):")
    print("-" * 125)
    print(f"{'RANK':<5} | {'STRATEGY MODEL':<52} | {'TRADES':<6} | {'WIN RATE':<8} | {'DELTA FEES':<10} | {'REAL NET P&L ($)':<16} | {'REAL NET P&L (₹)':<16} | {'PF':<5} | {'MAX DD':<8}")
    print("-" * 125)

    all_strats = [res_multi_tf, res_of_fusion, res_ob, res_apex, res_ib, res_fvg, res_br]
    all_strats.sort(key=lambda x: x["net_pl"], reverse=True)

    for rank, st in enumerate(all_strats, 1):
        print(f"#{rank:<4} | {st['strategy_name'][:52]:<52} | {st['total_trades']:<6} | {st['win_rate']:<6.1f}% | -${st['total_fees']:<8,.2f} | +${st['net_pl']:<14,.2f} | +₹{st['net_pl_inr']:<14,.0f} | {st['profit_factor']:<5.2f} | -${st['max_drawdown_usd']:<6.2f}")
    print("=" * 125)

if __name__ == "__main__":
    main()
