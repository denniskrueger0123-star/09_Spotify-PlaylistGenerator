"""Tests für die app-eigene Lizenzanbindung (lizenz_konfig.py, lizenz.py).

kds_lizenz selbst wird nicht angefasst und braucht hier keinen eigenen Test:
es kommt unveraendert aus 10_LicenseManager. Was hier zaehlt, ist die
Verdrahtung dieser App - der Produktname, der App-Schluessel-Umweg und dass
ein mit schluessel_erzeugen erzeugter Schluessel wieder angenommen wird.
"""

from datetime import date, timedelta

import pytest

import kds_lizenz
from spotify_playlist_generator import lizenz, lizenz_konfig

FAKE_APP_SCHLUESSEL = b"\x11" * 32


@pytest.fixture(autouse=True)
def appdata_umleiten(tmp_path, monkeypatch):
    """Jeder Test schreibt in ein temporaeres Verzeichnis, nie ins echte %APPDATA%."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    yield


@pytest.fixture
def eingerichtet_mit_fake_schluessel():
    """Richtet kds_lizenz mit einem Test-App-Schluessel ein und stellt danach

    die echte (leere) Einrichtung dieser App wieder her, damit andere Tests -
    allen voran die GUI-Tests, die sich auf den unveraenderten Auslieferungs-
    zustand verlassen - von diesem Test nichts mitbekommen.
    """
    kds_lizenz.einrichten(
        produkt=lizenz_konfig.PRODUKT,
        app_schluessel=FAKE_APP_SCHLUESSEL,
        vorsilbe=lizenz_konfig.VORSILBE,
        ordner=lizenz_konfig.ORDNER,
    )
    yield
    kds_lizenz.einrichten(
        produkt=lizenz_konfig.PRODUKT,
        app_schluessel=lizenz_konfig.APP_SCHLUESSEL,
        vorsilbe=lizenz_konfig.VORSILBE,
        ordner=lizenz_konfig.ORDNER,
    )


def test_produktname_ist_buchstabengenau():
    """Der Produktname geht in die App-Schluessel-Berechnung ein - er darf sich
    nicht mehr aendern, ohne alle ausgestellten Lizenzen zu entwerten."""
    assert lizenz_konfig.PRODUKT == "Spotify Playlist Generator"
    assert lizenz_konfig.ORDNER == "SpotifyPlaylistGenerator"
    assert lizenz_konfig.VORSILBE == "KDS"


def test_ausgelieferter_app_schluessel_ist_leer():
    """Solange kein App-Schluessel eingetragen ist, bleibt die App gesperrt."""
    assert lizenz_konfig.APP_SCHLUESSEL == ""
    assert lizenz.eingerichtet() is False
    assert lizenz.status() == (lizenz.FEHLT, None)


def test_erzeugter_schluessel_wird_wieder_angenommen(eingerichtet_mit_fake_schluessel):
    """schluessel_erzeugen -> schluessel_pruefen muss aufgehen (Rundlauf)."""
    schluessel = kds_lizenz.schluessel_erzeugen("Test Kunde", date.today() + timedelta(days=10))
    lic = lizenz.schluessel_pruefen(schluessel)
    assert lic is not None
    assert lic.kunde == "Test Kunde"


def test_ablauftag_selbst_zaehlt_noch_als_gueltig(eingerichtet_mit_fake_schluessel):
    """Eine Lizenz, die heute ablaeuft, ist heute noch gueltig - erst morgen nicht mehr."""
    schluessel = kds_lizenz.schluessel_erzeugen("Test Kunde", date.today())
    lic = lizenz.schluessel_pruefen(schluessel)
    assert lic.abgelaufen(date.today()) is False
    assert lic.abgelaufen(date.today() + timedelta(days=1)) is True


@pytest.mark.parametrize(
    "muell",
    ["", " ", "🎵🎵🎵", "x" * 5000, "KDS-AB", "KDS-KR2W-WYLO-EBSS-4VRO"],
)
def test_muell_als_eingabe_wird_abgelehnt_nie_absturz(eingerichtet_mit_fake_schluessel, muell):
    """Leer, Emoji, riesig, halber Schluessel: alles endet als None, nie als Ausnahme."""
    assert lizenz.schluessel_pruefen(muell) is None


def test_schluessel_einer_anderen_app_wird_abgelehnt(eingerichtet_mit_fake_schluessel):
    """Ein mit einem anderen App-Schluessel signierter Schluessel gehoert nicht hierher."""
    fremder_schluessel = kds_lizenz.schluessel_erzeugen(
        "Kunde", date.today() + timedelta(days=10), app_schluessel=b"\x99" * 32
    )
    assert lizenz.schluessel_pruefen(fremder_schluessel) is None


def test_gueltig_abgelaufen_fehlt_ueber_status(tmp_path, eingerichtet_mit_fake_schluessel):
    """Die drei Zustaende, die status() liefert, jeweils fuer sich."""
    zustand, lic = kds_lizenz.status()
    assert zustand == lizenz.FEHLT

    gueltiger_schluessel = kds_lizenz.schluessel_erzeugen("Kunde", date.today() + timedelta(days=5))
    kds_lizenz.lizenz_speichern(gueltiger_schluessel)
    zustand, lic = kds_lizenz.status()
    assert zustand == lizenz.GUELTIG
    assert lic.kunde == "Kunde"

    abgelaufener_schluessel = kds_lizenz.schluessel_erzeugen("Kunde", date.today() - timedelta(days=1))
    kds_lizenz.lizenz_speichern(abgelaufener_schluessel)
    zustand, lic = kds_lizenz.status()
    assert zustand == lizenz.ABGELAUFEN
