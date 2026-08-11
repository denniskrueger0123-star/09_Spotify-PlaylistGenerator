# Spotify Playlist Generator

Ein Python-Programm, das eine CSV-Datei mit Songs einliest, die passenden Tracks über die Spotify Web API sucht und daraus eine neue Spotify-Playlist im Account des angemeldeten Nutzers erstellt.

Das Tool lässt sich auf zwei Wegen benutzen: über die **grafische Oberfläche** (empfohlen) oder über die **Kommandozeile**.

## Schnellstart (grafische Oberfläche)

- Unter Windows: Doppelklick auf `Spotify-Playlist-Generator.bat`. Der Starter prüft die Python-Installation, richtet beim ersten Mal automatisch eine eigene Arbeitsumgebung ein, installiert die benötigten Pakete und öffnet dann das Fenster. Ab dem zweiten Start geht es sofort los.
- Unter Linux/macOS: `./run_gui.sh`
- Beim allerersten Start: In den Reiter **Einstellungen** wechseln, die eigene **Client ID** eintragen (siehe Abschnitt „Setup"), auf **Einstellungen speichern** klicken.
- Danach im Reiter **Playlist erstellen**: CSV-Datei auswählen, Namen vergeben, auf **Playlist erstellen** klicken. Beim ersten Lauf öffnet sich der Browser zur Anmeldung bei Spotify.
- Die Einstellungen liegen unter `~/.spotify_playlist_generator/settings.json` (unter Windows `C:\Users\<Name>\.spotify_playlist_generator\settings.json`) und nicht im Projektordner — wer das Programm weitergibt, gibt damit keine Zugangsdaten mit.

## Die Oberfläche im Überblick

- **Playlist erstellen** — CSV auswählen (mit sofortiger Rückmeldung, wie viele Songs erkannt wurden), Name und Beschreibung, die Schalter „Öffentlich sichtbar" und „Trockenlauf", aufklappbare erweiterte Einstellungen (Markt, Mindest-Score, Treffer pro Suche), Fortschrittsbalken und Live-Protokoll. Der Lauf lässt sich jederzeit abbrechen.
- **Ergebnis** — Kennzahlen und eine farbige Tabelle (grün gefunden, orange nicht gefunden, rot Fehler). Spalten sind per Klick auf die Überschrift sortierbar, ein Doppelklick öffnet den Song in Spotify. Der Report lässt sich als CSV speichern.
- **Einstellungen** — Client ID, optionales Client Secret, Redirect URI und der Pfad der Token-Datei. Dazu „Anmeldung zurücksetzen", falls du den gespeicherten Zugang löschen willst.

## Voraussetzungen

- Python 3.11 oder höher
- Ein Spotify-Account mit **aktivem Premium-Abo** für den Inhaber der Spotify-App
  (siehe „Was Spotify seit 2026 erlaubt")

## Was Spotify seit 2026 erlaubt

Spotify hat die Web-API im Februar/März 2026 umgestellt. Diese Regeln gelten für
eine App im **Entwicklungsmodus** — also für jede frisch im Dashboard angelegte App:

| Regel | Wert |
|---|---|
| Premium-Abo des App-Inhabers | zwingend erforderlich, sonst antwortet die API mit 403 |
| Zugelassene Nutzerkonten | max. 5, jedes muss im Dashboard unter „User Management" eingetragen sein |
| Suchtreffer pro Anfrage | max. 10 (vorher 50) |
| Client-IDs pro Entwickler-Account | 25, die sich ein gemeinsames Kontingent teilen |
| Titel pro Schreibvorgang in eine Playlist | 100 — das Tool teilt größere Listen automatisch auf |
| Anzahl Playlists / Titel pro Playlist | von der API nicht begrenzt (Spotify-Kontogrenzen gelten weiter, z. B. 10.000 Titel pro Playlist) |

Zusätzlich gilt ein Ratenlimit, das über ein gleitendes 30-Sekunden-Fenster
gerechnet wird. Wird es überschritten, antwortet Spotify mit HTTP 429 und einem
`Retry-After`-Header; das Tool wartet dann automatisch und versucht es erneut.

Endpunkte, die mit der Umstellung weggefallen sind und die dieses Tool deshalb
nicht mehr verwendet:

- `POST /users/{user_id}/playlists` → ersetzt durch `POST /me/playlists`
- `POST /playlists/{id}/tracks` → ersetzt durch `POST /playlists/{id}/items`

**Wenn die App plötzlich keinen einzigen Song mehr findet oder keine Playlist
mehr anlegt**, ist fast immer eine dieser drei Ursachen schuld: kein Premium-Abo
des App-Inhabers, das angemeldete Konto steht nicht in der Nutzerliste der App,
oder das Kontingent ist aufgebraucht. Die App nennt diese Punkte inzwischen
direkt in der Fehlermeldung.

## Setup

### 1. Spotify-App im Dashboard registrieren

1. Gehe zu https://developer.spotify.com/dashboard
2. Melde dich an oder erstelle einen Account
3. Erstelle eine neue App und akzeptiere die Bedingungen
4. Notiere dir die **Client-ID**
5. Unter "Redirect URIs" füge folgende Adresse ein: `http://127.0.0.1:8888/callback`
6. Speichern und bestätigen
7. Unter "User Management" das eigene Spotify-Konto (Name + E-Mail-Adresse des
   Kontos) eintragen — ohne diesen Eintrag lehnt Spotify jede Anfrage mit 403 ab

**Wichtig:** Du benötigst nur die Client-ID. Das Tool nutzt den PKCE-Flow (Proof Key for Code Exchange), daher ist kein Client-Secret nötig.

In der Oberfläche gibt es zusätzlich ein Feld für ein Client Secret. Das ist optional und für den PKCE-Flow nicht nötig — lass es leer, wenn deine Spotify-App keins verlangt.

### 2. Umgebungsvariablen konfigurieren

> Wer die grafische Oberfläche nutzt, braucht diesen Schritt nicht — dort wird die Client-ID im Reiter „Einstellungen" eingetragen. Die folgenden Schritte gelten für die Kommandozeile.

Kopiere die `.env.example` zu `.env` und trage deine Client-ID ein:

```bash
cp .env.example .env
```

Bearbeite `.env`:
```
SPOTIFY_CLIENT_ID=deine_client_id_hier
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

### 3. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

## CSV-Format

Das Tool akzeptiert CSV-Dateien mit folgenden Spalten:

**Titel-Spalte (erforderlich):**
Deutsch: `Titel`, `Songtitel` oder Englisch: `Title`, `Song`, `Track`, `Name`

**Interpret-Spalte (optional):**
Deutsch: `Interpret`, `Künstler`, `Kuenstler` oder Englisch: `Artist`, `Band`, `Performer`

### Beispiel

| title | artist |
|-------|--------|
| Bohemian Rhapsody | Queen |
| Smells Like Teen Spirit | Nirvana |
| Take Five | Dave Brubeck |
| Hallelujah | |
| Blinding Lights | The Weeknd |

**Hinweise:**
- Als Trennzeichen werden automatisch Komma (`,`), Semikolon (`;`) oder Tabulatoren erkannt
- Die Interpret-Spalte ist optional. Fehlt sie, sucht das Tool nur nach dem Titel
- Zeilen mit leerem Titel werden übersprungen

## Verwendung über die Kommandozeile

### Normale Ausführung

```bash
python3 -m spotify_playlist_generator --csv examples/songs.csv --name "Meine neue Playlist"
```

Beim ersten Lauf wird ein Browser-Fenster geöffnet, in dem du dich bei Spotify anmeldest. Der Token wird lokal gespeichert (unter `~/.spotify_playlist_generator/token.json`).

### Mit Beschreibung

```bash
python3 -m spotify_playlist_generator --csv examples/songs.csv --name "Meine neue Playlist" --description "Playlist erstellt mit Spotify Playlist Generator"
```

### Mit Report speichern

```bash
python3 -m spotify_playlist_generator --csv examples/songs.csv --name "Meine Playlist" --report report.csv
```

### Trockenlauf (ohne Playlist zu erstellen)

```bash
python3 -m spotify_playlist_generator --csv examples/songs.csv --name "Test" --dry-run
```

### Öffentliche Playlist

```bash
python3 -m spotify_playlist_generator --csv examples/songs.csv --name "Öffentliche Playlist" --public
```

## CLI-Optionen

| Option | Beschreibung | Default |
|--------|-------------|---------|
| `--csv PATH` | Pfad zur CSV-Datei mit Songs (erforderlich) | - |
| `--name NAME` | Name der zu erstellenden Playlist (erforderlich) | - |
| `--description TEXT` | Beschreibung der Playlist | leer |
| `--public` | Playlist als öffentlich erstellen | privat |
| `--report PATH` | Pfad zur CSV-Datei für den Report | nicht gespeichert |
| `--market CODE` | Spotify-Markt-Code (z. B. `DE`, `US`) | - |
| `--min-score FLOAT` | Minimaler Match-Score (0.0–1.0) | 0.6 |
| `--limit INT` | Maximale Anzahl Kandidaten pro Suchanfrage (Spotify erlaubt höchstens 10) | 10 |
| `--dry-run` | Simuliert Suche, erstellt keine Playlist | aus |
| `--env-file PATH` | Pfad zur `.env`-Datei | `.env` |
| `--token-path PATH` | Pfad zur Token-Cache-Datei | `~/.spotify_playlist_generator/token.json` |

## Nicht gefundene Songs

Wenn ein Song nicht in Spotify gefunden wird, bricht das Tool **nicht** ab. Stattdessen wird der Song als `not_found` protokolliert und die Verarbeitung setzt sich fort. Zeilen mit leerem Titel werden nicht gesucht und erscheinen im Report mit status `error` und dem Grund „Kein Titel in dieser Zeile".

### Report-Spalten

Wenn `--report` gesetzt ist, wird eine CSV-Datei mit folgenden Spalten geschrieben:

- `row` — Zeilennummer in der Datei (Kopfzeile = Zeile 1, erste Datenzeile = Zeile 2)
- `title` — Ursprünglicher Songtitel
- `artist` — Ursprünglicher Künstler
- `status` — `found`, `not_found` oder `error`
- `reason` — Grund bei Fehler oder nicht gefunden
- `matched_title` — Titel des gefundenen Spotify-Tracks (leer bei Fehler)
- `matched_artists` — Künstler des gefundenen Spotify-Tracks (leer bei Fehler)
- `spotify_url` — Link zum gefundenen Track auf Spotify (leer bei Fehler)
- `score` — Match-Score zwischen 0.0 und 1.0 (0.0 bei Fehler)

### min-score Parameter

Der `--min-score`-Parameter steuert die Akzeptanzqualität des Matching-Algorithmus:

- **Höherer Wert (z. B. 0.8)**: Nur sehr genaue Treffer werden akzeptiert, aber mehr Songs gehen als „nicht gefunden" ein
- **Niedrigerer Wert (z. B. 0.4)**: Auch ungenaue Treffer werden akzeptiert, aber das Risiko von falschen Matches steigt

Standardwert: `0.6` (gutes Gleichgewicht)

## Exit-Codes

Das Tool gibt folgende Exit-Codes zurück:

| Code | Bedeutung |
|------|-----------|
| `0` | Alle Songs gefunden (bei --dry-run wird dabei keine Playlist erstellt) |
| `1` | Mindestens ein Song nicht gefunden oder fehlerhaft, Lauf ist aber durchgelaufen |
| `2` | Abbruch durch einen Fehler: Konfiguration, CSV-Datei, Anmeldung oder Spotify-API |
| `130` | Vom Benutzer abgebrochen (Ctrl+C) |

## Lizenzschlüssel

Die App prüft ihre Lizenz offline über den geteilten KDS-Lizenzmechanismus
(`kds_lizenz/`, identisch in allen Apps von Krüger Digital Solutions). Es gibt
keinen Server und keinen Netzzugang für die Prüfung — Ablaufdatum und
Kundenname stecken im Schlüssel selbst, eine Unterschrift darüber beweist
ihre Echtheit.

Ohne gültige Lizenz ist der gesamte Suchlauf gesperrt (auch der Trockenlauf) —
das ist die eine Kernfunktion, für die bezahlt wird. Die App bleibt ansonsten
bedienbar.

### Wie der Zustand sichtbar wird

Der Lizenzzustand steht dauerhaft **oben rechts in der Kopfzeile**, auf jedem
Reiter — nicht erst in einer Meldung, wenn jemand auf „Playlist erstellen"
drückt. Ist der Lauf gesperrt, steht zusätzlich ein Hinweisbalken über den
Karten im Reiter **Playlist erstellen**, und der Startknopf ist ausgegraut.

Ab dreißig Tagen vor Ablauf wechselt die Kopfzeile von „Lizenziert bis …" auf
„Lizenz läuft in N Tagen ab", damit eine Verlängerung nicht am Ablauftag
überrascht.

### Wege zum Eingabedialog

Vier, alle zum selben Dialog:

- Klick auf die Zustandsanzeige **oben rechts in der Kopfzeile**
- Knopf **Lizenz eingeben …** im Hinweisbalken (Reiter Playlist erstellen)
- Knopf **Lizenz verwalten …** im Reiter **Über**
- Menüeintrag **Lizenz …** in der Menüleiste

Der Menüeintrag sitzt bewusst auf oberster Ebene und nicht unter „Hilfe": diesen
Namen trägt bereits ein Reiter, in dem nichts über Lizenzen steht.

### Einrichtung

- **App-spezifische Daten:** stehen in `spotify_playlist_generator/lizenz_konfig.py`
  (Produktname, APPDATA-Ordner, Vorsilbe, App-Schlüssel).
- **Schlüssel ausstellen:** geschieht zentral im KDS Lizenzmanager, nicht in
  diesem Repository. Der App-Schlüssel dieses Produkts wird dort einmalig in
  `APP_SCHLUESSEL` in `lizenz_konfig.py` eingetragen.
- **Solange `APP_SCHLUESSEL` leer ist:** ist die App absichtlich für jeden
  Schlüssel gesperrt und zeigt eine eigene Meldung dafür — eine ohne
  App-Schlüssel gebaute Auslieferung soll unbrauchbar sein, nicht unbewacht.

## Hilfe und Über

Die grafische Oberfläche hat zwei zusätzliche Reiter:

- **Hilfe** — Umfangreiche Dokumentation in deutsch oder English, mit
  Sprachumschalter oben rechts. Enthält auch einen Abschnitt zur Lizenz.
- **Über** — Firmenlogo, Versionsnummer, Entwicklerinformation und
  Lizenzstatus, mit Knopf zum Öffnen des Lizenzdialogs.

Zwei Bilddateien werden aus `assets/` geladen: `kds-logo.png` (vollständiges
Logo, im Reiter Über) und `kds-mark.png` (kompaktes Zeichen, in der Kopfzeile).
Beide sind freiwillig — fehlt eine, tritt ein Ersatz an ihre Stelle und die
Anwendung startet normal. Einzelheiten in `assets/README.md`.

## Tests

Führe alle Tests offline aus:

```bash
python3 -m pytest tests/ -q
```

Die Tests der Oberfläche brauchen `tkinter` und eine Anzeige. Fehlt beides, werden sie automatisch übersprungen, der Rest läuft normal durch.
