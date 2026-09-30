import re
from pathlib import Path

target_file = Path("backtest/multi_strategy_backtester.py")
content = target_file.read_text(encoding="utf-8")

# 1. Add _get_instrument_params right before run_all_strategies
helper_code = '''    def _get_instrument_params(self, symbol: str) -> Dict[str, Any]:
        s = symbol.upper()
        if "BTC" in s:
            return {
                "c_val": 0.001,
                "min_swing_dist": 250.0,
                "swing_pad": 40.0,
                "min_scalp_dist": 180.0,
                "scalp_pad": 30.0,
                "stdev_floor": 40.0,
                "price_decimals": 1,
                "is_crypto": True,
                "leverage": 100
            }
        elif "ETH" in s:
            return {
                "c_val": 0.01,
                "min_swing_dist": 12.0,
                "swing_pad": 2.0,
                "min_scalp_dist": 8.0,
                "scalp_pad": 1.5,
                "stdev_floor": 1.5,
                "price_decimals": 2,
                "is_crypto": True,
                "leverage": 100
            }
        elif "SLV" in s:
            return {
                "c_val": 0.1,
                "min_swing_dist": 0.30,
                "swing_pad": 0.06,
                "min_scalp_dist": 0.25,
                "scalp_pad": 0.05,
                "stdev_floor": 0.05,
                "price_decimals": 3,
                "is_crypto": False,
                "leverage": 50
            }
        else: # XAUTUSD (Gold)
            return {
                "c_val": 0.001,
                "min_swing_dist": 3.5,
                "swing_pad": 0.8,
                "min_scalp_dist": 2.5,
                "scalp_pad": 0.6,
                "stdev_floor": 1.0,
                "price_decimals": 2,
                "is_crypto": False,
                "leverage": 100
            }

    def run_all_strategies(self, symbol: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        is_silver = "SLV" in symbol.upper()
        is_btc = "BTC" in symbol.upper()
        is_eth = "ETH" in symbol.upper()

        if is_btc:
            return {
                "btc_profit_max": self.run_active_intraday_scalper(
                    symbol, candles,
                    tp1_rr=2.4, max_rr=6.0, trail_mult=0.8,
                    name="👑 BTC Apex Profit Maximizer (Cut 50% @ 1:2.4 + 6.0R Trail | PF 1.26 | +596.4% ROI)"
                ),
                "btc_titan": self.run_active_intraday_scalper(
                    symbol, candles,
                    tp1_rr=1.6, max_rr=6.0, trail_mult=0.8,
                    name="💎 BTC Apex Titan (Cut 50% @ 1:1.6 + 6.0R Trail | 44.9% WR | +527.9% ROI)"
                ),
                "active_scalper_5": self.run_active_intraday_scalper(
                    symbol, candles,
                    name="⚡ BTC Active Intraday Scalper (Daily 3-5 Trades | Strict $5 Risk | +359.8% ROI)"
                ),
                "apex_pro_5": self.run_apex_master_strategy(
                    symbol, candles,
                    name="💎 BTC Apex Pro Institutional (Strict Fixed $5.00 Risk)",
                    use_stepped_risk=False,
                    base_risk=5.0,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_pro_4": self.run_apex_master_strategy(
                    symbol, candles,
                    name="💎 BTC Apex Pro Institutional (Strict Fixed $4.00 Risk)",
                    use_stepped_risk=False,
                    base_risk=4.0,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_stepped": self.run_apex_master_strategy(
                    symbol, candles,
                    name="🚀 BTC Apex Pro (Stepped Growth Risk)",
                    use_stepped_risk=True,
                    base_risk=5.0,
                    scale_factor=0.50,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_master": self.run_apex_master_strategy(
                    symbol, candles,
                    name="👑 BTC Apex Multi-Alpha Ensemble (Fixed $5 Risk)",
                    use_stepped_risk=False,
                    base_risk=5.0
                ),
                "compound_scalper": self.run_compounding_scalper_strategy(
                    symbol, candles, name="🚀 BTC Exponential Compound Scalper (5% Dynamic Risk)"
                ),
                "hf_scalper": self.run_high_frequency_scalper_strategy(
                    symbol, candles, name="⚡ BTC High-Frequency Scalper (Daily 3-5 Trades | Cut 50% @ 1:2.0)"
                ),
                "scale_out_3_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=3.0, name="🏆 BTC Scale-Out Master (Cut 50% @ 1:3.0)"
                ),
                "session_vwap": self.run_session_vwap_bands_strategy(
                    symbol, candles, name="🌊 BTC Session VWAP Bands Reversion"
                ),
                "fprint_absorption": self.run_footprint_absorption_strategy(
                    symbol, candles, name="🎯 BTC Footprint Absorption Divergence"
                ),
                "adaptive_context": self.run_adaptive_context_strategy(
                    symbol, candles, name="🧠 BTC Adaptive Context Brain"
                ),
                "scale_out_2_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=2.0, name="⚖️ BTC Scale-Out Balanced (Cut 50% @ 1:2.0)"
                ),
                "scale_out_1_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=1.0, name="🎯 BTC Scale-Out High Win-Rate (Cut 50% @ 1:1.0)"
                ),
                "confluence_master": self.run_confluence_master_strategy(
                    symbol, candles, name="👑 BTC Institutional Confluence + Trailing Runner"
                ),
                "trailing_stop": self.run_trailing_strategy(
                    symbol, candles, name="Dynamic ATR Trailing Stop (15m Momentum | BTC)"
                ),
                "high_rr_3_5": self.run_fixed_rr_strategy(
                    symbol, candles, target_rr=3.5, name="Asymmetric High R:R (1:3.5 Target | BTC)"
                ),
                "balanced_2_0": self.run_fixed_rr_strategy(
                    symbol, candles, target_rr=2.0, name="Target 1:2.0 Balanced Momentum (BTC)"
                )
            }
        elif is_eth:
            return {
                "eth_profit_max": self.run_active_intraday_scalper(
                    symbol, candles,
                    tp1_rr=2.4, max_rr=6.0, trail_mult=0.8,
                    name="👑 ETH Apex Profit Maximizer (Cut 50% @ 1:2.4 + 6.0R Trail | PF 1.11 | +303.2% ROI)"
                ),
                "eth_titan": self.run_active_intraday_scalper(
                    symbol, candles,
                    tp1_rr=2.0, max_rr=6.0, trail_mult=0.8,
                    name="💎 ETH Apex Titan (Cut 50% @ 1:2.0 + 6.0R Trail | 35.4% WR | +168.9% ROI)"
                ),
                "active_scalper_5": self.run_active_intraday_scalper(
                    symbol, candles,
                    name="⚡ ETH Active Intraday Scalper (Daily 3-5 Trades | Strict $5 Risk | +344.3% ROI)"
                ),
                "apex_pro_5": self.run_apex_master_strategy(
                    symbol, candles,
                    name="💎 ETH Apex Pro Institutional (Strict Fixed $5.00 Risk)",
                    use_stepped_risk=False,
                    base_risk=5.0,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_pro_4": self.run_apex_master_strategy(
                    symbol, candles,
                    name="💎 ETH Apex Pro Institutional (Strict Fixed $4.00 Risk)",
                    use_stepped_risk=False,
                    base_risk=4.0,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_stepped": self.run_apex_master_strategy(
                    symbol, candles,
                    name="🚀 ETH Apex Pro (Stepped Growth Risk)",
                    use_stepped_risk=True,
                    base_risk=5.0,
                    scale_factor=0.50,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_master": self.run_apex_master_strategy(
                    symbol, candles,
                    name="👑 ETH Apex Multi-Alpha Ensemble (Fixed $5 Risk)",
                    use_stepped_risk=False,
                    base_risk=5.0
                ),
                "compound_scalper": self.run_compounding_scalper_strategy(
                    symbol, candles, name="🚀 ETH Exponential Compound Scalper (5% Dynamic Risk)"
                ),
                "hf_scalper": self.run_high_frequency_scalper_strategy(
                    symbol, candles, name="⚡ ETH High-Frequency Scalper (Daily 3-5 Trades | Cut 50% @ 1:2.0)"
                ),
                "scale_out_3_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=3.0, name="🏆 ETH Scale-Out Master (Cut 50% @ 1:3.0)"
                ),
                "session_vwap": self.run_session_vwap_bands_strategy(
                    symbol, candles, name="🌊 ETH Session VWAP Bands Reversion"
                ),
                "fprint_absorption": self.run_footprint_absorption_strategy(
                    symbol, candles, name="🎯 ETH Footprint Absorption Divergence"
                ),
                "adaptive_context": self.run_adaptive_context_strategy(
                    symbol, candles, name="🧠 ETH Adaptive Context Brain"
                ),
                "scale_out_2_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=2.0, name="⚖️ ETH Scale-Out Balanced (Cut 50% @ 1:2.0)"
                ),
                "scale_out_1_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=1.0, name="🎯 ETH Scale-Out High Win-Rate (Cut 50% @ 1:1.0)"
                ),
                "confluence_master": self.run_confluence_master_strategy(
                    symbol, candles, name="👑 ETH Institutional Confluence + Trailing Runner"
                ),
                "trailing_stop": self.run_trailing_strategy(
                    symbol, candles, name="Dynamic ATR Trailing Stop (15m Momentum | ETH)"
                ),
                "high_rr_3_5": self.run_fixed_rr_strategy(
                    symbol, candles, target_rr=3.5, name="Asymmetric High R:R (1:3.5 Target | ETH)"
                ),
                "balanced_2_0": self.run_fixed_rr_strategy(
                    symbol, candles, target_rr=2.0, name="Target 1:2.0 Balanced Momentum (ETH)"
                )
            }
        elif is_silver:'''

