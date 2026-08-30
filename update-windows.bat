@echo off
setlocal
cd /d "%~dp0"
echo Getting the newest CV Studio. Your own CV files are kept.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-windows.ps1"
pause
