#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
fi
echo "Fertig. Trage nun DISCORD_TOKEN in .env ein und starte mit ./start.sh"