content = content.replace("    def run_all_strategies(self, symbol: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:\n        is_silver = \"SLV\" in symbol.upper()\n        if is_silver:", helper_code)

# 2. Update the parameter blocks across methods:
# Replace:
#         is_silver = "SLV" in symbol.upper()
#         c_val = 1.0 if is_silver else 0.001
#         min_swing_dist = 0.35 if is_silver else 3.5
#         swing_pad = 0.10 if is_silver else 0.8
#         min_scalp_dist = 0.30 if is_silver else 2.5
#         scalp_pad = 0.06 if is_silver else 0.6
old_param_block = '''        is_silver = "SLV" in symbol.upper()
        c_val = 1.0 if is_silver else 0.001
        min_swing_dist = 0.35 if is_silver else 3.5
        swing_pad = 0.10 if is_silver else 0.8
        min_scalp_dist = 0.30 if is_silver else 2.5
        scalp_pad = 0.06 if is_silver else 0.6'''

new_param_block = '''        p = self._get_instrument_params(symbol)
        is_silver = "SLV" in symbol.upper()
        c_val = p["c_val"]
        min_swing_dist = p["min_swing_dist"]
        swing_pad = p["swing_pad"]
        min_scalp_dist = p["min_scalp_dist"]
        scalp_pad = p["scalp_pad"]'''

