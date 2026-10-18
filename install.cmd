@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_local.ps1"
if errorlevel 1 (
  echo Installation failed. See the error above.
  pause
  exit /b 1
)
pause
