@echo off
cd /d "%~dp0"
set MINDTRACE_ENV=development
set MINDTRACE_SHARED_MODE=0
if not exist ".venv\Scripts\python.exe" (
  echo Please create .venv and install requirements.txt first. See README.md.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start_development.ps1" -Port 8501
pause
