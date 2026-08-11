"""Der Hauptschluessel - nur auf dem Rechner des Entwicklers.

Aus dem Hauptschluessel wird fuer jede App ein eigener App-Schluessel
abgeleitet. Nur der App-Schluessel wandert in die ausgelieferte EXE; der
Hauptschluessel selbst verlaesst diesen Rechner nie.

Warum er NICHT im Projektordner liegt
-------------------------------------
Alles im Projektordner landet frueher oder spaeter in einem git-Verlauf und
damit womoeglich in einem oeffentlichen Repository - und aus einem git-Verlauf
bekommt man eine Datei nicht wieder heraus, indem man sie loescht. Der
Hauptschluessel liegt deshalb in %APPDATA%, wo er weder eingecheckt noch
versehentlich mit einem ZIP weitergegeben wird.

BITTE SICHERN
-------------
Geht die Datei verloren, lassen sich fuer bestehende Apps keine neuen
Schluessel mehr ausstellen: die App-Schluessel in den ausgelieferten EXEs sind
dann nicht mehr nachzubilden. Ausgelieferte Programme laufen zwar weiter, aber
jede Verlaengerung erfordert eine neue EXE. Eine Kopie an einem sicheren Ort
(Passwortmanager, verschluesselter Stick) erspart diesen Fall.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

# Laenge des Hauptschluessels. 32 Byte sind die Blockgroesse von SHA-256 -
# mehr brachte keinen Gewinn, weniger waere die einzige schwache Stelle.
LAENGE = 32

ORDNER = "KDS-Lizenz"
DATEI = "hauptschluessel.txt"


def pfad() -> Path:
    """Wo der Hauptschluessel liegt.

    Ueber die Umgebungsvariable KDS_HAUPTSCHLUESSEL_PFAD umlenkbar - die Tests
    brauchen das, und wer mehrere Schluesselbunde trennen will, ebenfalls.
    """
    umleitung = os.environ.get("KDS_HAUPTSCHLUESSEL_PFAD")
    if umleitung:
        return Path(umleitung)
    appdata = os.environ.get("APPDATA")
    basis = Path(appdata) if appdata else Path.home() / ".config"
    return basis / ORDNER / DATEI


def vorhanden() -> bool:
    """True, wenn schon ein Hauptschluessel angelegt wurde."""
    return pfad().is_file()


def anlegen(ueberschreiben: bool = False) -> bytes:
    """Wuerfelt einen neuen Hauptschluessel und legt ihn ab.

    Ohne `ueberschreiben` bleibt ein vorhandener Schluessel unangetastet und
    wird zurueckgegeben. Das ist die wichtigere Haelfte dieser Funktion: ein
    zweiter Aufruf darf nicht stillschweigend alle bereits ausgestellten
    Schluessel aller Apps entwerten.
    """
    ziel = pfad()
    if ziel.is_file() and not ueberschreiben:
        return lesen()

    # secrets statt random: random ist auf Vorhersagbarkeit ausgelegt (gleicher
    # Startwert, gleiche Folge) und damit fuer Schluessel unbrauchbar.
    roh = secrets.token_bytes(LAENGE)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(roh.hex() + "\n", encoding="utf-8")
    try:
        # Nur der Eigentuemer darf lesen. Unter Windows ohne Wirkung, dort
        # schuetzt die Lage im Benutzerprofil.
        ziel.chmod(0o600)
    except OSError:
        pass
    return roh


def lesen() -> bytes:
    """Der Hauptschluessel; klare Meldung, wenn er fehlt."""
    ziel = pfad()
    try:
        text = ziel.read_text(encoding="utf-8").strip()
    except OSError as fehler:
        raise FileNotFoundError(
            f"Kein Hauptschluessel unter {ziel}.\n"
            "Bitte einmal 'Lizenz-Einrichtung.bat' doppelklicken oder\n"
            "'python tools/hauptschluessel_anlegen.py' ausfuehren."
        ) from fehler
    try:
        roh = bytes.fromhex(text.replace(" ", ""))
    except ValueError as fehler:
        raise ValueError(
            f"Die Datei {ziel} enthaelt keinen lesbaren Hauptschluessel."
        ) from fehler
    if len(roh) < 16:
        raise ValueError(f"Der Hauptschluessel in {ziel} ist zu kurz.")
    return roh


def app_schluessel(produkt: str, haupt: bytes | None = None) -> bytes:
    """Leitet den Schluessel einer App aus dem Hauptschluessel ab.

    Dieselbe App ergibt immer denselben App-Schluessel - sonst waere er nach
    einem Neubau der EXE ein anderer und alle ausgestellten Schluessel waeren
    hin. Zwei verschiedene Apps ergeben zwei voellig verschiedene Schluessel,
    und aus einem App-Schluessel laesst sich der Hauptschluessel nicht
    zurueckrechnen - das ist genau die Eigenschaft, die HMAC mitbringt.

    Der Produktname wird dabei nur an den Raendern von Leerzeichen befreit,
    aber NICHT kleingeschrieben: "Spotify" und "spotify" sind damit zwei
    verschiedene Apps. Das ist die unauffaelligere Falle - deshalb steht der
    verwendete Name in der Ausgabe von tools/app_schluessel.py mit dabei.
    """
    if haupt is None:
        haupt = lesen()
    return hmac.new(haupt, produkt.strip().encode("utf-8"), hashlib.sha256).digest()
