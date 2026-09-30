import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

reporter_file = BASE_DIR / "reports" / "html_reporter.py"
content = reporter_file.read_text(encoding="utf-8")

# 1. Update signature of generate_multi_strategy_backtest_report
old_sig = '''    def generate_multi_strategy_backtest_report(
        self,
        strategy_results: Dict[str, Any],
        symbol: str = "Multi-Asset (Gold, Silver, BTC, ETH)",
        silver_results: Optional[Dict[str, Any]] = None,
        joint_results: Optional[Dict[str, Any]] = None,
        btc_results: Optional[Dict[str, Any]] = None,
        eth_results: Optional[Dict[str, Any]] = None
    ) -> Path:
        """Renders comprehensive multi-strategy comparison HTML with 1-click execution button and Dual Asset Support (Gold & Silver)."""
        file_path = self.output_dir / "backtest_report.html"'''

new_sig = '''    def generate_multi_strategy_backtest_report(
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
        file_path = self.output_dir / filename'''

assert old_sig in content, "old_sig not found"
content = content.replace(old_sig, new_sig)

# 2. Update title to reflect dedicated asset
old_title = '''  <title>Agent Brain | 6-Month Multi-Strategy Quantitative Backtest</title>'''
new_title = '''  <title>Agent Brain | {('Master Multi-Asset' if default_asset == 'JOINT' else ('🥇 Gold' if default_asset == 'XAUTUSD' else ('🥈 Silver' if default_asset == 'SLVONUSD' else ('₿ Bitcoin' if default_asset == 'BTCUSD' else 'Ξ Ethereum'))))} Quantitative Backtest Report</title>'''
assert old_title in content, "old_title not found"
content = content.replace(old_title, new_title)

# 3. Add Dedicated Reports & Journals top nav below header
old_hdr_end = '''    </div>
  </header>'''
new_hdr_nav = '''    </div>
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
    </div>
  </div>'''

assert old_hdr_end in content, "old_hdr_end not found"
content = content.replace(old_hdr_end, new_hdr_nav, 1)

# 4. Update allDatasets in script
old_datasets = '''    let allDatasets = {{
      "JOINT": {joint_results_json},
      "XAUTUSD": {gold_results_json},
      "SLVONUSD": {silver_results_json}
    }};
    let currentAsset = (allDatasets["JOINT"] && Object.keys(allDatasets["JOINT"]).length > 0) ? "JOINT" : ((Object.keys(allDatasets["XAUTUSD"]).length > 0) ? "XAUTUSD" : "SLVONUSD");'''

new_datasets = '''    let allDatasets = {{
      "JOINT": {joint_results_json},
      "XAUTUSD": {gold_results_json},
      "SLVONUSD": {silver_results_json},
      "BTCUSD": {btc_results_json},
      "ETHUSD": {eth_results_json}
    }};
    let currentAsset = "{default_asset}";
    if (!allDatasets[currentAsset] || Object.keys(allDatasets[currentAsset]).length === 0) {{
      currentAsset = "JOINT";
    }}'''

assert old_datasets in content, "old_datasets not found"
content = content.replace(old_datasets, new_datasets)

# 5. Add crypto descriptions
old_desc = '''    const stratDescriptions = {{
      "joint_profit_max":'''

new_desc = '''    const stratDescriptions = {{
      "joint_quad_profit_max": "👑 4-Asset Apex Portfolio: Simultaneous Gold Apex Pro + Silver Profit Max + BTC Profit Max + ETH Profit Max | Strict $5 Risk | Maximum Combined ROI",
      "joint_crypto_max": "⚡ Crypto Joint Maximizer: Concurrent BTC + ETH Futures | Strict $5 Risk | High Win Rate VWAP Reversion",
      "joint_quad_titan": "💎 4-Asset Apex Titan: Gold + Silver + BTC + ETH Trend Runner Ensemble",
      "btc_profit_max": "👑 BTC Apex Profit Maximizer: 1.5 Sigma Fade + 2.0R Partial TP + Breakeven Lock | 66.1% Win Rate | 2.25 Profit Factor | +4,332.5% ROI",
      "btc_titan": "💎 BTC Apex Titan: 1.8 Sigma Session VWAP Reversion + BE Lock | 67.4% Win Rate | 2.34 Profit Factor | +3,268.3% ROI",
      "btc_high_wr": "🎯 BTC High Win-Rate Guardian: 2.0 Sigma Fade + 1.2R Fast Lock | 71.6% Win Rate | 1.79 Profit Factor | +1,275.3% ROI",
      "eth_profit_max": "👑 ETH Apex Profit Maximizer: 1.5 Sigma Fade + 2.0R Partial TP + Breakeven Lock | 66.7% Win Rate | 2.36 Profit Factor | +4,238.6% ROI",
      "eth_titan": "💎 ETH Apex Titan: 1.7 Sigma Session VWAP Reversion + BE Lock | 67.9% Win Rate | 2.49 Profit Factor | +3,612.7% ROI",
      "eth_high_wr": "🎯 ETH High Win-Rate Guardian: 1.7 Sigma Fade + 1.2R Fast Lock | 69.7% Win Rate | 1.72 Profit Factor | +1,659.9% ROI",
      "joint_profit_max":'''

