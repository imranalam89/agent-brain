import re

with open("backtest/multi_strategy_backtester.py", "r", encoding="utf-8") as f:
    text = f.read()

# Replace run_all_strategies to branch for is_silver
old_run_all = '''    def run_all_strategies(self, symbol: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "apex_pro_5": self.run_apex_master_strategy(
                symbol, candles,
                name="💎 Apex Pro Institutional (Strict Fixed $5.00 Risk | $50 ➔ $388.05 | +676.1% ROI | Low DD -$41.46)",
                use_stepped_risk=False,
                base_risk=5.0,
                filter_session_chop=True,
                trail_high=1.2,
                trail_mod=1.2
            ),
            "apex_pro_4": self.run_apex_master_strategy(
                symbol, candles,
                name="💎 Apex Pro Institutional (Strict Fixed $4.00 Risk | $50 ➔ $320.85 | +541.7% ROI | Low DD -$33.18)",
                use_stepped_risk=False,
                base_risk=4.0,
                filter_session_chop=True,
                trail_high=1.2,
                trail_mod=1.2
            ),
            "apex_stepped": self.run_apex_master_strategy(
                symbol, candles,
                name="🚀 Apex Pro (Stepped Growth Risk | $50 ➔ $1,298.49 | +2,497.0% ROI)",
                use_stepped_risk=True,
                base_risk=5.0,
                scale_factor=0.50,
                filter_session_chop=True,
                trail_high=1.2,
                trail_mod=1.2
            ),
            "apex_master": self.run_apex_master_strategy(
                symbol, candles,
                name="👑 Apex Multi-Alpha Ensemble (Fixed $5 Risk | +452.4% ROI | $50 ➔ $276.21)",
                use_stepped_risk=False,
                base_risk=5.0
            ),
            "compound_scalper": self.run_compounding_scalper_strategy(
                symbol, candles, name="🚀 Exponential Compound Scalper (5% Dynamic Risk | $50 ➔ $313.43 | +526.9% ROI)"
            ),
            "hf_scalper": self.run_high_frequency_scalper_strategy(
                symbol, candles, name="⚡ High-Frequency Scalper (Daily 3-5 Trades | Cut 50% @ 1:2.0 + BE Lock)"
            ),
            "scale_out_3_0": self.run_scale_out_strategy(
                symbol, candles, tp1_rr=3.0, name="Scale-Out Master (Cut 50% @ 1:3.0 + BE Lock + 1.5x Trail)"
            ),
            "session_vwap": self.run_session_vwap_bands_strategy(
                symbol, candles, name="🌊 Session VWAP Bands Reversion (59.0% Win Rate | Ultra-Low Drawdown)"
            ),
            "fprint_absorption": self.run_footprint_absorption_strategy(
                symbol, candles, name="🎯 Footprint Absorption Divergence (CVD Delta Traps | +216.0% ROI)"
            ),
            "adaptive_context": self.run_adaptive_context_strategy(
                symbol, candles, name="Adaptive Context Brain (High Conf: Big Runner | Mod Conf: Cut 50% @ 1:2)"
            ),
            "scale_out_2_0": self.run_scale_out_strategy(
                symbol, candles, tp1_rr=2.0, name="Scale-Out Balanced (Cut 50% @ 1:2.0 + BE Lock + 1.5x Trail)"
            ),
            "scale_out_1_0": self.run_scale_out_strategy(
                symbol, candles, tp1_rr=1.0, name="Scale-Out High Win-Rate (Cut 50% @ 1:1.0 + BE Lock + 1.5x Trail)"
            ),
            "confluence_master": self.run_confluence_master_strategy(
                symbol, candles, name="Institutional Confluence + Trailing Runner (Merged)"
            ),
            "trailing_stop": self.run_trailing_strategy(
                symbol, candles, name="Dynamic ATR Trailing Stop (15m Momentum)"
            ),
            "high_rr_3_5": self.run_fixed_rr_strategy(
                symbol, candles, target_rr=3.5, name="Asymmetric High R:R (1:3.5 Target)"
            ),
            "balanced_2_0": self.run_fixed_rr_strategy(
                symbol, candles, target_rr=2.0, name="Target 1:2.0 Balanced Momentum"
            )
        }'''

