import re
from pathlib import Path

target_file = Path("reports/html_reporter.py")
content = target_file.read_text(encoding="utf-8")

# 1. Update generate_multi_strategy_backtest_report signature
old_sig = '''    def generate_multi_strategy_backtest_report(
        self,
        strategy_results: Dict[str, Any],
        symbol: str = "Multi-Asset (Gold & Silver)",
        silver_results: Optional[Dict[str, Any]] = None,
        joint_results: Optional[Dict[str, Any]] = None
    ) -> Path:'''

new_sig = '''    def generate_multi_strategy_backtest_report(
        self,
        strategy_results: Dict[str, Any],
        symbol: str = "Multi-Asset (Gold, Silver, BTC, ETH)",
        silver_results: Optional[Dict[str, Any]] = None,
        joint_results: Optional[Dict[str, Any]] = None,
        btc_results: Optional[Dict[str, Any]] = None,
        eth_results: Optional[Dict[str, Any]] = None
    ) -> Path:'''

content = content.replace(old_sig, new_sig)

# 2. Update JSON serialization at start of report
old_json = '''        gold_results_json = json.dumps(strategy_results)
        silver_results_json = json.dumps(silver_results or {})
        joint_results_json = json.dumps(joint_results or {})'''

new_json = '''        gold_results_json = json.dumps(strategy_results)
        silver_results_json = json.dumps(silver_results or {})
        joint_results_json = json.dumps(joint_results or {})
        btc_results_json = json.dumps(btc_results or {})
        eth_results_json = json.dumps(eth_results or {})'''

content = content.replace(old_json, new_json)

# 3. Update header subtitle
old_sub = '''<p id="headerSubtitle" class="text-xs text-slate-400">Delta Exchange India Futures Only • XAUTUSD (100x) & SLVONUSD (50x) • Brokerage Fee: 0.01% • Strict $5 Capped Risk</p>'''
new_sub = '''<p id="headerSubtitle" class="text-xs text-slate-400">Delta Exchange India Futures Only • Gold (100x), Silver (50x), BTC (100x), ETH (100x) • Fee: 0.01% • Strict $5 Capped Risk</p>'''
content = content.replace(old_sub, new_sub)

# 4. Update asset toggle tabs in header
old_tabs = '''    <!-- ASSET TOGGLE TABS (JOINT vs GOLD vs SILVER) -->
    <div class="flex items-center bg-slate-900/90 p-1 rounded-2xl border border-slate-800 shadow-inner font-mono text-xs">
      <button id="assetTabJoint" onclick="switchAsset('JOINT')" class="px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer bg-gradient-to-r from-emerald-500 to-teal-400 text-black shadow-md shadow-emerald-950/40">
        <span>🌐 Joint Portfolio</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-black/20 text-black">Gold + Silver</span>
      </button>
      <button id="assetTabGold" onclick="switchAsset('XAUTUSD')" class="px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800">
        <span>🥇 Gold (XAUTUSD)</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">23.5M Ticks</span>
      </button>
      <button id="assetTabSilver" onclick="switchAsset('SLVONUSD')" class="px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800">
        <span>🥈 Silver (SLVONUSD)</span>
        <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300">801k Ticks</span>
      </button>
    </div>'''

new_tabs = '''    <!-- ASSET TOGGLE TABS (4 ASSETS + JOINT) -->
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
    </div>'''

content = content.replace(old_tabs, new_tabs)

# 5. Update datasets in script
old_ds = '''    const allDatasets = {{
      JOINT: {joint_results_json},
      XAUTUSD: {gold_results_json},
      SLVONUSD: {silver_results_json}
    }};'''

new_ds = '''    const allDatasets = {{
      JOINT: {joint_results_json},
      XAUTUSD: {gold_results_json},
      SLVONUSD: {silver_results_json},
      BTCUSD: {btc_results_json},
      ETHUSD: {eth_results_json}
    }};'''

content = content.replace(old_ds, new_ds)

# 6. Update switchAsset function to style all 5 tabs
old_switch_body = '''      const tabJoint = document.getElementById('assetTabJoint');
      const tabGold = document.getElementById('assetTabGold');
      const tabSilver = document.getElementById('assetTabSilver');
      const badge = document.getElementById('headerAssetBadge');
      const subtitle = document.getElementById('headerSubtitle');

      if (asset === 'JOINT') {{
        if (tabJoint) tabJoint.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer bg-gradient-to-r from-emerald-500 to-teal-400 text-black shadow-md shadow-emerald-950/40";
        if (tabGold) tabGold.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        if (tabSilver) tabSilver.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        if (badge) {{
          badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
          badge.innerText = "🌐 Joint Portfolio (Gold + Silver)";
        }}
        if (subtitle) subtitle.innerText = "Simultaneous Multi-Asset Portfolio Execution on Delta Exchange • 24.3 Million Combined Ticks • Strict $5 Risk • 100x Leverage";
      }} else if (asset === 'XAUTUSD') {{
        if (tabGold) tabGold.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer bg-gradient-to-r from-amber-500 to-yellow-400 text-black shadow-md shadow-amber-950/40";
        if (tabJoint) tabJoint.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        if (tabSilver) tabSilver.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        if (badge) {{
          badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20";
          badge.innerText = "Gold (XAUTUSD)";
        }}
        if (subtitle) subtitle.innerText = "23.5 Million Delta Trade Ticks • April – September 2026 • 100x Isolated Leverage • $4-$5 Capped Risk";
      }} else {{
        if (tabSilver) tabSilver.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer bg-gradient-to-r from-cyan-400 to-blue-500 text-black shadow-md shadow-cyan-950/40";
        if (tabJoint) tabJoint.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        if (tabGold) tabGold.className = "px-3.5 py-1.5 rounded-xl font-bold transition flex items-center gap-2 cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800";
        if (badge) {{
          badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20";
          badge.innerText = "Silver (SLVONUSD)";
        }}
        if (subtitle) subtitle.innerText = "801,831 Delta Trade Ticks • February – September 2026 • 100x Isolated Leverage • $4-$5 Capped Risk";
      }}'''

