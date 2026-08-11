"""Bruecke zum gemeinsamen Lizenzteil kds_lizenz.

Richtet kds_lizenz beim Import einmalig ein und reicht die Namen weiter,
damit der Rest der App nur dieses eine Modul kennt.
"""

import kds_lizenz

from . import lizenz_konfig

# Beim Import, nicht in einer Startfunktion: der Lizenzteil muss stehen, bevor
# irgendein Fenster aufgeht, und ein Import passiert genau einmal.
kds_lizenz.einrichten(
    produkt=lizenz_konfig.PRODUKT,
    app_schluessel=lizenz_konfig.APP_SCHLUESSEL,
    vorsilbe=lizenz_konfig.VORSILBE,
    ordner=lizenz_konfig.ORDNER,
)

GUELTIG = kds_lizenz.GUELTIG
ABGELAUFEN = kds_lizenz.ABGELAUFEN
FEHLT = kds_lizenz.FEHLT
status = kds_lizenz.status
schluessel_pruefen = kds_lizenz.schluessel_pruefen
lizenz_speichern = kds_lizenz.lizenz_speichern
PRODUKT = lizenz_konfig.PRODUKT


def eingerichtet() -> bool:
    """False, solange kein App-Schluessel hinterlegt ist."""
    return not kds_lizenz.einstellung().unvollstaendig
