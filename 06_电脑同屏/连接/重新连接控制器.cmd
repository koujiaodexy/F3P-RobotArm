@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\manage-pc-board-hotspot.ps1" -Start
if errorlevel 1 goto failed
"artifacts\cubes-training-20261028\windows-env\Scripts\python.exe" -B -X utf8 "scripts\reconnect-desktop-mirror.py" --no-browser %*
if errorlevel 1 goto failed
"artifacts\cubes-training-20261028\windows-env\Scripts\python.exe" -B -X utf8 "scripts\reconnect-camera-preview.py"
if errorlevel 1 goto failed
 powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\start-desktop-watch.ps1"
if errorlevel 1 goto failed
exit /b 0
:failed
pause
exit /b 1
