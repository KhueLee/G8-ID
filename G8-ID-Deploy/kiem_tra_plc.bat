@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------------
rem Chan doan ket noi PLC (cap CH340 + MX Component): tu do cong, chay test, xuat bao cao
rem logs\kiem_tra_plc-*.txt. THOAT G8 ID truoc. Nen chuot phai -> Run as administrator
rem (de thu tat / bat lai CH340). Tham so: --giay 900 (chay ben lau hon), --khong-reset.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"
set PYTHONUTF8=1
python tools\plc_diag.py %*
echo.
pause
