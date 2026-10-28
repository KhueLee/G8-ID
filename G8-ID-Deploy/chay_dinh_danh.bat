@echo off
chcp 65001 >nul
rem Xin quyen Administrator (de tu tat / bat lai cap PLC CH340 khi bat phan mem va khi cap treo).
rem Bam No o hop thoai UAC thi van chay, chi khong tu tat / bat lai cap. Bo qua: chay_dinh_danh.bat noadmin
net session >nul 2>nul
if not errorlevel 1 goto admin_ok
if /i "%~1"=="noadmin" goto no_admin
echo Dang xin quyen Administrator...
powershell -NoProfile -Command "try { Start-Process -FilePath '%~f0' -ArgumentList 'noadmin' -Verb RunAs -ErrorAction Stop; exit 0 } catch { exit 1 }"
if not errorlevel 1 exit /b 0
:no_admin
net session >nul 2>nul
if not errorlevel 1 goto admin_ok
echo [CANH BAO] Khong co quyen Administrator - van chay, nhung KHONG tu tat / bat lai cap PLC CH340 khi bi treo.
:admin_ok
title PHAN MEM DINH DANH - G8 ID (KHONG DONG CUA SO NAY)
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Python. Cai Python 3.10+ 64-bit va chon "Add python.exe to PATH", sau do chay install.bat
  pause
  exit /b 1
)
python -c "import pymongo, serial, flask, waitress, comtypes" >nul 2>nul
if errorlevel 1 (
  echo Chua co thu vien Python - dang chay install.bat ...
  call "%~dp0install.bat" nopause
)

:loop
python tools\banner.py app
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
