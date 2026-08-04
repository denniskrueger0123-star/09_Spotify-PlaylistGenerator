"""Reine Anzeige-Logik der Oberfläche — bewusst ohne tkinter-Abhängigkeit."""

from dataclasses import dataclass
from pathlib import Path

from ..csv_reader import read_songs
from ..errors import PlaylistGeneratorError
from ..matcher import DEFAULT_MIN_SCORE
from ..pipeline import GenerationParams
from ..report import ResultRow, summarize

MARKETS = ("", "DE", "AT", "CH", "US", "GB")

STATUS_LABELS = {
    "found": "Gefunden",
    "not_found": "Nicht gefunden",
    "error": "Fehler",
}

RESULT_COLUMNS = ("row", "title", "artist", "status", "matched", "score")
RESULT_HEADINGS = ("Zeile", "Titel", "Interpret", "Status", "Gefunden als", "Score")


@dataclass(frozen=True)
class CsvInfo:
    """Ergebnis der Vorabprüfung einer CSV-Datei."""
    ok: bool
    message: str
    song_count: int = 0
    skipped_count: int = 0


def describe_csv(path: Path) -> CsvInfo:
    """
    Prüft eine CSV-Datei und beschreibt ihren Inhalt in einer CsvInfo.

    Liest die Datei mit read_songs und übersetzt das Ergebnis (oder einen
    aufgetretenen Fehler) in eine für die Oberfläche verständliche Meldung.
    """
    try:
        songs, skipped = read_songs(path)
    except PlaylistGeneratorError as exc:
        return CsvInfo(ok=False, message=str(exc))
    except OSError as exc:
        return CsvInfo(ok=False, message=f"Datei konnte nicht gelesen werden: {exc}")

    song_count = len(songs)
    skipped_count = len(skipped)

    if song_count == 0:
        return CsvInfo(
            ok=False,
            message="Keine verwertbaren Zeilen in der Datei",
            song_count=song_count,
            skipped_count=skipped_count,
        )

    if skipped_count:
        message = f"{song_count} Song(s) erkannt, {skipped_count} Zeile(n) übersprungen"
    else:
        message = f"{song_count} Song(s) erkannt"

    return CsvInfo(ok=True, message=message, song_count=song_count, skipped_count=skipped_count)


def default_playlist_name(path: Path) -> str:
    """Leitet einen Vorschlag für den Playlist-Namen aus dem Dateinamen ab."""
    return path.stem or "Neue Playlist"


def validate(csv_text: str, playlist_name: str) -> list[str]:
    """Prüft die Eingaben und gibt eine Liste deutscher Fehlermeldungen zurück."""
    errors: list[str] = []

    if not csv_text.strip():
        errors.append("Bitte eine CSV-Datei auswählen.")
    elif not Path(csv_text).exists():
        errors.append("Die gewählte CSV-Datei existiert nicht.")

    if not playlist_name.strip():
        errors.append("Bitte einen Namen für die Playlist eingeben.")

    return errors


def build_params(
    csv_text,
    playlist_name,
    description="",
    public=False,
    market="",
    min_score=DEFAULT_MIN_SCORE,
    limit=10,
    dry_run=False,
) -> GenerationParams:
    """Baut aus den rohen Formular-Eingaben ein GenerationParams-Objekt."""
    return GenerationParams(
        csv_path=Path(csv_text.strip()),
        playlist_name=playlist_name.strip(),
        description=description.strip(),
        public=bool(public),
        market=market.strip().upper() or None,
        min_score=round(float(min_score), 4),
        limit=int(limit),
        dry_run=bool(dry_run),
    )


def format_score(score: float) -> str:
    """Formatiert einen Score für die Anzeige, 0 wird als leerer String dargestellt."""
    if score == 0:
        return ""
    return f"{score:.2f}"


def status_label(status: str) -> str:
    """Übersetzt einen internen Status in eine deutsche Anzeige-Bezeichnung."""
    return STATUS_LABELS.get(status, status)


def result_row_values(row: ResultRow) -> tuple[str, ...]:
    """Wandelt eine ResultRow in die für die Ergebnistabelle passenden Werte um."""
    if row.matched_title and row.matched_artists:
        matched = f"{row.matched_title} — {row.matched_artists}"
    elif row.matched_title:
        matched = row.matched_title
    else:
        matched = row.reason

    return (
        str(row.row),
        row.title,
        row.artist,
        status_label(row.status),
        matched,
        format_score(row.score),
    )


def summary_line(rows: list[ResultRow]) -> str:
    """Baut eine einzeilige Zusammenfassung der Ergebnisse."""
    s = summarize(rows)
    return f"{s['total']} gesamt · {s['found']} gefunden · {s['not_found']} nicht gefunden · {s['error']} Fehler"


def sort_key(rows_values: tuple[str, ...], column_index: int):
    """Liefert den Sortierschlüssel für eine Tabellenzeile bei gegebener Spalte."""
    value = rows_values[column_index]
    if column_index in (0, 5):
        try:
            return float(value)
        except (TypeError, ValueError):
            return -1.0
    return value.lower()
