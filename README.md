# Spotify Playlist Generator

Ein Python-CLI-Tool, das eine CSV-Datei mit Songs einliest, die passenden Tracks über die Spotify Web API sucht und daraus eine neue Spotify-Playlist im Account des angemeldeten Nutzers erstellt.

## Voraussetzungen

- Python 3.11 oder höher
- Ein Spotify-Account (kostenlos oder Premium)

## Setup

### 1. Spotify-App im Dashboard registrieren

1. Gehe zu https://developer.spotify.com/dashboard
2. Melde dich an oder erstelle einen Account
3. Erstelle eine neue App und akzeptiere die Bedingungen
4. Notiere dir die **Client-ID**
5. Unter "Redirect URIs" füge folgende Adresse ein: `http://127.0.0.1:8888/callback`
6. Speichern und bestätigen

**Wichtig:** Du benötigst nur die Client-ID. Das Tool nutzt den PKCE-Flow (Proof Key for Code Exchange), daher ist kein Client-Secret nötig.

### 2. Umgebungsvariablen konfigurieren

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

## Verwendung

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
| `--limit INT` | Maximale Anzahl Kandidaten pro Suchanfrage | 10 |
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

## Tests

Führe alle Tests offline aus:

```bash
python3 -m pytest tests/ -q
```
