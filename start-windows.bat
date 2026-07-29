@echo off
setlocal
where py >nul 2>nul
if errorlevel 1 (
  echo Python is needed first. Download it from https://www.python.org/downloads/
  pause
  exit /b 1
)
echo Starting CV Studio on this computer...
start "CV Studio server" /b py -3 server.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765
echo.
echo Keep this window open while using CV Studio. Close it when you are done.
pause
