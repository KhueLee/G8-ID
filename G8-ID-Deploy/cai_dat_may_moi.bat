@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------------
rem CAI DAT MAY TRAM MOI - chay MOT LAN sau khi da cai Python 3.13 64-bit (tick "Add python.exe to PATH").
rem Gom cac buoc can quyen Administrator: thu vien Python, firewall 8500, tat chuot serial,
rem tao 2 bieu tuong tren Desktop, (tuy chon) cai thoi gian quet dau doc, kiem tra may.
rem Chay lai nhieu lan cung khong sao. Xong thi mo "Chay phan mem" (chay_dinh_danh.bat).
rem ---------------------------------------------------------------------------
title CAI DAT MAY TRAM MOI - G8 ID

rem Tu xin quyen Administrator (hien hop thoai UAC) neu chua co.
net session >nul 2>nul
if errorlevel 1 (
  echo Dang xin quyen Administrator...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
set PYTHONUTF8=1
set ERR=0

echo === 1/6. Kiem tra Python ===
rem Goi thu python that su: "python" cua Microsoft Store (WindowsApps) co the co ma khong chay duoc.
python -c "import sys; assert sys.version_info >= (3, 10) and sys.maxsize > 2**32" >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Python 3.10+ 64-bit, hoac chua tick "Add python.exe to PATH".
  echo       Cai Python 3.13 64-bit tu python.org, roi chay lai file nay.
  goto fail
)
python --version

echo.
echo === 2/6. Cai thu vien Python ===
call "%~dp0install.bat" nopause
python -c "import pymongo, serial, flask, waitress, comtypes" >nul 2>nul
if errorlevel 1 goto fail

echo.
echo === 3/6. Mo firewall cong 8500 (nhan lenh tu WMS/WCS) ===
netsh advfirewall firewall delete rule name="G8ID Open Port 8500" >nul 2>nul
netsh advfirewall firewall add rule name="G8ID Open Port 8500" dir=in action=allow protocol=TCP localport=8500
if errorlevel 1 (echo [LOI] Khong mo duoc firewall. & set ERR=1)

echo.
echo === 4/6. Tat chuot serial (chong Windows nhan nham can la chuot) ===
reg add HKLM\SYSTEM\CurrentControlSet\Services\sermouse /v Start /t REG_DWORD /d 4 /f
if errorlevel 1 (echo [LOI] Khong tat duoc dich vu chuot serial. & set ERR=1)

echo.
echo === 5/6. Tao bieu tuong tren Desktop ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\tao_shortcut.ps1" -Root "%~dp0."
if errorlevel 1 set ERR=1

echo.
echo === 6/6. Dau doc ma vach (tuy chon) ===
echo Neu dau doc DA CAM va config.json da dung cong COM dau doc: bam Y de cai thoi gian quet.
echo Chua cam / chua biet cong COM: bam N (sau nay chay tools\scanner_timeout.bat).
choice /c YN /t 30 /d N /m "Cai thoi gian quet dau doc ngay bay gio"
if errorlevel 2 goto check
python tools\scanner_cmd.py

:check
echo.
echo === Kiem tra may ===
python tools\check_env.py
echo.
echo ---------------------------------------------------------------------------
if "%ERR%"=="1" (
  echo [!] Co buoc bi loi - xem thong bao o tren.
) else (
  echo [OK] Cai dat xong.
)
echo  - Can KHOI DONG LAI MAY mot lan de tat chuot serial co hieu luc.
echo  - Viec lam tay: sua station_id / cong COM / pallet_done_url ^(config.json hoac the Cai dat^),
echo    cai MX Component 5 + Logical Station cho PLC, tat VTP_Induction.exe cu.
echo  - Sau do nhap dup "Chay phan mem" tren Desktop.
echo ---------------------------------------------------------------------------
pause
exit /b 0

:fail
echo.
pause
exit /b 1
