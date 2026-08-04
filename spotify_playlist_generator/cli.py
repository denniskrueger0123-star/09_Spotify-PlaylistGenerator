"""CLI for Spotify Playlist Generator."""

import argparse
import dataclasses
import sys
from pathlib import Path

from . import matcher
from .config import load_config
from .errors import PlaylistGeneratorError
from .pipeline import GenerationParams, run_generation
from .report import format_summary, write_report


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
        config = load_config(env_file=args.env_file)

        if args.token_path:
            config = dataclasses.replace(config, token_path=args.token_path)

        params = GenerationParams(
            csv_path=args.csv,
            playlist_name=args.name,
            description=args.description,
            public=args.public,
            market=args.market,
            min_score=args.min_score,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        def on_progress(event):
            if event.kind == "song":
                print(event.message)
            elif event.kind == "info":
                print(f"\n{event.message}")

        result = run_generation(config, params, progress=on_progress)

        if args.report:
            write_report(args.report, result.rows)

        print(f"\n{format_summary(result.rows)}")

        return result.exit_code

    except PlaylistGeneratorError as exc:
        # Expected error - print to stderr without traceback
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    except KeyboardInterrupt:
        # User interrupted
        print("\nAbgebrochen vom Benutzer", file=sys.stderr)
        return 130
