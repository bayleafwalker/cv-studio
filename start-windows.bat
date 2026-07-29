@echo off
setlocal
where py >nul 2>nul
if errorlevel 1 (
  echo Python is needed first. Download it from https://www.python.org/downloads/
  pause
  exit /b 1
)
echo Preparing the local CV editor. This only happens on the first start.
py -3 -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo The optional PDF helper could not be installed. The editor can still run;
  echo use Download HTML and print it as a PDF from your browser.
)
start "" http://127.0.0.1:8765
py -3 server.py
pause
