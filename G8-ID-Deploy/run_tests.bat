@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
echo Bo kiem tra tu dong dung thu muc tam va cong rieng (186xx, 27718) - khong dung toi du lieu tram.
python tests\run_tests.py
echo.
pause