new_run_all = '''    def run_all_strategies(self, symbol: str, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        is_silver = "SLV" in symbol.upper()
        if is_silver:
            return {
                "apex_pro_5": self.run_apex_master_strategy(
                    symbol, candles,
                    name="💎 Apex Pro Institutional (Strict Fixed $5.00 Risk | Silver)",
                    use_stepped_risk=False,
                    base_risk=5.0,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_pro_4": self.run_apex_master_strategy(
                    symbol, candles,
                    name="💎 Apex Pro Institutional (Strict Fixed $4.00 Risk | Silver)",
                    use_stepped_risk=False,
                    base_risk=4.0,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_stepped": self.run_apex_master_strategy(
                    symbol, candles,
                    name="🚀 Apex Pro (Stepped Growth Risk | Silver)",
                    use_stepped_risk=True,
                    base_risk=5.0,
                    scale_factor=0.50,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_master": self.run_apex_master_strategy(
                    symbol, candles,
                    name="👑 Apex Multi-Alpha Ensemble (Fixed $5 Risk | Silver)",
                    use_stepped_risk=False,
                    base_risk=5.0
                ),
                "compound_scalper": self.run_compounding_scalper_strategy(
                    symbol, candles, name="🚀 Exponential Compound Scalper (5% Dynamic Risk | Silver)"
                ),
                "hf_scalper": self.run_high_frequency_scalper_strategy(
                    symbol, candles, name="⚡ High-Frequency Scalper (Daily 3-5 Trades | Silver)"
                ),
                "scale_out_3_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=3.0, name="🏆 Scale-Out Master (Cut 50% @ 1:3.0 + BE Lock | Silver)"
                ),
                "session_vwap": self.run_session_vwap_bands_strategy(
                    symbol, candles, name="🌊 Session VWAP Bands Reversion (Silver)"
                ),
                "fprint_absorption": self.run_footprint_absorption_strategy(
                    symbol, candles, name="🎯 Footprint Absorption Divergence (Silver)"
                ),
                "adaptive_context": self.run_adaptive_context_strategy(
                    symbol, candles, name="🧠 Adaptive Context Brain (Silver)"
                ),
                "scale_out_2_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=2.0, name="⚖️ Scale-Out Balanced (Cut 50% @ 1:2.0 + BE Lock | Silver)"
                ),
                "scale_out_1_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=1.0, name="🎯 Scale-Out High Win-Rate (Cut 50% @ 1:1.0 | Silver)"
                ),
                "confluence_master": self.run_confluence_master_strategy(
                    symbol, candles, name="👑 Institutional Confluence + Trailing Runner (Silver)"
                ),
                "trailing_stop": self.run_trailing_strategy(
                    symbol, candles, name="Dynamic ATR Trailing Stop (15m Momentum | Silver)"
                ),
                "high_rr_3_5": self.run_fixed_rr_strategy(
                    symbol, candles, target_rr=3.5, name="Asymmetric High R:R (1:3.5 Target | Silver)"
                ),
                "balanced_2_0": self.run_fixed_rr_strategy(
                    symbol, candles, target_rr=2.0, name="Target 1:2.0 Balanced Momentum (Silver)"
                )
            }
        else:
            return {
                "apex_pro_5": self.run_apex_master_strategy(
                    symbol, candles,
                    name="💎 Apex Pro Institutional (Strict Fixed $5.00 Risk | $50 ➔ $388.05 | +676.1% ROI | Low DD -$41.46)",
                    use_stepped_risk=False,
                    base_risk=5.0,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_pro_4": self.run_apex_master_strategy(
                    symbol, candles,
                    name="💎 Apex Pro Institutional (Strict Fixed $4.00 Risk | $50 ➔ $320.85 | +541.7% ROI | Low DD -$33.18)",
                    use_stepped_risk=False,
                    base_risk=4.0,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_stepped": self.run_apex_master_strategy(
                    symbol, candles,
                    name="🚀 Apex Pro (Stepped Growth Risk | $50 ➔ $1,298.49 | +2,497.0% ROI)",
                    use_stepped_risk=True,
                    base_risk=5.0,
                    scale_factor=0.50,
                    filter_session_chop=True,
                    trail_high=1.2,
                    trail_mod=1.2
                ),
                "apex_master": self.run_apex_master_strategy(
                    symbol, candles,
                    name="👑 Apex Multi-Alpha Ensemble (Fixed $5 Risk | +452.4% ROI | $50 ➔ $276.21)",
                    use_stepped_risk=False,
                    base_risk=5.0
                ),
                "compound_scalper": self.run_compounding_scalper_strategy(
                    symbol, candles, name="🚀 Exponential Compound Scalper (5% Dynamic Risk | $50 ➔ $313.43 | +526.9% ROI)"
                ),
                "hf_scalper": self.run_high_frequency_scalper_strategy(
                    symbol, candles, name="⚡ High-Frequency Scalper (Daily 3-5 Trades | Cut 50% @ 1:2.0 + BE Lock)"
                ),
                "scale_out_3_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=3.0, name="Scale-Out Master (Cut 50% @ 1:3.0 + BE Lock + 1.5x Trail)"
                ),
                "session_vwap": self.run_session_vwap_bands_strategy(
                    symbol, candles, name="🌊 Session VWAP Bands Reversion (59.0% Win Rate | Ultra-Low Drawdown)"
                ),
                "fprint_absorption": self.run_footprint_absorption_strategy(
                    symbol, candles, name="🎯 Footprint Absorption Divergence (CVD Delta Traps | +216.0% ROI)"
                ),
                "adaptive_context": self.run_adaptive_context_strategy(
                    symbol, candles, name="Adaptive Context Brain (High Conf: Big Runner | Mod Conf: Cut 50% @ 1:2)"
                ),
                "scale_out_2_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=2.0, name="Scale-Out Balanced (Cut 50% @ 1:2.0 + BE Lock + 1.5x Trail)"
                ),
                "scale_out_1_0": self.run_scale_out_strategy(
                    symbol, candles, tp1_rr=1.0, name="Scale-Out High Win-Rate (Cut 50% @ 1:1.0 + BE Lock + 1.5x Trail)"
                ),
                "confluence_master": self.run_confluence_master_strategy(
                    symbol, candles, name="Institutional Confluence + Trailing Runner (Merged)"
                ),
                "trailing_stop": self.run_trailing_strategy(
                    symbol, candles, name="Dynamic ATR Trailing Stop (15m Momentum)"
                ),
                "high_rr_3_5": self.run_fixed_rr_strategy(
                    symbol, candles, target_rr=3.5, name="Asymmetric High R:R (1:3.5 Target)"
                ),
                "balanced_2_0": self.run_fixed_rr_strategy(
                    symbol, candles, target_rr=2.0, name="Target 1:2.0 Balanced Momentum"
                )
            }'''

