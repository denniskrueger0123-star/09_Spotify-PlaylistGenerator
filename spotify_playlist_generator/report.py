"""Report generation for Spotify Playlist Generator."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ResultRow:
    """Represents a single song search result."""
    row: int
    title: str
    artist: str
    status: str  # "found", "not_found", or "error"
    reason: str
    matched_title: str
    matched_artists: str
    spotify_url: str
    score: float


REPORT_FIELDS = [
    "row",
    "title",
    "artist",
    "status",
    "reason",
    "matched_title",
    "matched_artists",
    "spotify_url",
    "score",
]


def write_report(path: Path, rows: list[ResultRow]) -> None:
    """
    Write search results to a CSV report file.

    Args:
        path: Path to the report file to write.
        rows: List of ResultRow objects to write.

    Creates parent directory if needed.
    Uses UTF-8 encoding and newline="".
    """
    # Create parent directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write CSV
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "row": row.row,
                "title": row.title,
                "artist": row.artist,
                "status": row.status,
                "reason": row.reason,
                "matched_title": row.matched_title,
                "matched_artists": row.matched_artists,
                "spotify_url": row.spotify_url,
                "score": row.score,
            })


def summarize(rows: list[ResultRow]) -> dict[str, int]:
    """
    Summarize the results.

    Args:
        rows: List of ResultRow objects.

    Returns:
        Dictionary with keys: "found", "not_found", "error", "total"
    """
    found = sum(1 for r in rows if r.status == "found")
    not_found = sum(1 for r in rows if r.status == "not_found")
    error = sum(1 for r in rows if r.status == "error")
    total = len(rows)

    return {
        "found": found,
        "not_found": not_found,
        "error": error,
        "total": total,
    }


def format_summary(rows: list[ResultRow]) -> str:
    """
    Format a summary of the results as a human-readable string.

    Args:
        rows: List of ResultRow objects.

    Returns:
        Multiline German text with summary and list of problematic rows.
    """
    summary = summarize(rows)

    lines = []
    lines.append(f"Gesamt: {summary['total']} Song(s)")
    lines.append(f"Gefunden: {summary['found']}")
    lines.append(f"Nicht gefunden: {summary['not_found']}")
    lines.append(f"Fehler: {summary['error']}")

    # List problematic rows
    problems = [r for r in rows if r.status in ("not_found", "error")]

    if not problems:
        lines.append("\nAlle Songs erfolgreich verarbeitet!")
    else:
        lines.append("\nProblematische Zeilen:")
        for row in problems:
            artist_str = f" — {row.artist}" if row.artist else ""
            lines.append(f"  - Zeile {row.row}: {row.title}{artist_str} ({row.reason})")

    return "\n".join(lines)
