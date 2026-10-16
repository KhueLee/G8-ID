@echo off
chcp 65001 >nul
title CAP NHAT PHAN MEM - G8 ID
cd /d "%~dp0"
echo === Cap nhat phan mem G8 ID (git pull) ===
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Git. Cai Git for Windows roi chay lai.
  goto fail
)

rem Phan mem dang chay (cong 8600 dang mo) thi phai thoat truoc: cap nhat xong can chay lai moi co hieu luc.
netstat -ano | findstr /r /c:":8600 .*LISTENING" >nul
if not errorlevel 1 (
  echo [DUNG] Phan mem dinh danh dang chay.
  echo        Bam Dung, vao the Cai dat - Thoat phan mem, roi chay lai update.bat.
  goto fail
)

for /f %%i in ('git rev-parse HEAD') do set OLD=%%i
echo Ban hien tai:
git log -1 --format="  %%h  %%cd  %%s" --date=format:"%%d/%%m/%%Y %%H:%%M"
echo.
echo Dang tai ban moi...
git pull --ff-only
if errorlevel 1 (
  echo.
  echo [LOI] Khong cap nhat duoc. Kiem tra mang / tai khoan GitHub.
  echo       Neu bao co file da sua tren may tram, chup man hinh gui ky thuat phan mem:
  git status --short
  goto fail
)
for /f %%i in ('git rev-parse HEAD') do set NEW=%%i
echo.
if "%OLD%"=="%NEW%" (
  echo Da la ban moi nhat - khong co gi thay doi.
  goto done
)
echo Cac thay doi vua tai ve:
git log --format="  %%h  %%s" %OLD%..%NEW%
git diff --quiet %OLD% %NEW% -- requirements.txt
if errorlevel 1 (
  echo.
  echo Danh sach thu vien thay doi - dang chay install.bat ...
  call "%~dp0install.bat" nopause
)
echo.
echo [OK] Da cap nhat. Nhap dup "Chay phan mem" de chay ban moi.

:done
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
