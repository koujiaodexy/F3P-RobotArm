@echo off
setlocal
cd /d "%~dp0"
set "F3P_DISPLAY_PYTHON=%~dp0artifacts\cubes-training-20261028\windows-env\Scripts\python.exe"
if not exist "%F3P_DISPLAY_PYTHON%" (
  echo Project Python environment is missing.
  pause
  exit /b 1
)
echo Restoring F3P desktop connection...
"%F3P_DISPLAY_PYTHON%" -B -X utf8 "%~dp0scripts\reconnect-desktop-mirror.py" --no-browser
if errorlevel 1 (
  echo Check board power and the PC mobile hotspot, then retry.
  pause
  exit /b 1
)
"%F3P_DISPLAY_PYTHON%" -B -X utf8 "%~dp0scripts\reconnect-camera-preview.py" --no-browser
if errorlevel 1 echo Camera preview is unavailable. The control page can still open.
"%F3P_DISPLAY_PYTHON%" -B -X utf8 "%~dp0scripts\restart-desktop-watch.py"
if errorlevel 1 echo Automatic reconnect did not start. Retry this launcher if disconnected.
start "" "http://127.0.0.1:6080/control.html"
endlocal
