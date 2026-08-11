"""Lizenzschluessel fuer die Apps von KDS Krueger Digital Solutions.

Dieses Paket ist in JEDER App identisch. Es wird nie angepasst - beim Umzug in
eine andere App wird der Ordner unveraendert hineinkopiert. Was die eine App
von der anderen unterscheidet, steht in deren eigener Konfigurationsdatei und
kommt ueber `einrichten()` herein.

So wird es in einer App benutzt::

    import kds_lizenz

    kds_lizenz.einrichten(
        produkt="Spotify Playlist Generator",
        app_schluessel="a1b2c3...",   # aus tools/app_schluessel.py
        ordner="Spotify-Playlist-Generator",
    )

    zustand, lizenz = kds_lizenz.status()
    if zustand == kds_lizenz.GUELTIG:
        ...

Das Einrichten gehoert an den Programmstart, vor den ersten Aufruf von
`status()`. Wer es vergisst, bekommt einen NichtEingerichtet-Fehler und keine
stillschweigend falsche Antwort.
"""

from .kern import (
    ABGELAUFEN,
    FEHLT,
    GUELTIG,
    Einstellung,
    Lizenz,
    NichtEingerichtet,
    aktive_lizenz,
    einrichten,
    einstellung,
    gespeicherten_schluessel_lesen,
    lizenz_pfad,
    lizenz_speichern,
    schluessel_erzeugen,
    schluessel_pruefen,
    status,
)

__all__ = [
    "ABGELAUFEN",
    "FEHLT",
    "GUELTIG",
    "Einstellung",
    "Lizenz",
    "NichtEingerichtet",
    "aktive_lizenz",
    "einrichten",
    "einstellung",
    "gespeicherten_schluessel_lesen",
    "lizenz_pfad",
    "lizenz_speichern",
    "schluessel_erzeugen",
    "schluessel_pruefen",
    "status",
]
