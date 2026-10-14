@echo off
chcp 65001 >nul
rem Mo firewall cho cong nhan lenh 8500 (he thong WMS/WCS goi vao). Chay bang quyen Administrator.
rem Khong can "netsh http add urlacl" nhu ban WinForms cu.
net session >nul 2>nul
if errorlevel 1 (
  echo [LOI] Hay bam chuot phai vao file nay va chon "Run as administrator".
  pause
  exit /b 1
)
netsh advfirewall firewall delete rule name="G8ID Open Port 8500" >nul 2>nul
netsh advfirewall firewall add rule name="G8ID Open Port 8500" dir=in action=allow protocol=TCP localport=8500
pause
