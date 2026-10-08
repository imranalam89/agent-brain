import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

USD_TO_INR = 90.0  # Live Delta India conversion reference

def generate_backtest_v6_html(
    report_data: Dict[str, Any],
    output_dir: Path,
    filename: str = "backtest_v6.html"
) -> Path:
    """
    Renders institutional-grade Backtest V6 HTML Dashboard:
    - 3 Years Continuous Historical Data from Delta Exchange API (Oct 2023 - Oct 2026)
    - 24/7 Round-the-Clock Trading Coverage (All 24 Hours & All 7 Days)
    - Strategy: 💎 4-Asset Apex Hybrid Sniper ($5 Strict Risk Per Trade)
    - Time & Days Profitability Suite (Hourly Breakdown 00-23 IST + Day of Week Edge Monday-Sunday)
    - Interactive P&L Calendar Heatmap with full 37-month navigation
    - Winning and Losing Streak Analytics & KPI Badges
    - Multi-Timeframe Performance Breakdown: Yearly, Monthly, Weekly, and Custom Date Range
    - Dynamic Client-Side Filtering: Recalculates KPIs, Equity Curve, and Ledger on the fly
    - Zero 50% Cut (100% Position Retained for High R:R Expansion up to 40R)
    - 3-Layer Apex Hybrid Trailing Engine (Ratchet Floor + Structural Buffer + Reversal Pinch)
    - Squad Correlation Veto (Metals Squad vs Crypto Squad)
    - Calibrated Delta Exchange India Fees + 18% GST
    - Today's Live Trade Audit Section
    """
    file_path = output_dir / filename

    strategies = report_data.get("strategies", {})
    joint = report_data.get("joint_portfolio", {})
    per_pair = report_data.get("per_pair", {})

    if not strategies:
        strategies = {"V6_APEX_SNIPER_24_7": joint}

    default_key = report_data.get("default_strategy_key", "V6_APEX_SNIPER_24_7")
    sorted_strategies = sorted(strategies.items(), key=lambda item: item[1].get("net_pl", 0.0), reverse=True)
    active_key = default_key if default_key in strategies else (sorted_strategies[0][0] if sorted_strategies else "V6_APEX_SNIPER_24_7")
    active_strat = strategies.get(active_key, joint)

    def fmt_badge(strat_key: str, fallback: str = "+$0.00") -> str:
        st = strategies.get(strat_key)
        if not st:
            return fallback
        net = st.get("net_pl", 0.0)
        pfx = "+" if net >= 0 else "-"
        inr_val = abs(net * USD_TO_INR)
        if inr_val >= 100000:
            inr_str = f"{inr_val / 100000:.2f}L"
        else:
            inr_str = f"{inr_val:,.0f}"
        return f"{pfx}${abs(net):,.2f} (₹{inr_str})"

    # Generate dynamic navigation tabs
    nav_tabs_html = ""
    for idx, (k, strat) in enumerate(sorted_strategies):
        is_active = (k == active_key)
        active_cls = "bg-gradient-to-r from-emerald-500 to-teal-400 text-black shadow-lg shadow-emerald-950/40 ring-2 ring-emerald-400 font-bold" if is_active else "bg-slate-900 border border-slate-800 text-slate-300 hover:border-slate-700 hover:text-white font-semibold"
        badge_cls = "bg-black/20 text-black font-extrabold" if is_active else "bg-slate-800 text-slate-400 font-mono"
        badge_val = fmt_badge(k)
        name = strat.get("strategy_name", k)
        tab_label = name.split("(")[0].strip() if "(" in name else name
        nav_tabs_html += f"""
        <button id="tab_{k}" onclick="selectStrategy('{k}')" class="px-4 py-2.5 rounded-xl text-xs flex items-center gap-2 transition whitespace-nowrap {active_cls}">
          <span>{tab_label}</span>
          <span id="badge_{k}" class="px-2 py-0.5 rounded-full text-[11px] {badge_cls}">{badge_val}</span>
        </button>"""

    # Generate dynamic Leaderboard rows
    leaderboard_rows_html = ""
    for rank, (k, s_data) in enumerate(sorted_strategies, 1):
        is_selected = (k == active_key)
        row_bg = "bg-emerald-950/20 border-l-4 border-emerald-500" if is_selected else ""
        trades = s_data.get("trades", [])
        net = s_data.get("net_pl", 0.0)
        net_inr = net * USD_TO_INR
        inr_fmt = f"{net_inr/100000:.2f}L" if net_inr >= 100000 else f"{net_inr:,.0f}"
        wr = s_data.get("win_rate", 0.0)
        pf = s_data.get("profit_factor", 0.0)
        tot_tr = s_data.get("total_trades", len(trades))
        strat_full_name = s_data.get("strategy_name", k)
        fees = s_data.get("total_fees", 0.0)
        max_dd = s_data.get("max_drawdown_usd", 0.0)
        max_w = s_data.get("max_w_streak", 0)
        max_l = s_data.get("max_l_streak", 0)

        t_under_2 = sum(1 for t in trades if 0 < t.get("pnl_usd", 0.0) < 2.0)
        t_2_5 = sum(1 for t in trades if 2.0 <= t.get("pnl_usd", 0.0) < 5.0)
        t_5_10 = sum(1 for t in trades if 5.0 <= t.get("pnl_usd", 0.0) < 10.0)
        t_10_50 = sum(1 for t in trades if 10.0 <= t.get("pnl_usd", 0.0) < 50.0)
        t_50_100 = sum(1 for t in trades if 50.0 <= t.get("pnl_usd", 0.0) < 100.0)
        t_100_150 = sum(1 for t in trades if 100.0 <= t.get("pnl_usd", 0.0) < 150.0)
        t_above_150 = sum(1 for t in trades if t.get("pnl_usd", 0.0) >= 150.0)

        btn_action = f"""<button onclick="selectStrategy('{k}')" class="px-3 py-1.5 rounded {'bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold shadow-sm' if is_selected else 'bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold'} text-[11px] transition">{'★ Active View' if is_selected else 'Load View'}</button>"""

        leaderboard_rows_html += f"""
            <tr class="hover:bg-slate-900/60 transition {row_bg}">
              <td class="py-3 px-4 font-bold text-white">
                <div class="flex items-center gap-2">
                  <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-amber-400 font-mono font-bold">#{rank}</span>
                  <div>
                    <div class="{'text-emerald-300' if is_selected else 'text-white'} font-semibold">{strat_full_name}</div>
                    <div class="text-[10px] text-slate-400 font-normal">Model ID: {k}</div>
                  </div>
                </div>
              </td>
              <td class="py-3 px-3"><span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700">Strict $5 Fixed</span></td>
              <td class="py-3 px-3 text-right text-slate-200 font-mono">{tot_tr:,}</td>
              <td class="py-3 px-3 text-right font-bold text-white font-mono">{wr:.1f}%</td>
              <td class="py-3 px-3 text-right text-cyan-400 font-bold font-mono">{pf:.2f}</td>
              <td class="py-3 px-3 text-right font-mono text-amber-400">-${fees:,.2f}</td>
              <td class="py-3 px-3 text-right font-extrabold text-emerald-400 font-mono">+${net:,.2f}</td>
              <td class="py-3 px-3 text-right font-extrabold text-emerald-400 font-mono">+₹{inr_fmt}</td>
              <td class="py-3 px-2 text-right font-mono text-slate-400">{t_under_2}</td>
              <td class="py-3 px-2 text-right font-mono text-slate-300">{t_2_5}</td>
              <td class="py-3 px-2 text-right font-mono text-slate-200">{t_5_10}</td>
              <td class="py-3 px-2 text-right font-mono text-emerald-400 font-semibold">{t_10_50}</td>
              <td class="py-3 px-2 text-right font-mono text-teal-300 font-semibold">{t_50_100}</td>
              <td class="py-3 px-2 text-right font-mono text-cyan-300 font-semibold">{t_100_150}</td>
              <td class="py-3 px-2 text-right font-mono text-amber-300 font-bold">{t_above_150}</td>
              <td class="py-3 px-2 text-right font-mono text-emerald-400 font-bold">{max_w}</td>
              <td class="py-3 px-2 text-right font-mono text-rose-400 font-bold">{max_l}</td>
              <td class="py-3 px-3 text-right font-mono text-rose-400">-${max_dd:,.2f}</td>
              <td class="py-3 px-4 text-center">{btn_action}</td>
            </tr>"""

    # Build Yearly YoY rows
    yearly_rows_html = ""
    for y in active_strat.get("yearly_summary", []):
        yr = y["year"]
        tr = y["trades"]
        wr = y["win_rate"]
        fees = y["total_fees"]
        net = y["net_pnl"]
        net_inr = y["net_pnl_inr"]
        pf = y["profit_factor"]
        inr_str = f"{net_inr/100000:.2f}L" if abs(net_inr) >= 100000 else f"{abs(net_inr):,.0f}"
        pnl_cls = "text-emerald-400" if net >= 0 else "text-rose-400"
        pfx = "+" if net >= 0 else "-"
        yearly_rows_html += f"""
        <tr class="hover:bg-slate-900/60 transition">
          <td class="py-3 px-4 font-bold text-white font-mono flex items-center gap-2">
            <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs">{yr}</span>
            <span class="text-xs text-slate-300">{'Oct-Dec 2023 (Delta Launch)' if yr == '2023' else ('Full Year 2024' if yr == '2024' else ('Full Year 2025' if yr == '2025' else 'Jan-Oct 2026 (YTD)'))}</span>
          </td>
          <td class="py-3 px-3 text-right font-mono text-slate-200">{tr:,}</td>
          <td class="py-3 px-3 text-right font-mono text-emerald-400 font-semibold">{y['wins']:,}</td>
          <td class="py-3 px-3 text-right font-mono text-rose-400">{y['losses']:,}</td>
          <td class="py-3 px-3 text-right font-mono text-white font-bold">{wr:.1f}%</td>
          <td class="py-3 px-3 text-right font-mono text-cyan-400 font-bold">{pf:.2f}</td>
          <td class="py-3 px-3 text-right font-mono text-amber-400">-${fees:,.2f}</td>
          <td class="py-3 px-3 text-right font-mono font-extrabold {pnl_cls}">{pfx}${abs(net):,.2f}</td>
          <td class="py-3 px-3 text-right font-mono font-extrabold {pnl_cls}">{pfx}₹{inr_str}</td>
          <td class="py-3 px-4 text-center">
            <button onclick="filterByYear('{yr}')" class="px-3 py-1 rounded-lg bg-slate-800 hover:bg-emerald-500 hover:text-black text-slate-200 font-bold text-[11px] transition">Filter Year</button>
          </td>
        </tr>"""

    # Build Monthly rows
    monthly_rows_html = ""
    for m in active_strat.get("monthly_summary", []):
        ym = m["month_str"]
        tr = m["trades"]
        wr = m["win_rate"]
        fees = m["total_fees"]
        net = m["net_pnl"]
        net_inr = m["net_pnl_inr"]
        pf = m["profit_factor"]
        pnl_cls = "text-emerald-400" if net >= 0 else "text-rose-400"
        pfx = "+" if net >= 0 else "-"
        inr_str = f"{net_inr/100000:.2f}L" if abs(net_inr) >= 100000 else f"{abs(net_inr):,.0f}"
        status_badge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">PROFITABLE</span>' if net > 0 else '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30">DRAWDOWN</span>'
        monthly_rows_html += f"""
        <tr class="hover:bg-slate-900/60 transition">
          <td class="py-2.5 px-4 font-mono font-semibold text-white">{ym} ({m['month'][:3]} {m['year']})</td>
          <td class="py-2.5 px-3 text-center">{status_badge}</td>
          <td class="py-2.5 px-3 text-right font-mono text-slate-200">{tr:,}</td>
          <td class="py-2.5 px-3 text-right font-mono text-emerald-400 font-semibold">{m['wins']:,}</td>
          <td class="py-2.5 px-3 text-right font-mono text-rose-400">{m['losses']:,}</td>
          <td class="py-2.5 px-3 text-right font-mono text-white font-bold">{wr:.1f}%</td>
          <td class="py-2.5 px-3 text-right font-mono text-cyan-400 font-bold">{pf:.2f}</td>
          <td class="py-2.5 px-3 text-right font-mono text-amber-400">-${fees:,.2f}</td>
          <td class="py-2.5 px-3 text-right font-mono font-extrabold {pnl_cls}">{pfx}${abs(net):,.2f}</td>
          <td class="py-2.5 px-3 text-right font-mono font-extrabold {pnl_cls}">{pfx}₹{inr_str}</td>
          <td class="py-2.5 px-4 text-center">
            <button onclick="filterByMonth('{ym}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-cyan-500 hover:text-black text-slate-200 font-bold text-[10px] transition">Filter Month</button>
          </td>
        </tr>"""

    # Build Weekly rows
    weekly_rows_html = ""
    for w in reversed(active_strat.get("weekly_summary", [])):
        yw = w["week_str"]
        tr = w["trades"]
        wr = w["win_rate"]
        fees = w["total_fees"]
        net = w["net_pnl"]
        net_inr = w["net_pnl_inr"]
        pf = w["profit_factor"]
        pnl_cls = "text-emerald-400" if net >= 0 else "text-rose-400"
        pfx = "+" if net >= 0 else "-"
        weekly_rows_html += f"""
        <tr class="hover:bg-slate-900/60 transition">
          <td class="py-2 px-3 font-mono font-semibold text-white">{yw}</td>
          <td class="py-2 px-3 font-mono text-slate-300 text-[11px]">{w['start_date']} &rarr; {w['end_date']}</td>
          <td class="py-2 px-3 text-right font-mono text-slate-200">{tr:,}</td>
          <td class="py-2 px-3 text-right font-mono text-white font-bold">{wr:.1f}%</td>
          <td class="py-2 px-3 text-right font-mono text-cyan-400 font-bold">{pf:.2f}</td>
          <td class="py-2 px-3 text-right font-mono text-amber-400">-${fees:,.2f}</td>
          <td class="py-2 px-3 text-right font-mono font-extrabold {pnl_cls}">{pfx}${abs(net):,.2f}</td>
          <td class="py-2 px-3 text-right font-mono font-extrabold {pnl_cls}">{pfx}₹{abs(net_inr):,.0f}</td>
          <td class="py-2 px-3 text-center">
            <button onclick="filterByWeek('{w['start_date']}', '{w['end_date']}', '{yw}')" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-amber-400 hover:text-black text-slate-300 font-bold text-[10px] transition">Filter</button>
          </td>
        </tr>"""

    # Serialize data for client-side interactivity
    strategies_json = json.dumps(strategies, default=str)
    per_pair_json = json.dumps(per_pair, default=str)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Brain | Backtest V6 (💎 3-Year 24/7 Apex Hybrid Sniper • Calendar • Journal • Streaks • Time &amp; Days Edge)</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    body {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: #060911;
      color: #e2e8f0;
    }}
    .mono {{ font-family: 'JetBrains Mono', monospace; }}
    .glass {{
      background: rgba(13, 19, 33, 0.75);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.07);
    }}
    .glass-card {{
      background: rgba(15, 23, 42, 0.65);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .day-cell {{
      transition: all 0.15s ease-in-out;
    }}
    .day-cell:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 16px -2px rgba(0, 0, 0, 0.5);
    }}
    .custom-scroll::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    .custom-scroll::-webkit-scrollbar-track {{
      background: #060911;
    }}
    .custom-scroll::-webkit-scrollbar-thumb {{
      background: #1e293b;
      border-radius: 4px;
    }}
    .custom-scroll::-webkit-scrollbar-thumb:hover {{
      background: #334155;
    }}
  </style>
