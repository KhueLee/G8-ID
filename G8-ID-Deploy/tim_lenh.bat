@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
python tools\find_order.py %*
echo.
pause
