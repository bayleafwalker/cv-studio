@echo off
setlocal
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python is needed first. Download it from https://www.python.org/downloads/
  echo During installation, tick "Add Python to PATH". Then double-click this file again.
  pause
  exit /b 1
)
echo Starting CV Studio on this computer...
start "CV Studio server" /b %PY% server.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765
echo.
echo Keep this window open while using CV Studio. Close it when you are done.
echo If the browser did not open, go to http://127.0.0.1:8765 yourself.
echo To get the newest version later, double-click update-windows.bat.
pause
