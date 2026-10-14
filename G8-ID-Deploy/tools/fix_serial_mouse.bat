@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------------
rem Chay MOT LAN tren moi may tram, bang quyen Administrator, roi khoi dong lai may.
rem
rem Can dien tu phat du lieu lien tuc. Luc Windows khoi dong, no co the nhan nham
rem luong du lieu do la "chuot serial" (Microsoft Serial BallPoint) va chiem luon
rem cong COM cua cap CH340 -> phan mem khong mo duoc cong, phai go/cai lai driver.
rem File nay tat dich vu chuot serial (sermouse). Khong anh huong chuot USB.
rem
rem Hoan tac:  reg add HKLM\SYSTEM\CurrentControlSet\Services\sermouse /v Start /t REG_DWORD /d 3 /f
rem ---------------------------------------------------------------------------
net session >nul 2>nul
if errorlevel 1 (
  echo [LOI] Hay bam chuot phai vao file nay va chon "Run as administrator".
  pause
  exit /b 1
)
echo Gia tri hien tai:
reg query HKLM\SYSTEM\CurrentControlSet\Services\sermouse /v Start
reg add HKLM\SYSTEM\CurrentControlSet\Services\sermouse /v Start /t REG_DWORD /d 4 /f
echo.
echo Da tat dich vu chuot serial. HAY KHOI DONG LAI MAY de co hieu luc.
pause
