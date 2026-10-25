@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
python tools\restore_orders.py %*
echo.
pause
