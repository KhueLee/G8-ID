@echo off
chcp 65001 >nul
title G8 ID - Phan mem dinh danh (KHONG DONG CUA SO NAY)
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Python. Cai Python 3.10+ 64-bit va chon "Add python.exe to PATH", sau do chay install.bat
  pause
  exit /b 1
)
python -c "import pymongo, serial, flask, waitress" >nul 2>nul
if errorlevel 1 (
  echo Chua co thu vien Python - dang chay install.bat ...
  call "%~dp0install.bat" nopause
)

:loop
python -m app.main
set RC=%errorlevel%
if %RC%==0 goto end
if %RC%==3 goto end
echo.
echo [%date% %time%] Phan mem dung bat thuong (ma %RC%). Tu khoi dong lai sau 3 giay... Xem logs\crash.log
echo [%date% %time%] restart after exit code %RC%>>"%~dp0logs\restart.log"
timeout /t 3 /nobreak >nul
goto loop

:end
exit /b 0
