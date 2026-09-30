@echo off
title AGENT BRAIN - Autonomous Multi-Pair Live Trader
cd /d "%~dp0"
echo ===============================================================================
echo     🧠 AGENT BRAIN: AUTONOMOUS MULTI-PAIR LIVE TRADER (DELTA EXCHANGE) 🧠
echo ===============================================================================
echo Starting live trading engine with Python virtual environment...
.\.venv\Scripts\python.exe run_live_trader.py
pause
