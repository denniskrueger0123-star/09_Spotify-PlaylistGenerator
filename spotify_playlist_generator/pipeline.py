"""Gemeinsamer Ablauf für CLI und grafische Oberfläche."""

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import matcher
from .auth import SpotifyAuth
from .config import Config
from .csv_reader import read_songs, TITLE_HEADERS, ARTIST_HEADERS, _normalize_header
from .errors import OperationCancelled, SpotifyApiError
from .report import ResultRow
from .spotify_client import SpotifyClient


@dataclass(frozen=True)
class GenerationParams:
    """Alle Eingaben für einen Lauf."""
    csv_path: Path
    playlist_name: str
    description: str = ""
    public: bool = False
    market: str | None = None
    min_score: float = matcher.DEFAULT_MIN_SCORE
    limit: int = 10
    dry_run: bool = False


@dataclass(frozen=True)
class ProgressEvent:
    """Eine Fortschrittsmeldung aus dem laufenden Vorgang."""
    kind: str            # "auth" | "start" | "song" | "info" | "done"
    index: int = 0
    total: int = 0
    message: str = ""
    row: ResultRow | None = None


@dataclass
class GenerationResult:
    """Das Ergebnis eines Laufs."""
    rows: list[ResultRow] = field(default_factory=list)
    playlist_url: str = ""
    playlist_id: str = ""
    cancelled: bool = False

    @property
    def counts(self) -> dict[str, int]:
        found = sum(1 for r in self.rows if r.status == "found")
        not_found = sum(1 for r in self.rows if r.status == "not_found")
        error = sum(1 for r in self.rows if r.status == "error")
        total = len(self.rows)
        return {
            "found": found,
            "not_found": not_found,
            "error": error,
            "total": total,
        }

    @property
    def exit_code(self) -> int:
        counts = self.counts
        if counts["not_found"] > 0 or counts["error"] > 0:
            return 1
        return 0


def extract_field(raw_dict: dict, header_set: set[str]) -> str:
    """
    Extract a field value from a raw CSV row dict using normalized header names.

    Args:
        raw_dict: The raw row dictionary from CSV reader.
        header_set: Set of acceptable normalized header names (e.g., TITLE_HEADERS).

    Returns:
        The stripped value of the first matching field, or empty string if not found.
    """
    for key, value in raw_dict.items():
        if _normalize_header(key) in header_set:
            return (value or "").strip()
    return ""


