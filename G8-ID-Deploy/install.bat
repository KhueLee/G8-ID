@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Cai thu vien Python cho G8 ID ===
where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Python. Cai Python 3.10+ 64-bit va chon "Add python.exe to PATH".
  if not "%1"=="nopause" pause
  exit /b 1
)
python --version
rem Uu tien cai offline tu thu muc wheels (may tram thuong khong co internet).
python -m pip install --no-index --find-links "%~dp0wheels" -r requirements.txt
if errorlevel 1 (
  echo Cai offline khong duoc ^(khac phien ban Python?^) - thu cai qua internet...
  python -m pip install -r requirements.txt
)
python -c "import pymongo, serial, flask, waitress; print('Thu vien OK')"
if errorlevel 1 echo [LOI] Cai thu vien that bai - xem thong bao o tren.
if not "%1"=="nopause" pause
