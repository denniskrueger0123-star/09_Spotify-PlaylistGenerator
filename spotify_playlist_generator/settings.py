"""Benutzereinstellungen (settings.json) für den Spotify Playlist Generator."""

import json
import os
from pathlib import Path

from . import i18n

DEFAULT_SETTINGS_PATH = Path.home() / ".spotify_playlist_generator" / "settings.json"
SETTINGS_KEYS = ("client_id", "client_secret", "redirect_uri", "token_path", "language")


def load_settings(path: Path | None = None) -> dict[str, str]:
    """
    Lädt Benutzereinstellungen aus der settings.json-Datei.

    Existiert die Datei nicht oder ist der Inhalt kein gültiges JSON-Objekt,
    wird ein leeres dict zurückgegeben statt einen Fehler auszulösen. Nur
    bekannte Schlüssel (SETTINGS_KEYS) werden übernommen, ihre Werte werden
    in Strings umgewandelt und getrimmt. Leere Werte werden verworfen.
    """
    if path is None:
        path = DEFAULT_SETTINGS_PATH

    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return {}

    if not isinstance(data, dict):
        return {}

    result: dict[str, str] = {}
    for key in SETTINGS_KEYS:
        if key not in data:
            continue
        value = str(data[key]).strip()
        if not value:
            continue
        # Sprache validieren: nur akzeptierte Werte übernehmen
        if key == "language" and value not in i18n.LANGUAGES:
            continue
        result[key] = value

    return result


def save_settings(data: dict[str, str], path: Path | None = None) -> None:
    """
    Speichert Benutzereinstellungen in der settings.json-Datei.

    Nur bekannte Schlüssel (SETTINGS_KEYS) werden gespeichert, ihre Werte
    werden in Strings umgewandelt und getrimmt. Leere Werte werden
    weggelassen. Das Elternverzeichnis wird bei Bedarf angelegt und die
    Datei anschließend (soweit möglich) auf 0600 gesetzt.
    """
    if path is None:
        path = DEFAULT_SETTINGS_PATH

    path.parent.mkdir(parents=True, exist_ok=True)

    to_save: dict[str, str] = {}
    for key in SETTINGS_KEYS:
        if key not in data:
            continue
        value = str(data[key]).strip()
        if value:
            to_save[key] = value

    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def clear_settings(path: Path | None = None) -> None:
    """Löscht die settings.json-Datei, falls vorhanden."""
    if path is None:
        path = DEFAULT_SETTINGS_PATH

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
