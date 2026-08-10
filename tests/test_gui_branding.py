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