new_switch_body = '''      const tabs = {{
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
      }}'''

content = content.replace(old_switch_body, new_switch_body)

# 7. Update journal navbar
old_j_nav = '''    <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
      <a href="agent_journal.html" class="px-3 py-1.5 rounded-xl {'bg-blue-500/20 text-blue-300 border border-blue-500/30 font-bold shadow' if active_nav == 'JOINT' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>🌐 Joint Journal</span>
      </a>
      <a href="gold_journal.html" class="px-3 py-1.5 rounded-xl {'bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold shadow' if active_nav == 'GOLD' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>🥇 Gold Journal</span>
      </a>
      <a href="silver_journal.html" class="px-3 py-1.5 rounded-xl {'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-bold shadow' if active_nav == 'SILVER' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>🥈 Silver Journal</span>
      </a>
      <a href="backtest_report.html" class="px-3 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 font-bold transition flex items-center gap-1.5">
        <i data-lucide="bar-chart-2" class="w-3.5 h-3.5"></i>
        <span>Scorecard</span>
      </a>
    </div>'''

new_j_nav = '''    <div class="flex flex-wrap items-center gap-2 font-mono text-xs">
      <a href="agent_journal.html" class="px-3 py-1.5 rounded-xl {'bg-blue-500/20 text-blue-300 border border-blue-500/30 font-bold shadow' if active_nav == 'JOINT' else 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700 font-bold'} transition flex items-center gap-1.5">
        <span>🌐 Joint</span>
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
      <a href="backtest_report.html" class="px-3 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 font-bold transition flex items-center gap-1.5">
        <i data-lucide="bar-chart-2" class="w-3.5 h-3.5"></i>
        <span>Scorecard</span>
      </a>
    </div>'''

content = content.replace(old_j_nav, new_j_nav)

# 8. Update journal asset selector tabs
old_j_assets = '''        <!-- ASSET SELECTOR TABS -->
        <div class="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
          <button onclick="setAssetFilter('ALL')" id="aTab_ALL" class="px-2.5 py-1 rounded bg-amber-500 text-black font-extrabold text-[11px] shadow">All Assets</button>
          <button onclick="setAssetFilter('XAUTUSD')" id="aTab_XAUTUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">🥇 Gold</button>
          <button onclick="setAssetFilter('SLVONUSD')" id="aTab_SLVONUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">🥈 Silver</button>
        </div>'''

new_j_assets = '''        <!-- ASSET SELECTOR TABS -->
        <div class="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
          <button onclick="setAssetFilter('ALL')" id="aTab_ALL" class="px-2.5 py-1 rounded bg-amber-500 text-black font-extrabold text-[11px] shadow">All</button>
          <button onclick="setAssetFilter('XAUTUSD')" id="aTab_XAUTUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">🥇 Gold</button>
          <button onclick="setAssetFilter('SLVONUSD')" id="aTab_SLVONUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">🥈 Silver</button>
          <button onclick="setAssetFilter('BTCUSD')" id="aTab_BTCUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">₿ BTC</button>
          <button onclick="setAssetFilter('ETHUSD')" id="aTab_ETHUSD" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px] border border-slate-700">Ξ ETH</button>
        </div>'''

content = content.replace(old_j_assets, new_j_assets)

# 9. Update setAssetFilter JS in journal
old_set_asset = '''      const assets = ['ALL', 'XAUTUSD', 'SLVONUSD'];'''
new_set_asset = '''      const assets = ['ALL', 'XAUTUSD', 'SLVONUSD', 'BTCUSD', 'ETHUSD'];'''
content = content.replace(old_set_asset, new_set_asset)

# 10. Update generate_all_journals method
old_gen_all_j = '''    def generate_all_journals(self, joint_trades: List[Dict], gold_trades: List[Dict], silver_trades: List[Dict], db_thoughts: List[Dict]) -> Dict[str, Path]:
        """Generates Joint, Gold, and Silver standalone journals with synchronized navigation."""
        p_joint = self.generate_agent_journal(joint_trades, db_thoughts, filename="agent_journal.html", active_nav="JOINT")
        p_gold = self.generate_agent_journal(gold_trades, db_thoughts, filename="gold_journal.html", active_nav="GOLD")
        p_silver = self.generate_agent_journal(silver_trades, db_thoughts, filename="silver_journal.html", active_nav="SILVER")
        return {"joint": p_joint, "gold": p_gold, "silver": p_silver}'''

new_gen_all_j = '''    def generate_all_journals(
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
        return {"joint": p_joint, "gold": p_gold, "silver": p_silver, "btc": p_btc, "eth": p_eth}'''

content = content.replace(old_gen_all_j, new_gen_all_j)

target_file.write_text(content, encoding="utf-8")
print("[SUCCESS] Patched html_reporter.py successfully!")
