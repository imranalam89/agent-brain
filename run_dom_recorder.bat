@echo off
title AGENT BRAIN - 24/7 Level 2 DOM Orderbook & Heatmap Recorder (1s Multi-Pair)
cd /d "%~dp0"
echo ===============================================================================
echo     📊 AGENT BRAIN: 24/7 LEVEL 2 DOM RECORDER (1s ULTRA-HIGH-FREQUENCY) 📊
echo ===============================================================================
echo Starting 24/7 DOM recorder (1s cadence) for BTCUSD, ETHUSD, XAUTUSD...
.\.venv\Scripts\python.exe scripts/record_l2_dom.py --interval 1.0
pause