</head>
<body class="min-h-screen p-4 md:p-8 space-y-6 custom-scroll">

  <!-- TOP HEADER & BRANDING -->
  <header class="glass rounded-2xl p-6 border-emerald-500/30 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950">
    <div class="flex items-center gap-4">
      <div class="w-12 h-12 rounded-xl bg-gradient-to-tr from-amber-500 via-emerald-500 to-cyan-400 flex items-center justify-center text-black font-extrabold text-2xl shadow-lg shadow-emerald-500/20">
        👑
      </div>
      <div>
        <div class="flex items-center gap-2">
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/30">BACKTEST V6 FLAGSHIP</span>
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 font-bold border border-cyan-500/30">24/7 ROUND-THE-CLOCK (3 YEARS)</span>
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 font-bold border border-purple-500/30">STRICT $5.00 RISK</span>
        </div>
        <h1 class="text-xl md:text-2xl font-black text-white mt-1 flex items-center gap-2">
          💎 4-Asset Apex Hybrid Sniper 24/7
        </h1>
        <p class="text-xs text-slate-400 mt-0.5">
          3-Year Historical Audit (Oct 2023 &ndash; Oct 2026) from Delta Exchange API &bull; Gold, Silver, BTC &amp; ETH &bull; Calendar Heatmap &bull; Time &amp; Days Edge &bull; Streak Analysis
        </p>
      </div>
    </div>

    <!-- QUICK CURRENCY & ACTIONS -->
    <div class="flex items-center gap-3">
      <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-1 flex items-center text-xs">
        <button id="currBtnUSD" onclick="setCurrency(false)" class="px-3 py-1.5 rounded-lg bg-emerald-500 text-black font-bold transition">USD ($)</button>
        <button id="currBtnINR" onclick="setCurrency(true)" class="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white font-semibold transition">INR (₹90)</button>
      </div>
      <button onclick="exportTradesCSV()" class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 hover:border-slate-600 text-xs font-semibold text-slate-300 flex items-center gap-1.5 transition">
        <i data-lucide="download" class="w-4 h-4"></i> Export CSV
      </button>
      <button onclick="window.print()" class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 hover:border-slate-600 text-xs font-semibold text-slate-300 flex items-center gap-1.5 transition">
        <i data-lucide="printer" class="w-4 h-4"></i> Print
      </button>
    </div>
  </header>

  <!-- STRATEGY MODEL TABS -->
  <div class="glass rounded-2xl p-4 border-slate-800">
    <div class="flex items-center justify-between gap-2 mb-3">
      <div class="flex items-center gap-2">
        <i data-lucide="zap" class="w-4 h-4 text-amber-400"></i>
        <span class="text-xs font-bold text-white uppercase tracking-wider">Select 24/7 Strategy View:</span>
      </div>
      <span class="text-[11px] text-slate-400 font-mono">1-Click Switch Updates Entire Dashboard &bull; All 3 Years</span>
    </div>
    <div class="flex items-center gap-2 overflow-x-auto pb-1 custom-scroll">
      {nav_tabs_html}
    </div>
  </div>

  <!-- MULTI-TIMEFRAME DATE FILTER TOOLBAR -->
  <div class="glass rounded-2xl p-5 border-cyan-500/30 bg-gradient-to-r from-slate-950 via-slate-900/90 to-slate-950">
    <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <span class="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
            <i data-lucide="calendar" class="w-4 h-4"></i> Interactive Timeframe Filter Engine
          </span>
          <span id="activeFilterBadge" class="text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 font-mono font-bold border border-cyan-500/40">
            All 3 Years (Oct 2023 - Oct 2026)
          </span>
        </div>
        <div class="text-xs text-slate-300 mt-1">
          Filter KPIs, charts, streak graphs, heatmap, and the full trade journal by any Year, Month, Week, or Custom Date!
        </div>
      </div>

      <!-- Quick Year Filter Buttons -->
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-xs text-slate-400 font-semibold mr-1">Quick Year:</span>
        <button id="yearBtn_ALL" onclick="filterByYear('ALL')" class="px-3 py-1.5 rounded-xl text-xs font-bold bg-cyan-500 text-black shadow-sm transition">All 3 Years</button>
        <button id="yearBtn_2023" onclick="filterByYear('2023')" class="px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 transition">2023 (Q4)</button>
        <button id="yearBtn_2024" onclick="filterByYear('2024')" class="px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 transition">2024</button>
        <button id="yearBtn_2025" onclick="filterByYear('2025')" class="px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 transition">2025</button>
        <button id="yearBtn_2026" onclick="filterByYear('2026')" class="px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 transition">2026 (YTD)</button>
      </div>
    </div>

    <!-- Custom Date Range Form -->
    <div class="mt-4 pt-4 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-xs">
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2">
          <label class="text-slate-400 font-semibold">Start Date:</label>
          <input type="date" id="customStartDate" min="2023-10-01" max="2026-10-08" value="2023-10-08" class="bg-slate-900 border border-slate-700 text-white rounded-lg px-2.5 py-1.5 font-mono text-xs focus:ring-1 focus:ring-cyan-400 outline-none">
        </div>
        <div class="flex items-center gap-2">
          <label class="text-slate-400 font-semibold">End Date:</label>
          <input type="date" id="customEndDate" min="2023-10-01" max="2026-10-08" value="2026-10-07" class="bg-slate-900 border border-slate-700 text-white rounded-lg px-2.5 py-1.5 font-mono text-xs focus:ring-1 focus:ring-cyan-400 outline-none">
        </div>
        <button onclick="applyCustomDateFilter()" class="px-4 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold transition shadow-sm">
          Apply Custom Filter
        </button>
        <button onclick="resetDateFilter()" id="resetDateBtn" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold transition hidden">
          Reset Filter ✕
        </button>
      </div>

      <div class="text-slate-400 font-mono text-[11px] flex items-center gap-2">
        <span>Active Trade Filter:</span>
        <span id="filteredTradeCountBadge" class="text-white font-bold px-2 py-0.5 rounded bg-slate-800 border border-slate-700">8,700 Trades</span>
      </div>
    </div>
  </div>

  <!-- TOP SCORECARD METRICS (WITH STREAKS & EXACT COMMISSIONS) -->
  <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
    <!-- Initial Capital -->
    <div class="glass-card rounded-xl p-3.5 flex flex-col justify-between">
      <span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Initial Capital</span>
      <div class="mt-2">
        <div class="text-lg font-bold text-white mono">$50.00</div>
        <div class="text-[10px] text-slate-400 mt-0.5">₹4,500 INR</div>
      </div>
    </div>

    <!-- Real Net Profit -->
    <div class="glass-card rounded-xl p-3.5 flex flex-col justify-between border-emerald-500/30 bg-emerald-950/10">
      <span class="text-[10px] font-semibold text-emerald-300 uppercase tracking-wider">Real Net Profit</span>
      <div class="mt-2">
        <div class="text-lg font-extrabold text-emerald-400 mono" id="topNetPnl">+$2,407.67</div>
        <div class="text-[10px] font-bold text-emerald-400 mt-0.5" id="topNetPnlInr">+₹2.17L (+4,815.3%)</div>
      </div>
    </div>

    <!-- Win Rate -->
    <div class="glass-card rounded-xl p-3.5 flex flex-col justify-between">
      <span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Win Rate</span>
      <div class="mt-2">
        <div class="text-lg font-extrabold text-white mono" id="topWinRate">39.1%</div>
        <div class="text-[10px] text-slate-400" id="topWinsLosses">3,400W / 5,300L (8,700 Tr)</div>
      </div>
    </div>

    <!-- Gross Profit vs Loss -->
    <div class="glass-card rounded-xl p-3.5 flex flex-col justify-between">
      <span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Gross Profit / Loss</span>
      <div class="mt-2">
        <div class="text-xs font-bold text-emerald-400 mono" id="topGrossProfit">+$41,439.50</div>
        <div class="text-xs font-bold text-rose-400 mono" id="topGrossLoss">-$26,500.00</div>
      </div>
    </div>

    <!-- Delta Fees Paid -->
    <div class="glass-card rounded-xl p-3.5 flex flex-col justify-between border-amber-500/20 bg-amber-950/10">
      <span class="text-[10px] font-semibold text-amber-300 uppercase tracking-wider flex items-center gap-1">
        <i data-lucide="receipt" class="w-3 h-3"></i> Delta Fees
      </span>
      <div class="mt-2">
        <div class="text-lg font-extrabold text-amber-400 mono" id="topTotalFees">-$12,531.85</div>
        <div class="text-[10px] text-slate-300 mt-0.5" id="topTotalFeesInr">~₹11.28L INR</div>
      </div>
    </div>

    <!-- Profit Factor & Max DD -->
    <div class="glass-card rounded-xl p-3.5 flex flex-col justify-between">
      <span class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">PF &amp; Max DD</span>
      <div class="mt-2">
        <div class="text-sm font-extrabold text-cyan-400 mono" id="topPf">PF: 1.98</div>
        <div class="text-[10px] text-rose-400 mono mt-0.5" id="topMaxDd">Max DD: -$638.43</div>
      </div>
    </div>

    <!-- Winning Streak Card -->
    <div class="glass-card rounded-xl p-3.5 flex flex-col justify-between border-emerald-500/20 bg-emerald-950/15">
      <span class="text-[10px] font-semibold text-emerald-300 uppercase tracking-wider flex items-center gap-1">
        <i data-lucide="flame" class="w-3 h-3 text-emerald-400"></i> Winning Streak
      </span>
      <div class="mt-2">
        <div class="text-lg font-extrabold text-emerald-400 mono" id="topWinStreak">18 Wins</div>
        <div class="text-[10px] text-slate-400 mt-0.5" id="topAvgWinStreak">Avg: 3.65 consecutive</div>
      </div>
    </div>

    <!-- Losing Streak Card -->
    <div class="glass-card rounded-xl p-3.5 flex flex-col justify-between border-rose-500/20 bg-rose-950/15">
      <span class="text-[10px] font-semibold text-rose-300 uppercase tracking-wider flex items-center gap-1">
        <i data-lucide="shield-alert" class="w-3 h-3 text-rose-400"></i> Losing Streak
      </span>
      <div class="mt-2">
        <div class="text-lg font-extrabold text-rose-400 mono" id="topLossStreak">9 Losses</div>
        <div class="text-[10px] text-slate-400 mt-0.5" id="topAvgLossStreak">Avg: 1.82 consecutive</div>
      </div>
    </div>
  </div>

  <!-- INTERACTIVE EQUITY CURVE CHART -->
  <div class="glass rounded-2xl p-6 border-slate-800">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
      <div>
        <h2 class="text-base font-extrabold text-white flex items-center gap-2">
          📈 Cumulative Equity Curve (24/7 &bull; $50 Base &bull; 100% Reinvested Net Growth)
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          Dynamic equity growth across the active timeframe with exact fees and GST deducted after every single closed position.
        </p>
      </div>
      <div class="flex items-center gap-2 text-xs">
        <span class="px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 font-mono font-bold border border-emerald-500/20">
          Peak Equity: <span id="chartPeakVal">$2,457.67</span>
        </span>
      </div>
    </div>
    <div class="h-72 w-full">
      <canvas id="equityChartCanvas"></canvas>
    </div>
  </div>

  <!-- TIME & DAY PROFITABILITY SUITE (CORE REQUESTED FEATURE) -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- Hourly Profitability Breakdown -->
    <div class="glass rounded-2xl p-6 border-slate-800">
      <div class="flex items-center justify-between mb-3">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <i data-lucide="clock" class="w-5 h-5 text-amber-400"></i>
            <span>⏰ 24-Hour Hourly Profitability Breakdown (IST)</span>
          </h2>
          <p class="text-xs text-slate-400">Net P&amp;L performance across all 24 hours of the day (00:00 to 23:00 IST)</p>
        </div>
        <span id="bestHourBadge" class="font-mono text-[11px] px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
          Best Hour: 22:00 IST (+$358.41)
        </span>
      </div>
      <div class="h-64 w-full">
        <canvas id="hourlyChart"></canvas>
      </div>
      <div class="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
        <div class="flex items-center gap-2">
          <span class="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/60 text-emerald-400">● Green = Profitable Hour</span>
          <span class="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-800/60 text-rose-400">● Red = Loss Hour</span>
        </div>
        <span id="worstHourBadge" class="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-800/60 text-rose-300">
          Worst Hour: 09:00 IST (-$180.13)
        </span>
      </div>
    </div>

    <!-- Day of Week Profitability -->
    <div class="glass rounded-2xl p-6 border-slate-800">
      <div class="flex items-center justify-between mb-3">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <i data-lucide="calendar-days" class="w-5 h-5 text-cyan-400"></i>
            <span>📅 Day of the Week Edge (Monday – Sunday)</span>
          </h2>
          <p class="text-xs text-slate-400">Win rate and net profitability by day of week across the full 7-day cycle</p>
        </div>
        <span id="bestDayBadge" class="font-mono text-[11px] px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
          Best Day: Wednesday (+$669.58)
        </span>
      </div>
      <div class="h-64 w-full">
        <canvas id="dowChart"></canvas>
      </div>
      <div id="dowSummaryCards" class="mt-3 grid grid-cols-7 gap-1 font-mono text-center text-[10px]">
        <!-- Rendered dynamically by JS -->
      </div>
    </div>
  </div>

  <!-- INTERACTIVE P&L CALENDAR HEATMAP (FULL 37-MONTH NAVIGATION) -->
  <div class="glass rounded-2xl p-6 border-slate-800">
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
      <div>
        <h2 class="text-lg font-bold text-white flex items-center gap-2">
          <i data-lucide="calendar" class="w-5 h-5 text-emerald-400"></i> Interactive P&amp;L Calendar Heatmap (Real Net Profit)
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          Color-coded daily Net P&amp;L after Delta Exchange fees. Click any date tile to filter the execution ledger below!
        </p>
      </div>

      <!-- Month Navigation -->
      <div class="flex items-center gap-3">
        <button onclick="changeCalMonth(-1)" class="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white transition">
          <i data-lucide="chevron-left" class="w-4 h-4"></i>
        </button>
        <span id="calMonthTitle" class="text-sm font-bold text-white mono min-w-[140px] text-center">October 2026</span>
        <button onclick="changeCalMonth(1)" class="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white transition">
          <i data-lucide="chevron-right" class="w-4 h-4"></i>
        </button>
        <button onclick="resetDateFilter()" id="resetCalFilterBtn" class="hidden px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition">
          Reset Filter ✕
        </button>
      </div>
    </div>

    <!-- Calendar Grid -->
    <div class="grid grid-cols-7 gap-2 mb-2 text-center text-[11px] font-bold text-slate-400 uppercase tracking-wider">
      <div>Sun</div><div>Mon</div><div>Tue</div><div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div>
    </div>
    <div id="calendarDaysGrid" class="grid grid-cols-7 gap-2">
      <!-- Rendered dynamically by JavaScript -->
    </div>
  </div>

  <!-- BREAKDOWN TABS: YEAR-OVER-YEAR, MONTHLY MATRIX, WEEKLY MATRIX, LEADERBOARD -->
  <div class="glass rounded-2xl p-6 border-slate-800">
    <div class="flex items-center justify-between border-b border-slate-800 pb-4 mb-4 flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <button id="viewTab_YoY" onclick="switchBreakdownView('YoY')" class="px-4 py-2 rounded-xl text-xs font-bold bg-emerald-500 text-black shadow-sm transition">📅 Year-over-Year Summary</button>
        <button id="viewTab_Monthly" onclick="switchBreakdownView('Monthly')" class="px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition">🗓️ Monthly Breakdown (37 Months)</button>
        <button id="viewTab_Weekly" onclick="switchBreakdownView('Weekly')" class="px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition">📊 Weekly Performance</button>
        <button id="viewTab_Leaderboard" onclick="switchBreakdownView('Leaderboard')" class="px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition">🏆 Strategy Leaderboard</button>
      </div>
      <div class="text-xs text-slate-400 font-mono">
        Click any row's filter button to isolate that period!
      </div>
    </div>

    <!-- VIEW 1: YEAR-OVER-YEAR TABLE -->
    <div id="viewContainer_YoY" class="overflow-x-auto custom-scroll rounded-xl border border-slate-800">
      <table class="w-full text-xs text-left border-collapse bg-slate-950/60">
        <thead class="bg-slate-900 text-slate-400 uppercase text-[10px] tracking-wider font-mono border-b border-slate-800">
          <tr>
            <th class="py-3 px-4">Calendar Year / Period</th>
            <th class="py-3 px-3 text-right">Trades</th>
            <th class="py-3 px-3 text-right text-emerald-400">Wins</th>
            <th class="py-3 px-3 text-right text-rose-400">Losses</th>
            <th class="py-3 px-3 text-right text-white">Win Rate</th>
            <th class="py-3 px-3 text-right text-cyan-400">Profit Factor</th>
            <th class="py-3 px-3 text-right text-amber-400">Delta Fees</th>
            <th class="py-3 px-3 text-right text-emerald-400 font-bold">Net P&amp;L ($)</th>
            <th class="py-3 px-3 text-right text-emerald-400 font-bold">Net P&amp;L (₹)</th>
            <th class="py-3 px-4 text-center">Action</th>
          </tr>
        </thead>
        <tbody id="yearlyTableBody" class="divide-y divide-slate-800/60 font-mono text-[11px]">
          {yearly_rows_html}
        </tbody>
      </table>
    </div>

    <!-- VIEW 2: MONTHLY BREAKDOWN TABLE -->
    <div id="viewContainer_Monthly" class="hidden overflow-x-auto custom-scroll rounded-xl border border-slate-800 max-h-[460px]">
      <table class="w-full text-xs text-left border-collapse bg-slate-950/60">
        <thead class="sticky top-0 bg-slate-900 text-slate-400 uppercase text-[10px] tracking-wider font-mono border-b border-slate-800 z-10">
          <tr>
            <th class="py-3 px-4">Month / Year</th>
            <th class="py-3 px-3 text-center">Status</th>
            <th class="py-3 px-3 text-right">Trades</th>
            <th class="py-3 px-3 text-right text-emerald-400">Wins</th>
            <th class="py-3 px-3 text-right text-rose-400">Losses</th>
            <th class="py-3 px-3 text-right text-white">Win Rate</th>
            <th class="py-3 px-3 text-right text-cyan-400">Profit Factor</th>
            <th class="py-3 px-3 text-right text-amber-400">Delta Fees</th>
            <th class="py-3 px-3 text-right text-emerald-400 font-bold">Net P&amp;L ($)</th>
            <th class="py-3 px-3 text-right text-emerald-400 font-bold">Net P&amp;L (₹)</th>
            <th class="py-3 px-4 text-center">Filter</th>
          </tr>
        </thead>
        <tbody id="monthlyTableBody" class="divide-y divide-slate-800/60 font-mono text-[11px]">
          {monthly_rows_html}
        </tbody>
      </table>
    </div>

    <!-- VIEW 3: WEEKLY BREAKDOWN TABLE -->
    <div id="viewContainer_Weekly" class="hidden overflow-x-auto custom-scroll rounded-xl border border-slate-800 max-h-[460px]">
      <table class="w-full text-xs text-left border-collapse bg-slate-950/60">
        <thead class="sticky top-0 bg-slate-900 text-slate-400 uppercase text-[10px] tracking-wider font-mono border-b border-slate-800 z-10">
          <tr>
            <th class="py-2.5 px-3">ISO Week</th>
            <th class="py-2.5 px-3">Date Range</th>
            <th class="py-2.5 px-3 text-right">Trades</th>
            <th class="py-2.5 px-3 text-right text-white">Win Rate</th>
            <th class="py-2.5 px-3 text-right text-cyan-400">Profit Factor</th>
            <th class="py-2.5 px-3 text-right text-amber-400">Fees ($)</th>
            <th class="py-2.5 px-3 text-right text-emerald-400 font-bold">Net P&amp;L ($)</th>
            <th class="py-2.5 px-3 text-right text-emerald-400 font-bold">Net P&amp;L (₹)</th>
            <th class="py-2.5 px-3 text-center">Action</th>
          </tr>
        </thead>
        <tbody id="weeklyTableBody" class="divide-y divide-slate-800/60 font-mono text-[11px]">
          {weekly_rows_html}
        </tbody>
      </table>
    </div>

    <!-- VIEW 4: STRATEGY LEADERBOARD TABLE -->
    <div id="viewContainer_Leaderboard" class="hidden overflow-x-auto custom-scroll rounded-xl border border-slate-800">
      <table class="w-full text-xs text-left border-collapse bg-slate-950/60">
        <thead class="bg-slate-900 text-slate-400 uppercase text-[10px] tracking-wider font-mono border-b border-slate-800">
          <tr>
            <th class="py-3 px-4">Strategy Model</th>
            <th class="py-3 px-3">Risk Sizing</th>
            <th class="py-3 px-3 text-right">Trades</th>
            <th class="py-3 px-3 text-right">Win Rate</th>
            <th class="py-3 px-3 text-right">Profit Factor</th>
            <th class="py-3 px-3 text-right text-amber-400">Delta Fees</th>
            <th class="py-3 px-3 text-right text-emerald-400">Real Net ($)</th>
            <th class="py-3 px-3 text-right text-emerald-400">Real Net (₹)</th>
            <th class="py-3 px-2 text-right text-slate-400">&lt;$2</th>
            <th class="py-3 px-2 text-right text-slate-300">$2-$5</th>
            <th class="py-3 px-2 text-right text-slate-200">$5-$10</th>
            <th class="py-3 px-2 text-right text-emerald-400">$10-$50</th>
            <th class="py-3 px-2 text-right text-teal-300">$50-$100</th>
            <th class="py-3 px-2 text-right text-cyan-300">$100-$150</th>
            <th class="py-3 px-2 text-right text-amber-300">&gt;$150</th>
            <th class="py-3 px-2 text-right text-emerald-400">Max W</th>
            <th class="py-3 px-2 text-right text-rose-400">Max L</th>
            <th class="py-3 px-3 text-right text-rose-400">Max DD</th>
            <th class="py-3 px-4 text-center">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-800/60 font-mono text-[11px]">
          {leaderboard_rows_html}
        </tbody>
      </table>
    </div>
  </div>

  <!-- 3-YEAR MASTER TRADE JOURNAL & AUDIT LEDGER -->
  <div class="glass rounded-2xl p-6 border-slate-800">
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4 pb-4 border-b border-slate-800">
      <div>
        <h2 class="text-base font-extrabold text-white flex items-center gap-2">
          📖 3-Year Master Trade Journal &amp; Audit Ledger
        </h2>
        <p class="text-xs text-slate-400 mt-0.5">
          Full empirical trade log. Every trade includes exact entry/exit timestamps, fees paid, duration, and trailing exit mechanics.
        </p>
      </div>

      <!-- Search & Sort Controls -->
      <div class="flex flex-wrap items-center gap-2.5">
        <div class="relative">
          <input type="text" id="journalSearchInput" oninput="filterLedger()" placeholder="Search symbol, side, reason..." class="bg-slate-900 border border-slate-700 text-white rounded-xl pl-8 pr-3 py-1.5 text-xs focus:ring-1 focus:ring-emerald-400 outline-none w-56">
          <i data-lucide="search" class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5"></i>
        </div>

        <button id="sortToggleBtn" onclick="toggleSortOrder()" class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-cyan-400 font-semibold flex items-center gap-1.5 transition">
          <span id="sortToggleLabel">Recent Trades First ⬇</span>
        </button>

        <select id="pageSizeSelect" onchange="changePageSize(this.value)" class="bg-slate-900 border border-slate-700 text-white rounded-xl px-2.5 py-1.5 text-xs outline-none">
          <option value="50">50 per page</option>
          <option value="100" selected>100 per page</option>
          <option value="250">250 per page</option>
          <option value="500">500 per page</option>
        </select>
      </div>
    </div>

    <!-- Active Filter Notice Banner -->
    <div class="flex items-center justify-between mb-3 text-xs bg-slate-900/50 p-2.5 rounded-xl border border-slate-800/80 font-mono">
      <div class="flex items-center gap-2">
        <span class="text-slate-400">Ledger Status:</span>
        <span id="ledgerFilterNotice" class="text-emerald-400 font-semibold">Showing all historical trades (Oct 2023 - Oct 2026)</span>
      </div>
      <div class="text-slate-400">
        Showing <span id="ledgerFilteredCount" class="text-white font-bold">0</span> of <span id="ledgerTotalCount" class="text-white font-bold">0</span> matching trades
      </div>
    </div>

    <!-- Master Table -->
    <div class="overflow-x-auto custom-scroll rounded-xl border border-slate-800 max-h-[600px]">
      <table class="w-full text-xs text-left border-collapse bg-slate-950/60">
        <thead class="sticky top-0 bg-slate-900 text-slate-400 uppercase text-[10px] tracking-wider font-mono border-b border-slate-800 z-10">
          <tr>
            <th class="py-2.5 px-3">#</th>
            <th class="py-2.5 px-3">Trade Date</th>
            <th class="py-2.5 px-3">Entry Time</th>
            <th class="py-2.5 px-3">Exit Time</th>
            <th class="py-2.5 px-3">Duration</th>
            <th class="py-2.5 px-3">Symbol</th>
            <th class="py-2.5 px-3">Side</th>
            <th class="py-2.5 px-3 text-center">Stars</th>
            <th class="py-2.5 px-3 text-right">Lots</th>
            <th class="py-2.5 px-3 text-right">Entry ($)</th>
            <th class="py-2.5 px-3 text-right text-rose-400">Stop Loss ($)</th>
            <th class="py-2.5 px-3 text-right text-emerald-400">Take Profit ($)</th>
            <th class="py-2.5 px-3 text-right">Exit Price ($)</th>
            <th class="py-2.5 px-3 text-right">Gross ($)</th>
            <th class="py-2.5 px-3 text-right text-amber-400">Delta Fee</th>
            <th class="py-2.5 px-3 text-right text-emerald-400 font-bold">Net P&amp;L ($)</th>
            <th class="py-2.5 px-3 text-right text-cyan-400 font-bold">R:R Achieved</th>
            <th class="py-2.5 px-4">Exit Reason</th>
          </tr>
        </thead>
        <tbody id="journalTableBody" class="divide-y divide-slate-800/60 font-mono text-[11px]">
          <!-- Rendered dynamically by JavaScript -->
        </tbody>
      </table>
    </div>

    <!-- Pagination Controls -->
    <div class="flex items-center justify-between mt-4 text-xs">
      <div id="journalPageInfo" class="text-slate-400 font-mono">
        Showing page 1 of 1
      </div>
      <div class="flex items-center gap-2">
        <button id="btnPrevPage" onclick="changePage(-1)" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold transition disabled:opacity-40">Previous</button>
        <button id="btnNextPage" onclick="changePage(1)" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold transition disabled:opacity-40">Next</button>
      </div>
    </div>
  </div>

  <!-- FOOTER -->
  <footer class="text-center text-xs text-slate-500 py-6 border-t border-slate-900 font-mono">
    Agent Brain Backtest V6 Engine &bull; Strictly Local Quantitative Simulation &bull; 3 Years Continuous Data from Delta Exchange API &bull; No Cloud / Git Push
  </footer>

  <!-- EMBEDDED JAVASCRIPT DATA & LOGIC -->
  <script>
    const STRATEGIES_DATA = {strategies_json};
    const PER_PAIR_DATA = {per_pair_json};
    const USD_INR_RATE = {USD_TO_INR};

    let currentStrategyKey = "{active_key}";
    let currentTrades = [];
    let filteredTrades = [];
    let useINR = false;

    let filterStartDate = null;
    let filterEndDate = null;
    let currentYearFilter = "ALL";
    let currentMonthFilter = null;
    let currentWeekFilter = null;
    let currentCalYear = 2026;
    let currentCalMonth = 9; // October (0-indexed: 9)

    let sortNewestFirst = true;
    let currentPage = 1;
    let pageSize = 100;

    let equityChartInstance = null;
    let hourlyChartInstance = null;
    let dowChartInstance = null;

    document.addEventListener("DOMContentLoaded", () => {{
      lucide.createIcons();
      selectStrategy(currentStrategyKey);
    }});

    function setCurrency(isINR) {{
      useINR = isINR;
      document.getElementById("currBtnUSD").className = !useINR ? "px-3 py-1.5 rounded-lg bg-emerald-500 text-black font-bold transition" : "px-3 py-1.5 rounded-lg text-slate-400 hover:text-white font-semibold transition";
      document.getElementById("currBtnINR").className = useINR ? "px-3 py-1.5 rounded-lg bg-emerald-500 text-black font-bold transition" : "px-3 py-1.5 rounded-lg text-slate-400 hover:text-white font-semibold transition";
      updateKPICards();
      renderLedger();
      renderEquityChart();
      renderTimeAndDayCharts();
      renderCalendar();
    }}

    function selectStrategy(stratKey) {{
      if (!STRATEGIES_DATA[stratKey]) return;
      currentStrategyKey = stratKey;

      Object.keys(STRATEGIES_DATA).forEach(k => {{
        const btn = document.getElementById("tab_" + k);
        const badge = document.getElementById("badge_" + k);
        if (btn) {{
          if (k === stratKey) {{
            btn.className = "px-4 py-2.5 rounded-xl text-xs flex items-center gap-2 transition whitespace-nowrap bg-gradient-to-r from-emerald-500 to-teal-400 text-black shadow-lg shadow-emerald-950/40 ring-2 ring-emerald-400 font-bold";
            if (badge) badge.className = "px-2 py-0.5 rounded-full text-[11px] bg-black/20 text-black font-extrabold";
          }} else {{
            btn.className = "px-4 py-2.5 rounded-xl text-xs flex items-center gap-2 transition whitespace-nowrap bg-slate-900 border border-slate-800 text-slate-300 hover:border-slate-700 hover:text-white font-semibold";
            if (badge) badge.className = "px-2 py-0.5 rounded-full text-[11px] bg-slate-800 text-slate-400 font-mono";
          }}
        }}
      }});

      const strat = STRATEGIES_DATA[stratKey];
      currentTrades = strat.trades || [];
      resetDateFilter();
    }}

    function switchBreakdownView(viewName) {{
      ["YoY", "Monthly", "Weekly", "Leaderboard"].forEach(v => {{
        const container = document.getElementById("viewContainer_" + v);
        const tabBtn = document.getElementById("viewTab_" + v);
        if (container) container.classList.add("hidden");
        if (tabBtn) tabBtn.className = "px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition";
      }});

      const activeContainer = document.getElementById("viewContainer_" + viewName);
      const activeTabBtn = document.getElementById("viewTab_" + viewName);
      if (activeContainer) activeContainer.classList.remove("hidden");
      if (activeTabBtn) activeTabBtn.className = "px-4 py-2 rounded-xl text-xs font-bold bg-emerald-500 text-black shadow-sm transition";
    }}

    // ==========================================
    // DATE FILTERING FUNCTIONS
    // ==========================================
    function filterByYear(yearStr) {{
      currentYearFilter = yearStr;
      currentMonthFilter = null;
      currentWeekFilter = null;

      ["ALL", "2023", "2024", "2025", "2026"].forEach(y => {{
        const btn = document.getElementById("yearBtn_" + y);
        if (btn) {{
          btn.className = (y === yearStr)
            ? "px-3 py-1.5 rounded-xl text-xs font-bold bg-cyan-500 text-black shadow-sm transition"
            : "px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:border-slate-700 transition";
        }}
      }});

      if (yearStr === "ALL") {{
        filterStartDate = null;
        filterEndDate = null;
        document.getElementById("activeFilterBadge").innerText = "All 3 Years (Oct 2023 - Oct 2026)";
        document.getElementById("resetDateBtn").classList.add("hidden");
      }} else {{
        filterStartDate = `${{yearStr}}-01-01`;
        filterEndDate = `${{yearStr}}-12-31`;
        document.getElementById("activeFilterBadge").innerText = `Calendar Year ${{yearStr}}`;
        document.getElementById("resetDateBtn").classList.remove("hidden");
        document.getElementById("customStartDate").value = filterStartDate;
        document.getElementById("customEndDate").value = filterEndDate;
      }}

      applyFilters();
    }}

    function filterByMonth(ymStr) {{
      currentMonthFilter = ymStr;
      currentYearFilter = null;
      currentWeekFilter = null;

      ["ALL", "2023", "2024", "2025", "2026"].forEach(y => {{
        const btn = document.getElementById("yearBtn_" + y);
        if (btn) btn.className = "px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition";
      }});

      filterStartDate = `${{ymStr}}-01`;
      filterEndDate = `${{ymStr}}-31`;
      document.getElementById("activeFilterBadge").innerText = `Month: ${{ymStr}}`;
      document.getElementById("resetDateBtn").classList.remove("hidden");
      document.getElementById("customStartDate").value = filterStartDate;
      document.getElementById("customEndDate").value = filterEndDate;

      // Also align calendar heatmap view
      const parts = ymStr.split("-");
      if (parts.length === 2) {{
        currentCalYear = parseInt(parts[0], 10);
        currentCalMonth = parseInt(parts[1], 10) - 1;
        renderCalendar();
      }}

      applyFilters();
    }}

    function filterByWeek(startDate, endDate, weekLabel) {{
      currentWeekFilter = weekLabel;
      currentMonthFilter = null;
      currentYearFilter = null;

      ["ALL", "2023", "2024", "2025", "2026"].forEach(y => {{
        const btn = document.getElementById("yearBtn_" + y);
        if (btn) btn.className = "px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition";
      }});

      filterStartDate = startDate;
      filterEndDate = endDate;
      document.getElementById("activeFilterBadge").innerText = `Week: ${{weekLabel}} (${{startDate}} to ${{endDate}})`;
      document.getElementById("resetDateBtn").classList.remove("hidden");
      document.getElementById("customStartDate").value = filterStartDate;
      document.getElementById("customEndDate").value = filterEndDate;

      applyFilters();
    }}

    function applyCustomDateFilter() {{
      const st = document.getElementById("customStartDate").value;
      const et = document.getElementById("customEndDate").value;
      if (!st || !et) return;

      filterStartDate = st;
      filterEndDate = et;
      currentYearFilter = null;
      currentMonthFilter = null;
      currentWeekFilter = null;

      ["ALL", "2023", "2024", "2025", "2026"].forEach(y => {{
        const btn = document.getElementById("yearBtn_" + y);
        if (btn) btn.className = "px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition";
      }});

      document.getElementById("activeFilterBadge").innerText = `Custom Range: ${{st}} to ${{et}}`;
      document.getElementById("resetDateBtn").classList.remove("hidden");

      applyFilters();
    }}

    function resetDateFilter() {{
      filterStartDate = null;
      filterEndDate = null;
      currentYearFilter = "ALL";
      currentMonthFilter = null;
      currentWeekFilter = null;

      ["ALL", "2023", "2024", "2025", "2026"].forEach(y => {{
        const btn = document.getElementById("yearBtn_" + y);
        if (btn) {{
          btn.className = (y === "ALL")
            ? "px-3 py-1.5 rounded-xl text-xs font-bold bg-cyan-500 text-black shadow-sm transition"
            : "px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition";
        }}
      }});

      document.getElementById("activeFilterBadge").innerText = "All 3 Years (Oct 2023 - Oct 2026)";
      document.getElementById("resetDateBtn").classList.add("hidden");
      document.getElementById("resetCalFilterBtn").classList.add("hidden");
      document.getElementById("customStartDate").value = "2023-10-08";
      document.getElementById("customEndDate").value = "2026-10-07";

      applyFilters();
    }}

    function applyFilters() {{
      const query = (document.getElementById("journalSearchInput")?.value || "").toLowerCase();

      filteredTrades = currentTrades.filter(t => {{
        const tradeDate = (t.closed_at || t.opened_at || "").split(" ")[0].split("T")[0];

        if (filterStartDate && tradeDate < filterStartDate) return false;
        if (filterEndDate && tradeDate > filterEndDate) return false;

        if (query) {{
          const str = `${{t.symbol}} ${{t.side}} ${{t.close_reason || ''}}`.toLowerCase();
          if (!str.includes(query)) return false;
        }}

        return true;
      }});

      if (sortNewestFirst) {{
        filteredTrades.sort((a, b) => (b.closed_at || b.opened_at || "").localeCompare(a.closed_at || a.opened_at || ""));
      }} else {{
        filteredTrades.sort((a, b) => (a.closed_at || a.opened_at || "").localeCompare(b.closed_at || b.opened_at || ""));
      }}

      currentPage = 1;
      updateKPICards();
      renderEquityChart();
      renderTimeAndDayCharts();
      renderCalendar();
      renderLedger();

      const fCnt = filteredTrades.length;
      document.getElementById("filteredTradeCountBadge").innerText = `${{fCnt.toLocaleString()}} Trades`;
      document.getElementById("ledgerFilteredCount").innerText = fCnt.toLocaleString();
      document.getElementById("ledgerTotalCount").innerText = currentTrades.length.toLocaleString();

      if (filterStartDate || filterEndDate) {{
        document.getElementById("ledgerFilterNotice").innerText = `Filtered for ${{filterStartDate || 'Start'}} to ${{filterEndDate || 'End'}}`;
      }} else {{
        document.getElementById("ledgerFilterNotice").innerText = "Showing all historical trades (Oct 2023 - Oct 2026)";
      }}
    }}

    function filterLedger() {{
      applyFilters();
    }}

    function updateKPICards() {{
      const wins = filteredTrades.filter(t => (t.pnl_usd || 0) > 0);
      const losses = filteredTrades.filter(t => (t.pnl_usd || 0) < 0);
      const total = filteredTrades.length;

      const netUSD = filteredTrades.reduce((acc, t) => acc + (t.pnl_usd || 0), 0);
      const netINR = netUSD * USD_INR_RATE;
      const feesUSD = filteredTrades.reduce((acc, t) => acc + (t.total_fees_usd || 0), 0);
      const feesINR = feesUSD * USD_INR_RATE;
      const gpUSD = wins.reduce((acc, t) => acc + (t.gross_pnl_usd || 0), 0);
      const glUSD = Math.abs(losses.reduce((acc, t) => acc + (t.gross_pnl_usd || 0), 0));

      const wr = total > 0 ? (wins.length / total * 100) : 0;
      const pf = glUSD > 0 ? (gpUSD / glUSD) : (gpUSD > 0 ? 99.0 : 0.0);

      // Streaks calculation in filtered trades
      let maxW = 0, maxL = 0, curW = 0, curL = 0, totalWRuns = 0, totalLRuns = 0, numWRuns = 0, numLRuns = 0;
      filteredTrades.forEach(t => {{
        const p = t.pnl_usd || 0;
        if (p > 0) {{
          if (curL > 0) {{ totalLRuns += curL; numLRuns++; }}
          curL = 0;
          curW++;
          if (curW > maxW) maxW = curW;
        }} else if (p < 0) {{
          if (curW > 0) {{ totalWRuns += curW; numWRuns++; }}
          curW = 0;
          curL++;
          if (curL > maxL) maxL = curL;
        }}
      }});
      if (curW > 0) {{ totalWRuns += curW; numWRuns++; }}
      if (curL > 0) {{ totalLRuns += curL; numLRuns++; }}

      const avgW = numWRuns > 0 ? (totalWRuns / numWRuns).toFixed(2) : "0.00";
      const avgL = numLRuns > 0 ? (totalLRuns / numLRuns).toFixed(2) : "0.00";

      // Max DD
      let runningCap = 50.0;
      let peak = 50.0;
      let maxDD = 0.0;
      filteredTrades.forEach(t => {{
        runningCap += (t.pnl_usd || 0);
        if (runningCap > peak) peak = runningCap;
        const dd = peak - runningCap;
        if (dd > maxDD) maxDD = dd;
      }});

      const pfx = netUSD >= 0 ? "+" : "-";
      const pfxINR = netINR >= 0 ? "+" : "-";
      const inrStr = Math.abs(netINR) >= 100000 ? `${{(Math.abs(netINR)/100000).toFixed(2)}}L` : Math.abs(netINR).toLocaleString(undefined, {{maximumFractionDigits: 0}});

      document.getElementById("topNetPnl").innerText = `${{pfx}}$${{Math.abs(netUSD).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}`;
      document.getElementById("topNetPnl").className = netUSD >= 0 ? "text-lg font-extrabold text-emerald-400 mono" : "text-lg font-extrabold text-rose-400 mono";
      document.getElementById("topNetPnlInr").innerText = `${{pfxINR}}₹${{inrStr}} (${{pfx}}${{((netUSD/50.0)*100).toLocaleString(undefined, {{maximumFractionDigits: 1}})}}%)`;

      document.getElementById("topWinRate").innerText = `${{wr.toFixed(1)}}%`;
      document.getElementById("topWinsLosses").innerText = `${{wins.length.toLocaleString()}}W / ${{losses.length.toLocaleString()}}L (${{total.toLocaleString()}} Tr)`;

      document.getElementById("topPf").innerText = `PF: ${{pf.toFixed(2)}}`;
      document.getElementById("topGrossProfit").innerText = `+${{useINR ? '₹' : '$'}}${{(useINR ? gpUSD * USD_INR_RATE : gpUSD).toLocaleString(undefined, {{maximumFractionDigits: 1}})}}`;
      document.getElementById("topGrossLoss").innerText = `-${{useINR ? '₹' : '$'}}${{(useINR ? glUSD * USD_INR_RATE : glUSD).toLocaleString(undefined, {{maximumFractionDigits: 1}})}}`;

      document.getElementById("topTotalFees").innerText = `-${{useINR ? '₹' : '$'}}${{(useINR ? feesINR : feesUSD).toLocaleString(undefined, {{maximumFractionDigits: 2}})}}`;
      document.getElementById("topTotalFeesInr").innerText = `~₹${{feesINR >= 100000 ? (feesINR/100000).toFixed(2) + 'L' : feesINR.toLocaleString(undefined, {{maximumFractionDigits: 0}})}} INR`;

      document.getElementById("topMaxDd").innerText = `Max DD: -$${{maxDD.toFixed(2)}}`;
      document.getElementById("topWinStreak").innerText = `${{maxW}} Wins`;
      document.getElementById("topAvgWinStreak").innerText = `Avg: ${{avgW}} consecutive`;
      document.getElementById("topLossStreak").innerText = `${{maxL}} Losses`;
      document.getElementById("topAvgLossStreak").innerText = `Avg: ${{avgL}} consecutive`;
    }}

    function renderEquityChart() {{
      const ctx = document.getElementById("equityChartCanvas");
      if (!ctx) return;

      const chronological = [...filteredTrades].sort((a, b) => (a.closed_at || a.opened_at || "").localeCompare(b.closed_at || b.opened_at || ""));

      let cap = 50.0;
      let peak = 50.0;
      const labels = ["Start"];
      const dataPoints = [useINR ? cap * USD_INR_RATE : cap];

      const step = Math.max(1, Math.floor(chronological.length / 300));
      chronological.forEach((t, i) => {{
        cap += (t.pnl_usd || 0);
        if (cap > peak) peak = cap;
        if (i % step === 0 || i === chronological.length - 1) {{
          const dStr = (t.closed_at || t.opened_at || "").split(" ")[0];
          labels.push(dStr);
          dataPoints.push(Math.round(useINR ? (cap * USD_INR_RATE) : cap));
        }}
      }});

      document.getElementById("chartPeakVal").innerText = useINR ? `₹${{(peak * USD_INR_RATE).toLocaleString(undefined, {{maximumFractionDigits: 0}})}}` : `$${{peak.toFixed(2)}}`;

      if (equityChartInstance) {{
        equityChartInstance.destroy();
      }}

      equityChartInstance = new Chart(ctx, {{
        type: 'line',
        data: {{
          labels: labels,
          datasets: [{{
            label: useINR ? 'Portfolio Equity (₹ INR)' : 'Portfolio Equity ($ USD)',
            data: dataPoints,
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.08)',
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            tension: 0.1
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              mode: 'index',
              intersect: false,
              backgroundColor: 'rgba(15, 23, 42, 0.95)',
              titleColor: '#94a3b8',
              bodyColor: '#10b981',
              borderColor: 'rgba(255, 255, 255, 0.1)',
              borderWidth: 1,
              callbacks: {{
                label: function(context) {{
                  return (useINR ? '₹' : '$') + Number(context.parsed.y).toLocaleString();
                }}
              }}
            }}
          }},
          scales: {{
            x: {{
              grid: {{ color: 'rgba(255, 255, 255, 0.04)' }},
              ticks: {{ color: '#64748b', maxTicksLimit: 10, font: {{ family: 'JetBrains Mono', size: 10 }} }}
            }},
            y: {{
              grid: {{ color: 'rgba(255, 255, 255, 0.04)' }},
              ticks: {{
                color: '#64748b',
                font: {{ family: 'JetBrains Mono', size: 10 }},
                callback: function(val) {{
                  return (useINR ? '₹' : '$') + Number(val).toLocaleString();
                }}
              }}
            }}
          }}
        }}
      }});
    }}

    // ==========================================
    // TIME & DAY CHARTS ENGINE
    // ==========================================
    function renderTimeAndDayCharts() {{
      const hourlyData = Array.from({{ length: 24 }}, (_, h) => ({{ hour: h, pnl: 0, count: 0, wins: 0 }}));
      const dowNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
      const dowData = dowNames.map(d => ({{ day: d, pnl: 0, count: 0, wins: 0 }}));
      const dowIndexMap = {{ "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6 }};

      filteredTrades.forEach(t => {{
        const op = t.opened_at || '';
        const p = t.pnl_usd || 0;
        if (op.length >= 13) {{
          const hour = parseInt(op.substring(11, 13), 10);
          if (hour >= 0 && hour < 24) {{
            hourlyData[hour].pnl += p;
            hourlyData[hour].count++;
            if (p > 0) hourlyData[hour].wins++;
          }}
        }}
        const dStr = op.split(" ")[0];
        if (dStr.length === 10) {{
          const dObj = new Date(dStr + "T00:00:00Z");
          const dayName = dObj.toLocaleDateString("en-US", {{ weekday: "long", timeZone: "UTC" }});
          if (dayName in dowIndexMap) {{
            const idx = dowIndexMap[dayName];
            dowData[idx].pnl += p;
            dowData[idx].count++;
            if (p > 0) dowData[idx].wins++;
          }}
        }}
      }});

      // Hourly Chart
      let bestH = 0, bestHPnl = -Infinity;
      let worstH = 0, worstHPnl = Infinity;
      hourlyData.forEach((d, h) => {{
        if (d.pnl > bestHPnl && d.count > 0) {{ bestHPnl = d.pnl; bestH = h; }}
        if (d.pnl < worstHPnl && d.count > 0) {{ worstHPnl = d.pnl; worstH = h; }}
      }});

      const bestHVal = useINR ? bestHPnl * USD_INR_RATE : bestHPnl;
      const worstHVal = useINR ? worstHPnl * USD_INR_RATE : worstHPnl;
      const hPrefix = useINR ? "₹" : "$";

      document.getElementById("bestHourBadge").innerText = `Best Hour: ${{bestH.toString().padStart(2, '0')}}:00 IST (${{bestHPnl >= 0 ? '+' : '-'}}${{hPrefix}}${{Math.abs(bestHVal).toFixed(2)}})`;
      document.getElementById("worstHourBadge").innerText = `Worst Hour: ${{worstH.toString().padStart(2, '0')}}:00 IST (${{worstHPnl >= 0 ? '+' : '-'}}${{hPrefix}}${{Math.abs(worstHVal).toFixed(2)}})`;

      const hCtx = document.getElementById("hourlyChart");
      if (hCtx) {{
        if (hourlyChartInstance) hourlyChartInstance.destroy();

        hourlyChartInstance = new Chart(hCtx, {{
          type: 'bar',
          data: {{
            labels: hourlyData.map(d => `${{d.hour.toString().padStart(2, '0')}}:00`),
            datasets: [{{
              data: hourlyData.map(d => useINR ? d.pnl * USD_INR_RATE : d.pnl),
              backgroundColor: hourlyData.map(d => d.pnl >= 0 ? 'rgba(16, 185, 129, 0.85)' : 'rgba(244, 63, 94, 0.85)'),
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
                  label: function(ctx) {{
                    const d = hourlyData[ctx.dataIndex];
                    const wr = d.count > 0 ? (d.wins / d.count * 100).toFixed(1) : '0';
                    return [
                      `Net P&L: ${{d.pnl >= 0 ? '+' : '-'}}${{hPrefix}}${{Math.abs(useINR ? d.pnl * USD_INR_RATE : d.pnl).toFixed(2)}}`,
                      `Trades: ${{d.count}} (${{d.wins}}W / ${{d.count - d.wins}}L)`,
                      `Win Rate: ${{wr}}%`
                    ];
                  }}
                }}
              }}
            }},
            scales: {{
              x: {{ grid: {{ color: 'rgba(255, 255, 255, 0.04)' }}, ticks: {{ color: '#64748b', font: {{ family: 'JetBrains Mono', size: 9 }} }} }},
              y: {{ grid: {{ color: 'rgba(255, 255, 255, 0.04)' }}, ticks: {{ color: '#64748b', font: {{ family: 'JetBrains Mono', size: 9 }} }} }}
            }}
          }}
        }});
      }}

      // Day of Week Chart
      let bestD = "Monday", bestDPnl = -Infinity;
      let worstD = "Sunday", worstDPnl = Infinity;
      dowData.forEach(d => {{
        if (d.pnl > bestDPnl && d.count > 0) {{ bestDPnl = d.pnl; bestD = d.day; }}
        if (d.pnl < worstDPnl && d.count > 0) {{ worstDPnl = d.pnl; worstD = d.day; }}
      }});

      const bestDVal = useINR ? bestDPnl * USD_INR_RATE : bestDPnl;
      const worstDVal = useINR ? worstDPnl * USD_INR_RATE : worstDPnl;

      document.getElementById("bestDayBadge").innerText = `Best Day: ${{bestD}} (${{bestDPnl >= 0 ? '+' : '-'}}${{hPrefix}}${{Math.abs(bestDVal).toFixed(2)}})`;

      const dCtx = document.getElementById("dowChart");
      if (dCtx) {{
        if (dowChartInstance) dowChartInstance.destroy();

        dowChartInstance = new Chart(dCtx, {{
          type: 'bar',
          data: {{
            labels: dowData.map(d => d.day.substring(0, 3)),
            datasets: [{{
              data: dowData.map(d => useINR ? d.pnl * USD_INR_RATE : d.pnl),
              backgroundColor: dowData.map(d => d.pnl >= 0 ? 'rgba(6, 182, 212, 0.85)' : 'rgba(244, 63, 94, 0.85)'),
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
                  label: function(ctx) {{
                    const d = dowData[ctx.dataIndex];
                    const wr = d.count > 0 ? (d.wins / d.count * 100).toFixed(1) : '0';
                    return [
                      `Net P&L: ${{d.pnl >= 0 ? '+' : '-'}}${{hPrefix}}${{Math.abs(useINR ? d.pnl * USD_INR_RATE : d.pnl).toFixed(2)}}`,
                      `Trades: ${{d.count}} (${{d.wins}}W / ${{d.count - d.wins}}L)`,
                      `Win Rate: ${{wr}}%`
                    ];
                  }}
                }}
              }}
            }},
            scales: {{
              x: {{ grid: {{ color: 'rgba(255, 255, 255, 0.04)' }}, ticks: {{ color: '#64748b', font: {{ family: 'JetBrains Mono', size: 10 }} }} }},
              y: {{ grid: {{ color: 'rgba(255, 255, 255, 0.04)' }}, ticks: {{ color: '#64748b', font: {{ family: 'JetBrains Mono', size: 10 }} }} }}
            }}
          }}
        }});
      }}

      // Day of Week Summary Cards
      const dowContainer = document.getElementById("dowSummaryCards");
      if (dowContainer) {{
        dowContainer.innerHTML = "";
        dowData.forEach(d => {{
          const pVal = useINR ? d.pnl * USD_INR_RATE : d.pnl;
          const pfx = d.pnl >= 0 ? "+" : "-";
          const wr = d.count > 0 ? (d.wins / d.count * 100).toFixed(0) : "0";
          const cls = d.pnl > 0 ? "text-cyan-400" : (d.pnl < 0 ? "text-rose-400" : "text-slate-400");
          dowContainer.innerHTML += `
            <div class="bg-slate-900/80 border border-slate-800 rounded-lg p-2">
              <div class="text-[10px] text-slate-400 font-bold">${{d.day.substring(0, 3)}}</div>
              <div class="text-[11px] font-extrabold ${{cls}} mt-0.5">${{pfx}}${{hPrefix}}${{Math.abs(pVal).toFixed(0)}}</div>
              <div class="text-[9px] text-slate-400 mt-0.5">${{d.count}}T &bull; ${{wr}}%</div>
            </div>
          `;
        }});
      }}
    }}

    // ==========================================
    // INTERACTIVE CALENDAR ENGINE
    // ==========================================
    function changeCalMonth(delta) {{
      currentCalMonth += delta;
      if (currentCalMonth < 0) {{
        currentCalMonth = 11;
        currentCalYear--;
      }} else if (currentCalMonth > 11) {{
        currentCalMonth = 0;
        currentCalYear++;
      }}
      renderCalendar();
    }}

    function renderCalendar() {{
      const grid = document.getElementById("calendarDaysGrid");
      const title = document.getElementById("calMonthTitle");
      if (!grid || !title) return;

      grid.innerHTML = "";

      const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
      title.innerText = `${{monthNames[currentCalMonth]}} ${{currentCalYear}}`;

      const strat = STRATEGIES_DATA[currentStrategyKey] || {{}};
      const dailyMap = strat.daily_calendar || {{}};

      const firstDayIndex = new Date(currentCalYear, currentCalMonth, 1).getDay();
      const daysInMonth = new Date(currentCalYear, currentCalMonth + 1, 0).getDate();

      // Empty slots before 1st of month
      for (let i = 0; i < firstDayIndex; i++) {{
        grid.innerHTML += `<div class="p-2 min-h-[76px] rounded-lg bg-slate-950/20 border border-slate-900/40 opacity-30"></div>`;
      }}

      const prefix = useINR ? "₹" : "$";

      for (let day = 1; day <= daysInMonth; day++) {{
        const mStr = (currentCalMonth + 1).toString().padStart(2, '0');
        const dNumStr = day.toString().padStart(2, '0');
        const dStr = `${{currentCalYear}}-${{mStr}}-${{dNumStr}}`;
        const data = dailyMap[dStr];

        let contentHtml = `<span class="text-[10px] text-slate-600 font-mono">-</span>`;
        let bgClass = "bg-slate-900/40 border-slate-800/60";
        const isSelected = (filterStartDate === dStr && filterEndDate === dStr);

        if (data) {{
          const net = useINR ? (data.net_pnl * USD_INR_RATE) : data.net_pnl;
          const gp = useINR ? (data.gross_profit * USD_INR_RATE) : data.gross_profit;
          const gl = useINR ? (data.gross_loss * USD_INR_RATE) : data.gross_loss;
          const fee = useINR ? (data.total_fees * USD_INR_RATE) : data.total_fees;

          const pfx = data.net_pnl >= 0 ? "+" : "-";
          const colorClass = data.net_pnl > 0 ? "text-emerald-400" : (data.net_pnl < 0 ? "text-rose-400" : "text-slate-400");
          bgClass = data.net_pnl > 0 ? "bg-emerald-950/20 border-emerald-500/40 hover:border-emerald-400" : (data.net_pnl < 0 ? "bg-rose-950/20 border-rose-500/40 hover:border-rose-400" : "bg-slate-900 border-slate-800");

          contentHtml = `
            <div class="mt-0.5 flex flex-col gap-0.5">
              <div class="text-[11px] font-extrabold ${{colorClass}} mono leading-tight">
                ${{pfx}}${{prefix}}${{Math.abs(net).toFixed(useINR ? 0 : 2)}}
              </div>
              <div class="flex items-center justify-between text-[8px] font-mono text-slate-300">
                <span class="text-emerald-400 font-semibold">+${{prefix}}${{Math.abs(gp).toFixed(useINR ? 0 : 1)}}</span>
                <span class="text-rose-400 font-semibold">-${{prefix}}${{Math.abs(gl).toFixed(useINR ? 0 : 1)}}</span>
              </div>
              <div class="flex items-center justify-between text-[8px] font-mono pt-0.5 border-t border-slate-800/60">
                <span class="text-slate-400">${{data.trades_count}}T (${{data.wins}}W/${{data.losses}}L)</span>
                <span class="text-amber-400 font-semibold">-${{prefix}}${{Math.abs(fee).toFixed(useINR ? 0 : 2)}}</span>
              </div>
            </div>
          `;
        }}

        const selectedStyle = isSelected ? "ring-2 ring-emerald-400 border-emerald-400" : "";

        grid.innerHTML += `
          <div onclick="selectCalDate('${{dStr}}')" class="day-cell p-2 min-h-[76px] rounded-lg border ${{bgClass}} ${{selectedStyle}} cursor-pointer flex flex-col justify-between">
            <div class="flex items-center justify-between">
              <span class="text-[10px] font-bold text-slate-400">${{day}}</span>
              ${{data ? `<span class="text-[8px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">${{data.trades_count}} Tr</span>` : ''}}
            </div>
            ${{contentHtml}}
          </div>
        `;
      }}
    }}

    function selectCalDate(dateStr) {{
      if (filterStartDate === dateStr && filterEndDate === dateStr) {{
        resetDateFilter();
        return;
      }}
      filterStartDate = dateStr;
      filterEndDate = dateStr;
      document.getElementById("resetCalFilterBtn").classList.remove("hidden");
      document.getElementById("resetDateBtn").classList.remove("hidden");
      document.getElementById("activeFilterBadge").innerText = `Day: ${{dateStr}}`;
      document.getElementById("customStartDate").value = dateStr;
      document.getElementById("customEndDate").value = dateStr;
      applyFilters();
    }}

    // ==========================================
    // LEDGER & PAGINATION FUNCTIONS
    // ==========================================
    function toggleSortOrder() {{
      sortNewestFirst = !sortNewestFirst;
      document.getElementById("sortToggleLabel").innerText = sortNewestFirst ? "Recent Trades First ⬇" : "Oldest Trades First ⬆";
      applyFilters();
    }}

    function changePageSize(val) {{
      pageSize = parseInt(val, 10);
      currentPage = 1;
      renderLedger();
    }}

    function changePage(delta) {{
      currentPage += delta;
      renderLedger();
    }}

    function renderLedger() {{
      const tbody = document.getElementById("journalTableBody");
      if (!tbody) return;
      tbody.innerHTML = "";

      const start = (currentPage - 1) * pageSize;
      const end = start + pageSize;
      const pageTrades = filteredTrades.slice(start, end);

      const prefix = useINR ? "₹" : "$";

      pageTrades.forEach((t, i) => {{
        const netVal = useINR ? (t.pnl_usd * USD_INR_RATE) : t.pnl_usd;
        const grossVal = useINR ? ((t.gross_pnl_usd || t.pnl_usd) * USD_INR_RATE) : (t.gross_pnl_usd || t.pnl_usd);
        const feeVal = useINR ? ((t.total_fees_usd || 0.05) * USD_INR_RATE) : (t.total_fees_usd || 0.05);

        const openStr = t.opened_at || "";
        const closeStr = t.closed_at || "";
        const tradeDate = (closeStr || openStr).split(" ")[0] || "Unknown";
        const entryTime = openStr.includes(" ") ? openStr.split(" ")[1] : (openStr || "-");
        const exitTime = closeStr.includes(" ") ? closeStr.split(" ")[1] : (closeStr || "-");
        const durStr = t.duration_str || `${{t.duration_minutes || 0}}m`;

        const isWin = (t.pnl_usd || 0) > 0;
        const pnlClass = isWin ? "text-emerald-400" : "text-rose-400";
        const sideClass = t.side === "BUY" ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" : "text-rose-400 bg-rose-500/10 border-rose-500/30";
        const tradeIndex = t.trade_num ? `#${{t.trade_num}}` : `#${{start + i + 1}}`;
        const starVal = Number(t.conviction_stars || 5.0);
        const starBadge = starVal >= 5.0
          ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">5.0★</span>`
          : `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">${{starVal.toFixed(1)}}★</span>`;

        tbody.innerHTML += `
          <tr class="hover:bg-slate-900/50 transition">
            <td class="py-2.5 px-3 text-slate-500 font-mono">${{tradeIndex}}</td>
            <td class="py-2.5 px-3 text-slate-300 font-mono whitespace-nowrap">${{tradeDate}}</td>
            <td class="py-2.5 px-3 text-emerald-400 font-mono font-semibold whitespace-nowrap">${{entryTime}}</td>
            <td class="py-2.5 px-3 text-amber-400 font-mono font-semibold whitespace-nowrap">${{exitTime}}</td>
            <td class="py-2.5 px-3 text-slate-400 font-mono whitespace-nowrap">${{durStr}}</td>
            <td class="py-2.5 px-3 font-bold text-white whitespace-nowrap">${{t.symbol}}</td>
            <td class="py-2.5 px-3 whitespace-nowrap"><span class="px-2 py-0.5 rounded border text-[10px] font-bold ${{sideClass}}">${{t.side}}</span></td>
            <td class="py-2.5 px-3 text-center whitespace-nowrap">${{starBadge}}</td>
            <td class="py-2.5 px-3 text-right text-slate-300 font-mono">${{t.lots || 1}}</td>
            <td class="py-2.5 px-3 text-right text-slate-300 font-mono">$${{Number(t.entry_price || 0).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
            <td class="py-2.5 px-3 text-right text-rose-400 font-mono font-medium">$${{Number(t.stop_loss || 0).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
            <td class="py-2.5 px-3 text-right text-emerald-400 font-mono font-medium">$${{Number(t.take_profit || 0).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
            <td class="py-2.5 px-3 text-right text-slate-300 font-mono">$${{Number(t.exit_price || 0).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</td>
            <td class="py-2.5 px-3 text-right font-mono ${{pnlClass}}">${{grossVal >= 0 ? '+' : '-'}}${{prefix}}${{Math.abs(grossVal).toFixed(useINR ? 0 : 2)}}</td>
            <td class="py-2.5 px-3 text-right font-mono text-amber-400">-${{prefix}}${{Math.abs(feeVal).toFixed(useINR ? 0 : 2)}}</td>
            <td class="py-2.5 px-3 text-right font-mono font-extrabold ${{pnlClass}}">${{netVal >= 0 ? '+' : '-'}}${{prefix}}${{Math.abs(netVal).toFixed(useINR ? 0 : 2)}}</td>
            <td class="py-2.5 px-3 text-right font-mono text-cyan-400 font-bold">${{t.rr_achieved || 0}}R</td>
            <td class="py-2.5 px-4 text-slate-400 font-mono text-[11px] whitespace-nowrap"><span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">${{t.close_reason || 'CLOSED'}}</span></td>
          </tr>
        `;
      }});

      const totalPages = Math.ceil(filteredTrades.length / pageSize) || 1;
      document.getElementById("journalPageInfo").innerText = `Showing page ${{currentPage}} of ${{totalPages}} (${{filteredTrades.length.toLocaleString()}} total)`;
      document.getElementById("btnPrevPage").disabled = (currentPage === 1);
      document.getElementById("btnNextPage").disabled = (currentPage >= totalPages);
    }}

    function exportTradesCSV() {{
      const headers = ["Trade#", "Symbol", "Side", "OpenedAt", "ClosedAt", "Duration", "EntryPrice", "StopLoss", "TakeProfit", "ExitPrice", "Lots", "RiskUSD", "GrossPnL_USD", "DeltaFees_USD", "NetPnL_USD", "R_Achieved", "CloseReason"];
      const rows = filteredTrades.map(t => [
        t.trade_num || "",
        t.symbol,
        t.side,
        t.opened_at,
        t.closed_at,
        t.duration_str || "",
        t.entry_price,
        t.stop_loss,
        t.take_profit,
        t.exit_price,
        t.lots,
        t.risk_usd,
        t.gross_pnl_usd,
        t.total_fees_usd,
        t.pnl_usd,
        t.rr_achieved,
        `"${{(t.close_reason || '').replace(/"/g, '""')}}"`
      ]);

      let csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\\n");
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", `backtest_v6_24_7_trades_${{currentStrategyKey}}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }}
  </script>
</body>
</html>
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return file_path
