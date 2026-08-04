"""Tests for the gui.viewmodel module."""

from pathlib import Path

import pytest

from spotify_playlist_generator.gui import viewmodel as vm
from spotify_playlist_generator.report import ResultRow


def test_viewmodel_does_not_import_tkinter():
    """viewmodel must stay importable on systems without tkinter."""
    import subprocess, sys
    code = (
        "import sys; "
        "sys.modules['tkinter'] = None; "
        "import spotify_playlist_generator.gui.viewmodel as vm; "
        "print('ok')"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_describe_csv_ok(tmp_path):
    """describe_csv reports success for a valid CSV with two songs."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\nSong One,Artist One\nSong Two,Artist Two\n")

    info = vm.describe_csv(csv_file)

    assert info.ok is True
    assert "2 Song(s) erkannt" in info.message
    assert info.song_count == 2


def test_describe_csv_with_skipped(tmp_path):
    """describe_csv reports skipped rows in its message."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\nSong One,Artist One\n,Artist Two\n")

    info = vm.describe_csv(csv_file)

    assert "übersprungen" in info.message
    assert info.skipped_count == 1


def test_describe_csv_missing_file():
    """describe_csv reports a non-empty message for a missing file."""
    info = vm.describe_csv(Path("/nonexistent/songs.csv"))

    assert info.ok is False
    assert info.message != ""


def test_describe_csv_no_title_column(tmp_path):
    """describe_csv reports failure when there's no title column."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("foo,bar\n1,2\n")

    info = vm.describe_csv(csv_file)

    assert info.ok is False


def test_describe_csv_only_header(tmp_path):
    """describe_csv reports failure when there are no data rows."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\n")

    info = vm.describe_csv(csv_file)

    assert info.ok is False
    assert info.message == "Keine verwertbaren Zeilen in der Datei"


def test_default_playlist_name_from_stem(tmp_path):
    """default_playlist_name uses the file stem."""
    path = tmp_path / "My Songs.csv"

    assert vm.default_playlist_name(path) == "My Songs"


def test_default_playlist_name_fallback():
    """default_playlist_name falls back when the stem is empty."""
    path = Path(".")

    assert vm.default_playlist_name(path) == "Neue Playlist"


def test_validate_all_ok(tmp_path):
    """validate returns an empty list when everything is fine."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title\nSong One\n")

    errors = vm.validate(str(csv_file), "My Playlist")

    assert errors == []


def test_validate_missing_csv():
    """validate flags an empty csv_text."""
    errors = vm.validate("", "My Playlist")

    assert "Bitte eine CSV-Datei auswählen." in errors


def test_validate_csv_not_found():
    """validate flags a csv path that doesn't exist."""
    errors = vm.validate("/nonexistent/songs.csv", "My Playlist")

    assert "Die gewählte CSV-Datei existiert nicht." in errors


