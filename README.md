# 🧠 Agent Brain | Quantitative Trading & Risk Architecture

Autonomous, multi-timeframe quantitative trading engine and intelligent decision brain engineered specifically for **BTCUSD**, **XAUTUSD (Gold)**, and **SLVONUSD (Silver)** on **Delta Exchange**.

---

## ⚡ Core Architecture

```text
Agent Brain/
│
├── config/
│   ├── settings.py           # Assets, $3-$5 risk rules, 100x leverage, weekend locks
│   └── .env                  # Private Delta API Key & Secret
│
├── data/
│   ├── database.py           # Local SQLite Database (State persistence across reboots)
│   ├── historical_loader.py  # Fetches Delta API candles & parses monthly trade CSVs
│   ├── trading_brain.db      # Local SQLite database (Auto-generated)
│   └── csv_imports/          # Place Delta Exchange monthly tick-by-tick CSVs here
│
├── exchange/
│   └── delta_client.py       # REST API client (L2 DOM, Candles, Native Bracket Orders)
│
├── strategies/
│   ├── sr_engine.py          # Swing High/Low fractals, PDH/PDL, Key Zone tests
│   ├── orderflow_engine.py   # DOM Imbalance Ratio, Footprint CVD & Institutional Absorption
│   └── confluence_brain.py   # 1.0 - 5.0 Star Conviction Scoring & Strict Veto Engine
│
├── execution/
│   └── risk_manager.py       # Dynamic Lot Sizer ($3-$5 risk), 100x Margin Solver, $20 Circuit Breaker
│
├── backtest/
│   └── backtester.py         # Realistic simulator with maker/taker fees and slippage
│
├── reports/
│   ├── html_reporter.py      # Generates interactive dark-mode HTML dashboards
│   ├── backtest_report.html  # Interactive backtest analytics & equity curve
│   └── agent_journal.html    # Living trade journal & AI Brain thoughts feed
│
├── main.py                   # Master Interactive Cockpit Runner
└── requirements.txt
```

---

## 🔬 Evidence-Driven AI Trading Brain Research Suite

A quantitative research engine with zero-lookahead backtesting, multi-timeframe structural analysis, and an interactive 8-dashboard verification report:

### Core Research Components
* **`data/data_pipeline.py`**: Clean multi-timeframe aggregation (15m, 1h, 4h, 1D), ATR, swing pivots, and order flow metrics.
* **`strategies/research_strategies.py`**: 7 standardized strategy families (HTF Trend Continuation, S/R Reversal, Consolidation Breakout, Liquidity Sweep & Reclaim, Pullback Continuation, Order Flow CVD, and Multi-Factor Confluence).
* **`backtest/research_backtest_engine.py`**: Strict chronological bar-by-bar engine with Delta Exchange fees (0.01% + 18% GST), slippage, and 8 counterfactual exit models (including the Special 1R Management Hypothesis).
* **`analysis/trade_analyzer.py`**: Granular MFE/MAE analysis, failure mode categorization, and session analysis.
* **`tests/test_research_engine.py`**: 5 unit tests covering contract specifications, fee math, intra-bar conservative execution, and no-lookahead constraints.

### How to Run Research & View Dashboard
1. Run Unit Tests:
   ```powershell
   .\.venv\Scripts\python.exe -m unittest tests/test_research_engine.py
   ```
2. Run Backtest Experiments & Trade Analysis:
   ```powershell
   .\.venv\Scripts\python.exe scripts/run_research_experiments.py
   .\.venv\Scripts\python.exe scripts/run_trade_analysis.py
   ```
3. Generate & Open the Interactive HTML Report:
   ```powershell
   .\.venv\Scripts\python.exe scripts/build_research_dashboard_html.py
   Start-Process "reports/ai_trading_brain_research_dashboard.html"
   ```

---

## 🛡️ Risk Management Parameters

* **Starting Capital Base:** ₹5,000 (~$50 - $60 USD)
* **Risk Per Trade:** **$3.00 to $5.00 USD** (Strictly enforced by dynamic lot sizing)
* **Daily Max Loss Limit:** **$20.00 USD** (Emergency circuit breaker halts trading for 24h)
* **Leverage:** **50x to 100x Isolated** (Ensures minimal margin requirement so you never see "Insufficient Balance")
* **Minimum Risk-to-Reward:** **1:2.0** (Risk $4 to make $8+)
* **Weekend Lock:** Friday night (23:30 IST) to Monday morning (05:30 IST) complete trading freeze

---

## 🚀 How to Run

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Credentials (Optional for Paper/Backtesting)
Copy `.env.example` to `.env` and fill in your Delta API key and secret:
```bash
copy .env.example .env
```

### 3. Launch the Cockpit
```bash
python main.py
```

### Interactive Menu Options:
1. **Run Multi-Timeframe Backtest & Generate Interactive HTML Report** (Opens `reports/backtest_report.html`)
2. **Run Paper Trading Engine** (Connects to live Delta market feeds, scans DOM/Footprint)
3. **Run AI Post-Mortem & Parameter Calibration** (Calibrates conviction thresholds from trade logs)
4. **Open Living Trade Journal** (Opens `reports/agent_journal.html`)

---

## 📊 Ingesting Delta Tick-by-Tick CSV Files

If you download monthly trade history CSV files from `delta.exchange/app/trade_history`:
1. Drop the CSV files into `data/csv_imports/`.
2. The `HistoricalDataLoader` will parse and aggregate the tick trades into candles with full **Volume Delta (Buy - Sell)** and **CVD** for backtesting.
