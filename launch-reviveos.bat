@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run the setup commands in README.md once before using this launcher.
  pause
  exit /b 1
)
echo ReviveOS will open in your browser. Press Ctrl+C here to stop.
".venv\Scripts\python.exe" launch.py
pause
