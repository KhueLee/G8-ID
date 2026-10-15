@echo off
chcp 65001 >nul
title PHAN MEM MO PHONG DINH DANH - CHI CHAY THU (dong truoc khi ve AUTO)
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
if not exist data mkdir data

rem Cua so nay giu file data\simulator_bat.lock suot thoi gian mo.
rem Phan mem chinh dua vao do de biet "file bat mo phong da dong chua" truoc khi cho ve AUTO.
(
  python tools\banner.py sim
  python simulator\sim_main.py
  echo.
  echo Cong cu mo phong da dung. HAY DONG CUA SO NAY truoc khi chuyen phan mem chinh ve AUTO.
  pause
) 9>"data\simulator_bat.lock"
del "data\simulator_bat.lock" >nul 2>nul
