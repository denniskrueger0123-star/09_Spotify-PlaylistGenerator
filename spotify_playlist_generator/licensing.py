"""
Modul zur Prüfung signierter Lizenzschlüssel.

Ein Lizenzschlüssel hat das Format KDS1.<payload>.<signature>.
Die Prüfung liefert nur einen Status — Sperren geschehen später.
"""

import base64
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Konstanten für Schlüsselformat und Zustände
KEY_PREFIX = "KDS1"
PUBLIC_KEY_HEX = ""   # Leer = noch kein Schlüsselpaar erzeugt. Siehe licensetool.py

STATE_MISSING   = "missing"     # kein Schlüssel hinterlegt
STATE_VALID     = "valid"
STATE_EXPIRED   = "expired"
STATE_INVALID   = "invalid"     # Format kaputt oder Signatur falsch
STATE_UNCHECKED = "unchecked"   # PUBLIC_KEY_HEX leer, Prüfung nicht möglich
STATE_CLOCK     = "clock"       # Systemuhr wurde zurückgedreht

DEFAULT_LICENSE_PATH = Path.home() / ".spotify_playlist_generator" / "license.json"


class LicenseError(Exception):
    """Fehler beim Parsen oder Prüfen eines Lizenzschlüssels."""
    pass


@dataclass(frozen=True)
class License:
    """Lizenzinformation aus einem gültigen Schlüssel."""
    name: str
    key_id: str
    issued: date
    expires: date | None   # None = unbefristet


@dataclass(frozen=True)
class LicenseStatus:
    """Ergebnis einer Lizenzprüfung."""
    state: str
    license: License | None = None
    days_left: int | None = None      # None bei unbefristet oder ohne Lizenz
    detail: str = ""                  # technische Zusatzinfo, z.B. Parse-Fehler


def parse_key(text: str) -> License:
    """
    Zerlegt und prüft einen Lizenzschlüssel.

    Format: KDS1.<payload>.<signature>
    - payload: base64url ohne Polsterung über JSON {n, id, i, e}
    - signature: Ed25519-Signatur über die Payload-Bytes

    Wirft LicenseError bei:
    - falsches Präfix
    - kaputtem base64
    - ungültigem JSON
    - fehlenden Pflichtfeldern
    - unlesbarem Datum
    - falscher Signatur (wenn PUBLIC_KEY_HEX gesetzt ist)

    Leerzeichen und Zeilenumbrüche werden vorher entfernt, damit
    ein aus E-Mail kopierter Schlüssel funktioniert.
    """
    # Leerzeichen und Zeilenumbrüche entfernen
    text = text.strip()
    text = "".join(text.split())

    # Präfix prüfen
    if not text.startswith(KEY_PREFIX + "."):
        raise LicenseError(f"Schlüssel muss mit {KEY_PREFIX}. beginnen")

    # Teile zerlegen: KDS1.payload.signature
    parts = text.split(".")
    if len(parts) != 3:
        raise LicenseError("Schlüssel muss aus genau drei Teilen bestehen: PREFIX.payload.signature")

    prefix, payload_b64, signature_b64 = parts

    # base64url dekodieren (ohne Polsterung)
    # base64url nutzt - statt + und _ statt /
    try:
        # base64url ohne Polsterung: Padding hinzufügen vor Dekodierung
        payload_b64_padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64_padded)
    except Exception as e:
        raise LicenseError(f"Payload base64 kaputt: {e}")

    try:
        signature_b64_padded = signature_b64 + "=" * (4 - len(signature_b64) % 4)
        signature_bytes = base64.urlsafe_b64decode(signature_b64_padded)
    except Exception as e:
        raise LicenseError(f"Signatur base64 kaputt: {e}")

    # JSON parsen
    try:
        payload_dict = json.loads(payload_bytes)
    except json.JSONDecodeError as e:
        raise LicenseError(f"Payload JSON ungültig: {e}")

    # Pflichtfelder prüfen
    if "n" not in payload_dict:
        raise LicenseError("Feld 'n' (Name) fehlt")
    if "id" not in payload_dict:
        raise LicenseError("Feld 'id' (Kennung) fehlt")
    if "i" not in payload_dict:
        raise LicenseError("Feld 'i' (Ausstellungsdatum) fehlt")

    name = str(payload_dict["n"])
    key_id = str(payload_dict["id"])

    # Daten parsen: YYYY-MM-DD
    try:
        issued = date.fromisoformat(payload_dict["i"])
    except (ValueError, TypeError) as e:
        raise LicenseError(f"Ausstellungsdatum ungültig: {e}")

    expires = None
    if payload_dict.get("e") is not None:
        try:
            expires = date.fromisoformat(payload_dict["e"])
        except (ValueError, TypeError) as e:
            raise LicenseError(f"Ablaufdatum ungültig: {e}")

    # Signatur prüfen (wenn PUBLIC_KEY_HEX gesetzt ist)
    if PUBLIC_KEY_HEX:
        _verify_signature(payload_bytes, signature_bytes)

    return License(name=name, key_id=key_id, issued=issued, expires=expires)


