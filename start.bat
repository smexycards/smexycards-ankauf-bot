@echo off
cd /d %~dp0
if not exist .env (
  echo FEHLER: .env fehlt. Starte zuerst install_windows.bat.
  pause
  exit /b 1
)
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe bot.py
) else (
  python bot.py
)
pause