def run_generation(
    config: Config,
    params: GenerationParams,
    progress: Callable[[ProgressEvent], None] | None = None,
    cancel: threading.Event | None = None,
    client: SpotifyClient | None = None,
    auth: SpotifyAuth | None = None,
) -> GenerationResult:
    """
    Führt den kompletten Ablauf aus: CSV lesen, Songs suchen, Playlist anlegen.

    Args:
        config: Konfiguration für Spotify-Zugriff.
        params: Eingaben für diesen Lauf.
        progress: Optionaler Callback, der ProgressEvent-Objekte erhält.
        cancel: Optionales Event, das den Ablauf zwischen Songs abbricht.
        client: Optionaler bereits vorhandener SpotifyClient (für Tests).
        auth: Optionale bereits vorhandene SpotifyAuth (für Tests).

    Returns:
        GenerationResult mit allen Zeilen und ggf. Playlist-Informationen.
    """

    def emit(event: ProgressEvent) -> None:
        if progress is not None:
            progress(event)

    def notify(text: str) -> None:
        """Reicht Statustexte aus Anmeldung und API-Client an die Oberfläche durch."""
        emit(ProgressEvent(kind="info", message=text))

    def is_cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    songs, skipped = read_songs(params.csv_path)

    result = GenerationResult()

    for skipped_row in skipped:
        result.rows.append(ResultRow(
            row=skipped_row["row"],
            title=extract_field(skipped_row["raw"], TITLE_HEADERS),
            artist=extract_field(skipped_row["raw"], ARTIST_HEADERS),
            status="error",
            reason=skipped_row["reason"],
            matched_title="",
            matched_artists="",
            spotify_url="",
            score=0.0,
        ))

    auth = auth or SpotifyAuth(config, notify=notify)

    emit(ProgressEvent(kind="auth", message="Anmeldung bei Spotify …"))
    auth.get_token()

    token_provider = lambda: auth.get_token().access_token
    client = client or SpotifyClient(token_provider, cancel=cancel, notify=notify)

    # Eine einzige billige Anfrage vorab. Scheitert der Zugang (etwa weil dem
    # Inhaber der Spotify-App das Premium-Abo fehlt), bricht der Lauf hier mit
    # einer klaren Meldung ab, statt bei jedem einzelnen Song erneut zu scheitern
    # und dabei das Kontingent aufzubrauchen.
    emit(ProgressEvent(kind="info", message="Prüfe den Zugang zu Spotify …"))
    try:
        client.current_user()
    except OperationCancelled:
        result.cancelled = True
        emit(ProgressEvent(kind="done"))
        return result

    emit(ProgressEvent(kind="start", total=len(songs)))

    seen_uris = set()
    uris_ordered = []

    for idx, song in enumerate(songs, start=1):
        if is_cancelled():
            result.cancelled = True
            break

        progress_text = f"[{idx}/{len(songs)}] {song.title}"
        if song.artist:
            progress_text += f" — {song.artist}"

        try:
            queries = matcher.build_queries(song.title, song.artist)
            best_match = None

            for query in queries:
                items = client.search_track(
                    query,
                    market=params.market,
                    limit=params.limit
                )
                best_match = matcher.pick_best(
                    song.title,
                    song.artist,
                    items,
                    params.min_score
                )
                if best_match:
                    break

            if best_match:
                row = ResultRow(
                    row=song.row,
                    title=song.title,
                    artist=song.artist,
                    status="found",
                    reason="",
                    matched_title=best_match.name,
                    matched_artists=best_match.artists,
                    spotify_url=best_match.url,
                    score=best_match.score,
                )
                message = f"{progress_text} … gefunden"
                if best_match.uri not in seen_uris:
                    seen_uris.add(best_match.uri)
                    uris_ordered.append(best_match.uri)
            else:
                row = ResultRow(
                    row=song.row,
                    title=song.title,
                    artist=song.artist,
                    status="not_found",
                    reason="Kein passender Track gefunden",
                    matched_title="",
                    matched_artists="",
                    spotify_url="",
                    score=0.0,
                )
                message = f"{progress_text} … nicht gefunden"

        except OperationCancelled:
            result.cancelled = True
            break

        except SpotifyApiError as exc:
            row = ResultRow(
                row=song.row,
                title=song.title,
                artist=song.artist,
                status="error",
                reason=str(exc),
                matched_title="",
                matched_artists="",
                spotify_url="",
                score=0.0,
            )
            message = f"{progress_text} … Fehler"

        result.rows.append(row)
        emit(ProgressEvent(kind="song", index=idx, total=len(songs), message=message, row=row))

    if result.cancelled:
        emit(ProgressEvent(kind="done"))
        return result

    try:
        if not params.dry_run:
            if uris_ordered:
                playlist = client.create_playlist(
                    params.playlist_name,
                    public=params.public,
                    description=params.description
                )
                playlist_id = playlist.get("id")
                if not playlist_id:
                    raise SpotifyApiError("Playlist konnte nicht erstellt werden")

                # Vor dem Hochladen merken: Die Playlist existiert ab jetzt im Account,
                # auch wenn add_tracks abgebrochen wird. Sonst fände der Nutzer sie nicht wieder.
                result.playlist_id = playlist_id
                result.playlist_url = (playlist.get("external_urls") or {}).get("spotify", "")

                client.add_tracks(playlist_id, uris_ordered)
                if result.playlist_url:
                    emit(ProgressEvent(kind="info", message=f"Playlist erstellt: {result.playlist_url}"))
            else:
                emit(ProgressEvent(kind="info", message="Warnung: Keine URIs gefunden, Playlist wird nicht erstellt"))
        else:
            emit(ProgressEvent(kind="info", message="(--dry-run: Playlist wird nicht erstellt)"))
    except OperationCancelled:
        result.cancelled = True

    emit(ProgressEvent(kind="done"))
    return result
