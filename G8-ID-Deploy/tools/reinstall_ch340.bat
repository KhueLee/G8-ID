@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------------
rem GO va CAI LAI driver CH340 (CH341SER 3.4) cho moi cap USB-SERIAL CH340 dang cam
rem (can, dau doc, cap PLC). Thay cho viec tu go / cai lai bang tay sau moi lan bat may.
rem Chay bang quyen Administrator, sau khi da THOAT G8 ID. Log: logs\reinstall_ch340-*.log
rem Chi can khoi dong lai cong (khong go driver): dung restart_ch340.bat.
rem ---------------------------------------------------------------------------
net session >nul 2>nul
if errorlevel 1 (
  echo [LOI] Hay bam chuot phai vao file nay va chon "Run as administrator".
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0reinstall_ch340.ps1" -Root "%~dp0.."
echo.
pause
