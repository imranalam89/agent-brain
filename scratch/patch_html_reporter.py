import re

with open("reports/html_reporter.py", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Update function signature & dataset packing
old_fn_start = '''    def generate_multi_strategy_backtest_report(
        self,
        strategy_results: Dict[str, Any],
        symbol: str = "XAUTUSD (6-Month Delta Ticks)"
    ) -> Path:
        """Renders comprehensive multi-strategy comparison HTML with 1-click execution button."""
        file_path = self.output_dir / "backtest_report.html"
        results_json = json.dumps(strategy_results)'''

new_fn_start = '''    def generate_multi_strategy_backtest_report(
        self,
        strategy_results: Dict[str, Any],
        symbol: str = "Multi-Asset (Gold & Silver)",
        silver_results: Optional[Dict[str, Any]] = None
    ) -> Path:
        """Renders comprehensive multi-strategy comparison HTML with 1-click execution button and Dual Asset Support (Gold & Silver)."""
        file_path = self.output_dir / "backtest_report.html"

        if silver_results is not None:
            gold_results_json = json.dumps(strategy_results)
            silver_results_json = json.dumps(silver_results)
        elif "XAUTUSD" in strategy_results or "SLVONUSD" in strategy_results:
            gold_results_json = json.dumps(strategy_results.get("XAUTUSD", {}))
            silver_results_json = json.dumps(strategy_results.get("SLVONUSD", {}))
        elif "SLV" in symbol.upper():
            gold_results_json = json.dumps({})
            silver_results_json = json.dumps(strategy_results)
        else:
            gold_results_json = json.dumps(strategy_results)
            silver_results_json = json.dumps({})'''

assert old_fn_start in text, "old_fn_start not found"
text = text.replace(old_fn_start, new_fn_start)

# 2. Update Header with Asset Selector
old_header = '''  <!-- TOP HEADER WITH 1-CLICK ACTION BUTTONS -->
  <header class="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 border-b border-slate-800 pb-5">
    <div class="flex items-center gap-3">
      <div class="h-11 w-11 rounded-xl bg-gradient-to-tr from-amber-500 to-emerald-400 flex items-center justify-center font-bold text-black text-2xl shadow-lg shadow-emerald-950">
        🧠
      </div>
      <div>
        <h1 class="text-xl font-bold flex items-center gap-2">
          <span>6-Month Multi-Strategy Quantitative Backtest</span>
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{symbol}</span>
        </h1>
        <p class="text-xs text-slate-400">23.5 Million Delta Trade Ticks • April – September 2026 • 100x Isolated Leverage • $4 Target Risk</p>
      </div>
    </div>
    
    <!-- INTERACTIVE 1-CLICK ACTION CONTROLS -->'''

new_header = '''  <!-- TOP HEADER WITH ASSET SELECTOR & 1-CLICK ACTION CONTROLS -->
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
        <p id="headerSubtitle" class="text-xs text-slate-400">23.5 Million Delta Trade Ticks • April – September 2026 • 100x Isolated Leverage • $4-$5 Capped Risk</p>
      </div>
    </div>

    <!-- ASSET TOGGLE TABS (GOLD vs SILVER) -->
    <div class="flex items-center bg-slate-900/90 p-1 rounded-2xl border border-slate-800 shadow-inner font-mono text-xs">
      <button id="assetTabGold" onclick="switchAsset('XAUTUSD')" class="px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer bg-gradient-to-r from-amber-500 to-yellow-400 text-black shadow-md shadow-amber-950/40">
        <span>🥇 Gold (XAUTUSD)</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-black/20 text-black">23.5M Ticks</span>
      </button>
      <button id="assetTabSilver" onclick="switchAsset('SLVONUSD')" class="px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800">
        <span>🥈 Silver (SLVONUSD)</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">801k Ticks</span>
      </button>
    </div>
    
    <!-- INTERACTIVE 1-CLICK ACTION CONTROLS -->'''

assert old_header in text, "old_header not found"
text = text.replace(old_header, new_header)

# 3. Add Mar & Feb to calendar tabs in HTML
old_cal_tabs = '''          <button onclick="changeCalMonth('2026-04')" id="cTab_2026-04" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Apr 2026</button>
        </div>'''
new_cal_tabs = '''          <button onclick="changeCalMonth('2026-04')" id="cTab_2026-04" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Apr 2026</button>
          <button onclick="changeCalMonth('2026-03')" id="cTab_2026-03" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Mar 2026</button>
          <button onclick="changeCalMonth('2026-02')" id="cTab_2026-02" class="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Feb 2026</button>
        </div>'''
assert old_cal_tabs in text, "old_cal_tabs not found"
text = text.replace(old_cal_tabs, new_cal_tabs)

# 4. Add Mar & Feb to trade ledger month tabs
old_ledger_tabs = '''          <button onclick="setBacktestMonthFilter('2026-04')" id="bTab_2026-04" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Apr 2026</button>
        </div>'''
new_ledger_tabs = '''          <button onclick="setBacktestMonthFilter('2026-04')" id="bTab_2026-04" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Apr 2026</button>
          <button onclick="setBacktestMonthFilter('2026-03')" id="bTab_2026-03" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Mar 2026</button>
          <button onclick="setBacktestMonthFilter('2026-02')" id="bTab_2026-02" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]">Feb 2026</button>
        </div>'''
assert old_ledger_tabs in text, "old_ledger_tabs not found"
text = text.replace(old_ledger_tabs, new_ledger_tabs)

# 5. Update JavaScript data declaration and add switchAsset
old_js_init = '''    let data = {results_json};
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
    let isRunning = false;'''

new_js_init = '''    let allDatasets = {{
      "XAUTUSD": {gold_results_json},
      "SLVONUSD": {silver_results_json}
    }};
    let currentAsset = (Object.keys(allDatasets["XAUTUSD"]).length > 0) ? "XAUTUSD" : "SLVONUSD";
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

      const tabGold = document.getElementById('assetTabGold');
      const tabSilver = document.getElementById('assetTabSilver');
      const badge = document.getElementById('headerAssetBadge');
      const subtitle = document.getElementById('headerSubtitle');

      if (asset === 'XAUTUSD') {{
        if (tabGold) tabGold.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer bg-gradient-to-r from-amber-500 to-yellow-400 text-black shadow-md shadow-amber-950/40";
        if (tabSilver) tabSilver.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        if (badge) {{
          badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20";
          badge.innerText = "Gold (XAUTUSD)";
        }}
        if (subtitle) subtitle.innerText = "23.5 Million Delta Trade Ticks • April – September 2026 • 100x Isolated Leverage • $4-$5 Capped Risk";
      }} else {{
        if (tabSilver) tabSilver.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer bg-gradient-to-r from-cyan-400 to-blue-500 text-black shadow-md shadow-cyan-950/40";
        if (tabGold) tabGold.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        if (badge) {{
          badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20";
          badge.innerText = "Silver (SLVONUSD)";
        }}
        if (subtitle) subtitle.innerText = "801,831 Delta Trade Ticks • February – September 2026 • 100x Isolated Leverage • $4-$5 Capped Risk";
      }}

      renderComparisonTable();
      const defaultKey = data["apex_pro_5"] ? "apex_pro_5" : Object.keys(data).reduce((a, b) => data[a].net_pl > data[b].net_pl ? a : b);
      selectStrategy(defaultKey);
    }}'''

assert old_js_init in text, "old_js_init not found"
text = text.replace(old_js_init, new_js_init)

# 6. Update triggerRunBacktest to pass symbol
old_trigger = '''      try {{
        const response = await fetch(`${{API_BASE}}/api/run-backtest`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }}
        }});

        if (!response.ok) throw new Error("Server returned " + response.status);

        const result = await response.json();
        if (result.success && result.results) {{
          data = result.results;
          renderComparisonTable();
          selectStrategy('scale_out_3_0');
          showToast("success", "Backtest Completed!", `Top Strategy: ${{result.best_strategy || 'Scale-Out Master'}} refreshed.`);
        }} else {{
          throw new Error(result.error || "Simulation failed");
        }}'''

new_trigger = '''      try {{
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
        }}'''

assert old_trigger in text, "old_trigger not found"
text = text.replace(old_trigger, new_trigger)

# 7. Update calendar & ledger month lists in JS
text = text.replace(
    "const months = ['2026-09', '2026-08', '2026-07', '2026-06', '2026-05', '2026-04'];",
    "const months = ['2026-09', '2026-08', '2026-07', '2026-06', '2026-05', '2026-04', '2026-03', '2026-02'];"
)
text = text.replace(
    "const months = ['ALL', '2026-09', '2026-08', '2026-07', '2026-06', '2026-05', '2026-04'];",
    "const months = ['ALL', '2026-09', '2026-08', '2026-07', '2026-06', '2026-05', '2026-04', '2026-03', '2026-02'];"
)

with open("reports/html_reporter.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Updated reports/html_reporter.py successfully!")
