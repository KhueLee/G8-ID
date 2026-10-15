@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1
rem Dat thoi gian quet cua dau doc = 300000 ms (lenh cua ban cu). Dong G8 ID truoc khi chay.
python tools\scanner_cmd.py %*
echo.
pause