def test_validate_missing_name(tmp_path):
    """validate flags an empty playlist name."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title\nSong One\n")

    errors = vm.validate(str(csv_file), "  ")

    assert "Bitte einen Namen für die Playlist eingeben." in errors


def test_validate_reports_both_problems():
    """validate reports both problems when both csv_text and name are empty."""
    errors = vm.validate("", "")

    assert len(errors) == 2


def test_build_params_market_empty_becomes_none(tmp_path):
    """build_params turns an empty market string into None."""
    params = vm.build_params(str(tmp_path / "songs.csv"), "Playlist", market="")

    assert params.market is None


def test_build_params_market_uppercased(tmp_path):
    """build_params uppercases the market code."""
    params = vm.build_params(str(tmp_path / "songs.csv"), "Playlist", market="de")

    assert params.market == "DE"


def test_build_params_strips_text(tmp_path):
    """build_params strips whitespace from text fields."""
    csv_path = tmp_path / "songs.csv"
    params = vm.build_params(f"  {csv_path}  ", "  Playlist  ", description="  desc  ")

    assert params.csv_path == csv_path
    assert params.playlist_name == "Playlist"
    assert params.description == "desc"


def test_build_params_rounds_min_score(tmp_path):
    """build_params rounds min_score to 4 decimal places."""
    params = vm.build_params(str(tmp_path / "songs.csv"), "Playlist", min_score=0.123456789)

    assert params.min_score == 0.1235


def test_build_params_types(tmp_path):
    """build_params converts limit to int and public/dry_run to bool."""
    params = vm.build_params(
        str(tmp_path / "songs.csv"),
        "Playlist",
        public=1,
        limit="7",
        dry_run=0,
    )

    assert params.limit == 7
    assert isinstance(params.limit, int)
    assert params.public is True
    assert params.dry_run is False


def test_build_params_caps_limit(tmp_path):
    """Spotify nimmt seit Februar 2026 höchstens 10 Treffer pro Suche an."""
    params = vm.build_params(str(tmp_path / "songs.csv"), "Playlist", limit="50")

    assert params.limit == 10


def test_format_score_zero_is_empty():
    """format_score returns an empty string for a score of zero."""
    assert vm.format_score(0.0) == ""


def test_format_score_two_decimals():
    """format_score formats with two decimal places."""
    assert vm.format_score(0.8567) == "0.86"


def test_status_label_known():
    """status_label translates all known statuses."""
    assert vm.status_label("found") == "Gefunden"
    assert vm.status_label("not_found") == "Nicht gefunden"
    assert vm.status_label("error") == "Fehler"


def test_status_label_unknown_falls_back():
    """status_label falls back to the raw status for unknown values."""
    assert vm.status_label("mystery") == "mystery"


def test_result_row_values_found():
    """result_row_values returns six values with a joined matched string."""
    row = ResultRow(
        row=2,
        title="Song",
        artist="Artist",
        status="found",
        reason="",
        matched_title="Matched Song",
        matched_artists="Matched Artist",
        spotify_url="https://open.spotify.com/track/x",
        score=0.9,
    )

    values = vm.result_row_values(row)

    assert len(values) == 6
    assert "—" in values[4]
    assert values[4] == "Matched Song — Matched Artist"


def test_result_row_values_only_title():
    """result_row_values uses just the matched title when no artist matched."""
    row = ResultRow(
        row=2,
        title="Song",
        artist="Artist",
        status="found",
        reason="",
        matched_title="Matched Song",
        matched_artists="",
        spotify_url="https://open.spotify.com/track/x",
        score=0.9,
    )

    values = vm.result_row_values(row)

    assert values[4] == "Matched Song"


def test_result_row_values_error_uses_reason():
    """result_row_values falls back to the reason when nothing matched."""
    row = ResultRow(
        row=2,
        title="Song",
        artist="Artist",
        status="error",
        reason="Kein passender Track gefunden",
        matched_title="",
        matched_artists="",
        spotify_url="",
        score=0.0,
    )

    values = vm.result_row_values(row)

    assert values[4] == "Kein passender Track gefunden"


def test_summary_line_format():
    """summary_line produces the exact expected format."""
    rows = [
        ResultRow(row=2, title="A", artist="", status="found", reason="", matched_title="A", matched_artists="", spotify_url="", score=1.0),
        ResultRow(row=3, title="B", artist="", status="not_found", reason="x", matched_title="", matched_artists="", spotify_url="", score=0.0),
        ResultRow(row=4, title="C", artist="", status="error", reason="y", matched_title="", matched_artists="", spotify_url="", score=0.0),
    ]

    assert vm.summary_line(rows) == "3 gesamt · 1 gefunden · 1 nicht gefunden · 1 Fehler"


def test_sort_key_numeric_columns():
    """sort_key returns a float for the row and score columns."""
    values = ("3", "Title", "Artist", "Gefunden", "Matched", "0.75")

    assert vm.sort_key(values, 0) == 3.0
    assert vm.sort_key(values, 5) == 0.75


def test_sort_key_text_columns():
    """sort_key returns a lowercased string for non-numeric columns."""
    values = ("3", "Title", "Artist", "Gefunden", "Matched", "0.75")

    assert vm.sort_key(values, 1) == "title"


def test_sort_key_invalid_number():
    """sort_key falls back to -1.0 for an empty/invalid numeric value."""
    values = ("3", "Title", "Artist", "Gefunden", "Matched", "")

    assert vm.sort_key(values, 5) == -1.0
