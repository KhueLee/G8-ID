@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------------
rem Khoi dong lai cac cong USB-SERIAL CH340 (VID 1A86) ma KHONG can go/cai lai driver.
rem Dung khi cong COM bi ket. Chay bang quyen Administrator, sau khi da THOAT phan mem.
rem ---------------------------------------------------------------------------
net session >nul 2>nul
if errorlevel 1 (
  echo [LOI] Hay bam chuot phai vao file nay va chon "Run as administrator".
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\VID_1A86*' };" ^
  "if (-not $d) { Write-Host 'Khong thay thiet bi CH340 nao dang cam.'; exit }" ^
  "foreach ($x in $d) { Write-Host ('Khoi dong lai: ' + $x.FriendlyName + '  [' + $x.InstanceId + ']');" ^
  "  Disable-PnpDevice -InstanceId $x.InstanceId -Confirm:$false; Start-Sleep 2;" ^
  "  Enable-PnpDevice -InstanceId $x.InstanceId -Confirm:$false }" ^
  "Start-Sleep 2; Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\VID_1A86*' } | Format-Table Status, FriendlyName -AutoSize"
pause
