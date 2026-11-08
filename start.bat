@echo off
cd /d "%~dp0"
set MINDTRACE_ENV=development
set MINDTRACE_SHARED_MODE=0
if not exist ".venv\Scripts\python.exe" (
  echo Please create .venv and install requirements.txt first. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
pause
