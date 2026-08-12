from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)

BUYER_NAME = os.getenv("BUYER_NAME", "Chris Schneider").strip()
BUYER_STREET = os.getenv("BUYER_STREET", "Oberfrohnaer Straße 31").strip()
BUYER_CITY = os.getenv("BUYER_CITY", "09117 Chemnitz").strip()

TIMEZONE_NAME = os.getenv("TIMEZONE", "Europe/Berlin").strip() or "Europe/Berlin"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

# Lokal wird weiterhin ./data verwendet. Auf Railway kann DATA_DIR auf ein
# persistentes Volume (z. B. /data) zeigen, damit Daten Deployments überleben.
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).expanduser()
DB_PATH = DATA_DIR / "ankauf.sqlite3"
GENERATED_DIR = DATA_DIR / "generated"
BACKUP_DIR = DATA_DIR / "backups"
EXPORT_DIR = DATA_DIR / "exports"
PDF_TEMPLATE = BASE_DIR / "assets" / "Smexycards_Privates_Ankaufsformular_mit_Kaeuferdaten.pdf"

BRAND_COLOR = 0x182A43


def validate_config() -> None:
    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN fehlt. Kopiere .env.example nach .env und trage deinen Bot-Token ein."
        )
    if not PDF_TEMPLATE.exists():
        raise RuntimeError(f"PDF-Vorlage fehlt: {PDF_TEMPLATE}")
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
