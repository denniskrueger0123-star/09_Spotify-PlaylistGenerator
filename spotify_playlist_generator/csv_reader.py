"""CSV file reading for Spotify Playlist Generator."""

import csv
from dataclasses import dataclass
from pathlib import Path

from .errors import CsvError

# Header column name sets
TITLE_HEADERS = {"title", "titel", "song", "track", "name", "songtitel"}
ARTIST_HEADERS = {"artist", "interpret", "kuenstler", "künstler", "band", "performer"}


@dataclass(frozen=True)
class SongRequest:
    """A song request parsed from CSV."""
    row: int  # 1-based line number in the file
    title: str
    artist: str
    raw: dict[str, str]


def _normalize_header(value: str) -> str:
    """Normalize header name: lowercase, strip whitespace and BOM."""
    # Remove BOM if present
    if value.startswith('﻿'):
        value = value[1:]
    # Lowercase and strip whitespace
    return value.strip().lower()


def read_songs(path: Path) -> tuple[list[SongRequest], list[dict]]:
    """
    Read songs from a CSV file.

    Args:
        path: Path to the CSV file

    Returns:
        Tuple of (songs, skipped) where:
        - songs: list of SongRequest objects
        - skipped: list of dicts with keys 'row', 'reason', 'raw'

    Raises:
        CsvError: If file doesn't exist or title column is missing
    """
    if not path.exists():
        raise CsvError(f"CSV-Datei nicht gefunden: {path}")

    songs = []
    skipped = []

    with open(path, encoding='utf-8-sig', newline='') as f:
        # Read sample for delimiter detection
        sample = f.read(4096)
        f.seek(0)

        # Detect delimiter
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","

        # Create DictReader with detected delimiter
        reader = csv.DictReader(f, delimiter=delimiter)

        if not reader.fieldnames:
            raise CsvError("CSV-Datei ist leer oder hat keinen Header")

        # Normalize and map header names
        normalized_headers = {_normalize_header(name): name for name in reader.fieldnames}

        # Find title and artist columns
        title_col = None
        artist_col = None

        for normalized, original in normalized_headers.items():
            if normalized in TITLE_HEADERS:
                title_col = original
            elif normalized in ARTIST_HEADERS:
                artist_col = original

        if not title_col:
            accepted = ", ".join(sorted(TITLE_HEADERS | ARTIST_HEADERS))
            raise CsvError(
                f"Keine Titel-Spalte gefunden. Akzeptierte Spaltennamen: {accepted}"
            )

        # Process data rows
        for row_num, row_dict in enumerate(reader, start=2):  # Start at 2 (after header)
            # Skip completely empty rows
            if all(v is None or v.strip() == '' for v in row_dict.values()):
                continue

            # Extract and normalize values
            title = (row_dict.get(title_col) or "").strip()
            artist = (row_dict.get(artist_col) or "").strip() if artist_col else ""

            # Skip rows with empty title (add to skipped, not songs)
            if not title:
                skipped.append({
                    "row": row_num,
                    "reason": "Kein Titel in dieser Zeile",
                    "raw": {k: (v or "") for k, v in row_dict.items()}
                })
                continue

            # Create SongRequest
            song = SongRequest(
                row=row_num,
                title=title,
                artist=artist,
                raw={k: (v or "") for k, v in row_dict.items()}
            )
            songs.append(song)

    return songs, skipped