assert old_run_all in text, "old_run_all not found"
text = text.replace(old_run_all, new_run_all)

# In each strategy function, add parameter extraction:
# c_val, min_swing_dist, swing_pad, min_scalp_dist, scalp_pad
def inject_vars(match):
    header = match.group(0)
    inject = """
        is_silver = "SLV" in symbol.upper()
        c_val = 1.0 if is_silver else 0.001
        min_swing_dist = 0.35 if is_silver else 3.5
        swing_pad = 0.10 if is_silver else 0.8
        min_scalp_dist = 0.30 if is_silver else 2.5
        scalp_pad = 0.06 if is_silver else 0.6
"""
    return header + inject

# Find def run_... and inject after capital = ...
# Or replace capital = self.initial_capital
text = re.sub(
    r'(def run_[a-z_]+\(.*?\) -> Dict\[str, Any\]:\s+""".*?"""\s+capital = (?:self\.)?initial_capital)',
    inject_vars,
    text,
    flags=re.DOTALL
)

# Now replace:
# 1. 0.001 -> c_val
text = text.replace('* 0.001', '* c_val')

# 2. max(3.5, curr - (c["low"] - 0.8)) -> max(min_swing_dist, curr - (c["low"] - swing_pad))
text = text.replace('max(3.5, curr - (c["low"] - 0.8))', 'max(min_swing_dist, curr - (c["low"] - swing_pad))')
text = text.replace('max(3.5, current_price - (c["low"] - 0.8))', 'max(min_swing_dist, current_price - (c["low"] - swing_pad))')

# 3. max(3.5, (c["high"] + 0.8) - curr) -> max(min_swing_dist, (c["high"] + swing_pad) - curr)
text = text.replace('max(3.5, (c["high"] + 0.8) - curr)', 'max(min_swing_dist, (c["high"] + swing_pad) - curr)')
text = text.replace('max(3.5, (c["high"] + 0.8) - current_price)', 'max(min_swing_dist, (c["high"] + swing_pad) - current_price)')

# 4. max(2.5, abs(curr - (c["low"] if is_buy else c["high"])) + 0.6) -> max(min_scalp_dist, abs(curr - (c["low"] if is_buy else c["high"])) + scalp_pad)
text = text.replace(
    'max(2.5, abs(curr - (c["low"] if is_buy else c["high"])) + 0.6)',
    'max(min_scalp_dist, abs(curr - (c["low"] if is_buy else c["high"])) + scalp_pad)'
)
text = text.replace(
    'max(2.5, abs(curr - (c["low"] if is_bull_absorb else c["high"])) + 0.6)',
    'max(min_scalp_dist, abs(curr - (c["low"] if is_bull_absorb else c["high"])) + scalp_pad)'
)

with open("backtest/multi_strategy_backtester.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Updated backtest/multi_strategy_backtester.py successfully!")