def _verify_signature(payload_bytes: bytes, signature_bytes: bytes) -> None:
    """
    Prüft Ed25519-Signatur. Wirft LicenseError bei falscher Signatur.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:
        raise LicenseError("cryptography nicht installiert")

    try:
        # Öffentlichen Schlüssel aus hex-String laden
        public_key_bytes = bytes.fromhex(PUBLIC_KEY_HEX)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)

        # Signatur verprüfen
        public_key.verify(signature_bytes, payload_bytes)
    except Exception as e:
        raise LicenseError(f"Signatur ungültig: {e}")


def check(key_text: str | None, now: date, last_seen: date | None = None) -> LicenseStatus:
    """
    Prüft einen Lizenzschlüssel. Reihenfolge:

    1. key_text leer/None → STATE_MISSING
    2. parse_key wirft → STATE_INVALID mit Fehlertext
    3. last_seen gesetzt und now < last_seen → STATE_CLOCK
    4. PUBLIC_KEY_HEX leer → STATE_UNCHECKED
    5. expires gesetzt und now > expires → STATE_EXPIRED
    6. sonst STATE_VALID

    days_left wird gesetzt, wenn expires vorhanden ist.
    """
    # 1. Schlüssel fehlt
    if not key_text:
        return LicenseStatus(state=STATE_MISSING)

    # 2. Schlüssel parsen
    try:
        license = parse_key(key_text)
    except LicenseError as e:
        return LicenseStatus(state=STATE_INVALID, detail=str(e))

    # 3. Systemuhr wurde zurückgedreht (Vergleich mit letzter Beobachtung)
    if last_seen is not None and now < last_seen:
        return LicenseStatus(state=STATE_CLOCK, license=license)

    # 4. Öffentlicher Schlüssel nicht gesetzt — Prüfung nicht möglich
    if not PUBLIC_KEY_HEX:
        days_left = None
        if license.expires is not None:
            days_left = (license.expires - now).days
        return LicenseStatus(state=STATE_UNCHECKED, license=license, days_left=days_left)

    # 5. Licenz abgelaufen
    if license.expires is not None and now > license.expires:
        days_left = (license.expires - now).days
        return LicenseStatus(state=STATE_EXPIRED, license=license, days_left=days_left)

    # 6. Licenz gültig
    days_left = None
    if license.expires is not None:
        days_left = (license.expires - now).days
    return LicenseStatus(state=STATE_VALID, license=license, days_left=days_left)


def load_state(path: Path | None = None) -> dict:
    """
    Liest `~/.spotify_playlist_generator/license.json`.

    Bei fehlender Datei, kaputtem JSON oder Lesefehler wird ein leeres
    dict zurückgegeben. Es wird niemals eine Ausnahme nach außen gelassen.

    Erwartete Felder: `key` (String), `last_seen` (YYYY-MM-DD).
    """
    if path is None:
        path = DEFAULT_LICENSE_PATH

    try:
        if not path.exists():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        # Datei nicht lesbar oder JSON kaputt → leeres dict
        return {}


def save_state(key: str, last_seen: date, path: Path | None = None) -> None:
    """
    Legt das Elternverzeichnis an und schreibt den Lizenzstatus als JSON.
    Setzt anschließend os.chmod(path, 0o600) in try/except OSError.
    """
    if path is None:
        path = DEFAULT_LICENSE_PATH

    # Elternverzeichnis anlegen
    path.parent.mkdir(parents=True, exist_ok=True)

    # JSON schreiben
    data = {
        "key": key,
        "last_seen": last_seen.isoformat(),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Dateirechte setzen: nur Besitzer lesen/schreiben
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Fehler beim chmod ignorieren
        pass
