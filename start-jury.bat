@echo off
rem Jury one-click launch: installs deps, opens browser, starts server.
cd /d "%~dp0medi-ai"
where python >nul 2>nul
if errorlevel 1 (
  echo [MediAI] Need Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)
echo [MediAI] Installing dependencies...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [MediAI] pip install failed. Check internet and retry.
  pause
  exit /b 1
)
echo [MediAI-REWORK] Starting server on http://127.0.0.1:8001 ...
start "" http://127.0.0.1:8001
python -m uvicorn app.main:app --port 8001
pause
