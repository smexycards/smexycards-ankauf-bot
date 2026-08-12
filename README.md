# Smexycards Discord Ankauf-Bot v1.3

Komplettes Discord-Ticketsystem für den Ankauf von Trading Cards – inklusive Einzelkarten, Sammlungen, Angeboten, Deal-Abschluss, automatischem Ankaufsformular und Versandfreigabe.

## Funktionen

- Öffentliches, überarbeitetes Smexycards-Ankauf-Panel mit drei Buttons:
  - **🃏 Einzelkarte verkaufen**
  - **📦 Mehrere Karten / Sammlung**
  - **ℹ️ So läuft der Ankauf**
- Private Ticket-Channels, nur sichtbar für Verkäufer + Ankauf-Team.
- Einzelkarten-Formular mit Spieler/Karte, Set/Jahr, Parallel, Zustand/Grading und Preisvorstellung.
- Sammlungs-Formular ohne nervige Einzelkartenerfassung: Anzahl, Kartenart, Raw/Graded, Gesamtpreis und Kurzbeschreibung.
- Fotos, Excel-, PDF- oder Kartenlisten können anschließend normal in den Ticket-Channel hochgeladen werden.
- Mitarbeiter-Buttons:
  - **💶 Angebot machen**
  - **✅ Deal abschließen**
  - **❌ Ablehnen**
  - **📦 Versand freigeben**
  - **🔒 Ticket schließen**
- Verkäufer kann ein Angebot direkt mit Button **annehmen oder ablehnen**.
- Bei einem Deal wird das originale Smexycards-Ankaufsformular direkt ins Ticket geschickt.
- Verkäufer gibt Name/Adresse anschließend in einem Discord-Formular ein.
- Der Bot erzeugt automatisch ein **vorausgefülltes PDF** mit:
  - Verkäuferdaten
  - Belegdatum
  - Ankaufstyp
  - zusammengefasster Karte/Sammlung
  - vereinbartem Ankaufspreis
  - Zahlungsart
  - Discord-Ticketnummer
- Käufer-/Versanddaten sind bereits auf **Chris Schneider, Oberfrohnaer Straße 31, 09117 Chemnitz** voreingestellt.
- Geschlossene Tickets werden in ein Archiv verschoben und für den Verkäufer schreibgeschützt.
- SQLite speichert Ticketstatus und Angebote, damit die wichtigsten Daten Neustarts überleben.
- Buttons sind als **persistente Views** angelegt und funktionieren auch nach einem Bot-Neustart weiter.

## 1. Voraussetzungen

- Python 3.11 oder neuer empfohlen
- Ein Discord-Server, auf dem du `Server verwalten` darfst
- Eine eigene Discord Application / einen Bot

## 2. Bot im Discord Developer Portal anlegen

1. Öffne das **Discord Developer Portal**.
2. Erstelle eine neue Application, z. B. `Smexycards Ankauf`.
3. Gehe zu **Bot** und erstelle/verwende den Bot-User.
4. Kopiere den Bot-Token. **Den Token niemals öffentlich posten.**
5. Unter Installation/OAuth2 den Bot auf deinen Server einladen.

Der Bot benötigt für dieses Projekt mindestens diese Server-/Channel-Rechte:

- Kanäle ansehen
- Nachrichten senden
- Nachrichtenverlauf lesen
- Links einbetten
- Dateien anhängen
- **Kanäle verwalten**
- **Nachrichten verwalten** (für das Ankauf-Team-Handling sinnvoll)

Für Slash-Commands muss die App außerdem mit dem Scope `applications.commands` installiert sein.

Ein `Message Content Intent` ist für diesen Bot nicht nötig.

## 3. Installation auf Windows

### Einfachste Variante

1. Doppelklicke **`install_windows.bat`**. Das Script erstellt die Python-Umgebung und installiert alle benötigten Pakete.
2. Öffne danach die erzeugte Datei **`.env`**.
3. Trage bei `DISCORD_TOKEN=` deinen Bot-Token ein.
4. Optional deine Server-ID bei `GUILD_ID=` eintragen. Discord-Entwicklermodus aktivieren → Rechtsklick auf Server → `Server-ID kopieren`.
5. Starte den Bot mit **`start.bat`**.

### Manuell

Im Bot-Ordner eine Eingabeaufforderung/PowerShell öffnen:

```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Danach `.env` ausfüllen und `python bot.py` starten.

## 4. Ersteinrichtung auf Discord

Erstelle zuerst eine Rolle, z. B. **Ankauf-Team**, und gib sie dir bzw. deinen Mitarbeitern.

Danach im gewünschten öffentlichen Ankauf-Kanal:

```text
/ankauf_setup
```

Discord lässt dich direkt auswählen:

- `staff_rolle` → z. B. **Ankauf-Team**
- `ticket_kategorie` → optional; leer lassen, dann erstellt der Bot automatisch **💰 SMEXYCARDS ANKAUF**
- `log_kanal` → optional für interne Logs

Der Bot erstellt außerdem automatisch **📁 ANKAUF ARCHIV** und postet das fertige Verkaufspanel in den aktuellen Kanal.

## 5. Verkäufer-Ablauf

### Einzelkarte

Verkäufer klickt **Einzelkarte verkaufen** → füllt ein kleines Formular aus → privates Ticket `ankauf-0001` entsteht → Fotos werden direkt im Ticket hochgeladen.

### Mehrere Karten / Sammlung

Verkäufer klickt **Mehrere Karten / Sammlung** → gibt nur grobe Angaben an → privates Ticket entsteht → Übersichtsfotos oder eine vorhandene Kartenliste können hochgeladen werden.

Es ist bewusst **nicht nötig, jede Karte einzeln einzutragen**.

## 6. Deal-Ablauf

### Variante A: Smexycards macht ein Angebot

Mitarbeiter klickt **💶 Angebot machen** → Preis eingeben → Verkäufer bekommt Buttons **Annehmen** / **Ablehnen**.

Bei Annahme wird der Deal automatisch gespeichert und das Ankaufsformular ins Ticket geschickt.

### Variante B: Deal wurde im Chat ausgehandelt

Mitarbeiter klickt **✅ Deal abschließen** und trägt ein:

- vereinbarter Ankaufspreis
- Auszahlung, z. B. PayPal / Überweisung / Barzahlung
- kurze Beschreibung des Ankaufs

Danach bekommt der Verkäufer das originale Blanko-PDF und den Button **Verkäuferdaten für PDF**.

Der Verkäufer gibt nur noch Name, Straße, PLZ/Ort und optional Telefon/E-Mail ein. Anschließend erstellt der Bot automatisch das vorausgefüllte PDF. Die Unterschriftsfelder bleiben frei, damit beide Parteien unterschreiben können.

## 7. Versand

Wenn Formular und Deal passen, klickt ein Mitarbeiter **📦 Versand freigeben**.

Der Bot sendet dem Verkäufer im privaten Ticket automatisch:

```text
Chris Schneider
Oberfrohnaer Straße 31
09117 Chemnitz
```

plus Ticketnummer und Hinweis zur Sendungsnummer.

## 8. Tickets schließen

Mit **🔒 Ticket schließen** wird:

- der Ticketstatus gespeichert,
- der Channel zu `geschlossen-0001` umbenannt,
- in **📁 ANKAUF ARCHIV** verschoben,
- für den Verkäufer schreibgeschützt.

Der Verkäufer kann den bisherigen Verlauf weiterhin lesen.

## 9. Dateien / Daten

- Datenbank: `data/ankauf.sqlite3`
- Automatisch erzeugte PDFs: `data/generated/`
- Originales Ankaufformular: `assets/Smexycards_Privates_Ankaufsformular_mit_Kaeuferdaten.pdf`

Die Verkäuferadresse wird erst **nach einem Deal** abgefragt und lokal in der SQLite-Datei gespeichert. Sorge dafür, dass nur du bzw. dein Server/Host Zugriff auf den Bot-Ordner hat.

## 10. Nützliche Slash-Commands

- `/ankauf_setup` – System erstmals einrichten / Konfiguration neu setzen
- `/ankauf_panel` – Verkaufspanel erneut posten
- `/ankauf_panel_update` – bereits gespeichertes Panel direkt auf das aktuelle Design aktualisieren
- `/ankauf_status` – Status des aktuellen Tickets anzeigen

## Hosting

Der Bot muss dauerhaft laufen, wenn er rund um die Uhr Tickets annehmen soll. Lokal auf deinem PC funktioniert er nur, solange das Programm läuft. Für 24/7-Betrieb kannst du ihn später auf einen kleinen VPS oder einen Bot-/Python-Host legen.

## Wichtig

`DISCORD_TOKEN` niemals in Discord, GitHub oder Screenshots veröffentlichen. Falls der Token einmal öffentlich wurde, im Developer Portal sofort regenerieren.
