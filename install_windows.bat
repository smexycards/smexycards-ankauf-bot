@echo off
cd /d %~dp0

echo [1/4] Python-Umgebung wird erstellt...
py -m venv .venv
if errorlevel 1 (
  echo FEHLER: Python wurde nicht gefunden. Installiere Python 3.11+ und aktiviere "Add Python to PATH".
  pause
  exit /b 1
)

echo [2/4] Abhaengigkeiten werden installiert...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo FEHLER beim Installieren der Pakete.
  pause
  exit /b 1
)

echo [3/4] Konfiguration wird vorbereitet...
if not exist .env copy .env.example .env >nul

echo [4/4] Fertig.
echo.
echo Oeffne jetzt die Datei .env und trage deinen DISCORD_TOKEN ein.
echo Danach kannst du start.bat ausfuehren.
pause
