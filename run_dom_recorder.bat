@echo off
title AGENT BRAIN - 24/7 Level 2 DOM Orderbook & Heatmap Recorder
cd /d "%~dp0"
echo ===============================================================================
echo     📊 AGENT BRAIN: 24/7 LEVEL 2 DOM RECORDER (DELTA EXCHANGE) 📊
echo ===============================================================================
echo Starting 24/7 DOM recorder for BTCUSD, ETHUSD, XAUTUSD, SLVONUSD...
.\.venv\Scripts\python.exe scripts/record_l2_dom.py
pause
