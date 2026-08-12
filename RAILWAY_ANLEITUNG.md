# Smexycards Ankauf-Bot – 24/7 auf Railway

Diese Version ist für Railway vorbereitet.

## Wichtig

- Die lokale `.env` NICHT auf GitHub hochladen.
- Den Discord-Token auf Railway unter **Variables** eintragen.
- Für die SQLite-Datenbank ein Railway-Volume anlegen.
- Volume auf `/data` mounten und `DATA_DIR=/data` setzen.

## Railway-Variablen

```text
DISCORD_TOKEN=DEIN_DISCORD_BOT_TOKEN
GUILD_ID=DEINE_DISCORD_SERVER_ID
BUYER_NAME=Chris Schneider
BUYER_STREET=Oberfrohnaer Straße 31
BUYER_CITY=09117 Chemnitz
TIMEZONE=Europe/Berlin
DATA_DIR=/data
```

## Start

Railway liest `railway.json` und startet automatisch:

```text
python bot.py
```

## Persistenter Speicher

Erstelle in Railway am Bot-Service ein **Volume** mit dem Mount-Pfad:

```text
/data
```

Dadurch bleiben `ankauf.sqlite3` und erzeugte PDFs auch nach einem neuen Deployment erhalten.

## Bestehende lokale Daten

Wenn der Bot bereits produktive Tickets/Deals in der lokalen Datei
`data/ankauf.sqlite3` enthält, sollte diese Datenbank vor dem endgültigen Umstieg
auf das Railway-Volume übertragen werden. Für einen frischen Start ist das nicht nötig.
