"""
Branding-Komponenten für die GUI: Logo und visuelle Identität.

Zwei Bilddateien, beide freiwillig:

    assets/kds-logo.png   Das vollständige Logo mit Schriftzug. Steht groß im
                          Reiter Über.
    assets/kds-mark.png   Nur das KDS-Zeichen ohne Schriftzug. Steht klein in
                          der Kopfzeile und ist damit auf jedem Reiter zu sehen.

Fehlt eine der Dateien, wird None zurückgegeben und die Oberfläche zeigt an
dieser Stelle einen Ersatz. Ein fehlendes Bild darf die Anwendung niemals am
Starten hindern.
"""

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "assets"
LOGO_PATH = ASSETS / "kds-logo.png"
MARK_PATH = ASSETS / "kds-mark.png"


def load_logo(target_width: int = 260):
    """Das vollständige Logo, auf `target_width` skaliert, oder None."""
    return _laden(LOGO_PATH, breite=target_width)


def load_mark(target_height: int = 26):
    """Das kompakte KDS-Zeichen, auf `target_height` skaliert, oder None.

    Die Kopfzeile gibt die Höhe vor, nicht die Breite: das Zeichen soll neben
    dem Titel stehen, ohne die Zeile aufzublähen.
    """
    return _laden(MARK_PATH, hoehe=target_height)


def _laden(pfad: Path, breite: int | None = None, hoehe: int | None = None):
    """
    Gibt ein tkinter-taugliches Bild zurück oder None, wenn keines ladbar ist.

    Ablauf:
    1. Datei fehlt → None zurückgeben.
    2. Pillow vorhanden → sauber auf das Zielmaß skalieren,
       Seitenverhältnis erhalten, ImageTk.PhotoImage zurückgeben.
    3. Ohne Pillow → tk.PhotoImage nutzen und mit subsample verkleinern.
    4. Jede Ausnahme abfangen und None zurückgeben.
    """
    # Fehlt die Datei, wird nichts geladen und auch nichts importiert. Dieser Weg
    # muss ohne tkinter auskommen, sonst reißt ein fehlendes Logo die Anwendung
    # in Umgebungen mit, in denen tkinter nicht bereitsteht.
    if not pfad.exists():
        return None

    # Schritt 2: Mit Pillow
    try:
        from PIL import Image, ImageTk

        image = Image.open(pfad)
        if breite is not None:
            ziel_breite = breite
            ziel_hoehe = max(1, round(breite * image.height / image.width))
        else:
            ziel_hoehe = hoehe
            ziel_breite = max(1, round(hoehe * image.width / image.height))
        verkleinert = image.resize((ziel_breite, ziel_hoehe), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(verkleinert)
    except ImportError:
        # Pillow nicht vorhanden, Schritt 3: tk.PhotoImage mit subsample
        pass
    except Exception:
        # Fehler beim Laden oder Verarbeiten
        return None

    # Schritt 3: Ohne Pillow, tk.PhotoImage mit subsample. subsample kann nur
    # ganzzahlig verkleinern, das Ergebnis ist deshalb gröber als mit Pillow.
    try:
        import tkinter as tk

        photo = tk.PhotoImage(file=str(pfad))
        if breite is not None:
            teiler = max(1, round(photo.width() / breite))
        else:
            teiler = max(1, round(photo.height() / hoehe))
        return photo.subsample(teiler, teiler)
    except Exception:
        # Fehler beim Laden
        return None
