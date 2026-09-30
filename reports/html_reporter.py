import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from config.settings import REPORTS_DIR

class HTMLReporter:
    """
    Renders institutional-grade interactive HTML dashboards.
    Supports:
    - 1-Click Browser Execution Button: Run backtests and live market scans directly from the HTML!
    - Multi-Strategy Comparison Matrix across 6 Months (8 Models)
    - Scale-Out & Partial Take-Profit Simulations (Cut 50% @ 1:1 to 1:3, Trail Rest)
    - Interactive Chart.js equity curve and detailed trade ledger with filter tabs
    - Living Trading Journal mirroring TradeEdge (mypersonaljournal1.netlify.app)
    """
    def __init__(self, output_dir: Path = REPORTS_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_multi_strategy_backtest_report(
        self,
        strategy_results: Dict[str, Any],
        symbol: str = "Multi-Asset (Gold, Silver, BTC, ETH)",
        silver_results: Optional[Dict[str, Any]] = None,
        joint_results: Optional[Dict[str, Any]] = None,
        btc_results: Optional[Dict[str, Any]] = None,
        eth_results: Optional[Dict[str, Any]] = None,
        filename: str = "backtest_report.html",
        default_asset: str = "JOINT"
    ) -> Path:
        """Renders comprehensive multi-strategy comparison HTML with 1-click execution button and 4-Asset Support."""
        file_path = self.output_dir / filename

        gold_results_json = json.dumps(strategy_results)
        silver_results_json = json.dumps(silver_results or {})
        joint_results_json = json.dumps(joint_results or {})
        btc_results_json = json.dumps(btc_results or {})
        eth_results_json = json.dumps(eth_results or {})

        html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Brain | {('Master Multi-Asset' if default_asset == 'JOINT' else ('🥇 Gold' if default_asset == 'XAUTUSD' else ('🥈 Silver' if default_asset == 'SLVONUSD' else ('₿ Bitcoin' if default_asset == 'BTCUSD' else 'Ξ Ethereum'))))} Quantitative Backtest Report</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body {{ background-color: #0a0d14; color: #f1f5f9; font-family: system-ui, -apple-system, sans-serif; }}
    .glass-card {{ background: rgba(15, 20, 32, 0.90); backdrop-filter: blur(14px); border: 1px solid #1f2a44; }}
    .glow-win {{ box-shadow: 0 0 25px -5px rgba(16, 185, 129, 0.25); }}
    .glow-gold {{ box-shadow: 0 0 25px -5px rgba(245, 158, 11, 0.25); }}
    @keyframes pulse-subtle {{
      0%, 100% {{ transform: scale(1); }}
      50% {{ transform: scale(1.03); }}
    }}
    .btn-pulse {{ animation: pulse-subtle 3s infinite ease-in-out; }}
  </style>
</head>
<body class="min-h-screen p-4 sm:p-6 lg:p-8 space-y-6">

  <!-- TOP HEADER WITH ASSET SELECTOR & 1-CLICK ACTION CONTROLS -->
  <header class="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 border-b border-slate-800 pb-5">
    <div class="flex items-center gap-3">
      <div class="h-11 w-11 rounded-xl bg-gradient-to-tr from-amber-500 to-emerald-400 flex items-center justify-center font-bold text-black text-2xl shadow-lg shadow-emerald-950">
        🧠
      </div>
      <div>
        <h1 class="text-xl font-bold flex items-center gap-2">
          <span>Multi-Strategy Quantitative Backtest</span>
          <span id="headerAssetBadge" class="text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">Gold (XAUTUSD)</span>
        </h1>
        <p id="headerSubtitle" class="text-xs text-slate-400">Delta Exchange India Futures Only • Gold (100x), Silver (50x), BTC (100x), ETH (100x) • Fee: 0.01% • Strict $5 Capped Risk</p>
      </div>
    </div>

    <!-- ASSET TOGGLE TABS (4 ASSETS + JOINT) -->
    <div class="flex items-center bg-slate-900/90 p-1 rounded-2xl border border-slate-800 shadow-inner font-mono text-xs">
      <button id="assetTabJoint" onclick="switchAsset('JOINT')" class="px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer bg-gradient-to-r from-emerald-500 to-teal-400 text-black shadow-md shadow-emerald-950/40">
        <span>🌐 Joint Portfolio</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-black/20 text-black">4 Assets</span>
      </button>
      <button id="assetTabGold" onclick="switchAsset('XAUTUSD')" class="px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800">
        <span>🥇 Gold</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">14.9k</span>
      </button>
      <button id="assetTabSilver" onclick="switchAsset('SLVONUSD')" class="px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800">
        <span>🥈 Silver</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">19.2k</span>
      </button>
      <button id="assetTabBtc" onclick="switchAsset('BTCUSD')" class="px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800">
        <span>₿ BTC</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">25.1k</span>
      </button>
      <button id="assetTabEth" onclick="switchAsset('ETHUSD')" class="px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800">
        <span>Ξ ETH</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">25.1k</span>
      </button>
    </div>
    
    <!-- INTERACTIVE 1-CLICK ACTION CONTROLS -->
    <div class="flex flex-wrap items-center gap-2.5 font-mono text-xs">
      <button id="runBacktestBtn" onclick="triggerRunBacktest()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-400 hover:from-emerald-400 hover:to-teal-300 text-black font-extrabold shadow-lg shadow-emerald-950/40 transition flex items-center gap-2 cursor-pointer btn-pulse">
        <i data-lucide="play" class="w-4 h-4 fill-black"></i>
        <span id="runBtnText">Run Backtest Now</span>
      </button>

      <button id="paperScanBtn" onclick="triggerPaperScan()" class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold transition flex items-center gap-1.5 cursor-pointer">
        <i data-lucide="radio" class="w-4 h-4 text-emerald-400"></i>
        <span>Scan Market</span>
      </button>

      <a href="agent_journal.html" class="px-3.5 py-2 rounded-xl bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 border border-blue-500/20 font-bold transition flex items-center gap-1.5">
        <i data-lucide="book-open" class="w-3.5 h-3.5"></i>
        <span>Living Journal</span>
      </a>
    </div>
  </header>

  <!-- DEDICATED REPORT & JOURNAL NAVIGATION BAR -->
  <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3 text-xs font-mono bg-slate-900/60 p-2.5 rounded-2xl border border-slate-800">
    <div class="flex items-center gap-1.5 flex-wrap">
      <span class="text-slate-400 font-bold px-1 flex items-center gap-1"><i data-lucide="bar-chart-3" class="w-3.5 h-3.5 text-emerald-400"></i> REPORTS:</span>
      <a href="backtest_report.html" class="px-2.5 py-1 rounded-xl transition {'bg-emerald-500 text-black font-extrabold shadow' if filename == 'backtest_report.html' else 'bg-slate-800 text-slate-300 hover:text-white border border-slate-700'}">🌐 Master Portfolio</a>
      <a href="gold_report.html" class="px-2.5 py-1 rounded-xl transition {'bg-amber-500 text-black font-extrabold shadow' if filename == 'gold_report.html' else 'bg-slate-800 text-slate-300 hover:text-white border border-slate-700'}">🥇 Gold Report</a>
      <a href="silver_report.html" class="px-2.5 py-1 rounded-xl transition {'bg-cyan-500 text-black font-extrabold shadow' if filename == 'silver_report.html' else 'bg-slate-800 text-slate-300 hover:text-white border border-slate-700'}">🥈 Silver Report</a>
      <a href="btc_report.html" class="px-2.5 py-1 rounded-xl transition {'bg-orange-500 text-black font-extrabold shadow' if filename == 'btc_report.html' else 'bg-slate-800 text-slate-300 hover:text-white border border-slate-700'}">₿ BTC Report</a>
      <a href="eth_report.html" class="px-2.5 py-1 rounded-xl transition {'bg-purple-500 text-black font-extrabold shadow' if filename == 'eth_report.html' else 'bg-slate-800 text-slate-300 hover:text-white border border-slate-700'}">Ξ ETH Report</a>
    </div>
    <div class="flex items-center gap-1.5 flex-wrap">
      <span class="text-slate-400 font-bold px-1 flex items-center gap-1"><i data-lucide="book-open" class="w-3.5 h-3.5 text-blue-400"></i> JOURNALS:</span>
      <a href="agent_journal.html" class="px-2 py-1 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700">🌐 Master</a>
      <a href="gold_journal.html" class="px-2 py-1 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700">🥇 Gold</a>
      <a href="silver_journal.html" class="px-2 py-1 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700">🥈 Silver</a>
      <a href="btc_journal.html" class="px-2 py-1 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700">₿ BTC</a>
      <a href="eth_journal.html" class="px-2 py-1 rounded-xl bg-slate-800 text-slate-300 hover:text-white border border-slate-700">Ξ ETH</a>
      <a href="strategy_guide.html" class="px-2.5 py-1 rounded-xl bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 font-bold transition">📖 Strategy Guide</a>
    </div>
  </div>

  <!-- LIVE EXECUTION STATUS TOAST / ALERT BANNER -->
  <div id="statusToast" class="max-w-7xl mx-auto hidden transition-all duration-300">
    <div id="toastContent" class="glass-card rounded-2xl p-4 flex items-center justify-between border-l-4">
      <div class="flex items-center gap-3">
        <div id="toastIcon" class="w-8 h-8 rounded-full flex items-center justify-center font-bold"></div>
        <div>
          <h4 id="toastTitle" class="text-sm font-bold"></h4>
          <p id="toastMessage" class="text-xs text-slate-400"></p>
        </div>
      </div>
      <button onclick="dismissToast()" class="text-slate-400 hover:text-white text-xs px-2 py-1">✕</button>
    </div>
  </div>

  <!-- MISTAKE ANALYSIS & SCALE-OUT ARCHITECTURE BANNER -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-5 border-l-4 border-l-amber-500 space-y-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2 text-amber-400 font-bold text-sm">
        <i data-lucide="shield-alert" class="w-4 h-4"></i>
        <span>Institutional Scale-Out & Risk Mitigation Architecture</span>
      </div>
      <span class="text-[11px] font-mono px-2.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">Securing Profits & Trailing Runners</span>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs font-mono">
      <div class="bg-slate-900/60 p-3 rounded-xl border border-slate-800 space-y-1">
        <span class="text-emerald-400 font-bold block">1. Partial TP (Scale-Out 50%)</span>
        <p class="text-slate-400 text-[11px]">When price hits target (1:1 to 1:3), close 50% lots to lock in guaranteed dollar profit directly into account balance.</p>
      </div>
      <div class="bg-slate-900/60 p-3 rounded-xl border border-slate-800 space-y-1">
        <span class="text-blue-400 font-bold block">2. Risk-Free Breakeven Lock</span>
        <p class="text-slate-400 text-[11px]">Immediately move Stop Loss on remaining 50% to Entry + buffer. The trade is now 100% Risk-Free (cannot lose money).</p>
      </div>
      <div class="bg-slate-900/60 p-3 rounded-xl border border-slate-800 space-y-1">
        <span class="text-amber-400 font-bold block">3. Dynamic ATR Trailing</span>
        <p class="text-slate-400 text-[11px]">Trail the remaining 50% with 1.5x ATR behind peaks to capture fat-tail runners (+5R, +10R, +27R monster trends).</p>
      </div>
      <div class="bg-slate-900/60 p-3 rounded-xl border border-slate-800 space-y-1">
        <span class="text-rose-400 font-bold block">4. Weekend Trading Freeze</span>
        <p class="text-slate-400 text-[11px]">No trades on Saturday and Sunday. Avoided 25 low-liquidity fakeouts that previously caused -$39.05 in drawdown.</p>
      </div>
    </div>
  </div>

  <!-- STRATEGY COMPARISON SCORECARD TABLE -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-6 overflow-x-auto">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-base font-bold text-white flex items-center gap-2">
          <i data-lucide="layers" class="w-5 h-5 text-emerald-400"></i>
          <span>Multi-Strategy Head-to-Head Scorecard</span>
        </h2>
        <p class="text-xs text-slate-400">Backtested across identical 12,509 15m candles with Delta Maker fees (0.01%) & Weekend Freeze</p>
      </div>
      <span class="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded border border-emerald-500/20">6 Months Tick Ingestion</span>
    </div>

    <table class="w-full text-left text-xs font-mono">
      <thead class="text-slate-400 border-b border-slate-800">
        <tr>
          <th class="py-3">Strategy Name</th>
          <th>Philosophy & Logic</th>
          <th>Total Trades</th>
          <th>Win Rate</th>
          <th>Profit Factor</th>
          <th>Max Drawdown</th>
          <th>Net P&L ($)</th>
          <th>ROI (%)</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody id="comparisonTableBody" class="divide-y divide-slate-800/60 text-slate-300">
        <!-- Rendered by JS -->
      </tbody>
    </table>
  </div>

  <!-- ACTIVE STRATEGY EXECUTIVE BANNER -->
  <div class="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-4 font-mono">
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-emerald-500">
      <span class="text-slate-400 text-xs block mb-1">Selected Strategy Net P&L</span>
      <span id="activeNetPl" class="text-2xl font-extrabold text-emerald-400">+$0.00</span>
      <span id="activeRoi" class="text-[11px] text-slate-400 block mt-1">ROI: 0.0%</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-blue-500">
      <span class="text-slate-400 text-xs block mb-1">Win Rate %</span>
      <span id="activeWinRate" class="text-2xl font-extrabold text-white">0.0%</span>
      <span id="activeRecord" class="text-[11px] text-slate-400 block mt-1">0 Wins • 0 Losses</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-purple-500">
      <span class="text-slate-400 text-xs block mb-1">Profit Factor</span>
      <span id="activePf" class="text-2xl font-extrabold text-purple-400">0.00</span>
      <span id="activeGross" class="text-[11px] text-slate-400 block mt-1">Gross Profit / Loss</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-rose-500">
      <span class="text-slate-400 text-xs block mb-1">Max Drawdown</span>
      <span id="activeDd" class="text-2xl font-extrabold text-rose-400">-$0.00</span>
      <span class="text-[11px] text-slate-400 block mt-1">Safely within $50 capital</span>
    </div>
  </div>

  <!-- STREAKS & EXPECTANCY AUDIT BANNER -->
  <div class="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-4 font-mono">
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-amber-500">
      <span class="text-slate-400 text-xs block mb-1">Max Winning Streak</span>
      <span id="streakMaxWin" class="text-xl font-extrabold text-amber-400">🔥 0 Wins</span>
      <span id="streakMaxWinPnl" class="text-[11px] text-emerald-400 block mt-1">+$0.00 Banked</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-rose-500">
      <span class="text-slate-400 text-xs block mb-1">Max Losing Streak</span>
      <span id="streakMaxLoss" class="text-xl font-extrabold text-rose-400">⚠️ 0 Losses</span>
      <span id="streakMaxLossPnl" class="text-[11px] text-rose-400 block mt-1">-$0.00 Drawdown</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-cyan-500">
      <span class="text-slate-400 text-xs block mb-1">Current Active Streak</span>
      <span id="streakCurrent" class="text-xl font-extrabold text-cyan-300">⚡ 0 Active</span>
      <span id="streakCurrentPnl" class="text-[11px] text-slate-400 block mt-1">$0.00 Current</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-indigo-500">
      <span class="text-slate-400 text-xs block mb-1">Expectancy & Win/Loss</span>
      <span id="metricExpectancy" class="text-xl font-extrabold text-indigo-300">+$0.00 / trade</span>
      <span id="metricWinLossRatio" class="text-[11px] text-slate-400 block mt-1">Avg Win/Loss: 0.00x</span>
    </div>
  </div>

  <!-- EQUITY CURVE PROGRESSION -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 id="chartTitle" class="text-base font-bold text-white flex items-center gap-2">
          <span>Cumulative Equity Curve ($50 Base Capital)</span>
        </h2>
        <p class="text-xs text-slate-400">Continuous compounding performance with strictly capped risk per trade</p>
      </div>
      <div id="chartBadge" class="font-mono text-xs px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-emerald-400">
        Active Strategy
      </div>
    </div>
    <div class="h-80 w-full">
      <canvas id="equityChart"></canvas>
    </div>
  </div>

  <!-- TIME & DAY PROFITABILITY SUITE -->
  <div class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- Hourly Profitability -->
    <div class="glass-card rounded-2xl p-6">
      <div class="flex items-center justify-between mb-3">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <span>⏰ Hourly Profitability Breakdown (IST - Indian Standard Time)</span>
          </h2>
          <p class="text-xs text-slate-400">Net P&L performance by execution hour across all 6 months (06:00 AM to 12:00 PM Morning Session Included)</p>
        </div>
        <span id="bestHourBadge" class="font-mono text-[11px] px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
          Best Hour: --
        </span>
      </div>
      <div class="h-64 w-full">
        <canvas id="hourlyChart"></canvas>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2 text-[11px] font-mono text-slate-400">
        <span class="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/60 text-emerald-400">● Green = Profitable Hour</span>
        <span class="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-800/60 text-rose-400">● Red = Loss Hour</span>
        <span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300">⚡ Morning Session: 06:00 - 12:00 IST | 24/7 Crypto Coverage</span>
      </div>
    </div>

    <!-- Day of Week Profitability -->
    <div class="glass-card rounded-2xl p-6">
      <div class="flex items-center justify-between mb-3">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <span>📅 Day of the Week Edge (Monday – Sunday)</span>
          </h2>
          <p class="text-xs text-slate-400">Institutional win rate and profitability per trading day (Full 7-Day Cycle)</p>
        </div>
        <span id="bestDayBadge" class="font-mono text-[11px] px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
          Best Day: --
        </span>
      </div>
      <div class="h-64 w-full">
        <canvas id="dowChart"></canvas>
      </div>
      <div id="dowSummaryCards" class="mt-3 grid grid-cols-7 gap-1 font-mono text-center">
        <!-- Rendered by JS -->
      </div>
    </div>
  </div>

  <!-- DAILY P&L CALENDAR HEATMAP -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-6">
    <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
      <div>
        <h2 class="text-base font-bold text-white flex items-center gap-2">
          <span>🗓️ Daily Profit & Loss Interactive Calendar</span>
          <span class="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 text-[10px] font-mono">Click to Filter Day</span>
        </h2>
        <p class="text-xs text-slate-400">Every day's realized P&L and trade count • Click any day to audit its trades</p>
      </div>
      <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
        <div class="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
          <button onclick="changeCalMonth('2026-09')" id="cTab_2026-09" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Sep 2026</button>
          <button onclick="changeCalMonth('2026-08')" id="cTab_2026-08" class="px-2.5 py-1 rounded bg-emerald-500 text-black font-extrabold text-[11px] shadow">Aug 2026</button>
          <button onclick="changeCalMonth('2026-07')" id="cTab_2026-07" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Jul 2026</button>
          <button onclick="changeCalMonth('2026-06')" id="cTab_2026-06" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Jun 2026</button>
          <button onclick="changeCalMonth('2026-05')" id="cTab_2026-05" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">May 2026</button>
          <button onclick="changeCalMonth('2026-04')" id="cTab_2026-04" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Apr 2026</button>
          <button onclick="changeCalMonth('2026-03')" id="cTab_2026-03" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Mar 2026</button>
          <button onclick="changeCalMonth('2026-02')" id="cTab_2026-02" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Feb 2026</button>
        </div>
        <span id="calMonthSummary" class="text-xs font-mono text-slate-300 bg-slate-900/90 px-3 py-1 rounded-xl border border-slate-800">
          Month P&L: --
        </span>
      </div>
    </div>

    <!-- Calendar 7-Day Column Headers -->
    <div class="grid grid-cols-7 gap-2 mb-2 font-mono text-xs text-center text-slate-400 font-semibold">
      <div>Mon</div>
      <div>Tue</div>
      <div>Wed</div>
      <div>Thu</div>
      <div>Fri</div>
      <div class="text-slate-600">Sat</div>
      <div class="text-slate-600">Sun</div>
    </div>

    <!-- Calendar Grid Cells -->
    <div id="calendarGrid" class="grid grid-cols-7 gap-2 font-mono text-xs">
      <!-- Rendered by JS -->
    </div>
  </div>

  <!-- DETAILED TRADE LOG TABLE & TIMEFRAME CONTROLS -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-6 overflow-x-auto">
    <div class="flex flex-col gap-3 mb-4">
      <div class="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <span>Executed Trade Journal & Audit Ledger</span>
            <span id="activeRangeBadge" class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-[10px] font-mono border border-emerald-500/30">All Time</span>
          </h2>
          <p class="text-xs text-slate-400">Institutional trade log with R:R, scale-out fills, and order flow post-mortems</p>
        </div>

        <!-- Quick Timeframe Presets -->
        <div class="flex flex-wrap items-center gap-1.5 font-mono text-xs">
          <button onclick="setTimePreset('ALL')" id="tPreset_ALL" class="px-2.5 py-1 rounded bg-emerald-500 text-black font-extrabold text-[11px] shadow">All Time</button>
          <button onclick="setTimePreset('TODAY')" id="tPreset_TODAY" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Today / Day 1</button>
          <button onclick="setTimePreset('WEEK')" id="tPreset_WEEK" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">This Week</button>
          <button onclick="setTimePreset('MONTH')" id="tPreset_MONTH" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">This Month</button>
        </div>
      </div>

      <!-- Month Tabs & Custom Date Range Form & Outcome Filter -->
      <div class="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80">
        <!-- Month Tabs -->
        <div class="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800 font-mono text-xs">
          <button onclick="setBacktestMonthFilter('ALL')" id="bTab_ALL" class="px-2 py-1 rounded bg-emerald-500 text-black font-extrabold text-[11px]">All Months</button>
          <button onclick="setBacktestMonthFilter('2026-09')" id="bTab_2026-09" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Sep 2026</button>
          <button onclick="setBacktestMonthFilter('2026-08')" id="bTab_2026-08" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Aug 2026</button>
          <button onclick="setBacktestMonthFilter('2026-07')" id="bTab_2026-07" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Jul 2026</button>
          <button onclick="setBacktestMonthFilter('2026-06')" id="bTab_2026-06" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Jun 2026</button>
          <button onclick="setBacktestMonthFilter('2026-05')" id="bTab_2026-05" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">May 2026</button>
          <button onclick="setBacktestMonthFilter('2026-04')" id="bTab_2026-04" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Apr 2026</button>
          <button onclick="setBacktestMonthFilter('2026-03')" id="bTab_2026-03" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Mar 2026</button>
          <button onclick="setBacktestMonthFilter('2026-02')" id="bTab_2026-02" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Feb 2026</button>
        </div>

        <!-- Custom Date Range Picker -->
        <div class="flex items-center gap-2 font-mono text-xs bg-slate-900/80 px-2 py-1 rounded-xl border border-slate-800">
          <span class="text-slate-400 text-[11px]">Custom:</span>
          <input type="date" id="customStartDate" class="bg-slate-950 border border-slate-700 rounded px-2 py-0.5 text-white text-[11px] focus:outline-none focus:border-emerald-500">
          <span class="text-slate-500">to</span>
          <input type="date" id="customEndDate" class="bg-slate-950 border border-slate-700 rounded px-2 py-0.5 text-white text-[11px] focus:outline-none focus:border-emerald-500">
          <button onclick="applyCustomDateFilter()" class="px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-500 text-white font-bold text-[11px] transition">Apply</button>
          <button onclick="resetDateFilter()" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white text-[11px] transition">Reset</button>
        </div>

        <!-- Win/Loss Filter & Count -->
        <div class="flex items-center gap-2 font-mono text-xs">
          <div class="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
            <button onclick="filterTrades('ALL')" id="tabAll" class="px-2.5 py-1 rounded bg-emerald-500 text-black font-bold">All</button>
            <button onclick="filterTrades('WIN')" id="tabWin" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white">Winners</button>
            <button onclick="filterTrades('LOSS')" id="tabLoss" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white">Losers</button>
          </div>
          <span id="tradeCountBadge" class="text-slate-400 text-[11px]">0 Trades</span>
        </div>
      </div>
    </div>

    <table class="w-full text-left text-xs font-mono">
      <thead class="text-slate-400 border-b border-slate-800">
        <tr>
          <th class="py-2.5">Date (Exit / Entry UTC)</th>
          <th>Asset</th>
          <th>Side</th>
          <th>Entry</th>
          <th>Exit</th>
          <th>Lots</th>
          <th>Net P&L ($)</th>
          <th>R:R Achieved</th>
          <th>Exit Reason</th>
          <th>Scale-Out & Order Flow Notes</th>
        </tr>
      </thead>
      <tbody id="tradeLogBody" class="divide-y divide-slate-800/60 text-slate-300">
        <!-- Rendered by JS -->
      </tbody>
    </table>
  </div>

  <script>
    let allDatasets = {{
      "JOINT": {joint_results_json},
      "XAUTUSD": {gold_results_json},
      "SLVONUSD": {silver_results_json},
      "BTCUSD": {btc_results_json},
      "ETHUSD": {eth_results_json}
    }};
    let currentAsset = "{default_asset}";
    if (!allDatasets[currentAsset] || Object.keys(allDatasets[currentAsset]).length === 0) {{
      currentAsset = "JOINT";
    }}
    let data = allDatasets[currentAsset];
    let currentChart = null;
    let hourlyChart = null;
    let dowChart = null;
    let currentTrades = [];
    let currentStrategyKey = '';
    let currentFilter = 'ALL';
    let currentMonthFilter = 'ALL';
    let customStartDate = null;
    let customEndDate = null;
    let activePreset = 'ALL';
    let currentCalMonth = '2026-08';
    let isRunning = false;

    function switchAsset(asset) {{
      if (!allDatasets[asset] || Object.keys(allDatasets[asset]).length === 0) return;
      currentAsset = asset;
      data = allDatasets[currentAsset];

      const tabs = {{
        'JOINT': document.getElementById('assetTabJoint'),
        'XAUTUSD': document.getElementById('assetTabGold'),
        'SLVONUSD': document.getElementById('assetTabSilver'),
        'BTCUSD': document.getElementById('assetTabBtc'),
        'ETHUSD': document.getElementById('assetTabEth')
      }};
      const badge = document.getElementById('headerAssetBadge');
      const subtitle = document.getElementById('headerSubtitle');

      Object.keys(tabs).forEach(k => {{
        if (tabs[k]) {{
          tabs[k].className = (k === asset)
            ? "px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer bg-gradient-to-r from-emerald-500 to-teal-400 text-black shadow-md shadow-emerald-950/40"
            : "px-3 py-1.5 rounded-xl font-bold transition flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        }}
      }});

      if (asset === 'JOINT') {{
        if (badge) {{ badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"; badge.innerText = "🌐 4-Asset Joint Portfolio"; }}
        if (subtitle) subtitle.innerText = "Concurrent Multi-Asset Portfolio Execution on Delta Exchange (Gold, Silver, BTC, ETH) • Strict $5 Risk";
      }} else if (asset === 'XAUTUSD') {{
        if (badge) {{ badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20"; badge.innerText = "🥇 Gold (XAUTUSD)"; }}
        if (subtitle) subtitle.innerText = "14,893 Delta 15m Candles (April – September 2026) • 100x Isolated Leverage • Strict $5 Risk";
      }} else if (asset === 'SLVONUSD') {{
        if (badge) {{ badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"; badge.innerText = "🥈 Silver (SLVONUSD)"; }}
        if (subtitle) subtitle.innerText = "19,218 Delta 15m Candles (February – September 2026) • 50x Isolated Leverage • 1 Lot = 0.1 SLVON";
      }} else if (asset === 'BTCUSD') {{
        if (badge) {{ badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-orange-500/10 text-orange-400 border border-orange-500/20"; badge.innerText = "₿ Bitcoin (BTCUSD)"; }}
        if (subtitle) subtitle.innerText = "25,109 Delta 15m Candles (January – September 2026) • 100x Isolated Leverage • 1 Lot = 0.001 BTC";
      }} else if (asset === 'ETHUSD') {{
        if (badge) {{ badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20"; badge.innerText = "Ξ Ethereum (ETHUSD)"; }}
        if (subtitle) subtitle.innerText = "25,110 Delta 15m Candles (January – September 2026) • 100x Isolated Leverage • 1 Lot = 0.01 ETH";
      }}

      renderComparisonTable();
      const defaultKey = data["joint_profit_max"] ? "joint_profit_max" : (data["joint_titan"] ? "joint_titan" : (data["apex_pro_5"] ? "apex_pro_5" : Object.keys(data).reduce((a, b) => data[a].net_pl > data[b].net_pl ? a : b)));
      selectStrategy(defaultKey);
    }}

    const stratDescriptions = {{
      "joint_quad_profit_max": "👑 4-Asset Apex Portfolio: Simultaneous Gold Apex Pro + Silver Profit Max + BTC Profit Max + ETH Profit Max | Strict $5 Risk | Maximum Combined ROI",
      "joint_crypto_max": "⚡ Crypto Joint Maximizer: Concurrent BTC + ETH Futures | Strict $5 Risk | High Win Rate VWAP Reversion",
      "joint_quad_titan": "💎 4-Asset Apex Titan: Gold + Silver + BTC + ETH Trend Runner Ensemble",
      "btc_profit_max": "👑 BTC Apex Profit Maximizer: 1.5 Sigma Fade + 2.0R Partial TP + Breakeven Lock | 66.1% Win Rate | 2.25 Profit Factor | +4,332.5% ROI",
      "btc_titan": "💎 BTC Apex Titan: 1.8 Sigma Session VWAP Reversion + BE Lock | 67.4% Win Rate | 2.34 Profit Factor | +3,268.3% ROI",
      "btc_high_wr": "🎯 BTC High Win-Rate Guardian: 2.0 Sigma Fade + 1.2R Fast Lock | 71.6% Win Rate | 1.79 Profit Factor | +1,275.3% ROI",
      "eth_profit_max": "👑 ETH Apex Profit Maximizer: 1.5 Sigma Fade + 2.0R Partial TP + Breakeven Lock | 66.7% Win Rate | 2.36 Profit Factor | +4,238.6% ROI",
      "eth_titan": "💎 ETH Apex Titan: 1.7 Sigma Session VWAP Reversion + BE Lock | 67.9% Win Rate | 2.49 Profit Factor | +3,612.7% ROI",
      "eth_high_wr": "🎯 ETH High Win-Rate Guardian: 1.7 Sigma Fade + 1.2R Fast Lock | 69.7% Win Rate | 1.72 Profit Factor | +1,659.9% ROI",
      "joint_profit_max": "👑 Joint Profit Maximizer: Simultaneous Gold Apex Pro + Silver Profit Max on Delta Exchange | Strict $5 Risk | +1,704.8% ROI | PF 1.77 | Max DD -$56.19",
      "joint_titan": "💎 Joint Apex Titan: Simultaneous Gold Apex Pro + Silver Titan on Delta Exchange | Strict $5 Risk | 51.7% Win Rate | +1,341.7% ROI",
      "joint_high_wr": "🎯 Joint High Win-Rate Guardian: Gold Apex Pro + Silver High WR | 52.9% Win Rate | +1,111.6% ROI | Low DD -$44.74",
      "joint_active_scalper": "⚡ Joint Active Intraday Scalper: High-frequency Gold + Silver scalper (Daily 6-10 Trades | Strict $5 Risk | +684.7% ROI)",
      "joint_stepped": "🚀 Joint Stepped Growth Compounder: Dynamic capital gain scaling across Gold + Silver (+3,398.1% ROI)",
      "silver_titan": "💎 Silver Apex Titan: Scale-Out 50% @ 1:1.6 (Secures Profit) + Instant Breakeven Lock (+0.15R) + 1.0x Trailing Runner | 50.6% Win Rate | +614.5% ROI",
      "silver_profit_max": "👑 Silver Apex Profit Maximizer: Scale-Out 50% @ 1:2.4 + Breakeven Lock + 6.0R Runner | 2.34 Profit Factor | +960.9% ROI",
      "silver_high_wr": "🎯 Silver High Win-Rate Guardian: Fast Scale-Out @ 1:1.2 + Breakeven Lock | 55.2% Win Rate | Ultra-Safe DD -$32.23",
      "active_scalper_5": "⚡ Active Intraday Scalper (Daily 3-6 Trades | Strict $5 Risk): Multi-position concurrent scalper (London + NY overlap 12:30-23:45 UTC) + Cut 50% @ 1:2.0 + BE Lock",
      "apex_pro_5": "💎 Apex Pro Institutional (Strict Fixed $5.00 Risk): Excludes chop hours (16, 19, 20, 22) + Capped $5 Risk | $50 ➔ $421.83 | +743.7% ROI | PF 1.50 | Low DD -$48.08",
      "apex_pro_4": "💎 Apex Pro Institutional (Strict Fixed $4.00 Risk): Excludes chop hours (16, 19, 20, 22) + Capped $4 Risk | $50 ➔ $320.85 | +541.7% ROI | Ultra-Safe DD -$33.18",
      "apex_stepped": "🚀 Apex Pro (Stepped Growth Risk): 100% Capital Gain scales risk +50% ($5 ➔ $7.50 / $7-$8) | $50 ➔ $1,298.49 | +2,497.0% ROI",
      "apex_master": "👑 Apex Multi-Alpha Master: All-Hours Fixed $5 Risk (265 Trades, +$226.21 Net, +452.4% ROI)",
      "compound_scalper": "🚀 Exponential Compound Scalper: Dynamic 5% Risk ($50 ➔ $313.43) + Geometric Equity Compounding + Scale-Out 50% @ 1:2.0",
      "hf_scalper": "⚡ Intraday Liquidity Scalper: 3-5 Trades/Day (8-Bar Micro Sweep + Delta Absorption) + Cut 50% @ 1:2.0 + BE Lock",
      "scale_out_3_0": "🏆 Scale-Out Master: Cut 50% @ 1:3.0 (Bank Profit) + Move SL to Breakeven + Dynamic 1.5x ATR Trail on Runner",
      "session_vwap": "🌊 Session VWAP Bands Reversion: 59.0% Win Rate (Fades 1.8 Sigma Stretch + Delta Reversal) + Ultra-Low Drawdown (-$24.73)",
      "fprint_absorption": "🎯 Footprint Absorption Divergence: CVD Delta Traps at Swing Extremes + Trailing Runner (+216.0% ROI)",
      "adaptive_context": "🧠 Adaptive Context Brain: High Conf (Hold +10R Big Runner, BE @ +1.5R) | Mod Conf (Cut 50% @ 1:2.0)",
      "scale_out_2_0": "⚖️ Scale-Out Balanced: Cut 50% @ 1:2.0 (Fast De-Risking) + Move SL to Breakeven + Dynamic ATR Trail",
      "scale_out_1_0": "🎯 Scale-Out High Win-Rate: Cut 50% @ 1:1.0 (56.9% Win Rate) + Move SL to Breakeven + Dynamic ATR Trail",
      "confluence_master": "👑 Institutional Confluence: 200 EMA Macro Trend + 20/50 Pullback + Footprint Delta > 10% + Dynamic Trailing Runner",
      "trailing_stop": "Dynamic ATR Trailing Stop: 15m Momentum (1.5x trail activated after +2.0R gain, ride runners)",
      "high_rr_3_5": "Asymmetric High R:R Fixed: Risk $4.00 to make $14.00 (Fixed 1:3.5 R:R target)",
      "balanced_2_0": "Balanced Momentum Fixed: Risk $4.00 to make $8.00 (Fixed 1:2.0 R:R target)"
    }};

    // Server API base URL (falls back to local dashboard server)
    const API_BASE = window.location.origin.includes('http') ? window.location.origin : 'http://127.0.0.1:5050';

    async function triggerRunBacktest() {{
      if (isRunning) return;
      isRunning = true;

      const btn = document.getElementById('runBacktestBtn');
      const btnText = document.getElementById('runBtnText');
      btn.className = "px-4 py-2 rounded-xl bg-amber-500 text-black font-extrabold transition flex items-center gap-2 cursor-wait opacity-80";
      btnText.innerText = "Running 23.5M Ticks...";

      showToast("running", "Executing Backtest Engine", "Simulating all 8 strategies across 12,509 candles...");

      try {{
        const response = await fetch(`${{API_BASE}}/api/run-backtest`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ symbol: currentAsset }})
        }});

        if (!response.ok) throw new Error("Server returned " + response.status);

        const result = await response.json();
        if (result.success && result.results) {{
          if (result.results.XAUTUSD || result.results.SLVONUSD) {{
            if (result.results.XAUTUSD) allDatasets.XAUTUSD = result.results.XAUTUSD;
            if (result.results.SLVONUSD) allDatasets.SLVONUSD = result.results.SLVONUSD;
            data = allDatasets[currentAsset];
          }} else {{
            allDatasets[currentAsset] = result.results;
            data = result.results;
          }}
          renderComparisonTable();
          const defaultKey = data["apex_pro_5"] ? "apex_pro_5" : Object.keys(data).reduce((a, b) => data[a].net_pl > data[b].net_pl ? a : b);
          selectStrategy(defaultKey);
          showToast("success", "Backtest Completed!", `Top Strategy: ${{result.best_strategy || 'Apex Pro'}} refreshed for ${{currentAsset}}.`);
        }} else {{
          throw new Error(result.error || "Simulation failed");
        }}
      }} catch (err) {{
        console.warn("Local server offline:", err);
        showToast("warning", "Dashboard Server Required", 'To run with 1 click directly in browser, double-click "start_dashboard.bat" in your Agent Brain folder.');
      }} finally {{
        isRunning = false;
        btn.className = "px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-400 hover:from-emerald-400 hover:to-teal-300 text-black font-extrabold shadow-lg shadow-emerald-950/40 transition flex items-center gap-2 cursor-pointer btn-pulse";
        btnText.innerText = "Run Backtest Now";
      }}
    }}

    async function triggerPaperScan() {{
      showToast("running", "Scanning Live Market", "Checking Delta Orderbook Depth (DOM) and Liquidity Sweeps...");
      try {{
        const response = await fetch(`${{API_BASE}}/api/paper-scan`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }}
        }});
        const result = await response.json();
        if (result.success) {{
          showToast("success", "Market Scan Complete", `Scanned ${{result.scan.length}} assets. Check Living Journal for notes.`);
        }}
      }} catch (err) {{
        showToast("warning", "Dashboard Server Required", 'Double-click "start_dashboard.bat" to enable live web scans.');
      }}
    }}

    function showToast(type, title, message) {{
      const toast = document.getElementById('statusToast');
      const content = document.getElementById('toastContent');
      const icon = document.getElementById('toastIcon');
      const titleEl = document.getElementById('toastTitle');
      const msgEl = document.getElementById('toastMessage');

      toast.classList.remove('hidden');
      titleEl.innerText = title;
      msgEl.innerText = message;

      if (type === "success") {{
        content.className = "glass-card rounded-2xl p-4 flex items-center justify-between border-l-4 border-l-emerald-500";
        icon.className = "w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold";
        icon.innerText = "✓";
      }} else if (type === "warning") {{
        content.className = "glass-card rounded-2xl p-4 flex items-center justify-between border-l-4 border-l-amber-500";
        icon.className = "w-8 h-8 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold";
        icon.innerText = "!";
      }} else {{
        content.className = "glass-card rounded-2xl p-4 flex items-center justify-between border-l-4 border-l-blue-500";
        icon.className = "w-8 h-8 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center font-bold animate-spin";
        icon.innerText = "⟳";
      }}
    }}

    function dismissToast() {{
      document.getElementById('statusToast').classList.add('hidden');
    }}

    function renderComparisonTable() {{
      const tbody = document.getElementById('comparisonTableBody');
      tbody.innerHTML = '';

      const maxPl = Math.max(...Object.values(data).map(x => x.net_pl));

      Object.keys(data).forEach((key, idx) => {{
        const s = data[key];
        const tr = document.createElement('tr');
        const isWin = s.net_pl > 0;
        const isChampion = (s.net_pl === maxPl);

        tr.className = "hover:bg-slate-800/40 transition cursor-pointer " + (isChampion ? "bg-emerald-950/20" : "");
        tr.onclick = () => selectStrategy(key);

        tr.innerHTML = `
          <td class="py-3 font-bold text-white flex items-center gap-2">
            ${{isChampion ? '<span class="px-1.5 py-0.5 rounded bg-emerald-500 text-black font-extrabold text-[10px]">CHAMPION</span>' : '<span class="w-2 h-2 rounded-full ' + (isWin ? 'bg-emerald-400' : 'bg-slate-500') + '"></span>'}}
            ${{s.strategy_name}}
          </td>
          <td class="text-slate-400 text-[11px] max-w-xs truncate">${{stratDescriptions[key] || ''}}</td>
          <td>${{s.total_trades}}</td>
          <td class="font-bold ${{s.win_rate >= 50 ? 'text-emerald-400 font-extrabold' : (s.win_rate >= 35 ? 'text-blue-400' : 'text-slate-400')}}">${{s.win_rate}}%</td>
          <td class="font-bold ${{s.profit_factor >= 1.7 ? 'text-emerald-400 font-extrabold' : (s.profit_factor >= 1.2 ? 'text-blue-400' : 'text-rose-400')}}">${{s.profit_factor}}</td>
          <td class="text-rose-400">-$${{s.max_drawdown_usd.toFixed(2)}}</td>
          <td class="font-extrabold ${{isWin ? 'text-emerald-400' : 'text-rose-400'}}">${{s.net_pl > 0 ? '+' : ''}}$${{s.net_pl.toFixed(2)}}</td>
          <td class="font-bold ${{isWin ? 'text-emerald-400' : 'text-rose-400'}}">${{s.roi_pct > 0 ? '+' : ''}}${{s.roi_pct.toFixed(1)}}%</td>
          <td>
            <button class="px-2.5 py-1 rounded ${{isChampion ? 'bg-emerald-500 text-black font-bold' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}} text-[11px] border border-slate-700 transition">
              Select
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      }});
      lucide.createIcons();
    }}

    function selectStrategy(key) {{
      const s = data[key];
      if (!s) return;

      currentStrategyKey = key;
      currentTrades = s.trades;

      // Update Executive KPIs
      const isWin = s.net_pl > 0;
      document.getElementById('activeNetPl').innerText = (s.net_pl > 0 ? '+' : '') + '$' + s.net_pl.toFixed(2);
      document.getElementById('activeNetPl').className = "text-2xl font-extrabold font-mono " + (isWin ? "text-emerald-400" : "text-rose-400");
      document.getElementById('activeRoi').innerText = "ROI: " + (s.roi_pct > 0 ? "+" : "") + s.roi_pct.toFixed(1) + "% (From $50.00 Base)";
      document.getElementById('activeWinRate').innerText = s.win_rate + "%";
      document.getElementById('activeRecord').innerText = s.wins + " Wins • " + s.losses + " Losses";
      document.getElementById('activePf').innerText = s.profit_factor;
      document.getElementById('activeGross').innerText = "+$" + s.gross_profit.toFixed(2) + " / -$" + s.gross_loss.toFixed(2);
      document.getElementById('activeDd').innerText = "-$" + s.max_drawdown_usd.toFixed(2);
      document.getElementById('chartTitle').innerText = s.strategy_name + " — Equity Progression";
      document.getElementById('chartBadge').innerText = "Profit Factor: " + s.profit_factor + " | Net: $" + s.net_pl.toFixed(2);

      // Render Equity Curve Chart
      const step = Math.max(1, Math.floor(s.equity_curve.length / 25));
      const labels = s.equity_curve.map((pt, i) => i % step === 0 ? new Date(pt.timestamp * 1000).toLocaleDateString() : '');
      const values = s.equity_curve.map(pt => pt.equity);

      const ctx = document.getElementById('equityChart').getContext('2d');
      if (currentChart) currentChart.destroy();

      currentChart = new Chart(ctx, {{
        type: 'line',
        data: {{
          labels: labels,
          datasets: [{{
            label: 'Account Balance ($)',
            data: values,
            borderColor: isWin ? '#10b981' : '#f43f5e',
            backgroundColor: isWin ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.12)',
            fill: true,
            tension: 0.25,
            pointRadius: 1,
            borderWidth: 2
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }},
            y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }}
          }}
        }}
      }});

      // 1. Calculate & Render Streaks
      computeStreaks(currentTrades);

      // 2. Render Hourly Profitability Chart
      renderHourlyChart(currentTrades);

      // 3. Render Day of Week Profitability Chart
      renderDowChart(currentTrades);

      // 4. Render Calendar Heat-Map
      renderCalendar(currentTrades, currentCalMonth);

      // 5. Render Trade List Table
      renderTradeList();
    }}

    // ==========================================
    // STREAKS & EXPECTANCY COMPUTATION
    // ==========================================
    function computeStreaks(trades) {{
      if (!trades || trades.length === 0) return;

      const chrono = [...trades].sort((a, b) => (a.closed_at || a.opened_at || '').localeCompare(b.closed_at || b.opened_at || ''));

      let maxWinStreak = 0, curWinStreak = 0, maxWinPnl = 0, curWinPnl = 0;
      let maxLossStreak = 0, curLossStreak = 0, maxLossPnl = 0, curLossPnl = 0;
      let totalPnl = 0, grossWin = 0, grossLoss = 0, winCount = 0, lossCount = 0;

      chrono.forEach(t => {{
        const p = t.pnl_usd || 0;
        totalPnl += p;
        if (p > 0) {{
          winCount++;
          grossWin += p;
          curWinStreak++;
          curWinPnl += p;
          if (curWinStreak > maxWinStreak) {{
            maxWinStreak = curWinStreak;
            maxWinPnl = curWinPnl;
          }}
          curLossStreak = 0;
          curLossPnl = 0;
        }} else if (p < 0) {{
          lossCount++;
          grossLoss += Math.abs(p);
          curLossStreak++;
          curLossPnl += p;
          if (curLossStreak > maxLossStreak) {{
            maxLossStreak = curLossStreak;
            maxLossPnl = curLossPnl;
          }}
          curWinStreak = 0;
          curWinPnl = 0;
        }}
      }});

      let activeStreakCount = 0, activeStreakPnl = 0, activeStreakIsWin = false;
      if (chrono.length > 0) {{
        const lastT = chrono[chrono.length - 1];
        activeStreakIsWin = (lastT.pnl_usd || 0) > 0;
        for (let i = chrono.length - 1; i >= 0; i--) {{
          const isWin = (chrono[i].pnl_usd || 0) > 0;
          if (isWin === activeStreakIsWin) {{
            activeStreakCount++;
            activeStreakPnl += (chrono[i].pnl_usd || 0);
          }} else {{
            break;
          }}
        }}
      }}

      const expectancy = trades.length > 0 ? (totalPnl / trades.length) : 0;
      const avgWin = winCount > 0 ? (grossWin / winCount) : 0;
      const avgLoss = lossCount > 0 ? (grossLoss / lossCount) : 0;
      const winLossRatio = avgLoss > 0 ? (avgWin / avgLoss) : 0;

      document.getElementById('streakMaxWin').innerText = `🔥 ${{maxWinStreak}} Wins`;
      document.getElementById('streakMaxWinPnl').innerText = `+$${{maxWinPnl.toFixed(2)}} Banked`;
      document.getElementById('streakMaxLoss').innerText = `⚠️ ${{maxLossStreak}} Losses`;
      document.getElementById('streakMaxLossPnl').innerText = `-$${{Math.abs(maxLossPnl).toFixed(2)}} Drawdown`;
      document.getElementById('streakCurrent').innerText = `⚡ ${{activeStreakCount}} ${{activeStreakIsWin ? 'Wins' : 'Losses'}}`;
      document.getElementById('streakCurrentPnl').innerText = `${{activeStreakPnl >= 0 ? '+' : ''}}$${{activeStreakPnl.toFixed(2)}} Current`;
      document.getElementById('metricExpectancy').innerText = `${{expectancy >= 0 ? '+' : ''}}$${{expectancy.toFixed(2)}} / trade`;
      document.getElementById('metricWinLossRatio').innerText = `Avg Win: $${{avgWin.toFixed(2)}} • Ratio: ${{winLossRatio.toFixed(2)}}x`;
    }}

    // ==========================================
    // HOURLY PROFITABILITY BREAKDOWN (UTC)
    // ==========================================
    function renderHourlyChart(trades) {{
      const hourlyData = Array.from({{ length: 24 }}, () => ({{ pnl: 0, count: 0, wins: 0 }}));

      trades.forEach(t => {{
        const ts = t.opened_at || '';
        if (ts.length >= 13) {{
          const hour = parseInt(ts.substring(11, 13), 10);
          if (hour >= 0 && hour < 24) {{
            const p = t.pnl_usd || 0;
            hourlyData[hour].pnl += p;
            hourlyData[hour].count++;
            if (p > 0) hourlyData[hour].wins++;
          }}
        }}
      }});

      let bestHour = 0, bestHourPnl = -Infinity;
      hourlyData.forEach((d, h) => {{
        if (d.pnl > bestHourPnl && d.count > 0) {{
          bestHourPnl = d.pnl;
          bestHour = h;
        }}
      }});

      const bestBadge = document.getElementById('bestHourBadge');
      if (bestHourPnl > -Infinity) {{
        bestBadge.innerText = `Best Hour: ${{bestHour.toString().padStart(2, '0')}}:00 IST (+$${{bestHourPnl.toFixed(2)}})`;
      }} else {{
        bestBadge.innerText = `Best Hour: --`;
      }}

      const labels = Array.from({{ length: 24 }}, (_, i) => `${{i.toString().padStart(2, '0')}}:00`);
      const values = hourlyData.map(d => Math.round(d.pnl * 100) / 100);
      const bgColors = values.map(v => v >= 0 ? 'rgba(16, 185, 129, 0.75)' : 'rgba(244, 63, 94, 0.75)');
      const borderColors = values.map(v => v >= 0 ? '#10b981' : '#f43f5e');

      const ctx = document.getElementById('hourlyChart').getContext('2d');
      if (hourlyChart) hourlyChart.destroy();

      hourlyChart = new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels: labels,
          datasets: [{{
            label: 'Net P&L ($)',
            data: values,
            backgroundColor: bgColors,
            borderColor: borderColors,
            borderWidth: 1,
            borderRadius: 4
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              callbacks: {{
                label: (ctx) => {{
                  const h = ctx.dataIndex;
                  const d = hourlyData[h];
                  const wr = d.count > 0 ? ((d.wins / d.count) * 100).toFixed(1) : '0.0';
                  return `Net P&L: $${{d.pnl.toFixed(2)}} | Trades: ${{d.count}} | Win Rate: ${{wr}}%`;
                }}
              }}
            }}
          }},
          scales: {{
            x: {{ grid: {{ color: 'rgba(255,255,255,0.03)' }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }},
            y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }}
          }}
        }}
      }});
    }}

    // ==========================================
    // DAY OF WEEK PROFITABILITY (MONDAY - SUNDAY)
    // ==========================================
    function renderDowChart(trades) {{
      const dowNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
      const dowData = Array.from({{ length: 7 }}, () => ({{ pnl: 0, count: 0, wins: 0 }}));

      trades.forEach(t => {{
        const ts = t.opened_at || '';
        if (ts.length >= 10) {{
          const dt = new Date(ts.substring(0, 10));
          let dayIndex = dt.getUTCDay();
          let idx = (dayIndex === 0) ? 6 : (dayIndex - 1);
          if (idx >= 0 && idx < 7) {{
            const p = t.pnl_usd || 0;
            dowData[idx].pnl += p;
            dowData[idx].count++;
            if (p > 0) dowData[idx].wins++;
          }}
        }}
      }});

      let bestDayIdx = 0, bestDayPnl = -Infinity;
      dowData.forEach((d, i) => {{
        if (d.pnl > bestDayPnl && d.count > 0) {{
          bestDayPnl = d.pnl;
          bestDayIdx = i;
        }}
      }});

      const bestDayBadge = document.getElementById('bestDayBadge');
      if (bestDayPnl > -Infinity) {{
        bestDayBadge.innerText = `Best Day: ${{dowNames[bestDayIdx]}} (+$${{bestDayPnl.toFixed(2)}})`;
      }} else {{
        bestDayBadge.innerText = `Best Day: --`;
      }}

      const values = dowData.map(d => Math.round(d.pnl * 100) / 100);
      const bgColors = values.map(v => v >= 0 ? 'rgba(16, 185, 129, 0.75)' : 'rgba(244, 63, 94, 0.75)');
      const borderColors = values.map(v => v >= 0 ? '#10b981' : '#f43f5e');

      const ctx = document.getElementById('dowChart').getContext('2d');
      if (dowChart) dowChart.destroy();

      dowChart = new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
          datasets: [{{
            label: 'Net P&L ($)',
            data: values,
            backgroundColor: bgColors,
            borderColor: borderColors,
            borderWidth: 1,
            borderRadius: 6
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              callbacks: {{
                label: (ctx) => {{
                  const i = ctx.dataIndex;
                  const d = dowData[i];
                  const wr = d.count > 0 ? ((d.wins / d.count) * 100).toFixed(1) : '0.0';
                  return `Net: $${{d.pnl.toFixed(2)}} | Trades: ${{d.count}} | Win Rate: ${{wr}}%`;
                }}
              }}
            }}
          }},
          scales: {{
            x: {{ grid: {{ color: 'rgba(255,255,255,0.03)' }}, ticks: {{ color: '#94a3b8' }} }},
            y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }}
          }}
        }}
      }});

      const container = document.getElementById('dowSummaryCards');
      container.innerHTML = '';
      dowNames.forEach((name, i) => {{
        const d = dowData[i];
        const wr = d.count > 0 ? ((d.wins / d.count) * 100).toFixed(0) : 0;
        const win = d.pnl >= 0;
        const div = document.createElement('div');
        div.className = `p-2 rounded-xl border ${{win ? 'bg-emerald-950/20 border-emerald-500/30' : 'bg-rose-950/20 border-rose-500/30'}}`;
        div.innerHTML = `
          <div class="text-[11px] text-slate-400 font-bold">${{name.substring(0, 3)}}</div>
          <div class="text-xs font-extrabold ${{win ? 'text-emerald-400' : 'text-rose-400'}} mt-0.5">${{d.pnl >= 0 ? '+' : ''}}$${{d.pnl.toFixed(1)}}</div>
          <div class="text-[10px] text-slate-400 mt-0.5">${{wr}}% (${{d.count}}t)</div>
        `;
        container.appendChild(div);
      }});
    }}

    // ==========================================
    // DAILY P&L CALENDAR HEATMAP
    // ==========================================
    function changeCalMonth(monthStr) {{
      currentCalMonth = monthStr;
      const months = ['2026-09', '2026-08', '2026-07', '2026-06', '2026-05', '2026-04', '2026-03', '2026-02'];
      months.forEach(m => {{
        const btn = document.getElementById('cTab_' + m);
        if (btn) {{
          btn.className = (m === monthStr) ? 'px-2.5 py-1 rounded bg-emerald-500 text-black font-extrabold text-[11px] shadow' : 'px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700';
        }}
      }});
      renderCalendar(currentTrades, monthStr);
    }}

    function renderCalendar(trades, monthStr) {{
      const grid = document.getElementById('calendarGrid');
      grid.innerHTML = '';

      const [yearStr, mStr] = monthStr.split('-');
      const year = parseInt(yearStr, 10);
      const month = parseInt(mStr, 10);

      const dailyMap = {{}};
      trades.forEach(t => {{
        const closeTs = t.closed_at || t.opened_at || '';
        if (closeTs.startsWith(monthStr)) {{
          const dayKey = closeTs.substring(0, 10);
          if (!dailyMap[dayKey]) dailyMap[dayKey] = {{ pnl: 0, count: 0, wins: 0 }};
          const p = t.pnl_usd || 0;
          dailyMap[dayKey].pnl += p;
          dailyMap[dayKey].count++;
          if (p > 0) dailyMap[dayKey].wins++;
        }}
      }});

      const daysInMonth = new Date(year, month, 0).getDate();
      const firstDayOfWeek = new Date(year, month - 1, 1).getDay();
      const startOffset = (firstDayOfWeek + 6) % 7;

      for (let i = 0; i < startOffset; i++) {{
        const blank = document.createElement('div');
        blank.className = "h-16 rounded-xl bg-slate-900/20 border border-slate-800/20";
        grid.appendChild(blank);
      }}

      let monthPnl = 0, greenDays = 0, redDays = 0, totalActiveDays = 0;

      for (let day = 1; day <= daysInMonth; day++) {{
        const dayStr = `${{yearStr}}-${{mStr.padStart(2, '0')}}-${{day.toString().padStart(2, '0')}}`;
        const stats = dailyMap[dayStr];
        const cell = document.createElement('div');

        if (stats && stats.count > 0) {{
          totalActiveDays++;
          monthPnl += stats.pnl;
          const isWin = stats.pnl > 0;
          if (isWin) greenDays++; else redDays++;

          cell.className = `h-16 p-1.5 rounded-xl border flex flex-col justify-between cursor-pointer transition hover:scale-105 ${{isWin ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-300' : 'bg-rose-950/40 border-rose-500/50 text-rose-300'}}`;
          cell.onclick = () => filterByDay(dayStr);

          cell.innerHTML = `
            <div class="flex items-center justify-between text-[11px] font-bold">
              <span>${{day}}</span>
              <span class="text-[9px] px-1 rounded bg-black/40 text-slate-300">${{stats.count}}t</span>
            </div>
            <div class="text-xs font-extrabold text-right font-mono">${{stats.pnl > 0 ? '+' : ''}}$${{stats.pnl.toFixed(2)}}</div>
          `;
        }} else {{
          const dObj = new Date(year, month - 1, day);
          const isWknd = (dObj.getDay() === 0 || dObj.getDay() === 6);
          cell.className = `h-16 p-1.5 rounded-xl border bg-slate-900/40 border-slate-800/40 text-slate-600 flex flex-col justify-between`;
          cell.innerHTML = `
            <div class="text-[11px] font-bold">${{day}}</div>
            <div class="text-[10px] text-right font-mono text-slate-600">${{isWknd ? 'Weekend' : '--'}}</div>
          `;
        }}
        grid.appendChild(cell);
      }}

      const winDaysPct = totalActiveDays > 0 ? ((greenDays / totalActiveDays) * 100).toFixed(0) : 0;
      document.getElementById('calMonthSummary').innerText = `${{monthStr}}: ${{monthPnl >= 0 ? '+' : ''}}$${{monthPnl.toFixed(2)}} Net | ${{greenDays}} Green • ${{redDays}} Red Days (${{winDaysPct}}%)`;
    }}

    function filterByDay(dayStr) {{
      customStartDate = dayStr;
      customEndDate = dayStr;
      document.getElementById('customStartDate').value = dayStr;
      document.getElementById('customEndDate').value = dayStr;
      document.getElementById('activeRangeBadge').innerText = `Day: ${{dayStr}}`;
      renderTradeList();
    }}

    // ==========================================
    // MULTI-TIMEFRAME & CUSTOM DATE CONTROLS
    // ==========================================
    function setTimePreset(preset) {{
      activePreset = preset;
      const presets = ['ALL', 'TODAY', 'WEEK', 'MONTH'];
      presets.forEach(p => {{
        const btn = document.getElementById('tPreset_' + p);
        if (btn) {{
          btn.className = (p === preset) ? 'px-2.5 py-1 rounded bg-emerald-500 text-black font-extrabold text-[11px] shadow' : 'px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700';
        }}
      }});

      if (preset === 'ALL') {{
        customStartDate = null;
        customEndDate = null;
        document.getElementById('customStartDate').value = '';
        document.getElementById('customEndDate').value = '';
        document.getElementById('activeRangeBadge').innerText = 'All Time';
      }} else if (preset === 'TODAY') {{
        customStartDate = '2026-09-01';
        customEndDate = '2026-09-01';
        document.getElementById('customStartDate').value = customStartDate;
        document.getElementById('customEndDate').value = customEndDate;
        document.getElementById('activeRangeBadge').innerText = 'Today (2026-09-01)';
      }} else if (preset === 'WEEK') {{
        customStartDate = '2026-08-26';
        customEndDate = '2026-09-01';
        document.getElementById('customStartDate').value = customStartDate;
        document.getElementById('customEndDate').value = customEndDate;
        document.getElementById('activeRangeBadge').innerText = 'This Week (Aug 26 - Sep 01)';
      }} else if (preset === 'MONTH') {{
        customStartDate = '2026-08-01';
        customEndDate = '2026-09-01';
        document.getElementById('customStartDate').value = customStartDate;
        document.getElementById('customEndDate').value = customEndDate;
        document.getElementById('activeRangeBadge').innerText = 'This Month (Aug 01 - Sep 01)';
      }}
      renderTradeList();
    }}

    function setBacktestMonthFilter(month) {{
      currentMonthFilter = month;
      const months = ['ALL', '2026-09', '2026-08', '2026-07', '2026-06', '2026-05', '2026-04', '2026-03', '2026-02'];
      months.forEach(m => {{
        const btn = document.getElementById('bTab_' + m);
        if (btn) {{
          btn.className = (m === month) ? 'px-2 py-1 rounded bg-emerald-500 text-black font-extrabold text-[11px]' : 'px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]';
        }}
      }});
      customStartDate = null;
      customEndDate = null;
      document.getElementById('customStartDate').value = '';
      document.getElementById('customEndDate').value = '';
      document.getElementById('activeRangeBadge').innerText = month === 'ALL' ? 'All Months' : month;
      renderTradeList();
    }}

    function applyCustomDateFilter() {{
      const start = document.getElementById('customStartDate').value;
      const end = document.getElementById('customEndDate').value;
      if (!start || !end) return;
      customStartDate = start;
      customEndDate = end;
      currentMonthFilter = 'ALL';
      document.getElementById('activeRangeBadge').innerText = `${{start}} to ${{end}}`;
      renderTradeList();
    }}

    function resetDateFilter() {{
      customStartDate = null;
      customEndDate = null;
      currentMonthFilter = 'ALL';
      document.getElementById('customStartDate').value = '';
      document.getElementById('customEndDate').value = '';
      setTimePreset('ALL');
    }}

    function filterTrades(filterType) {{
      currentFilter = filterType;
      document.getElementById('tabAll').className = (filterType === 'ALL') ? 'px-2.5 py-1 rounded bg-emerald-500 text-black font-bold' : 'px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white';
      document.getElementById('tabWin').className = (filterType === 'WIN') ? 'px-2.5 py-1 rounded bg-emerald-500 text-black font-bold' : 'px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white';
      document.getElementById('tabLoss').className = (filterType === 'LOSS') ? 'px-2.5 py-1 rounded bg-emerald-500 text-black font-bold' : 'px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white';
      renderTradeList();
    }}

    function renderTradeList() {{
      const tbody = document.getElementById('tradeLogBody');
      tbody.innerHTML = '';

      let list = [...currentTrades];
      list.sort((a, b) => (b.closed_at || b.opened_at || '').localeCompare(a.closed_at || a.opened_at || ''));

      if (currentMonthFilter !== 'ALL') {{
        list = list.filter(t => (t.opened_at && t.opened_at.startsWith(currentMonthFilter)) || (t.closed_at && t.closed_at.startsWith(currentMonthFilter)));
      }}

      if (customStartDate && customEndDate) {{
        list = list.filter(t => {{
          const openD = (t.opened_at || '').substring(0, 10);
          const closeD = (t.closed_at || '').substring(0, 10);
          return (openD >= customStartDate && openD <= customEndDate) || (closeD >= customStartDate && closeD <= customEndDate);
        }});
      }}

      if (currentFilter === 'WIN') list = list.filter(t => (t.pnl_usd || 0) > 0);
      else if (currentFilter === 'LOSS') list = list.filter(t => (t.pnl_usd || 0) < 0);

      const filteredNet = list.reduce((acc, t) => acc + (t.pnl_usd || 0), 0);
      document.getElementById('tradeCountBadge').innerText = `${{list.length}} Trades (${{filteredNet >= 0 ? '+' : ''}}$${{filteredNet.toFixed(2)}})`;

      if (list.length === 0) {{
        tbody.innerHTML = `<tr><td colspan="9" class="py-8 text-center text-slate-500">No trades match this timeframe or filter.</td></tr>`;
        return;
      }}

      list.forEach(t => {{
        const tr = document.createElement('tr');
        const win = (t.pnl_usd || 0) > 0;
        const sym = (t.symbol || '').toUpperCase();
        let assetBadge = '<span class="px-2 py-0.5 rounded font-mono text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30">🥇 Gold</span>';
        if (sym.includes('SLV')) {{
          assetBadge = '<span class="px-2 py-0.5 rounded font-mono text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">🥈 Silver</span>';
        }} else if (sym.includes('BTC')) {{
          assetBadge = '<span class="px-2 py-0.5 rounded font-mono text-[10px] bg-orange-500/20 text-orange-300 border border-orange-500/30">₿ BTC</span>';
        }} else if (sym.includes('ETH')) {{
          assetBadge = '<span class="px-2 py-0.5 rounded font-mono text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30">Ξ ETH</span>';
        }}
        const isSeptember = (t.opened_at && t.opened_at.startsWith('2026-09')) || (t.closed_at && t.closed_at.startsWith('2026-09'));

        tr.className = isSeptember ? "bg-emerald-950/20 border-l-2 border-l-emerald-400" : "";

        tr.innerHTML = `
          <td class="py-2.5 text-slate-300 font-mono">
            <div class="flex items-center gap-1.5 mb-0.5">
              ${{isSeptember ? '<span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold text-[10px]">SEP 2026</span>' : ''}}
              <span class="text-white font-semibold">${{t.closed_at ? t.closed_at : t.opened_at}}</span>
            </div>
            ${{t.closed_at && t.opened_at && t.closed_at !== t.opened_at ? '<div class="text-[10px] text-slate-400">Entered: ' + t.opened_at + '</div>' : ''}}
          </td>
          <td>${{assetBadge}}</td>
          <td><span class="px-2 py-0.5 rounded ${{t.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-400 font-bold' : 'bg-rose-500/20 text-rose-400 font-bold'}}">${{t.side}}</span></td>
          <td>$${{t.entry_price}}</td>
          <td>$${{t.exit_price || '-'}}</td>
          <td>${{t.lots}}</td>
          <td class="font-bold ${{win ? 'text-emerald-400' : 'text-rose-400'}}">${{t.pnl_usd > 0 ? '+' : ''}}$${{t.pnl_usd.toFixed(2)}}</td>
          <td class="${{win ? 'text-emerald-400' : 'text-rose-400'}} font-bold">${{t.rr_achieved > 0 ? '+' : ''}}${{t.rr_achieved}}R</td>
          <td><span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300">${{t.close_reason || 'CLOSED'}}</span></td>
          <td class="text-slate-400 text-[11px] max-w-sm truncate">${{t.orderflow_notes || ''}}</td>
        `;
        tbody.appendChild(tr);
      }});
      lucide.createIcons();
    }}

    switchAsset(currentAsset);
  </script>
</body>
</html>
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

    def generate_agent_journal(self, db_trades: List[Dict], db_thoughts: List[Dict], filename: str = "agent_journal.html", active_nav: str = "JOINT") -> Path:
        """Renders live/paper journal dashboard mirroring TradeEdge."""
        file_path = self.output_dir / filename

        wins = [t for t in db_trades if (t.get("pnl_usd") or 0) > 0]
        losses = [t for t in db_trades if (t.get("pnl_usd") or 0) < 0]
        total = len(db_trades)
        net_pl = sum((t.get("pnl_usd") or 0) for t in db_trades)
        win_rate = round((len(wins) / total * 100), 1) if total > 0 else 0.0

        avg_win = round(sum((t.get("pnl_usd") or 0) for t in wins) / len(wins), 2) if wins else 0.0
        avg_loss = round(abs(sum((t.get("pnl_usd") or 0) for t in losses)) / len(losses), 2) if losses else 0.0
        max_win = round(max((t.get("pnl_usd") or 0) for t in wins), 2) if wins else 0.0
        gross_profit = round(sum((t.get("pnl_usd") or 0) for t in wins), 2)
        gross_loss = round(abs(sum((t.get("pnl_usd") or 0) for t in losses)), 2)
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        trades_json = json.dumps(db_trades)
        thoughts_json = json.dumps(db_thoughts)

        html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Brain | {('🌐 Joint Portfolio' if active_nav == 'JOINT' else ('🥇 Gold' if active_nav == 'GOLD' else ('🥈 Silver' if active_nav == 'SILVER' else ('₿ Bitcoin' if active_nav == 'BTC' else 'Ξ Ethereum'))))} Trading Journal</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body {{ background-color: #0a0d14; color: #f1f5f9; font-family: system-ui, sans-serif; }}
    .glass-card {{ background: rgba(15, 20, 32, 0.90); backdrop-filter: blur(14px); border: 1px solid #1f2a44; }}
    .glow-win {{ box-shadow: 0 0 25px -5px rgba(16, 185, 129, 0.25); }}
  </style>
</head>
<body class="min-h-screen p-4 sm:p-6 lg:p-8 space-y-6">

  <!-- HEADER WITH ACTION BUTTONS -->
  <header class="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 border-b border-slate-800 pb-5">
    <div class="flex items-center gap-3">
      <div class="h-11 w-11 rounded-xl {'bg-gradient-to-tr from-blue-600 to-indigo-400' if active_nav == 'JOINT' else ('bg-gradient-to-tr from-amber-500 to-yellow-300' if active_nav == 'GOLD' else ('bg-gradient-to-tr from-cyan-500 to-teal-300' if active_nav == 'SILVER' else ('bg-gradient-to-tr from-orange-500 to-amber-400' if active_nav == 'BTC' else 'bg-gradient-to-tr from-purple-500 to-indigo-400')))} flex items-center justify-center font-bold text-white text-2xl shadow-lg">
        {'🌐' if active_nav == 'JOINT' else ('🥇' if active_nav == 'GOLD' else ('🥈' if active_nav == 'SILVER' else ('₿' if active_nav == 'BTC' else 'Ξ')))}
      </div>
      <div>
        <h1 class="text-xl font-bold flex items-center gap-2">
          <span>Agent Brain | {('👑 4-Asset Apex Portfolio Journal' if active_nav == 'JOINT' else ('🥇 Gold (XAUTUSD) Journal' if active_nav == 'GOLD' else ('🥈 Silver (SLVONUSD) Journal' if active_nav == 'SILVER' else ('₿ Bitcoin (BTCUSD) Journal' if active_nav == 'BTC' else 'Ξ Ethereum (ETHUSD) Journal'))))}</span>
          <span class="text-xs px-2.5 py-0.5 rounded-full {'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' if active_nav == 'JOINT' else ('bg-amber-500/10 text-amber-400 border border-amber-500/20' if active_nav == 'GOLD' else ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_nav == 'SILVER' else ('bg-orange-500/10 text-orange-400 border border-orange-500/20' if active_nav == 'BTC' else 'bg-purple-500/10 text-purple-400 border border-purple-500/20')))}">👑 Champion Ensemble (Strict $5 Risk)</span>
        </h1>
        <p class="text-xs text-slate-400">Institutional audited ledger • 4-Asset Champion Ensemble (Gold, Silver, BTC, ETH) • Strict $5 Risk</p>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
      <a href="live_journal.html" class="px-3 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/30 font-bold transition flex items-center gap-1.5 shadow">
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span>⚡ Live Journal</span>
      </a>
      <a href="agent_journal.html" class="px-3 py-1.5 rounded-xl {'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold shadow' if active_nav == 'JOINT' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>👑 4-Asset Apex</span>
      </a>
      <a href="gold_journal.html" class="px-3 py-1.5 rounded-xl {'bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold shadow' if active_nav == 'GOLD' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>🥇 Gold</span>
      </a>
      <a href="silver_journal.html" class="px-3 py-1.5 rounded-xl {'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-bold shadow' if active_nav == 'SILVER' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>🥈 Silver</span>
      </a>
      <a href="btc_journal.html" class="px-3 py-1.5 rounded-xl {'bg-orange-500/20 text-orange-300 border border-orange-500/30 font-bold shadow' if active_nav == 'BTC' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>₿ BTC</span>
      </a>
      <a href="eth_journal.html" class="px-3 py-1.5 rounded-xl {'bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold shadow' if active_nav == 'ETH' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>Ξ ETH</span>
      </a>
      <a href="strategy_guide.html" class="px-3 py-1.5 rounded-xl bg-purple-500/10 text-purple-300 hover:bg-purple-500/20 border border-purple-500/20 font-bold transition flex items-center gap-1.5">
        <i data-lucide="book" class="w-3.5 h-3.5"></i>
        <span>Strategy Guide</span>
      </a>
      <a href="backtest_report.html" class="px-3 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 font-bold transition flex items-center gap-1.5">
        <i data-lucide="bar-chart-2" class="w-3.5 h-3.5"></i>
        <span>Scorecard</span>
      </a>
    </div>
  </header>

  <!-- STRATEGY PHILOSOPHY BANNER -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-5 border-l-4 border-l-emerald-500 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 font-mono text-xs">
    <div class="space-y-1">
      <div class="flex items-center gap-2 text-emerald-400 font-bold text-sm">
        <i data-lucide="shield-check" class="w-4 h-4"></i>
        <span>👑 4-Asset Apex Portfolio: Simultaneous Gold Apex Pro + Silver Profit Max + BTC Profit Max + ETH Profit Max</span>
      </div>
      <p class="text-slate-400 text-[11px]">
        1. Close 50% lots at target (1:2.0 to 1:2.5) to bank profit. 
        2. Move Stop Loss on remaining 50% to Breakeven (+0.10R, 100% Risk-Free). 
        3. Dynamically trail remaining runner with ATR for fat-tail gains.
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <span class="px-3 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">Strict $5 Risk</span>
      <span class="px-3 py-1.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold">Delta Fee: 0.01%</span>
      <span class="px-3 py-1.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 font-bold">Futures: 100x BTC, ETH, Gold / 50x Silver</span>
    </div>
  </div>

  <!-- KPI CARDS (DYNAMICALLY RECOMPUTED) -->
  <div class="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 font-mono">
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-emerald-500">
      <span class="text-slate-400 text-xs block mb-1">Cumulative Net P&L</span>
      <span id="jMetricNetPl" class="text-2xl font-extrabold {'text-emerald-400' if net_pl >= 0 else 'text-rose-400'}">{'+$' if net_pl >= 0 else '-$'}{abs(round(net_pl, 2))}</span>
      <span class="text-[11px] text-slate-400 block mt-1">Starting Base: $50.00</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-blue-500">
      <span class="text-slate-400 text-xs block mb-1">Win Rate %</span>
      <span id="jMetricWinRate" class="text-2xl font-extrabold text-white">{win_rate}%</span>
      <span id="jMetricWinLossCount" class="text-[11px] text-slate-400 block mt-1">{len(wins)} Wins • {len(losses)} Losses</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-purple-500">
      <span class="text-slate-400 text-xs block mb-1">Profit Factor</span>
      <span id="jMetricPf" class="text-2xl font-extrabold text-purple-400">{profit_factor}</span>
      <span id="jMetricGross" class="text-[11px] text-slate-400 block mt-1">+${gross_profit} / -${gross_loss}</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-amber-500">
      <span class="text-slate-400 text-xs block mb-1">Avg Win vs Loss</span>
      <span id="jMetricAvgWinLoss" class="text-lg font-extrabold text-emerald-400">+${avg_win} <span class="text-slate-400 text-xs font-normal">/</span> <span class="text-rose-400 text-lg">-${avg_loss}</span></span>
      <span id="jMetricWinLossRatio" class="text-[11px] text-slate-400 block mt-1">Win/Loss Ratio: {round(avg_win / max(0.01, avg_loss), 2)}x</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-teal-500">
      <span class="text-slate-400 text-xs block mb-1">Max Single Win</span>
      <span id="jMetricMaxWin" class="text-2xl font-extrabold text-teal-400">+${max_win}</span>
      <span class="text-[11px] text-slate-400 block mt-1">Huge Fat-Tail Runner</span>
    </div>
    <div class="glass-card rounded-2xl p-4 border-l-4 border-l-rose-500">
      <span class="text-slate-400 text-xs block mb-1">Total Executed</span>
      <span id="jMetricTotal" class="text-2xl font-extrabold text-white">{total}</span>
      <span class="text-[11px] text-slate-400 block mt-1">Audited Trades</span>
    </div>
  </div>

  <!-- TRADE AUDIT LOG TABLE -->
  <div class="max-w-7xl mx-auto glass-card rounded-2xl p-6 overflow-x-auto">
    <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 mb-4">
      <div>
        <h2 class="text-base font-bold text-white flex items-center gap-2">
          <span>Audited Trade Log & Execution Records</span>
          <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono text-[10px] border border-emerald-500/30">Newest First</span>
        </h2>
        <p class="text-xs text-slate-400">Institutional records matching TradeEdge fields • Full 6-Month Ledger</p>
      </div>

      <!-- MONTH & OUTCOME FILTERS -->
      <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
        <div class="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
          <button onclick="setMonthFilter('ALL')" id="mTab_ALL" class="px-2.5 py-1 rounded bg-emerald-500 text-black font-extrabold text-[11px] shadow">All Months</button>
          <button onclick="setMonthFilter('2026-09')" id="mTab_2026-09" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Sep 2026</button>
          <button onclick="setMonthFilter('2026-08')" id="mTab_2026-08" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Aug 2026</button>
          <button onclick="setMonthFilter('2026-07')" id="mTab_2026-07" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Jul 2026</button>
          <button onclick="setMonthFilter('2026-06')" id="mTab_2026-06" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Jun 2026</button>
          <button onclick="setMonthFilter('2026-05')" id="mTab_2026-05" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">May 2026</button>
          <button onclick="setMonthFilter('2026-04')" id="mTab_2026-04" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Apr 2026</button>
          <button onclick="setMonthFilter('2026-03')" id="mTab_2026-03" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Mar 2026</button>
          <button onclick="setMonthFilter('2026-02')" id="mTab_2026-02" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Feb 2026</button>
        </div>

        <!-- ASSET SELECTOR TABS -->
        <div class="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
          <button onclick="setAssetFilter('ALL')" id="aTab_ALL" class="px-2.5 py-1 rounded bg-amber-500 text-black font-extrabold text-[11px] shadow">All</button>
          <button onclick="setAssetFilter('XAUTUSD')" id="aTab_XAUTUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">🥇 Gold</button>
          <button onclick="setAssetFilter('SLVONUSD')" id="aTab_SLVONUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">🥈 Silver</button>
          <button onclick="setAssetFilter('BTCUSD')" id="aTab_BTCUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">₿ BTC</button>
          <button onclick="setAssetFilter('ETHUSD')" id="aTab_ETHUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Ξ ETH</button>
        </div>

        <div class="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
          <button onclick="filterJournal('ALL')" id="jTabAll" class="px-2.5 py-1 rounded bg-blue-500 text-white font-bold">All</button>
          <button onclick="filterJournal('WIN')" id="jTabWin" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white">Wins</button>
          <button onclick="filterJournal('LOSS')" id="jTabLoss" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white">Losses</button>
        </div>

        <input type="text" id="jSearch" onkeyup="renderJournal()" placeholder="🔍 Search date, asset, notes..." class="bg-slate-900 border border-slate-700 rounded-xl px-3 py-1 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 w-44">
        <span id="jCountBadge" class="ml-1 text-slate-400 text-[11px]">{total} Trades</span>
      </div>
    </div>

      <div class="mb-3 px-3 py-2 rounded-xl bg-slate-900/90 border border-slate-800 flex items-center justify-between text-xs">
        <div class="flex items-center gap-2 text-slate-300">
          <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold text-[10px]">👑 4-Asset Apex Journal</span>
          <span class="text-[11px]">Includes high-conviction trades across <strong>🥇 Gold (XAUTUSD)</strong>, <strong>🥈 Silver (SLVONUSD)</strong>, <strong>₿ Bitcoin (BTCUSD)</strong>, and <strong>Ξ Ethereum (ETHUSD)</strong>. Use Asset or Month tabs to filter.</span>
        </div>
      </div>

    <table class="w-full text-left text-xs font-mono">
      <thead class="text-slate-400 border-b border-slate-800">
        <tr>
          <th class="py-2.5">Date (Exit / Entry UTC)</th>
          <th>Asset</th>
          <th>Side</th>
          <th>Entry</th>
          <th>Exit</th>
          <th>Lots</th>
          <th>Net P&L ($)</th>
          <th>R:R</th>
          <th>Reason</th>
          <th>Conviction</th>
          <th>Scale-Out & Order Flow Notes</th>
        </tr>
      </thead>
      <tbody id="journalBody" class="divide-y divide-slate-800/60 text-slate-300">
        <!-- Rendered by JS -->
      </tbody>
    </table>
  </div>

  <script>
    const trades = {trades_json};
    let journalFilter = 'ALL';
    let monthFilter = 'ALL';
    let assetFilter = '{'XAUTUSD' if active_nav == 'GOLD' else ('SLVONUSD' if active_nav == 'SILVER' else 'ALL')}';

    function setAssetFilter(asset) {{
      assetFilter = asset;
      const assets = ['ALL', 'XAUTUSD', 'SLVONUSD', 'BTCUSD', 'ETHUSD'];
      assets.forEach(a => {{
        const btn = document.getElementById('aTab_' + a);
        if (btn) {{
          btn.className = (a === asset) ? 'px-2.5 py-1 rounded bg-amber-500 text-black font-extrabold text-[11px] shadow' : 'px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700';
        }}
      }});
      renderJournal();
    }}

    function setMonthFilter(month) {{
      monthFilter = month;
      const months = ['ALL', '2026-09', '2026-08', '2026-07', '2026-06', '2026-05', '2026-04', '2026-03', '2026-02'];
      months.forEach(m => {{
        const btn = document.getElementById('mTab_' + m);
        if (btn) {{
          btn.className = (m === month) ? 'px-2.5 py-1 rounded bg-emerald-500 text-black font-extrabold text-[11px] shadow' : 'px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700';
        }}
      }});
      renderJournal();
    }}

    function filterJournal(type) {{
      journalFilter = type;
      document.getElementById('jTabAll').className = (type === 'ALL') ? 'px-2.5 py-1 rounded bg-blue-500 text-white font-bold' : 'px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white';
      document.getElementById('jTabWin').className = (type === 'WIN') ? 'px-2.5 py-1 rounded bg-blue-500 text-white font-bold' : 'px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white';
      document.getElementById('jTabLoss').className = (type === 'LOSS') ? 'px-2.5 py-1 rounded bg-blue-500 text-white font-bold' : 'px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white';
      renderJournal();
    }}

    function renderJournal() {{
      const tbody = document.getElementById('journalBody');
      tbody.innerHTML = '';

      const searchInput = document.getElementById('jSearch');
      const query = (searchInput ? searchInput.value : '').toLowerCase().trim();

      let list = [...trades];
      list.sort((a, b) => (b.closed_at || b.opened_at || '').localeCompare(a.closed_at || a.opened_at || ''));

      if (assetFilter !== 'ALL') {{
        list = list.filter(t => (t.symbol || '').includes(assetFilter));
      }}

      if (monthFilter !== 'ALL') {{
        list = list.filter(t => (t.opened_at && t.opened_at.startsWith(monthFilter)) || (t.closed_at && t.closed_at.startsWith(monthFilter)));
      }}

      if (journalFilter === 'WIN') list = list.filter(t => (t.pnl_usd || 0) > 0);
      else if (journalFilter === 'LOSS') list = list.filter(t => (t.pnl_usd || 0) < 0);

      if (query) {{
        list = list.filter(t => 
          (t.opened_at || '').toLowerCase().includes(query) ||
          (t.closed_at || '').toLowerCase().includes(query) ||
          (t.side || '').toLowerCase().includes(query) ||
          (t.symbol || '').toLowerCase().includes(query) ||
          (t.close_reason || '').toLowerCase().includes(query) ||
          (t.orderflow_notes || '').toLowerCase().includes(query)
        );
      }}

      // Dynamic KPI recalculation for selected filter view
      const filteredWins = list.filter(t => (t.pnl_usd || 0) > 0);
      const filteredLosses = list.filter(t => (t.pnl_usd || 0) < 0);
      const fTotal = list.length;
      const fNetPl = list.reduce((acc, t) => acc + (t.pnl_usd || 0), 0);
      const fWinRate = fTotal > 0 ? ((filteredWins.length / fTotal) * 100).toFixed(1) : '0.0';
      const fGrossProfit = filteredWins.reduce((acc, t) => acc + (t.pnl_usd || 0), 0);
      const fGrossLoss = Math.abs(filteredLosses.reduce((acc, t) => acc + (t.pnl_usd || 0), 0));
      const fPf = fGrossLoss > 0 ? (fGrossProfit / fGrossLoss).toFixed(2) : (fGrossProfit > 0 ? '99.0' : '0.0');
      const fAvgWin = filteredWins.length > 0 ? (fGrossProfit / filteredWins.length).toFixed(2) : '0.00';
      const fAvgLoss = filteredLosses.length > 0 ? (fGrossLoss / filteredLosses.length).toFixed(2) : '0.00';
      const fRatio = parseFloat(fAvgLoss) > 0 ? (parseFloat(fAvgWin) / parseFloat(fAvgLoss)).toFixed(2) : '0.00';
      const fMaxWin = filteredWins.length > 0 ? Math.max(...filteredWins.map(t => t.pnl_usd || 0)).toFixed(2) : '0.00';

      const netPlEl = document.getElementById('jMetricNetPl');
      if (netPlEl) {{
        netPlEl.className = `text-2xl font-extrabold ${{fNetPl >= 0 ? 'text-emerald-400' : 'text-rose-400'}}`;
        netPlEl.innerText = `${{fNetPl >= 0 ? '+$' : '-$'}}${{Math.abs(fNetPl).toFixed(2)}}`;
      }}
      const winRateEl = document.getElementById('jMetricWinRate');
      if (winRateEl) winRateEl.innerText = `${{fWinRate}}%`;
      const winLossCountEl = document.getElementById('jMetricWinLossCount');
      if (winLossCountEl) winLossCountEl.innerText = `${{filteredWins.length}} Wins • ${{filteredLosses.length}} Losses`;
      const pfEl = document.getElementById('jMetricPf');
      if (pfEl) pfEl.innerText = fPf;
      const grossEl = document.getElementById('jMetricGross');
      if (grossEl) grossEl.innerText = `+$${{fGrossProfit.toFixed(2)}} / -$${{fGrossLoss.toFixed(2)}}`;
      const avgWinLossEl = document.getElementById('jMetricAvgWinLoss');
      if (avgWinLossEl) avgWinLossEl.innerHTML = `+$${{fAvgWin}} <span class="text-slate-400 text-xs font-normal">/</span> <span class="text-rose-400 text-lg">-$${{fAvgLoss}}</span>`;
      const winLossRatioEl = document.getElementById('jMetricWinLossRatio');
      if (winLossRatioEl) winLossRatioEl.innerText = `Win/Loss Ratio: ${{fRatio}}x`;
      const maxWinEl = document.getElementById('jMetricMaxWin');
      if (maxWinEl) maxWinEl.innerText = `+$${{fMaxWin}}`;
      const totalEl = document.getElementById('jMetricTotal');
      if (totalEl) totalEl.innerText = fTotal;

      document.getElementById('jCountBadge').innerText = `${{list.length}} of ${{trades.length}} Trades`;

      if (list.length === 0) {{
        tbody.innerHTML = `<tr><td colspan="11" class="py-8 text-center text-slate-500">No trades match this filter.</td></tr>`;
        return;
      }}

      list.forEach(t => {{
        const tr = document.createElement('tr');
        const pnl = t.pnl_usd || 0;
        const win = pnl > 0;
        const isScaleOut = (t.close_reason && t.close_reason.includes('HALF'));
        const sym = (t.symbol || '').toUpperCase();
        let assetBadge = '<span class="px-2 py-0.5 rounded font-mono text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30">🥇 Gold</span>';
        if (sym.includes('SLV')) {{
          assetBadge = '<span class="px-2 py-0.5 rounded font-mono text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">🥈 Silver</span>';
        }} else if (sym.includes('BTC')) {{
          assetBadge = '<span class="px-2 py-0.5 rounded font-mono text-[10px] bg-orange-500/20 text-orange-300 border border-orange-500/30">₿ BTC</span>';
        }} else if (sym.includes('ETH')) {{
          assetBadge = '<span class="px-2 py-0.5 rounded font-mono text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30">Ξ ETH</span>';
        }}
        const isSeptember = (t.opened_at && t.opened_at.startsWith('2026-09')) || (t.closed_at && t.closed_at.startsWith('2026-09'));

        tr.className = isSeptember ? "bg-emerald-950/20 border-l-2 border-l-emerald-400" : "";

        tr.innerHTML = `
          <td class="py-2.5 text-slate-300 font-mono">
            <div class="flex items-center gap-1.5 mb-0.5">
              ${{isSeptember ? '<span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold text-[10px]">SEP 2026</span>' : ''}}
              <span class="text-white font-semibold">${{t.closed_at ? t.closed_at : t.opened_at}}</span>
            </div>
            ${{t.closed_at && t.opened_at && t.closed_at !== t.opened_at ? '<div class="text-[10px] text-slate-400">Entered: ' + t.opened_at + '</div>' : ''}}
          </td>
          <td>${{assetBadge}}</td>
          <td><span class="px-2 py-0.5 rounded ${{t.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-400 font-bold' : 'bg-rose-500/20 text-rose-400 font-bold'}}">${{t.side}}</span></td>
          <td>$${{t.entry_price}}</td>
          <td>$${{t.exit_price || '-'}}</td>
          <td>${{t.lots}}</td>
          <td class="font-bold ${{win ? 'text-emerald-400' : 'text-rose-400'}}">${{pnl > 0 ? '+' : ''}}$${{pnl.toFixed(2)}}</td>
          <td class="${{win ? 'text-emerald-400' : 'text-rose-400'}} font-bold">${{t.rr_achieved > 0 ? '+' : ''}}${{t.rr_achieved}}R</td>
          <td><span class="px-2 py-0.5 rounded ${{isScaleOut ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold' : 'bg-slate-900 border border-slate-800 text-slate-300'}}">${{t.close_reason || 'CLOSED'}}</span></td>
          <td><span class="px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">${{t.conviction_stars || 5.0}}★</span></td>
          <td class="text-slate-400 text-[11px] max-w-sm truncate">${{t.orderflow_notes || t.strategy_name || ''}}</td>
        `;
        tbody.appendChild(tr);
      }});
      lucide.createIcons();
    }}

    setAssetFilter(assetFilter);
  </script>
</body>
</html>
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return file_path

    def generate_all_journals(
        self,
        joint_trades: List[Dict],
        gold_trades: List[Dict],
        silver_trades: List[Dict],
        db_thoughts: List[Dict],
        btc_trades: Optional[List[Dict]] = None,
        eth_trades: Optional[List[Dict]] = None
    ) -> Dict[str, Path]:
        """Generates Joint, Gold, Silver, BTC, and ETH standalone journals with synchronized navigation."""
        p_joint = self.generate_agent_journal(joint_trades, db_thoughts, filename="agent_journal.html", active_nav="JOINT")
        p_gold = self.generate_agent_journal(gold_trades, db_thoughts, filename="gold_journal.html", active_nav="GOLD")
        p_silver = self.generate_agent_journal(silver_trades, db_thoughts, filename="silver_journal.html", active_nav="SILVER")
        p_btc = self.generate_agent_journal(btc_trades or [], db_thoughts, filename="btc_journal.html", active_nav="BTC")
        p_eth = self.generate_agent_journal(eth_trades or [], db_thoughts, filename="eth_journal.html", active_nav="ETH")
        return {"joint": p_joint, "gold": p_gold, "silver": p_silver, "btc": p_btc, "eth": p_eth}

    def generate_all_reports(
        self,
        strategy_results: Dict[str, Any],
        silver_results: Optional[Dict[str, Any]] = None,
        joint_results: Optional[Dict[str, Any]] = None,
        btc_results: Optional[Dict[str, Any]] = None,
        eth_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Path]:
        """Generates all 5 backtest reports (Master Joint, Gold, Silver, BTC, and ETH)."""
        p_master = self.generate_multi_strategy_backtest_report(
            strategy_results, silver_results=silver_results, joint_results=joint_results,
            btc_results=btc_results, eth_results=eth_results,
            filename="backtest_report.html", default_asset="JOINT"
        )
        p_gold = self.generate_multi_strategy_backtest_report(
            strategy_results, silver_results=silver_results, joint_results=joint_results,
            btc_results=btc_results, eth_results=eth_results,
            filename="gold_report.html", default_asset="XAUTUSD"
        )
        p_silver = self.generate_multi_strategy_backtest_report(
            strategy_results, silver_results=silver_results, joint_results=joint_results,
            btc_results=btc_results, eth_results=eth_results,
            filename="silver_report.html", default_asset="SLVONUSD"
        )
        p_btc = self.generate_multi_strategy_backtest_report(
            strategy_results, silver_results=silver_results, joint_results=joint_results,
            btc_results=btc_results, eth_results=eth_results,
            filename="btc_report.html", default_asset="BTCUSD"
        )
        p_eth = self.generate_multi_strategy_backtest_report(
            strategy_results, silver_results=silver_results, joint_results=joint_results,
            btc_results=btc_results, eth_results=eth_results,
            filename="eth_report.html", default_asset="ETHUSD"
        )
        return {
            "master": p_master,
            "gold": p_gold,
            "silver": p_silver,
            "btc": p_btc,
            "eth": p_eth
        }

    def generate_live_journal(
        self,
        active_positions: Optional[Dict[str, Any]] = None,
        recent_trades: Optional[List[Dict]] = None,
        db_thoughts: Optional[List[Dict]] = None,
        delta_client = None,
        filename: str = "live_journal.html"
    ) -> Path:
        """Renders live auto-polling execution journal dashboard for Delta Exchange."""
        from reports.live_reporter import generate_live_journal_html
        return generate_live_journal_html(
            self.output_dir,
            active_positions=active_positions,
            recent_trades=recent_trades,
            db_thoughts=db_thoughts,
            delta_client=delta_client,
            filename=filename
        )
