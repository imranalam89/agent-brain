import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

def generate_live_journal_html(
    output_dir: Path,
    active_positions: Optional[Dict[str, Any]] = None,
    recent_trades: Optional[List[Dict]] = None,
    db_thoughts: Optional[List[Dict]] = None,
    delta_client = None,
    filename: str = "live_journal.html"
) -> Path:
    """
    Renders institutional-grade Real-Time Live Trading Journal for Delta Exchange.
    Features:
    - Interactive P&L Calendar with Daily, Weekly, Monthly, and Custom Date Range filtering
    - Auto-polling every 3 seconds to /api/live-status
    - Live Delta wallet balance (USD / INR)
    - Active concurrent open positions with 4-Phase Lifecycle tracking (Entry -> Scale-Out -> BE -> Runner)
    - Live execution history ledger of trades taken on Delta
    - Real-time AI Brain order flow thought terminal
    """
    file_path = output_dir / filename
    active_positions = active_positions or {}
    recent_trades = recent_trades or []
    db_thoughts = db_thoughts or []

    # Query initial wallet and ticker state if client available
    usd_bal = "0.00"
    inr_bal = "0.00"
    is_connected = False
    account_id = "74634658"

    if delta_client:
        try:
            bal_res = delta_client.get_wallet_balances()
            if bal_res.get("success"):
                is_connected = True
                for b in bal_res.get("result", []):
                    if b.get("asset_symbol") == "USD":
                        usd_bal = f"{float(b.get('balance', 0)):.2f}"
                    elif b.get("asset_symbol") == "INR":
                        inr_bal = f"{float(b.get('balance', 0)):.2f}"
        except Exception:
            pass

    # Filter strictly for real live trades (is_paper == 0 and starts with LIVE_)
    live_closed = [t for t in recent_trades if t.get("status") == "CLOSED" and t.get("is_paper") == 0 and str(t.get("id", "")).startswith("LIVE_")]
    live_open = [t for t in recent_trades if t.get("status") == "OPEN" and t.get("is_paper") == 0 and str(t.get("id", "")).startswith("LIVE_")]
    
    # Calculate contract-specific brokerage fees (XAUT/SLV flat $0.01; BTC/ETH 0.02% Maker / 0.05% Taker)
    total_live_fees = 0.0
    for t in live_closed:
        sym = str(t.get("symbol", "")).upper()
        notional = float(t.get("notional_usd") or 0.0)
        reason = str(t.get("close_reason") or "").upper()
        is_sl = "SL" in reason or "STOP" in reason or "CIRCUIT" in reason
        if "XAUT" in sym or "SLV" in sym:
            fee_usd = 0.01
        else:
            exit_rate = 0.0005 if is_sl else 0.0002
            fee_usd = round(notional * 0.0002 + notional * exit_rate, 4)
        net_pnl = float(t.get("pnl_usd") or 0.0)
        gross_pnl = round(net_pnl + fee_usd, 2)
        t["fee_usd"] = fee_usd
        t["fee_inr"] = round(fee_usd * 90.0, 2)
        t["gross_pnl_usd"] = gross_pnl
        t["pnl_inr"] = round(net_pnl * 90.0, 2)
        total_live_fees += fee_usd

    # Calculate live closed metrics (strictly starts at 0 for real live trades)
    total_closed = len(live_closed)
    wins = [t for t in live_closed if (t.get("pnl_usd") or 0) > 0]
    losses = [t for t in live_closed if (t.get("pnl_usd") or 0) < 0]
    net_pnl = sum((t.get("pnl_usd") or 0) for t in live_closed)
    net_pnl_inr = round(net_pnl * 90.0, 2)
    total_live_fees_inr = round(total_live_fees * 90.0, 2)
    win_rate = round(len(wins) / total_closed * 100, 1) if total_closed else 0.0

    # Filter thoughts for live session
    live_thoughts = [th for th in db_thoughts if "LIVE" in th.get("event_type", "") or "DELTA" in th.get("event_type", "") or "SCALE" in th.get("event_type", "") or "SCAN" in th.get("event_type", "")]
    if not live_thoughts:
        live_thoughts = [
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": "DELTA_LIVE",
                "event_type": "SESSION_INITIALIZED",
                "conviction_stars": 5.0,
                "message": "⚡ Live Trading Session Initialized on Delta Exchange India (User 74634658). Strict $5 risk sizing active. 4-Phase scale-out discipline standing by."
            }
        ]

    trades_json = json.dumps(live_closed)
    thoughts_json = json.dumps(live_thoughts[:25])
    open_json = json.dumps(list(active_positions.values()) if active_positions else live_open)

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Brain | ⚡ Autonomous Delta Live Journal</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body {{ background-color: #07090e; color: #f1f5f9; font-family: system-ui, -apple-system, sans-serif; }}
    .glass-card {{ background: rgba(13, 17, 28, 0.92); backdrop-filter: blur(14px); border: 1px solid #1a233a; }}
    .glass-active {{ background: rgba(16, 185, 129, 0.06); border: 1px solid rgba(16, 185, 129, 0.3); }}
    .glow-dot {{ box-shadow: 0 0 12px #10b981; }}
    .custom-scroll::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    .custom-scroll::-webkit-scrollbar-track {{ background: #0a0d14; }}
    .custom-scroll::-webkit-scrollbar-thumb {{ background: #1f2a44; border-radius: 4px; }}
    .cal-day-active {{ border-color: #3b82f6 !important; box-shadow: 0 0 10px rgba(59, 130, 246, 0.4); }}
    .cal-tab-active {{ background: #10b981 !important; color: #ffffff !important; font-weight: 700; }}
  </style>
</head>
<body class="min-h-screen p-4 sm:p-6 lg:p-8 space-y-6">

  <!-- TOP HEADER -->
  <header class="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 border-b border-slate-800 pb-5">
    <div class="flex items-center gap-3">
      <div class="h-12 w-12 rounded-2xl bg-gradient-to-tr from-emerald-600 via-teal-500 to-cyan-400 flex items-center justify-center font-bold text-white text-2xl shadow-xl shadow-emerald-500/20">
        🧠
      </div>
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-xl sm:text-2xl font-black tracking-tight text-white">AGENT BRAIN • DELTA LIVE JOURNAL</h1>
          <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
            LIVE EXECUTION
          </span>
        </div>
        <p class="text-xs text-slate-400 font-mono mt-0.5">
          Delta Exchange India Account ID: <span class="text-emerald-400 font-bold">{account_id}</span> • Status: <span class="text-emerald-400 font-bold">CONNECTED &amp; ACTIVE</span>
        </p>
      </div>
    </div>

    <!-- NAVIGATION TABS -->
    <div class="flex items-center gap-2 flex-wrap text-xs font-mono">
      <a href="live_journal.html" class="px-3 py-1.5 rounded-xl bg-emerald-500 text-white font-bold transition flex items-center gap-1.5 shadow-lg shadow-emerald-500/20">
        <i data-lucide="radio" class="w-3.5 h-3.5"></i>
        <span>Live Journal</span>
      </a>
      <a href="backtest_v2.html" class="px-3 py-1.5 rounded-xl bg-cyan-500/20 text-cyan-300 hover:text-white border border-cyan-500/40 font-bold transition flex items-center gap-1.5 shadow-lg shadow-cyan-500/10">
        <i data-lucide="cpu" class="w-3.5 h-3.5"></i>
        <span>Backtest V2</span>
      </a>
      <a href="agent_journal.html" class="px-3 py-1.5 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700 font-bold transition flex items-center gap-1.5">
        <i data-lucide="database" class="w-3.5 h-3.5"></i>
        <span>Backtest Ledger</span>
      </a>
      <a href="gold_journal.html" class="px-3 py-1.5 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700 font-bold transition flex items-center gap-1.5">
        <span>🥇 Gold</span>
      </a>
      <a href="silver_journal.html" class="px-3 py-1.5 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700 font-bold transition flex items-center gap-1.5">
        <span>🥈 Silver</span>
      </a>
      <a href="btc_journal.html" class="px-3 py-1.5 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700 font-bold transition flex items-center gap-1.5">
        <span>₿ BTC</span>
      </a>
      <a href="eth_journal.html" class="px-3 py-1.5 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700 font-bold transition flex items-center gap-1.5">
        <span>Ξ ETH</span>
      </a>
      <a href="strategy_guide.html" class="px-3 py-1.5 rounded-xl bg-purple-500/10 text-purple-300 hover:bg-purple-500/20 border border-purple-500/20 font-bold transition flex items-center gap-1.5">
        <i data-lucide="book" class="w-3.5 h-3.5"></i>
        <span>Strategy Guide</span>
      </a>
    </div>
  </header>

  <!-- LIVE ENFORCED STRATEGY BANNER -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-4 border-l-4 border-l-emerald-500 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs font-mono">
    <div class="flex items-center gap-3">
      <div class="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
        <i data-lucide="shield-check" class="w-5 h-5"></i>
      </div>
      <div>
        <div class="font-bold text-white flex items-center gap-2">
          <span>Active Strategy: 👑 Journal Proven Apex Champion (Model: JOURNAL_APEX_CHAMPION)</span>
          <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px]">Delta Futures Live</span>
        </div>
        <p class="text-slate-400 text-[11px] mt-0.5">
          Simultaneous Gold + Silver + BTC + ETH • Strict $5.00 Risk per Trade • 4-Phase Scale-Out Discipline
        </p>
      </div>
    </div>
    <div class="flex items-center gap-2 flex-wrap">
      <span class="px-3 py-1 rounded-xl bg-slate-900 border border-slate-700 text-slate-300">
        Brokerage Fee: <strong class="text-amber-400">XAUT/SLV $0.01 Flat • BTC/ETH 0.02% Maker / 0.05% Taker</strong>
      </span>
      <span class="px-3 py-1 rounded-xl bg-slate-900 border border-slate-700 text-slate-300">
        Leverage: <strong class="text-blue-400">100x BTC/ETH/Gold | 50x Silver</strong>
      </span>
      <span class="px-3 py-1 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-1">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
        <span id="pollTicker">Auto-Sync: 3s</span>
      </span>
    </div>
  </div>

  <!-- OPERATOR LIVE COMMAND & RISK CONTROL COCKPIT -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-5 border-l-4 border-l-cyan-500 shadow-xl font-mono">
    <div class="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
      
      <!-- LEFT: MASTER SLEEP / PAUSE SWITCH -->
      <div class="flex-1 space-y-2">
        <div class="flex items-center gap-2">
          <i data-lucide="power" class="w-5 h-5 text-cyan-400"></i>
          <h2 class="text-sm font-bold text-white uppercase tracking-wider">Engine Master Switch &amp; News Freeze</h2>
          <span id="botStatusBadge" class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span id="botStatusText">ACTIVE (Scanning A+ Setups)</span>
          </span>
        </div>
        <p id="botStatusSubtext" class="text-xs text-slate-400">
          Bot is actively scanning BTC, ETH, Gold, and Silver every 3 seconds for high-confluence entries.
        </p>
        <div class="flex items-center gap-2 flex-wrap pt-1 text-xs">
          <button id="btnToggleBot" onclick="toggleBotMasterStatus()" class="px-3 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 font-bold transition flex items-center gap-1.5">
            <i data-lucide="pause-circle" class="w-4 h-4"></i>
            <span id="btnToggleBotText">Pause Bot (News Sleep)</span>
          </button>
          <button onclick="pauseBotFor(60, 'News Event 1 Hour')" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 font-semibold transition flex items-center gap-1">
            <i data-lucide="clock" class="w-3.5 h-3.5 text-amber-400"></i>
            <span>Sleep 1 Hour</span>
          </button>
          <button onclick="pauseBotFor(120, 'News Event 2 Hours')" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 font-semibold transition flex items-center gap-1">
            <i data-lucide="clock" class="w-3.5 h-3.5 text-amber-400"></i>
            <span>Sleep 2 Hours</span>
          </button>
          <button onclick="resumeBotNow()" class="px-3 py-1.5 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 hover:text-white border border-emerald-500/30 font-semibold transition flex items-center gap-1">
            <i data-lucide="play" class="w-3.5 h-3.5"></i>
            <span>Resume Now</span>
          </button>
        </div>
      </div>

      <!-- RIGHT: DYNAMIC RISK PER TRADE SELECTOR -->
      <div class="lg:border-l lg:border-slate-800 lg:pl-6 space-y-2">
        <div class="flex items-center gap-2">
          <i data-lucide="shield-alert" class="w-5 h-5 text-rose-400"></i>
          <h2 class="text-sm font-bold text-white uppercase tracking-wider">Dynamic Risk Per Trade</h2>
          <span id="currentRiskBadge" class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 text-xs font-bold border border-rose-500/30">
            $5.00 / Trade
          </span>
        </div>
        <p class="text-xs text-slate-400">
          Strict lot sizing applied automatically to all upcoming bracket entries.
        </p>
        <div class="flex items-center gap-2 flex-wrap pt-1 text-xs">
          <button onclick="setRiskAmount(3.0)" class="btn-risk px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-bold transition" data-risk="3">$3</button>
          <button onclick="setRiskAmount(5.0)" class="btn-risk px-3 py-1.5 rounded-xl bg-rose-600 text-white border border-rose-500 font-bold transition shadow-lg shadow-rose-600/30" data-risk="5">$5 (Default)</button>
          <button onclick="setRiskAmount(10.0)" class="btn-risk px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-bold transition" data-risk="10">$10</button>
          <button onclick="setRiskAmount(15.0)" class="btn-risk px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-bold transition" data-risk="15">$15</button>
          
          <div class="flex items-center gap-1 ml-1">
            <span class="text-slate-500 font-bold">$</span>
            <input id="inputCustomRisk" type="number" min="1" max="100" step="0.5" placeholder="Custom" class="w-20 px-2 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-white text-xs font-bold text-center focus:outline-none focus:border-rose-500">
            <button onclick="applyCustomRisk()" class="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-rose-500 hover:text-white text-slate-300 border border-slate-700 font-bold transition">Set</button>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- FINANCIAL COCKPIT STATS -->
  <div class="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 font-mono">
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-emerald-500">
      <span class="text-slate-400 text-xs block mb-1">Delta USD Balance</span>
      <span id="statUsdBal" class="text-2xl font-extrabold text-emerald-400">${usd_bal}</span>
      <span class="text-[11px] text-slate-500 block mt-1">Live from Delta Wallet</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-cyan-500">
      <span class="text-slate-400 text-xs block mb-1">Delta INR Balance</span>
      <span id="statInrBal" class="text-2xl font-extrabold text-cyan-400">₹{inr_bal}</span>
      <span class="text-[11px] text-slate-500 block mt-1">FIU Delta India Wallet</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-purple-500">
      <span class="text-slate-400 text-xs block mb-1">Active Positions</span>
      <span id="statOpenCount" class="text-2xl font-extrabold text-white">{len(active_positions)} / 4</span>
      <span class="text-[11px] text-purple-400 block mt-1">Parallel Non-Blocking</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-amber-500">
      <span class="text-slate-400 text-xs block mb-1">Total Delta Fees</span>
      <span id="statTotalFees" class="text-2xl font-extrabold text-amber-400">-${total_live_fees:.2f}</span>
      <span id="statTotalFeesInr" class="text-[11px] text-amber-500/80 block mt-1 font-bold">~₹{total_live_fees_inr:.2f}</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-rose-500">
      <span class="text-slate-400 text-xs block mb-1">Risk Per Trade</span>
      <span id="statTargetRisk" class="text-2xl font-extrabold text-white">$5.00</span>
      <span class="text-[11px] text-slate-500 block mt-1">Max -$25 Circuit Breaker</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-blue-500">
      <span class="text-slate-400 text-xs block mb-1">Live Net Realized P&L</span>
      <span id="statNetPnl" class="text-2xl font-extrabold {'text-emerald-400' if net_pnl > 0 else ('text-rose-400' if net_pnl < 0 else 'text-white')}">{'+$' if net_pnl > 0 else ('-$' if net_pnl < 0 else '$')}{abs(round(net_pnl, 2)):.2f}</span>
      <span id="statWinRate" class="text-[11px] text-slate-400 block mt-1">{win_rate}% WR ({len(wins)}W/{len(losses)}L)</span>
    </div>
  </div>

  <!-- LIVE TICKERS BAR -->
  <div class="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs">
    <div class="glass-card rounded-xl p-3 flex items-center justify-between border-t-2 border-t-amber-500">
      <div>
        <span class="text-slate-400 text-[11px] block">🥇 Gold (XAUTUSD)</span>
        <span id="ticker_XAUTUSD" class="text-base font-bold text-white">--</span>
      </div>
      <span class="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 text-[10px]">100x Isolated</span>
    </div>
    <div class="glass-card rounded-xl p-3 flex items-center justify-between border-t-2 border-t-cyan-500">
      <div>
        <span class="text-slate-400 text-[11px] block">🥈 Silver (SLVONUSD)</span>
        <span id="ticker_SLVONUSD" class="text-base font-bold text-white">--</span>
      </div>
      <span class="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 text-[10px]">50x Isolated</span>
    </div>
    <div class="glass-card rounded-xl p-3 flex items-center justify-between border-t-2 border-t-orange-500">
      <div>
        <span class="text-slate-400 text-[11px] block">₿ Bitcoin (BTCUSD)</span>
        <span id="ticker_BTCUSD" class="text-base font-bold text-white">--</span>
      </div>
      <span class="px-2 py-0.5 rounded bg-orange-500/10 text-orange-400 text-[10px]">100x Isolated</span>
    </div>
    <div class="glass-card rounded-xl p-3 flex items-center justify-between border-t-2 border-t-purple-500">
      <div>
        <span class="text-slate-400 text-[11px] block">Ξ Ethereum (ETHUSD)</span>
        <span id="ticker_ETHUSD" class="text-base font-bold text-white">--</span>
      </div>
      <span class="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 text-[10px]">100x Isolated</span>
    </div>
  </div>

  <!-- ACTIVE LIVE POSITIONS BOARD -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-6">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <i data-lucide="layers" class="w-5 h-5 text-purple-400"></i>
        <h2 class="text-lg font-bold text-white tracking-tight">Active Live Positions on Delta Exchange</h2>
      </div>
      <span id="activeBadgeCount" class="px-2.5 py-1 rounded-full text-xs font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30 font-mono">
        {len(active_positions)} Open
      </span>
    </div>

    <div id="openPositionsContainer" class="overflow-x-auto">
      <!-- Populated dynamically via JS -->
    </div>
  </div>

  <!-- ======================================================== -->
  <!-- 📅 INTERACTIVE P&L CALENDAR & DATE RANGE ANALYZER COCKPIT -->
  <!-- ======================================================== -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-6 space-y-6">
    <div class="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-slate-800">
      <div>
        <div class="flex items-center gap-2.5">
          <i data-lucide="calendar" class="w-6 h-6 text-emerald-400"></i>
          <h2 class="text-lg font-bold text-white tracking-tight">P&amp;L Performance Calendar &amp; Time Filters</h2>
        </div>
        <p class="text-xs text-slate-400 mt-0.5 font-mono">
          Analyze Daily, Weekly, Monthly, or Custom Date P&amp;L • Click any date tile on the calendar to filter trades
        </p>
      </div>

      <!-- FILTER PRESET TABS -->
      <div class="flex items-center gap-1.5 bg-slate-900/90 p-1.5 rounded-xl border border-slate-800 text-xs font-mono flex-wrap">
        <button id="btnFilterToday" onclick="setFilterPreset('today')" class="px-3 py-1.5 rounded-lg text-slate-300 hover:text-white transition">
          🌟 Today
        </button>
        <button id="btnFilterWeek" onclick="setFilterPreset('week')" class="px-3 py-1.5 rounded-lg text-slate-300 hover:text-white transition">
          📅 This Week
        </button>
        <button id="btnFilterMonth" onclick="setFilterPreset('month')" class="px-3 py-1.5 rounded-lg text-slate-300 hover:text-white transition">
          🗓️ This Month
        </button>
        <button id="btnFilterAll" onclick="setFilterPreset('all')" class="px-3 py-1.5 rounded-lg cal-tab-active transition">
          ♾️ All Time
        </button>
      </div>
    </div>

    <!-- CUSTOM DATE RANGE SELECTOR & PERIOD SUMMARY CARDS -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center font-mono">
      <!-- Custom Date Inputs -->
      <div class="lg:col-span-4 bg-slate-900/60 p-4 rounded-xl border border-slate-800 space-y-3">
        <span class="text-xs font-bold text-slate-300 flex items-center gap-1.5">
          <i data-lucide="sliders" class="w-3.5 h-3.5 text-blue-400"></i>
          Custom Date Range
        </span>
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div>
            <label class="text-[10px] text-slate-400 block mb-1">From Date</label>
            <input type="date" id="customStartDate" class="w-full bg-[#0a0d14] border border-slate-700 rounded-lg p-2 text-white text-xs focus:outline-none focus:border-emerald-500">
          </div>
          <div>
            <label class="text-[10px] text-slate-400 block mb-1">To Date</label>
            <input type="date" id="customEndDate" class="w-full bg-[#0a0d14] border border-slate-700 rounded-lg p-2 text-white text-xs focus:outline-none focus:border-emerald-500">
          </div>
        </div>
        <div class="flex items-center gap-2 pt-1">
          <button onclick="applyCustomDateFilter()" class="flex-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition">
            Apply Date Filter
          </button>
          <button onclick="setFilterPreset('all')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition">
            Reset
          </button>
        </div>
      </div>

      <!-- Selected Period Financial Scorecard -->
      <div class="lg:col-span-8 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 border-l-4 border-l-emerald-500">
          <span class="text-[11px] text-slate-400 block">Period Net P&amp;L</span>
          <span id="periodNetPnl" class="text-xl font-extrabold text-emerald-400">+$0.00</span>
          <span id="periodNetPnlInr" class="text-[10px] text-emerald-400/80 block mt-0.5 font-bold">~₹0.00</span>
          <span id="periodLabel" class="text-[10px] text-slate-500 block mt-1">All Time</span>
        </div>
        <div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 border-l-4 border-l-amber-500">
          <span class="text-[11px] text-slate-400 block">Period Delta Fees</span>
          <span id="periodTotalFees" class="text-xl font-extrabold text-amber-400">-$0.00</span>
          <span id="periodTotalFeesInr" class="text-[10px] text-amber-400/80 block mt-0.5 font-bold">~₹0.00</span>
          <span class="text-[10px] text-slate-500 block mt-1">XAUT/SLV $0.01 | BTC/ETH %</span>
        </div>
        <div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 border-l-4 border-l-blue-500">
          <span class="text-[11px] text-slate-400 block">Period Win Rate</span>
          <span id="periodWinRate" class="text-xl font-extrabold text-blue-400">0.0%</span>
          <span id="periodWinLossCount" class="text-[10px] text-slate-500 block mt-1">0W / 0L</span>
          <span id="periodAvgTrade" class="text-[10px] text-blue-300 block mt-0.5">Avg: $0.00</span>
        </div>
        <div class="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 border-l-4 border-l-purple-500">
          <span class="text-[11px] text-slate-400 block">Trades &amp; Gross P&amp;L</span>
          <div class="flex items-center gap-2">
            <span id="periodGrossProfit" class="text-xs font-bold text-emerald-400 block">+$0.00</span>
            <span id="periodGrossLoss" class="text-xs font-bold text-rose-400 block">-$0.00</span>
          </div>
          <span id="periodTradesCount" class="text-[10px] text-purple-400 block mt-1">0 Trades Executed</span>
        </div>
      </div>
    </div>

    <!-- MONTHLY CALENDAR GRID HEATMAP -->
    <div class="bg-slate-900/50 p-4 rounded-xl border border-slate-800/80">
      <!-- Calendar Nav -->
      <div class="flex items-center justify-between mb-4 font-mono">
        <div class="flex items-center gap-2">
          <button onclick="changeCalendarMonth(-1)" class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition">
            <i data-lucide="chevron-left" class="w-4 h-4"></i>
          </button>
          <span id="calMonthYearTitle" class="text-sm font-bold text-white px-2">September 2026</span>
          <button onclick="changeCalendarMonth(1)" class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition">
            <i data-lucide="chevron-right" class="w-4 h-4"></i>
          </button>
        </div>
        <div class="flex items-center gap-3 text-xs text-slate-400">
          <span class="flex items-center gap-1.5">
            <span class="w-2.5 h-2.5 rounded bg-emerald-500/20 border border-emerald-500/40"></span>
            Profit Day
          </span>
          <span class="flex items-center gap-1.5">
            <span class="w-2.5 h-2.5 rounded bg-rose-500/20 border border-rose-500/40"></span>
            Loss Day
          </span>
          <span class="flex items-center gap-1.5">
            <span class="w-2.5 h-2.5 rounded bg-slate-800 border border-slate-700"></span>
            No Trades
          </span>
        </div>
      </div>

      <!-- Weekday Headers -->
      <div class="grid grid-cols-7 gap-2 text-center text-xs font-mono font-bold text-slate-400 mb-2">
        <div>SUN</div>
        <div>MON</div>
        <div>TUE</div>
        <div>WED</div>
        <div>THU</div>
        <div>FRI</div>
        <div>SAT</div>
      </div>

      <!-- Days Grid (Generated by JS) -->
      <div id="calendarDaysGrid" class="grid grid-cols-7 gap-2 font-mono">
        <!-- Rendered by renderCalendarGrid() -->
      </div>
    </div>
  </div>

  <!-- TWO-COLUMN SECTION: LIVE TRADES LEDGER & AI ORDER FLOW THOUGHTS -->
  <div class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">

    <!-- LEFT: REAL-TIME AI BRAIN THOUGHT LOG -->
    <div class="lg:col-span-5 glass-card rounded-2xl p-5 space-y-3 font-mono flex flex-col h-[520px]">
      <div class="flex items-center justify-between pb-3 border-b border-slate-800">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-emerald-400 glow-dot animate-pulse"></div>
          <h3 class="font-bold text-white text-sm">AI Brain Live Order Flow Stream</h3>
        </div>
        <span class="text-[10px] text-slate-400">Delta Live Terminal</span>
      </div>

      <div id="thoughtsTerminal" class="custom-scroll flex-1 overflow-y-auto space-y-2.5 pr-1">
        <!-- Injected dynamically via JS -->
      </div>
    </div>

    <!-- RIGHT: FILTERED DELTA LIVE TRADES LEDGER -->
    <div class="lg:col-span-7 glass-card rounded-2xl p-5 space-y-3 font-mono flex flex-col h-[520px]">
      <div class="flex items-center justify-between pb-3 border-b border-slate-800">
        <div class="flex items-center gap-2">
          <i data-lucide="check-circle-2" class="w-4 h-4 text-emerald-400"></i>
          <h3 class="font-bold text-white text-sm">Executed Trades Ledger</h3>
        </div>
        <span id="executedCount" class="text-xs text-emerald-400 font-bold bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/20">
          {len(live_closed)} Trades Banked
        </span>
      </div>

      <div class="custom-scroll flex-1 overflow-y-auto pr-1">
        <table class="w-full text-left text-xs">
          <thead class="text-slate-400 border-b border-slate-800 sticky top-0 bg-[#0d111c]">
            <tr>
              <th class="py-2">Time (IST)</th>
              <th>Asset</th>
              <th>Side</th>
              <th>Entry ➔ Exit</th>
              <th>Lots</th>
              <th>Gross P&amp;L ($)</th>
              <th>Fee ($ / ₹)</th>
              <th>Net P&amp;L ($ / ₹)</th>
              <th>R:R</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody id="closedTradesTbody" class="divide-y divide-slate-800/60">
            <!-- Populated dynamically -->
          </tbody>
        </table>
      </div>
    </div>

  </div>

  <footer class="max-w-7xl mx-auto text-center text-xs text-slate-500 font-mono pt-4 border-t border-slate-800">
    Agent Brain v2.0 • Autonomous Delta Live Journal • Dedicated to Disciplined Risk ($5/Trade) • Connected to Delta Exchange India
  </footer>

  <!-- DYNAMIC AUTO-POLLING & INTERACTIVE CALENDAR SCRIPT -->
  <script>
    const INITIAL_OPEN = {open_json};
    const INITIAL_TRADES = {trades_json};
    const INITIAL_THOUGHTS = {thoughts_json};

    let allClosedTrades = Array.isArray(INITIAL_TRADES) ? INITIAL_TRADES : [];
    let currentFilterMode = 'all'; // 'today', 'week', 'month', 'all', 'custom', 'day_click'
    let selectedDateStr = null;
    let customStart = null;
    let customEnd = null;

    // Calendar view state
    let calCurrentDate = new Date(); // defaults to current month

    function getTradeDateStr(trade) {{
      const raw = trade.closed_at || trade.opened_at || "";
      if (!raw) return "";
      const datePart = raw.includes("T") ? raw.split("T")[0] : raw.split(" ")[0];
      return datePart.substring(0, 10);
    }}

    function computeTradeFee(t) {{
      if (t.fee_usd !== undefined && t.fee_usd !== null && !isNaN(Number(t.fee_usd))) {{
        return Number(t.fee_usd);
      }}
      const sym = (t.symbol || "").toUpperCase();
      if (sym.includes("XAUT") || sym.includes("SLV")) {{
        return 0.01;
      }}
      const notional = Number(t.notional_usd || (Number(t.lots || 0) * Number(t.entry_price || 0))) || 0;
      const reason = (t.close_reason || "").toUpperCase();
      const isSl = reason.includes("SL") || reason.includes("STOP") || reason.includes("CIRCUIT");
      const exitRate = isSl ? 0.0005 : 0.0002;
      return Math.round((notional * 0.0002 + notional * exitRate) * 10000) / 10000;
    }}

    function filterTrades(trades) {{
      if (!trades || trades.length === 0) return [];
      const today = new Date();
      const todayStr = today.toISOString().split("T")[0];

      if (currentFilterMode === 'today') {{
        return trades.filter(t => getTradeDateStr(t) === todayStr);
      }}

      if (currentFilterMode === 'week') {{
        // Monday of current week
        const dayOfWeek = today.getDay(); // 0 is Sunday
        const diffToMon = today.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1);
        const monday = new Date(today.setDate(diffToMon));
        const monStr = monday.toISOString().split("T")[0];
        return trades.filter(t => getTradeDateStr(t) >= monStr);
      }}

      if (currentFilterMode === 'month') {{
        const yr = today.getFullYear();
        const mo = String(today.getMonth() + 1).padStart(2, '0');
        const monthPrefix = `${{yr}}-${{mo}}`;
        return trades.filter(t => getTradeDateStr(t).startsWith(monthPrefix));
      }}

      if (currentFilterMode === 'day_click' && selectedDateStr) {{
        return trades.filter(t => getTradeDateStr(t) === selectedDateStr);
      }}

      if (currentFilterMode === 'custom') {{
        return trades.filter(t => {{
          const d = getTradeDateStr(t);
          if (!d) return false;
          if (customStart && d < customStart) return false;
          if (customEnd && d > customEnd) return false;
          return true;
        }});
      }}

      return trades; // 'all'
    }}

    function updatePeriodScorecard(filteredTrades) {{
      const total = filteredTrades.length;
      const wins = filteredTrades.filter(t => (t.pnl_usd || 0) > 0);
      const losses = filteredTrades.filter(t => (t.pnl_usd || 0) < 0);
      const netPnl = filteredTrades.reduce((acc, t) => acc + (t.pnl_usd || 0), 0);
      const totalFees = filteredTrades.reduce((acc, t) => {{
        return acc + computeTradeFee(t);
      }}, 0);
      const grossProfit = wins.reduce((acc, t) => {{
        const gross = t.gross_pnl_usd !== undefined ? Number(t.gross_pnl_usd) : ((t.pnl_usd || 0) + computeTradeFee(t));
        return acc + gross;
      }}, 0);
      const grossLoss = Math.abs(losses.reduce((acc, t) => {{
        const gross = t.gross_pnl_usd !== undefined ? Number(t.gross_pnl_usd) : ((t.pnl_usd || 0) + computeTradeFee(t));
        return acc + gross;
      }}, 0));
      const wr = total > 0 ? ((wins.length / total) * 100).toFixed(1) : "0.0";
      const avgTrade = total > 0 ? (netPnl / total).toFixed(2) : "0.00";
      const netInr = Math.round(netPnl * 90.0 * 100) / 100;
      const feesInr = Math.round(totalFees * 90.0 * 100) / 100;

      const pnlEl = document.getElementById("periodNetPnl");
      pnlEl.innerText = (netPnl >= 0 ? "+$" : "-$") + Math.abs(netPnl).toFixed(2);
      pnlEl.className = "text-xl font-extrabold " + (netPnl > 0 ? "text-emerald-400" : (netPnl < 0 ? "text-rose-400" : "text-white"));

      const pnlInrEl = document.getElementById("periodNetPnlInr");
      if (pnlInrEl) {{
        pnlInrEl.innerText = (netInr >= 0 ? "+₹" : "-₹") + Math.abs(netInr).toFixed(2);
        pnlInrEl.className = "text-[10px] block mt-0.5 font-bold " + (netInr > 0 ? "text-emerald-400/80" : (netInr < 0 ? "text-rose-400/80" : "text-slate-400"));
      }}

      const feeEl = document.getElementById("periodTotalFees");
      if (feeEl) feeEl.innerText = `-$${{totalFees.toFixed(2)}}`;

      const feeInrEl = document.getElementById("periodTotalFeesInr");
      if (feeInrEl) feeInrEl.innerText = `~₹${{feesInr.toFixed(2)}}`;

      document.getElementById("periodWinRate").innerText = `${{wr}}%`;
      document.getElementById("periodWinLossCount").innerText = `${{wins.length}}W / ${{losses.length}}L`;
      document.getElementById("periodTradesCount").innerText = `${{total}} Trades Executed`;
      document.getElementById("periodAvgTrade").innerText = `Avg: ${{avgTrade >= 0 ? '+$' : '-$'}}${{Math.abs(avgTrade)}}`;
      document.getElementById("periodGrossProfit").innerText = `+$${{grossProfit.toFixed(2)}}`;
      document.getElementById("periodGrossLoss").innerText = `-$${{grossLoss.toFixed(2)}}`;

      // Update period label
      let labelText = "All Time";
      if (currentFilterMode === 'today') labelText = "Today";
      else if (currentFilterMode === 'week') labelText = "This Week";
      else if (currentFilterMode === 'month') labelText = "This Month";
      else if (currentFilterMode === 'day_click') labelText = `Date: ${{selectedDateStr}}`;
      else if (currentFilterMode === 'custom') labelText = `${{customStart || 'Start'}} to ${{customEnd || 'End'}}`;
      document.getElementById("periodLabel").innerText = labelText;
    }}

    function setFilterPreset(mode) {{
      currentFilterMode = mode;
      selectedDateStr = null;

      // Update button styles
      ['Today', 'Week', 'Month', 'All'].forEach(name => {{
        const btn = document.getElementById(`btnFilter${{name}}`);
        if (btn) {{
          if (name.toLowerCase() === mode) {{
            btn.className = "px-3 py-1.5 rounded-lg cal-tab-active transition";
          }} else {{
            btn.className = "px-3 py-1.5 rounded-lg text-slate-300 hover:text-white transition";
          }}
        }}
      }});

      renderAll();
    }}

    function applyCustomDateFilter() {{
      const start = document.getElementById("customStartDate").value;
      const end = document.getElementById("customEndDate").value;
      if (!start && !end) return;

      customStart = start;
      customEnd = end;
      currentFilterMode = 'custom';
      selectedDateStr = null;

      // Unhighlight preset buttons
      ['Today', 'Week', 'Month', 'All'].forEach(name => {{
        const btn = document.getElementById(`btnFilter${{name}}`);
        if (btn) btn.className = "px-3 py-1.5 rounded-lg text-slate-300 hover:text-white transition";
      }});

      renderAll();
    }}

    function onCalendarDayClick(dateStr) {{
      selectedDateStr = dateStr;
      currentFilterMode = 'day_click';

      // Unhighlight preset buttons
      ['Today', 'Week', 'Month', 'All'].forEach(name => {{
        const btn = document.getElementById(`btnFilter${{name}}`);
        if (btn) btn.className = "px-3 py-1.5 rounded-lg text-slate-300 hover:text-white transition";
      }});

      renderAll();
    }}

    function changeCalendarMonth(delta) {{
      calCurrentDate.setMonth(calCurrentDate.getMonth() + delta);
      renderCalendarGrid();
    }}

    function renderCalendarGrid() {{
      const container = document.getElementById("calendarDaysGrid");
      const titleEl = document.getElementById("calMonthYearTitle");
      if (!container) return;

      const year = calCurrentDate.getFullYear();
      const month = calCurrentDate.getMonth();
      const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
      titleEl.innerText = `${{monthNames[month]}} ${{year}}`;

      // Aggregate PnL, fees, and trade count by date
      const dailyMap = {{}};
      allClosedTrades.forEach(t => {{
        const dStr = getTradeDateStr(t);
        if (dStr) {{
          if (!dailyMap[dStr]) dailyMap[dStr] = {{ netPnl: 0, fees: 0, count: 0 }};
          dailyMap[dStr].netPnl += (t.pnl_usd || 0);
          dailyMap[dStr].fees += computeTradeFee(t);
          dailyMap[dStr].count += 1;
        }}
      }});

      const firstDayOfMonth = new Date(year, month, 1).getDay();
      const daysInMonth = new Date(year, month + 1, 0).getDate();

      let html = "";

      // Blank slots before first day
      for (let i = 0; i < firstDayOfMonth; i++) {{
        html += `<div class="p-2 min-h-[64px] rounded-lg bg-slate-950/40 border border-slate-900/50 opacity-40"></div>`;
      }}

      // Day slots
      for (let day = 1; day <= daysInMonth; day++) {{
        const dateStr = `${{year}}-${{String(month + 1).padStart(2, '0')}}-${{String(day).padStart(2, '0')}}`;
        const dayData = dailyMap[dateStr];
        const isSelected = selectedDateStr === dateStr;

        let bgClass = "bg-[#0b0f19] border-slate-800/80 hover:border-slate-700";
        let badgeHtml = "";

        if (dayData) {{
          const isProf = dayData.netPnl > 0;
          const isLoss = dayData.netPnl < 0;
          const netSign = isProf ? "+$" : (isLoss ? "-$" : "$");
          const pnlColor = isProf ? "text-emerald-400" : (isLoss ? "text-rose-400" : "text-slate-400");
          if (isProf) {{
            bgClass = "bg-emerald-950/20 border-emerald-500/40 hover:border-emerald-400";
          }} else if (isLoss) {{
            bgClass = "bg-rose-950/20 border-rose-500/40 hover:border-rose-400";
          }}
          const feeInr = Math.round(dayData.fees * 90.0 * 10) / 10;
          badgeHtml = `
            <div class="mt-1 space-y-0.5">
              <span class="text-[11px] font-extrabold ${{pnlColor}} block leading-tight">${{netSign}}${{Math.abs(dayData.netPnl).toFixed(2)}}</span>
              <div class="flex items-center justify-between text-[9px] text-amber-400 font-mono">
                <span>Fee:</span>
                <span>-$${{dayData.fees.toFixed(2)}}</span>
              </div>
              <div class="flex items-center justify-between text-[8px] text-slate-500 font-mono">
                <span>${{dayData.count}} ${{dayData.count === 1 ? 'trd' : 'trds'}}</span>
                <span>~₹${{feeInr.toFixed(1)}}</span>
              </div>
            </div>
          `;
        }}

        const selectedClass = isSelected ? "cal-day-active" : "";

        html += `
          <div onclick="onCalendarDayClick('${{dateStr}}')" class="p-2 min-h-[64px] rounded-lg border ${{bgClass}} ${{selectedClass}} cursor-pointer transition flex flex-col justify-between">
            <span class="text-xs font-bold ${{isSelected ? 'text-blue-400 font-extrabold' : 'text-slate-400'}}">${{day}}</span>
            ${{badgeHtml}}
          </div>
        `;
      }}

      container.innerHTML = html;
    }}

    function renderOpenPositions(positions) {{
      const container = document.getElementById("openPositionsContainer");
      const activeCount = positions ? Object.keys(positions).length : 0;
      document.getElementById("activeBadgeCount").innerText = `${{activeCount}} Open`;
      document.getElementById("statOpenCount").innerText = `${{activeCount}} / 4`;

      if (!positions || activeCount === 0) {{
        container.innerHTML = `
          <div class="p-8 text-center rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col items-center justify-center gap-2">
            <div class="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-400 animate-pulse">
              <i data-lucide="radar" class="w-5 h-5"></i>
            </div>
            <p class="text-sm font-bold text-slate-300">No Open Positions — Agent Brain is Actively Scanning</p>
            <p class="text-xs text-slate-500 max-w-lg">
              Scanning order book DOM imbalances, Footprint absorption, and Session VWAP across <strong>BTCUSD, ETHUSD, XAUTUSD, and SLVONUSD</strong>. High-conviction entry will trigger automatically.
            </p>
          </div>
        `;
        lucide.createIcons();
        return;
      }}

      let html = `
        <table class="w-full text-left text-xs font-mono">
          <thead class="text-slate-400 border-b border-slate-800">
            <tr>
              <th class="py-2">Asset</th>
              <th>Side</th>
              <th>Lots & Size</th>
              <th>Entry Price</th>
              <th>Live Mark Price</th>
              <th>Unrealized P&L ($)</th>
              <th>Stop Loss (SL)</th>
              <th>Target (TP)</th>
              <th>Lifecycle Phase</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800">
      `;

      Object.values(positions).forEach(pos => {{
        const sideClass = pos.side === 'BUY' ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' : 'text-rose-400 bg-rose-500/10 border-rose-500/30';
        const isBeLocked = pos.tp1_hit;
        let phaseBadge = `<span class="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[10px]">Phase 1: Entry Active</span>`;
        if (pos.tp1_hit) {{
          phaseBadge = `<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold text-[10px]">Phase 3: BE Stop Locked ($0 Risk)</span>`;
        }}

        html += `
          <tr class="hover:bg-slate-800/40 transition">
            <td class="py-3 font-bold text-white flex items-center gap-1.5">
              <span>${{pos.symbol.includes('BTC') ? '₿' : (pos.symbol.includes('ETH') ? 'Ξ' : (pos.symbol.includes('XAUT') ? '🥇' : '🥈'))}}</span>
              <span>${{pos.symbol}}</span>
            </td>
            <td><span class="px-2 py-0.5 rounded border text-[10px] font-bold ${{sideClass}}">${{pos.side}}</span></td>
            <td>${{pos.lots}} Lots <span class="text-slate-500">($${{pos.notional_usd || '--'}})</span></td>
            <td class="font-bold text-slate-200">$${{pos.entry_price}}</td>
            <td id="livePrice_${{pos.symbol}}" class="font-bold text-white">Scanning...</td>
            <td id="unrealized_${{pos.symbol}}" class="font-bold text-emerald-400">+$0.00</td>
            <td class="text-rose-400 font-bold">$${{pos.stop_loss}} ${{isBeLocked ? '<span class="text-[9px] text-emerald-400 bg-emerald-500/20 px-1 py-0.2 rounded">BE</span>' : ''}}</td>
            <td class="text-teal-400 font-bold">$${{pos.take_profit}}</td>
            <td>${{phaseBadge}}</td>
          </tr>
        `;
      }});

      html += `</tbody></table>`;
      container.innerHTML = html;
      lucide.createIcons();
    }}

    function renderClosedTrades(trades) {{
      const tbody = document.getElementById("closedTradesTbody");
      if (!trades || trades.length === 0) {{
        tbody.innerHTML = `
          <tr>
            <td colspan="10" class="text-center py-12 text-slate-400">
              <div class="flex flex-col items-center justify-center gap-2">
                <div class="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center text-slate-400">
                  <i data-lucide="inbox" class="w-5 h-5"></i>
                </div>
                <p class="text-sm font-bold text-slate-300">No Trades Found For Selected Filter</p>
                <p class="text-xs text-slate-500 max-w-md">
                  No trades match the selected date range. Select "All Time" or click another day on the calendar above.
                </p>
              </div>
            </td>
          </tr>
        `;
        document.getElementById("executedCount").innerText = "0 Trades";
        lucide.createIcons();
        return;
      }}

      let html = "";
      trades.forEach(t => {{
        const netPnl = (t.pnl_usd || 0);
        const isWin = netPnl > 0;
        const pnlClass = isWin ? 'text-emerald-400' : (netPnl < 0 ? 'text-rose-400' : 'text-slate-300');
        const sideClass = t.side === 'BUY' ? 'text-emerald-400 bg-emerald-500/10' : 'text-rose-400 bg-rose-500/10';
        const rr = t.rr_achieved ? (t.rr_achieved > 0 ? `+${{t.rr_achieved}}R` : `${{t.rr_achieved}}R`) : '--';
        
        const fee = (t.fee_usd !== undefined && t.fee_usd !== null) ? Number(t.fee_usd) : computeTradeFee(t);
        const feeInr = (t.fee_inr !== undefined && t.fee_inr !== null) ? Number(t.fee_inr) : Math.round(fee * 90.0 * 10) / 10;
        const grossPnl = (t.gross_pnl_usd !== undefined && t.gross_pnl_usd !== null) ? Number(t.gross_pnl_usd) : (netPnl + fee);
        const grossClass = grossPnl > 0 ? 'text-emerald-400' : (grossPnl < 0 ? 'text-rose-400' : 'text-slate-300');
        const pnlInr = (t.pnl_inr !== undefined && t.pnl_inr !== null) ? Number(t.pnl_inr) : Math.round(netPnl * 90.0 * 10) / 10;

        html += `
          <tr class="hover:bg-slate-800/40 transition">
            <td class="py-2 text-[11px] text-slate-400">${{t.closed_at || t.opened_at || '--'}}</td>
            <td class="font-bold text-white">${{t.symbol}}</td>
            <td><span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${{sideClass}}">${{t.side}}</span></td>
            <td class="text-[11px] text-slate-300">$${{t.entry_price}} ➔ $${{t.exit_price || '--'}}</td>
            <td>${{t.lots}}</td>
            <td class="font-bold ${{grossClass}}">${{grossPnl >= 0 ? '+$' : '-$'}}${{Math.abs(grossPnl).toFixed(2)}}</td>
            <td><span class="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] font-mono">-$${{fee.toFixed(2)}} <span class="text-amber-500/70">(₹${{feeInr.toFixed(1)}})</span></span></td>
            <td class="font-bold ${{pnlClass}}">${{netPnl >= 0 ? '+$' : '-$'}}${{Math.abs(netPnl).toFixed(2)}} <span class="text-[10px] block text-slate-400 font-normal">~₹${{pnlInr.toFixed(1)}}</span></td>
            <td class="font-bold ${{pnlClass}}">${{rr}}</td>
            <td><span class="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]">${{t.close_reason || 'CLOSED'}}</span></td>
          </tr>
        `;
      }});
      tbody.innerHTML = html;
      document.getElementById("executedCount").innerText = `${{trades.length}} Trades Banked`;
    }}

    function renderThoughts(thoughts) {{
      const terminal = document.getElementById("thoughtsTerminal");
      if (!thoughts || thoughts.length === 0) {{
        terminal.innerHTML = `<div class="text-slate-500 p-4 text-center">Awaiting live order flow events...</div>`;
        return;
      }}

      let html = "";
      thoughts.forEach(th => {{
        const isPositive = th.event_type.includes("WIN") || th.event_type.includes("ENTRY") || th.event_type.includes("SCALE");
        const dotColor = isPositive ? 'bg-emerald-400' : 'bg-cyan-400';

        html += `
          <div class="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition">
            <div class="flex items-center justify-between text-[10px] text-slate-500 mb-1">
              <span class="flex items-center gap-1.5 font-bold text-slate-300">
                <span class="w-1.5 h-1.5 rounded-full ${{dotColor}}"></span>
                <span>[${{th.symbol || 'SYSTEM'}}]</span>
                <span class="text-purple-400">${{th.event_type}}</span>
              </span>
              <span>${{th.timestamp || ''}}</span>
            </div>
            <p class="text-slate-300 text-[11px] leading-relaxed">${{th.message}}</p>
          </div>
        `;
      }});
      terminal.innerHTML = html;
    }}

    function renderAll() {{
      const filtered = filterTrades(allClosedTrades);
      updatePeriodScorecard(filtered);
      renderClosedTrades(filtered);
      renderCalendarGrid();
    }}

    let currentBotStatus = "ACTIVE";
    let currentTargetRisk = 5.0;

    // Interactive Operator Controls: Risk
    async function setRiskAmount(riskVal) {{
      try {{
        const val = parseFloat(riskVal);
        if (isNaN(val) || val <= 0) return;
        const res = await fetch('/api/set-risk', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ risk_usd: val }})
        }});
        const data = await res.json();
        if (data.success) {{
          currentTargetRisk = data.target_risk_usd;
          updateRiskUI(currentTargetRisk);
        }} else {{
          alert("Error setting risk: " + (data.error || "Unknown"));
        }}
      }} catch (err) {{
        console.error("Failed to set risk:", err);
      }}
    }}

    function applyCustomRisk() {{
      const input = document.getElementById("inputCustomRisk");
      if (input && input.value) {{
        setRiskAmount(input.value);
        input.value = "";
      }}
    }}

    function updateRiskUI(risk) {{
      const badge = document.getElementById("currentRiskBadge");
      const statCard = document.getElementById("statTargetRisk");
      if (badge) badge.innerText = `$${{risk.toFixed(2)}} / Trade`;
      if (statCard) statCard.innerText = `$${{risk.toFixed(2)}}`;

      document.querySelectorAll(".btn-risk").forEach(btn => {{
        const bRisk = parseFloat(btn.getAttribute("data-risk"));
        if (Math.abs(bRisk - risk) < 0.01) {{
          btn.className = "btn-risk px-3 py-1.5 rounded-xl bg-rose-600 text-white border border-rose-500 font-bold transition shadow-lg shadow-rose-600/30";
        }} else {{
          btn.className = "btn-risk px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-bold transition";
        }}
      }});
    }}

    // Interactive Operator Controls: Bot Status
    async function setBotStatus(status, durationMinutes = 0, reason = "") {{
      try {{
        const res = await fetch('/api/toggle-bot-status', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ status: status, duration_minutes: durationMinutes, reason: reason }})
        }});
        const data = await res.json();
        if (data.success) {{
          currentBotStatus = data.bot_status;
          updateBotStatusUI(data.bot_status, data.pause_reason, data.pause_until);
        }}
      }} catch (err) {{
        console.error("Failed to update bot status:", err);
      }}
    }}

    function toggleBotMasterStatus() {{
      if (currentBotStatus === "ACTIVE") {{
        setBotStatus("PAUSED", 0, "Manual Operator Pause");
      }} else {{
        setBotStatus("ACTIVE", 0, "Resumed by Operator");
      }}
    }}

    function pauseBotFor(minutes, reason) {{
      setBotStatus("PAUSED", minutes, reason);
    }}

    function resumeBotNow() {{
      setBotStatus("ACTIVE", 0, "Resumed by Operator");
    }}

    function updateBotStatusUI(status, reason, until) {{
      currentBotStatus = status;
      const badge = document.getElementById("botStatusBadge");
      const text = document.getElementById("botStatusText");
      const subtext = document.getElementById("botStatusSubtext");
      const toggleBtn = document.getElementById("btnToggleBot");
      const toggleBtnText = document.getElementById("btnToggleBotText");

      if (status === "PAUSED") {{
        if (badge) {{
          badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1.5";
          badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-amber-400"></span><span>SLEEP / PAUSED</span>`;
        }}
        const timeNote = until ? ` until ${{new Date(until).toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}})}}` : '';
        if (subtext) subtext.innerHTML = `<span class="text-amber-400 font-bold">⏸️ NEW ENTRIES FROZEN (${{reason || 'News Freeze'}}${{timeNote}}).</span> Active bracket positions remain protected on Delta.`;
        if (toggleBtn) toggleBtn.className = "px-3 py-1.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 font-bold transition flex items-center gap-1.5";
        if (toggleBtnText) toggleBtnText.innerText = "Resume Bot (Start Trading)";
      }} else {{
        if (badge) {{
          badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5";
          badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span><span>ACTIVE (Scanning A+ Setups)</span>`;
        }}
        if (subtext) subtext.innerText = "Bot is actively scanning BTC, ETH, Gold, and Silver every 3 seconds for high-confluence entries.";
        if (toggleBtn) toggleBtn.className = "px-3 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 font-bold transition flex items-center gap-1.5";
        if (toggleBtnText) toggleBtnText.innerText = "Pause Bot (News Sleep)";
      }}
      lucide.createIcons();
    }}

    // Real-time API Poller
    async function fetchLiveStatus() {{
      try {{
        const res = await fetch('/api/live-status');
        if (!res.ok) return;
        const data = await res.json();
        if (!data.success) return;

        // Update Bot Master Controls
        if (data.bot_status) {{
          updateBotStatusUI(data.bot_status, data.pause_reason, data.pause_until);
        }}
        if (data.target_risk_usd !== undefined) {{
          currentTargetRisk = parseFloat(data.target_risk_usd);
          updateRiskUI(currentTargetRisk);
        }}

        // Update Wallet Balances
        if (data.wallet) {{
          if (data.wallet.usd !== undefined) document.getElementById("statUsdBal").innerText = `$${{data.wallet.usd}}`;
          if (data.wallet.inr !== undefined) document.getElementById("statInrBal").innerText = `₹${{data.wallet.inr}}`;
        }}

        // Update Tickers
        if (data.tickers) {{
          for (const [sym, price] of Object.entries(data.tickers)) {{
            const el = document.getElementById(`ticker_${{sym}}`);
            if (el && price > 0) el.innerText = `$${{price.toFixed(sym.includes('SLV') ? 3 : (sym.includes('BTC') ? 1 : 2))}}`;
          }}
        }}

        // Update Open Positions
        if (data.open_trades) {{
          const posMap = {{}};
          data.open_trades.forEach(p => posMap[p.symbol] = p);
          renderOpenPositions(posMap);
        }}

        // Update Closed Trades & Live Financial Metrics
        if (data.closed_trades) {{
          allClosedTrades = data.closed_trades;
          const totalC = allClosedTrades.length;
          const winsC = allClosedTrades.filter(t => (t.pnl_usd || 0) > 0).length;
          const lossesC = allClosedTrades.filter(t => (t.pnl_usd || 0) < 0).length;
          const netPnlC = allClosedTrades.reduce((acc, t) => acc + (t.pnl_usd || 0), 0);
          const wrC = totalC > 0 ? ((winsC / totalC) * 100).toFixed(1) : "0.0";
          
          const totalFeesC = allClosedTrades.reduce((acc, t) => acc + computeTradeFee(t), 0);
          const totalFeesInrC = totalFeesC * 90.0;
          const feeStatEl = document.getElementById("statTotalFees");
          if (feeStatEl) feeStatEl.innerText = `-$${{totalFeesC.toFixed(2)}}`;
          const feeStatInrEl = document.getElementById("statTotalFeesInr");
          if (feeStatInrEl) feeStatInrEl.innerText = `~₹${{totalFeesInrC.toFixed(2)}}`;

          const pnlEl = document.getElementById("statNetPnl");
          if (pnlEl) {{
            pnlEl.innerText = (netPnlC > 0 ? "+$" : (netPnlC < 0 ? "-$" : "$")) + Math.abs(netPnlC).toFixed(2);
            pnlEl.className = "text-2xl font-extrabold " + (netPnlC > 0 ? "text-emerald-400" : (netPnlC < 0 ? "text-rose-400" : "text-white"));
          }}
          const wrEl = document.getElementById("statWinRate");
          if (wrEl) wrEl.innerText = `${{wrC}}% WR (${{winsC}}W/${{lossesC}}L)`;

          renderAll();
        }}

        // Update Thoughts
        if (data.thoughts) {{
          renderThoughts(data.thoughts);
        }}

      }} catch (err) {{
        console.warn("Live status fetch notice:", err);
      }}
    }}

    // Initial render
    renderOpenPositions(INITIAL_OPEN);
    renderAll();
    renderThoughts(INITIAL_THOUGHTS);
    lucide.createIcons();

    // Start 3-second live polling loop
    fetchLiveStatus();
    setInterval(fetchLiveStatus, 3000);
  </script>
</body>
</html>
"""

    file_path.write_text(html_content, encoding="utf-8")
    return file_path
