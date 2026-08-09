"""
Branding-Komponenten für die GUI: Logo und visuelle Identität.

Das Firmenlogo wird aus assets/kds-logo.png geladen. Die Bilddatei
kann fehlen — in diesem Fall wird None zurückgegeben und die GUI zeigt
Fallback-Text.
"""

from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "kds-logo.png"


def load_logo(target_width: int = 260):
    """
    Gibt ein tkinter-taugliches Bild zurück oder None, wenn keines ladbar ist.

    Ablauf:
    1. Datei fehlt → None zurückgeben.
    2. Pillow vorhanden → sauber auf target_width skalieren,
       Seitenverhältnis erhalten, ImageTk.PhotoImage zurückgeben.
    3. Ohne Pillow → tk.PhotoImage nutzen und mit subsample verkleinern.
    4. Jede Ausnahme abfangen und None zurückgeben.

    Ein fehlendes oder nicht ladbares Logo darf die App niemals
    am Starten hindern.
    """
    import tkinter as tk

    # Schritt 1: Datei nicht vorhanden
    if not LOGO_PATH.exists():
        return None

    # Schritt 2: Mit Pillow
    try:
        from PIL import Image, ImageTk

        image = Image.open(LOGO_PATH)
        # Auf target_width skalieren, Seitenverhältnis erhalten
        aspect_ratio = image.height / image.width
        target_height = int(target_width * aspect_ratio)
        image_resized = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image_resized)
    except ImportError:
        # Pillow nicht vorhanden, Schritt 3: tk.PhotoImage mit subsample
        pass
    except Exception:
        # Fehler beim Laden oder Verarbeiten
        return None

    # Schritt 3: Ohne Pillow, tk.PhotoImage mit subsample
    try:
        photo = tk.PhotoImage(file=str(LOGO_PATH))
        # Verkleinern mit subsample
        width = photo.width()
        subsample_factor = max(1, round(width / target_width))
        return photo.subsample(subsample_factor, subsample_factor)
    except Exception:
        # Fehler beim Laden
        return None