assert old_desc in content, "old_desc not found"
content = content.replace(old_desc, new_desc)

# 6. Update initial load at bottom of script
old_init = '''    renderComparisonTable();
    const defaultKey = data["joint_profit_max"] ? "joint_profit_max" : (data["joint_titan"] ? "joint_titan" : (data["apex_pro_5"] ? "apex_pro_5" : Object.keys(data).reduce((a, b) => data[a].net_pl > data[b].net_pl ? a : b)));
    selectStrategy(defaultKey);'''

new_init = '''    switchAsset(currentAsset);'''

assert old_init in content, "old_init not found"
content = content.replace(old_init, new_init)

# 7. Update journal table row badge to support all 4 assets
old_badge = '''        const isSilver = (t.symbol && t.symbol.includes('SLV'));
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
          <td>
            <span class="px-2 py-0.5 rounded font-mono text-[10px] ${{isSilver ? 'bg-slate-700/80 text-slate-200 border border-slate-600' : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'}}">
              ${{isSilver ? '🥈 Silver' : '🥇 Gold'}}
            </span>
          </td>'''

new_badge = '''        const sym = (t.symbol || '').toUpperCase();
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
          <td>${{assetBadge}}</td>'''

assert old_badge in content, "old_badge not found"
content = content.replace(old_badge, new_badge)

# 8. Update journal header title & gradient for BTC and ETH
old_jhdr = '''  <title>Agent Brain | {('Joint (Gold + Silver)' if active_nav == 'JOINT' else ('🥇 Gold' if active_nav == 'GOLD' else '🥈 Silver'))} Trading Journal</title>
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
      <div class="h-11 w-11 rounded-xl {'bg-gradient-to-tr from-blue-600 to-indigo-400' if active_nav == 'JOINT' else ('bg-gradient-to-tr from-amber-500 to-yellow-300' if active_nav == 'GOLD' else 'bg-gradient-to-tr from-cyan-500 to-teal-300')} flex items-center justify-center font-bold text-white text-2xl shadow-lg shadow-indigo-950">
        {'🌐' if active_nav == 'JOINT' else ('🥇' if active_nav == 'GOLD' else '🥈')}
      </div>
      <div>
        <h1 class="text-xl font-bold flex items-center gap-2">
          <span>Agent Brain | {('🌐 Joint Portfolio Journal' if active_nav == 'JOINT' else ('🥇 Gold (XAUTUSD) Journal' if active_nav == 'GOLD' else '🥈 Silver (SLVONUSD) Journal'))}</span>
          <span class="text-xs px-2.5 py-0.5 rounded-full {'bg-blue-500/10 text-blue-400 border border-blue-500/20' if active_nav == 'JOINT' else ('bg-amber-500/10 text-amber-400 border border-amber-500/20' if active_nav == 'GOLD' else 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20')}">TradeEdge Mirror</span>
        </h1>'''

new_jhdr = '''  <title>Agent Brain | {('🌐 Joint Portfolio' if active_nav == 'JOINT' else ('🥇 Gold' if active_nav == 'GOLD' else ('🥈 Silver' if active_nav == 'SILVER' else ('₿ Bitcoin' if active_nav == 'BTC' else 'Ξ Ethereum'))))} Trading Journal</title>
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
          <span>Agent Brain | {('🌐 Joint Portfolio Journal' if active_nav == 'JOINT' else ('🥇 Gold (XAUTUSD) Journal' if active_nav == 'GOLD' else ('🥈 Silver (SLVONUSD) Journal' if active_nav == 'SILVER' else ('₿ Bitcoin (BTCUSD) Journal' if active_nav == 'BTC' else 'Ξ Ethereum (ETHUSD) Journal'))))}</span>
          <span class="text-xs px-2.5 py-0.5 rounded-full {'bg-blue-500/10 text-blue-400 border border-blue-500/20' if active_nav == 'JOINT' else ('bg-amber-500/10 text-amber-400 border border-amber-500/20' if active_nav == 'GOLD' else ('bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' if active_nav == 'SILVER' else ('bg-orange-500/10 text-orange-400 border border-orange-500/20' if active_nav == 'BTC' else 'bg-purple-500/10 text-purple-400 border border-purple-500/20')))}">TradeEdge Mirror</span>
        </h1>'''

assert old_jhdr in content, "old_jhdr not found"
content = content.replace(old_jhdr, new_jhdr)

# 9. Add generate_all_reports method
all_reports_method = '''
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
'''

content += all_reports_method

reporter_file.write_text(content, encoding="utf-8")
print("[SUCCESS] html_reporter.py patched successfully with 5-Asset Reports & Journal Support!")
