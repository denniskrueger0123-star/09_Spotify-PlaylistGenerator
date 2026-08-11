"""Tests für das Laden des Firmenlogos."""

from spotify_playlist_generator.gui import branding


def test_missing_logo_returns_none(monkeypatch, tmp_path):
    """
    Ein fehlendes Logo liefert None statt einer Ausnahme.

    Dieser Weg läuft bewusst ohne tkinter und ohne Pillow. Er wird auch dort
    beschritten, wo die Anwendung gar keine Oberfläche starten kann, und darf
    deshalb nichts importieren, was möglicherweise fehlt.
    """
    monkeypatch.setattr(branding, "LOGO_PATH", tmp_path / "gibt-es-nicht.png")

    assert branding.load_logo() is None


def test_unreadable_logo_returns_none(monkeypatch, tmp_path):
    """Eine vorhandene, aber unlesbare Bilddatei führt nicht zum Absturz."""
    kaputt = tmp_path / "kds-logo.png"
    kaputt.write_bytes(b"das ist kein PNG")
    monkeypatch.setattr(branding, "LOGO_PATH", kaputt)

    assert branding.load_logo() is None


def test_missing_mark_returns_none(monkeypatch, tmp_path):
    """Fehlt das kompakte Zeichen, tritt in der Kopfzeile der Ersatz an seine
    Stelle — laden darf dafür keine Ausnahme werfen."""
    monkeypatch.setattr(branding, "MARK_PATH", tmp_path / "gibt-es-nicht.png")

    assert branding.load_mark() is None


def test_unreadable_mark_returns_none(monkeypatch, tmp_path):
    """Auch ein kaputtes Zeichen darf die Kopfzeile nicht mitreißen."""
    kaputt = tmp_path / "kds-mark.png"
    kaputt.write_bytes(b"das ist kein PNG")
    monkeypatch.setattr(branding, "MARK_PATH", kaputt)

    assert branding.load_mark() is None


def test_mark_is_scaled_by_height(monkeypatch, tmp_path):
    """Das Zeichen wird auf die vorgegebene Höhe gerechnet, die Breite folgt
    dem Seitenverhältnis — sonst bliebe ein breites Logo in der Kopfzeile
    entweder winzig oder überhoch."""
    import pytest

    pytest.importorskip("tkinter")
    pytest.importorskip("PIL")
    from PIL import Image

    quelle = tmp_path / "kds-mark.png"
    Image.new("RGBA", (420, 150), (0, 0, 0, 0)).save(quelle)
    monkeypatch.setattr(branding, "MARK_PATH", quelle)

    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"kein Bildschirm: {exc}")
    root.withdraw()
    try:
        bild = branding.load_mark(target_height=26)
        assert bild is not None
        assert bild.height() == 26
        # 420/150 * 26 = 72,8 -> 73
        assert bild.width() == 73
    finally:
        root.destroy()
