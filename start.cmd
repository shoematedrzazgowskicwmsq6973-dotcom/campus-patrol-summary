@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_local.ps1"
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import tkinter, rapidocr, onnxruntime, PIL, lxml" >nul 2>&1
if errorlevel 1 (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_local.ps1"
  if errorlevel 1 goto failed
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
exit /b 0
:failed
echo.
echo Could not start. See the error above or startup-error.log.
pause
exit /b 1
