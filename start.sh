#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  echo "FEHLER: .env fehlt. Starte zuerst ./install_linux.sh."
  exit 1
fi
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python bot.py
else
  exec python3 bot.py
fi
