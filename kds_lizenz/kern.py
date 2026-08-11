"""Offline-Lizenzschluessel: erzeugen, pruefen, speichern.

Diese Datei ist in JEDER App gleich und wird nicht angepasst. Was sich von App
zu App unterscheidet - Produktname und App-Schluessel - kommt ueber
`einrichten()` herein, das jede App einmal beim Start aufruft.

Verfahren
---------
Ablauftermin und Kundenname stecken IM Schluessel; eine HMAC-Unterschrift
darueber beweist, dass beides vom Herausgeber stammt. Damit prueft sich der
Schluessel allein aus sich selbst heraus - ohne Server, ohne Netzzugang.

Zwei Ebenen von Geheimnissen
----------------------------
Der HAUPTSCHLUESSEL liegt nur auf dem Rechner des Entwicklers (siehe
kds_lizenz/hauptschluessel.py) und wird NIE ausgeliefert. Aus ihm wird fuer
jede App ein eigener APP-SCHLUESSEL abgeleitet, und nur dieser steckt in der
ausgelieferten EXE.

Das hat zwei Folgen, die beide erwuenscht sind:

    Ein Schluessel fuer App A oeffnet App B nicht, denn beide unterschreiben
    mit verschiedenen App-Schluesseln.

    Wer App A auseinandernimmt und ihren App-Schluessel herausholt, kann sich
    damit Schluessel fuer App A ausstellen - aber fuer keine andere App. Der
    Hauptschluessel laesst sich aus einem App-Schluessel nicht zurueckrechnen.

Was dieses Verfahren ausdruecklich NICHT leistet
------------------------------------------------
Wer die EXE auseinandernimmt, findet den App-Schluessel darin und kann sich
fuer DIESE App beliebige Schluessel ausstellen. Dagegen ist bei einem reinen
Offline-System nichts zu machen: das Programm muss den Schluessel kennen, um
pruefen zu koennen, und alles, was es kennt, kennt auch der, der es
auseinandernimmt. Verschleierung verschoebe den Aufwand um eine
Nachmittagsstunde, mehr nicht.

Das ist eine bewusste Entscheidung: Die Sperre haelt ehrliche Nutzer davon ab,
das Programm nach Ablauf weiterzuverwenden oder weiterzureichen. Sie haelt
keinen Angreifer auf, und sie soll es auch nicht - der Aufwand fuer echten
Kopierschutz (Server, Aktivierungszaehler, Hardware-Bindung) stuende in keinem
Verhaeltnis zu Werkzeugen dieser Groesse.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Trennt Kundenname und Ablaufdatum in der Nutzlast. Der senkrechte Strich
# kommt in Firmennamen praktisch nicht vor; taucht er doch einmal auf, trennt
# die Pruefung am LETZTEN Vorkommen, damit der Name unversehrt bleibt.
TRENNER = "|"

# Laenge der Unterschrift in Bytes. 8 Bytes sind 64 Bit: wer einen Schluessel
# raten will, muesste im Mittel 2^63 Versuche machen - jeder davon ein
# Programmstart. Das ist gegen Raten mehr als genug. Mehr Bytes wuerden nur den
# Schluessel verlaengern, und der wird abgetippt und am Telefon vorgelesen;
# jede weitere Vierergruppe ist eine weitere Gelegenheit fuer einen Zahlendreher.
UNTERSCHRIFT_BYTES = 8

# Laenge der Bloecke, in die der Schluessel zerlegt wird. Vierergruppen sind
# das Mass, das man beim Abtippen noch am Stueck im Kopf behaelt - wie bei
# einer Kreditkartennummer oder einem Windows-Produktschluessel.
GRUPPE = 4

# Die drei Zustaende, die `status()` liefern kann.
GUELTIG = "gueltig"
ABGELAUFEN = "abgelaufen"
FEHLT = "fehlt"

# Name der Datei im Lizenzordner der App.
LIZENZ_DATEI = "lizenz.txt"


class NichtEingerichtet(RuntimeError):
    """einrichten() wurde vergessen.

    Ein eigener Fehlertyp und kein stilles Weiterlaufen: eine App, die ohne
    Einrichtung prueft, wuerde sonst mit irgendeinem Vorgabewert unterschreiben
    und dabei Schluessel erzeugen, die spaeter niemand mehr einloesen kann.
    """


@dataclass(frozen=True)
class Einstellung:
    """Was diese eine App von allen anderen unterscheidet."""

    produkt: str
    app_schluessel: bytes
    vorsilbe: str
    ordner: str

    @property
    def unvollstaendig(self) -> bool:
        """True, solange die App noch keinen App-Schluessel hat.

        Der Zustand tritt genau einmal auf: zwischen dem ersten Auschecken des
        Quelltextes und dem Ausfuehren der Lizenz-Einrichtung. Er fuehrt
        bewusst zu einer gesperrten App und nicht zu einem Absturz - und erst
        recht nicht zu einer freigeschalteten. Eine EXE, die versehentlich
        ohne App-Schluessel gebaut wurde, ist damit unbrauchbar statt
        unbewacht.
        """
        return not self.app_schluessel


# Die aktuelle Einrichtung. Modulweit, weil eine laufende Anwendung immer genau
# eine ist - ein Durchreichen durch jede Funktion waere Ballast ohne Nutzen.
_einstellung: Einstellung | None = None


def einrichten(
    produkt: str,
    app_schluessel: bytes | str,
    vorsilbe: str = "KDS",
    ordner: str | None = None,
) -> Einstellung:
    """Meldet dem Lizenzteil, um welche App es sich handelt.

    Muss einmal beim Start aufgerufen werden, bevor irgendetwas geprueft wird.

    produkt        Klarname der App, z.B. "MultiDoc Batchprinter". Er steht in
                   Meldungen und bestimmt, welcher App-Schluessel dazugehoert.
    app_schluessel Der aus dem Hauptschluessel abgeleitete Schluessel dieser
                   App - als bytes oder als Hex-Zeichenkette.
    vorsilbe       Sichtbarer Anfang des Schluessels. Sie sagt einem Nutzer,
                   der ihn in einer Mail findet, sofort wozu er gehoert.
    ordner         Unterordner in %APPDATA%. Vorgabe ist der Produktname.
                   Zwei Apps duerfen sich hier NICHT treffen, sonst
                   ueberschreibt die eine die Lizenzdatei der anderen.
    """
    global _einstellung
    if isinstance(app_schluessel, str):
        # Hex, weil ein App-Schluessel in einer Konfigurationsdatei steht und
        # dort les- und kopierbar sein muss. Eine leere Angabe ist ausdruecklich
        # erlaubt und bedeutet "noch nicht eingerichtet" - siehe
        # Einstellung.unvollstaendig.
        app_schluessel = bytes.fromhex(app_schluessel.strip().replace(" ", ""))
    if not produkt.strip():
        raise ValueError("produkt ist leer")
    _einstellung = Einstellung(
        produkt=produkt.strip(),
        app_schluessel=app_schluessel,
        vorsilbe=vorsilbe.upper(),
        ordner=(ordner or produkt).strip(),
    )
    return _einstellung


def einstellung() -> Einstellung:
    """Die aktuelle Einrichtung; Fehler, wenn sie fehlt."""
    if _einstellung is None:
        raise NichtEingerichtet(
            "kds_lizenz.einrichten(...) wurde nicht aufgerufen - ohne "
            "Produktname und App-Schluessel laesst sich nichts pruefen."
        )
    return _einstellung


@dataclass(frozen=True)
class Lizenz:
    """Was in einem gueltig unterschriebenen Schluessel steht.

    Mehr Felder gibt es bewusst nicht. Alles, was in die Nutzlast wandert,
    verlaengert den Schluessel - und abgetippt wird er von Hand. Der
    Produktname steht deshalb NICHT drin: er steckt bereits im App-Schluessel,
    mit dem unterschrieben wird, und wuerde jeden Schluessel nur verlaengern.
    """

    kunde: str
    ablauf: date

    def abgelaufen(self, heute: date | None = None) -> bool:
        """True, wenn der Ablauftermin bereits vorbei ist.

        Der Ablauftag selbst zaehlt noch als gueltig: wer eine Lizenz "bis
        31.12." verkauft, meint diesen Tag einschliesslich. Alles andere
        fuehrt zu einem Anruf am 31.12.
        """
        return (heute or date.today()) > self.ablauf

    def tage_rest(self, heute: date | None = None) -> int:
        """Verbleibende Tage; 0 am Ablauftag selbst, negativ danach.

        Negative Werte werden nicht abgeschnitten - der Aufrufer kann daran
        ablesen, wie lange eine Lizenz schon abgelaufen ist.
        """
        return (self.ablauf - (heute or date.today())).days


def _unterschrift(nutzlast: bytes, app_schluessel: bytes) -> bytes:
    """Die gekuerzte HMAC-Unterschrift ueber die Nutzlast."""
    return hmac.new(app_schluessel, nutzlast, hashlib.sha256).digest()[
        :UNTERSCHRIFT_BYTES
    ]


def schluessel_erzeugen(
    kunde: str,
    ablauf: date,
    app_schluessel: bytes | None = None,
    vorsilbe: str | None = None,
) -> str:
    """Baut den Lizenzschluessel fuer `kunde` mit Ablauftermin `ablauf`.

    app_schluessel und vorsilbe koennen uebergeben werden, damit der Generator
    auf dem Entwicklerrechner Schluessel fuer JEDE App ausstellen kann, ohne
    sich vorher als diese App einzurichten. Ohne Angabe gilt die Einrichtung.

    Base32 statt Base64, obwohl Base32 rund ein Fuenftel laenger wird. Der
    Grund ist der Weg, den so ein Schluessel nimmt: er wird abgetippt, aus
    einer Mail kopiert, im Zweifel am Telefon vorgelesen. Base32 kennt nur
    Grossbuchstaben und die Ziffern 2 bis 7 - es gibt also keine Gross-/
    Kleinschreibung, die verlorengehen kann, und keine der beruechtigten
    Verwechslungspaare 0/O, 1/l/I oder 8/B. Base64 haette alle davon plus die
    Sonderzeichen "+" und "/", die in Mailprogrammen gern zu Zeilenumbruechen
    oder Verlinkungen fuehren.
    """
    if app_schluessel is None or vorsilbe is None:
        aktuell = einstellung()
        app_schluessel = app_schluessel or aktuell.app_schluessel
        vorsilbe = aktuell.vorsilbe if vorsilbe is None else vorsilbe
    if not app_schluessel:
        raise NichtEingerichtet(
            "Ohne App-Schluessel laesst sich kein Lizenzschluessel ausstellen."
        )

    nutzlast = f"{kunde}{TRENNER}{ablauf.isoformat()}".encode("utf-8")
    roh = nutzlast + _unterschrift(nutzlast, app_schluessel)
    # Die "="-Fuellzeichen fliegen raus: sie tragen keine Information, sehen
    # in einer Mail nach Fehler aus und werden beim Abtippen ohnehin vergessen.
    text = base64.b32encode(roh).decode("ascii").rstrip("=")
    gruppen = [text[i : i + GRUPPE] for i in range(0, len(text), GRUPPE)]
    return "-".join([vorsilbe.upper(), *gruppen])


def _saeubern(schluessel: str) -> str:
    """Macht aus dem, was der Nutzer eingibt, reine Base32-Zeichen.

    Beim Kopieren aus einer Mail kommen Zeilenumbrueche, harte Leerzeichen und
    manchmal auch Tabulatoren mit; beim Abtippen bleiben Bindestriche weg oder
    stehen an der falschen Stelle. Nichts davon darf ein Grund sein, einen
    zahlenden Kunden abzuweisen - also fliegt alles raus, was kein Base32-
    Zeichen ist, und der Rest wird gross geschrieben.
    """
    erlaubt = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
    return "".join(z for z in schluessel.upper() if z in erlaubt)


def _entschluesseln(text: str, app_schluessel: bytes) -> Lizenz | None:
    """Prueft EINE Lesart der Zeichenkette; None, wenn sie nicht aufgeht."""
    try:
        # Die beim Erzeugen entfernten Fuellzeichen wieder ergaenzen: Base32
        # arbeitet in Bloecken zu 8 Zeichen.
        fehlend = (-len(text)) % 8
        roh = base64.b32decode(text + "=" * fehlend)
    except (binascii.Error, ValueError):
        return None

    if len(roh) <= UNTERSCHRIFT_BYTES:
        return None
    nutzlast, unterschrift = roh[:-UNTERSCHRIFT_BYTES], roh[-UNTERSCHRIFT_BYTES:]

    # compare_digest statt "==": der Vergleich braucht immer gleich lange,
    # egal an welcher Stelle der erste Unterschied steht. Ein "=="-Vergleich
    # bricht beim ersten falschen Byte ab und verraet damit ueber die
    # gemessene Laufzeit, wie weit man schon richtig geraten hat - so laesst
    # sich eine Unterschrift Byte fuer Byte erarbeiten, statt sie als Ganzes
    # raten zu muessen. Hier ist das eher Gewohnheit als Notwendigkeit (der
    # App-Schluessel steckt ohnehin in der EXE), aber es ist die Gewohnheit,
    # die an der naechsten Stelle den Unterschied macht.
    if not hmac.compare_digest(unterschrift, _unterschrift(nutzlast, app_schluessel)):
        return None

    try:
        inhalt = nutzlast.decode("utf-8")
    except UnicodeDecodeError:
        return None
    # Von rechts trennen: enthaelt der Kundenname selbst einen senkrechten
    # Strich, bleibt er dadurch unversehrt.
    kunde, _, datum = inhalt.rpartition(TRENNER)
    if not kunde:
        return None
    try:
        ablauf = date.fromisoformat(datum)
    except ValueError:
        return None
    return Lizenz(kunde=kunde, ablauf=ablauf)


def schluessel_pruefen(schluessel: str) -> Lizenz | None:
    """Liest einen Schluessel; None, wenn er nicht stimmt.

    JEDER Fehler endet hier als None und niemals als Ausnahme: kaputte
    Base32-Zeichen, eine abgeschnittene Zeichenkette, ein fehlendes
    Trennzeichen, ein unmoegliches Datum wie der 31. Februar, eine falsche
    Unterschrift - und ebenso ein echter Schluessel, der aber zu einer ANDEREN
    App gehoert. Der haeufigste Fall ist ein Tippfehler eines Nutzers, der
    gerade seine Lizenz eingibt - der darf ihm nicht das Programm abschiessen.

    Achtung: geprueft wird nur die Echtheit, nicht der Ablauf. Ob die Lizenz
    noch gilt, entscheidet der Aufrufer ueber `Lizenz.abgelaufen()` - nur so
    laesst sich "abgelaufen" von "gefaelscht" unterscheiden, und das sind zwei
    voellig verschiedene Meldungen fuer den Nutzer.
    """
    aktuell = einstellung()
    if aktuell.unvollstaendig:
        # Ohne App-Schluessel gibt es nichts, wogegen sich pruefen liesse.
        # Jeder Schluessel wird abgelehnt - die App bleibt zu.
        return None
    roh = _saeubern(schluessel)

    # Die Vorsilbe wird abgeschnitten - aber nur versuchsweise. "K", "D" und
    # "S" sind selbst gueltige Base32-Zeichen: gibt jemand den Schluessel ohne
    # Vorsilbe ein und beginnt die Nutzlast zufaellig mit "KDS", wuerde blindes
    # Abschneiden einen gueltigen Schluessel zerstoeren. Darum werden beide
    # Lesarten durchprobiert; die erste, die aufgeht, gewinnt.
    lesarten = [roh]
    if roh.startswith(aktuell.vorsilbe):
        lesarten.insert(0, roh[len(aktuell.vorsilbe) :])

    for lesart in lesarten:
        lizenz = _entschluesseln(lesart, aktuell.app_schluessel)
        if lizenz is not None:
            return lizenz
    return None


# ------------------------------------------------------------------ Speicherung


def lizenz_pfad() -> Path:
    """Wo der Schluessel des Nutzers liegt.

    Unter Windows in %APPDATA% - das ist der Ort, den Windows fuer genau
    solche Angaben vorsieht, er wandert bei servergespeicherten Profilen mit
    und er ist ohne Adminrecht beschreibbar. Neben die EXE darf die Datei
    nicht: die liegt bei einer Ein-Datei-Anwendung gern auf einem Stick oder
    in einem Ordner, in den ein normaler Nutzer nicht schreiben darf.

    Ausserhalb von Windows wird ~/.config genommen, damit sich Speichern und
    Lesen auf der Entwicklungsmaschine ueberhaupt testen lassen. Ein Zweig,
    den keiner ausfuehren kann, ist ein Zweig, der beim naechsten Umbau still
    kaputtgeht.
    """
    appdata = os.environ.get("APPDATA")
    basis = Path(appdata) if appdata else Path.home() / ".config"
    return basis / einstellung().ordner / LIZENZ_DATEI


def lizenz_speichern(schluessel: str) -> bool:
    """Schreibt den Schluessel; False, wenn das nicht ging.

    Kein Absturz bei OSError: ein schreibgeschuetztes Profil, ein volles
    Laufwerk oder eine Gruppenrichtlinie sind aergerlich, aber der Nutzer soll
    dann eine Meldung sehen und weiterarbeiten koennen - nicht einen
    Programmabsturz unmittelbar nach der Eingabe seines Schluessels.
    """
    pfad = lizenz_pfad()
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(schluessel.strip() + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def gespeicherten_schluessel_lesen() -> str | None:
    """Der hinterlegte Schluessel; None, wenn keiner lesbar ist.

    Fehlende Datei, fehlendes Leserecht, kaputte Kodierung - alles endet als
    None und damit im selben Zustand wie "noch nie eine Lizenz eingegeben".
    Das ist die richtige Antwort: in allen Faellen muss der Nutzer denselben
    Weg gehen und seinen Schluessel neu eingeben.
    """
    try:
        text = lizenz_pfad().read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return text or None


def aktive_lizenz() -> Lizenz | None:
    """Die hinterlegte Lizenz, sofern echt; sonst None.

    WICHTIG: Eine abgelaufene Lizenz kommt hier trotzdem zurueck. Das ist
    Absicht - der Aufrufer soll "abgelaufen am 31.12.2026" und "gar keine
    Lizenz hinterlegt" verschieden melden koennen. Wer beides zu None
    zusammenfasst, schickt einen Kunden, der nur verlaengern muss, auf die
    Suche nach einem Schluessel, den er laengst hat.
    """
    schluessel = gespeicherten_schluessel_lesen()
    if schluessel is None:
        return None
    return schluessel_pruefen(schluessel)


def status(heute: date | None = None) -> tuple[str, Lizenz | None]:
    """Zustand und Lizenz - die Auskunft, mit der die Oberflaeche arbeitet.

    Liefert eines von GUELTIG, ABGELAUFEN, FEHLT. Ein gefaelschter, vertippter
    oder zu einer anderen App gehoerender gespeicherter Schluessel faellt unter
    FEHLT: nach aussen ist das dasselbe wie keine Lizenz, und dem Nutzer hilft
    eine Unterscheidung an dieser Stelle nicht weiter.
    """
    lizenz = aktive_lizenz()
    if lizenz is None:
        return FEHLT, None
    if lizenz.abgelaufen(heute):
        return ABGELAUFEN, lizenz
    return GUELTIG, lizenz