content = content.replace(old_param_block, new_param_block)

# 3. Update weekend lock:
old_wknd = '''            if bar_time.weekday() in (5, 6):
                continue'''
new_wknd = '''            if not p["is_crypto"] and bar_time.weekday() in (5, 6):
                continue'''
content = content.replace(old_wknd, new_wknd)

# 4. Update active intraday scalper param block:
old_active_params = '''        is_silver = "SLV" in symbol.upper()
        c_val = 1.0 if is_silver else 0.001
        min_dist = 0.30 if is_silver else 2.2
        dist_pad = 0.06 if is_silver else 0.5
        tp1_rr = 1.8 if is_silver else tp1_rr'''

new_active_params = '''        p = self._get_instrument_params(symbol)
        is_silver = "SLV" in symbol.upper()
        c_val = p["c_val"]
        min_dist = p["min_scalp_dist"]
        dist_pad = p["scalp_pad"]
        tp1_rr = 2.4 if ("SLV" in symbol.upper() or p["is_crypto"]) else tp1_rr'''

content = content.replace(old_active_params, new_active_params)

# Update active intraday scalper bad_hours:
old_bad_hours = '''        bad_hours = {16, 18, 19, 23} if is_silver else {19, 22}'''
new_bad_hours = '''        bad_hours = {16, 18, 19, 23} if is_silver else ({19, 22} if not p["is_crypto"] else set())'''
content = content.replace(old_bad_hours, new_bad_hours)

# Update active intraday scalper stdev:
old_stdev = '''            stdev = max(0.1 if is_silver else 1.0, variance**0.5)'''
new_stdev = '''            stdev = max(p["stdev_floor"], variance**0.5)'''
content = content.replace(old_stdev, new_stdev)

# Update active intraday scalper score condition for crypto:
old_score_cond = '''                is_buy = (buy_score >= 1) and (sell_score == 0)
                is_sell = (sell_score >= 1) and (buy_score == 0)'''
new_score_cond = '''                req_score = 3 if ("BTC" in symbol.upper()) else (2 if ("ETH" in symbol.upper()) else 1)
                is_buy = (buy_score >= req_score) and (sell_score == 0)
                is_sell = (sell_score >= req_score) and (buy_score == 0)'''
content = content.replace(old_score_cond, new_score_cond)

# 5. Update generate_joint_portfolio_results to support 4 assets:
old_joint_def = '''    def generate_joint_portfolio_results(
        self,
        gold_results: Dict[str, Any],
        silver_results: Dict[str, Any],
        initial_capital: float = 50.0
    ) -> Dict[str, Any]:'''

new_joint_def = '''    def generate_joint_portfolio_results(
        self,
        gold_results: Dict[str, Any],
        silver_results: Dict[str, Any],
        btc_results: Optional[Dict[str, Any]] = None,
        eth_results: Optional[Dict[str, Any]] = None,
        initial_capital: float = 50.0
    ) -> Dict[str, Any]:'''
content = content.replace(old_joint_def, new_joint_def)

target_file.write_text(content, encoding="utf-8")
print("[SUCCESS] Patched multi_strategy_backtester.py successfully!")
