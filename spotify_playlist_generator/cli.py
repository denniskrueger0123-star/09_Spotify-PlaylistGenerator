"""CLI for Spotify Playlist Generator."""

import argparse
import dataclasses
import sys
from pathlib import Path

from . import matcher
from .auth import SpotifyAuth
from .config import load_config
from .csv_reader import read_songs, TITLE_HEADERS, ARTIST_HEADERS, _normalize_header
from .errors import PlaylistGeneratorError, SpotifyApiError
from .report import ResultRow, format_summary, write_report
from .spotify_client import SpotifyClient


def _extract_field(raw_dict: dict, header_set: set[str]) -> str:
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


def main(argv: list[str] | None = None) -> int:
    """
    Main CLI entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code: 0 = all found, 1 = some not found/error, 2 = config error, 130 = KeyboardInterrupt
    """
    parser = argparse.ArgumentParser(
        prog="spotify_playlist_generator",
        description="Erstelle Spotify-Playlists aus CSV-Dateien"
    )

    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Pfad zur CSV-Datei mit Songs (title, artist)"
    )

    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Name der zu erstellenden Playlist"
    )

    parser.add_argument(
        "--description",
        type=str,
        default="",
        help="Beschreibung der Playlist (default: leer)"
    )

    parser.add_argument(
        "--public",
        action="store_true",
        help="Playlist als öffentlich erstellen (default: privat)"
    )

    parser.add_argument(
        "--report",
        type=Path,
        help="Pfad zur CSV-Datei für den Report"
    )

    parser.add_argument(
        "--market",
        type=str,
        help="Spotify-Markt-Code (z. B. DE, US)"
    )

    parser.add_argument(
        "--min-score",
        type=float,
        default=matcher.DEFAULT_MIN_SCORE,
        help=f"Minimaler Match-Score (default: {matcher.DEFAULT_MIN_SCORE})"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximale Anzahl Kandidaten pro Suchanfrage (default: 10)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simuliert Suche, erstellt keine Playlist"
    )

    parser.add_argument(
        "--env-file",
        type=Path,
        help="Pfad zur .env-Datei"
    )

    parser.add_argument(
        "--token-path",
        type=Path,
        help="Pfad zur Token-Cache-Datei (überschreibt config.token_path)"
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse raises SystemExit on --help or error
        if e.code != 0:
            return e.code
        return 0

    try:
        # Step 1: Load configuration
        config = load_config(env_file=args.env_file)

        # Override token_path if provided
        if args.token_path:
            config = dataclasses.replace(config, token_path=args.token_path)

        # Step 2: Read songs from CSV
        songs, skipped = read_songs(args.csv)

        # Convert skipped rows to ResultRow with status="error"
        result_rows = []
        for skipped_row in skipped:
            result_rows.append(ResultRow(
                row=skipped_row["row"],
                title=_extract_field(skipped_row["raw"], TITLE_HEADERS),
                artist=_extract_field(skipped_row["raw"], ARTIST_HEADERS),
                status="error",
                reason=skipped_row["reason"],
                matched_title="",
                matched_artists="",
                spotify_url="",
                score=0.0,
            ))

        # Step 3: Create auth and token provider
        auth = SpotifyAuth(config)
        token_provider = lambda: auth.get_token().access_token

        # Step 4: Create Spotify client
        client = SpotifyClient(token_provider)

        # Step 5: Search for each song
        seen_uris = set()
        uris_ordered = []

        for idx, song in enumerate(songs, start=1):
            progress = f"[{idx}/{len(songs)}] {song.title}"
            if song.artist:
                progress += f" — {song.artist}"

            try:
                # Try each query in order until one hits
                queries = matcher.build_queries(song.title, song.artist)
                best_match = None

                for query in queries:
                    items = client.search_track(
                        query,
                        market=args.market,
                        limit=args.limit
                    )
                    best_match = matcher.pick_best(
                        song.title,
                        song.artist,
                        items,
                        args.min_score
                    )
                    if best_match:
                        break

                if best_match:
                    # Found
                    print(f"{progress} … gefunden")
                    result_rows.append(ResultRow(
                        row=song.row,
                        title=song.title,
                        artist=song.artist,
                        status="found",
                        reason="",
                        matched_title=best_match.name,
                        matched_artists=best_match.artists,
                        spotify_url=best_match.url,
                        score=best_match.score,
                    ))
                    # Deduplicate: only add if not seen before
                    if best_match.uri not in seen_uris:
                        seen_uris.add(best_match.uri)
                        uris_ordered.append(best_match.uri)
                else:
                    # Not found
                    print(f"{progress} … nicht gefunden")
                    result_rows.append(ResultRow(
                        row=song.row,
                        title=song.title,
                        artist=song.artist,
                        status="not_found",
                        reason="Kein passender Track gefunden",
                        matched_title="",
                        matched_artists="",
                        spotify_url="",
                        score=0.0,
                    ))

            except SpotifyApiError as exc:
                # API error for this song - continue
                print(f"{progress} … Fehler")
                result_rows.append(ResultRow(
                    row=song.row,
                    title=song.title,
                    artist=song.artist,
                    status="error",
                    reason=str(exc),
                    matched_title="",
                    matched_artists="",
                    spotify_url="",
                    score=0.0,
                ))

        # Step 6: Deduplicate URIs (first occurrence wins)
        # Already done above with seen_uris set

        # Step 7: Create playlist if not --dry-run and have URIs
        if not args.dry_run:
            if uris_ordered:
                user_info = client.current_user()
                user_id = user_info.get("id")
                if not user_id:
                    raise SpotifyApiError("Benutzerprofil konnte nicht gelesen werden")

                playlist = client.create_playlist(
                    user_id,
                    args.name,
                    public=args.public,
                    description=args.description
                )
                playlist_id = playlist.get("id")
                if not playlist_id:
                    raise SpotifyApiError("Playlist konnte nicht erstellt werden")

                client.add_tracks(playlist_id, uris_ordered)
                playlist_url = (playlist.get("external_urls") or {}).get("spotify", "")
                if playlist_url:
                    print(f"\nPlaylist erstellt: {playlist_url}")
            else:
                print("\nWarnung: Keine URIs gefunden, Playlist wird nicht erstellt")
        else:
            print("\n(--dry-run: Playlist wird nicht erstellt)")

        # Step 8: Write report if requested
        if args.report:
            write_report(args.report, result_rows)

        # Step 9: Print summary
        print(f"\n{format_summary(result_rows)}")

        # Return exit code
        summary = {
            "found": sum(1 for r in result_rows if r.status == "found"),
            "not_found": sum(1 for r in result_rows if r.status == "not_found"),
            "error": sum(1 for r in result_rows if r.status == "error"),
        }

        if summary["not_found"] > 0 or summary["error"] > 0:
            return 1
        else:
            return 0

    except PlaylistGeneratorError as exc:
        # Expected error - print to stderr without traceback
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    except KeyboardInterrupt:
        # User interrupted
        print("\nAbgebrochen vom Benutzer", file=sys.stderr)
        return 130
