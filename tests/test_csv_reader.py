"""Tests for csv_reader module."""

from pathlib import Path

import pytest

from spotify_playlist_generator.csv_reader import read_songs
from spotify_playlist_generator.errors import CsvError


def test_read_songs_basic(tmp_path):
    """read_songs parses a basic CSV file with title and artist."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\nSong One,Artist One\nSong Two,Artist Two\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 2
    assert len(skipped) == 0
    assert songs[0].title == "Song One"
    assert songs[0].artist == "Artist One"
    assert songs[1].title == "Song Two"
    assert songs[1].artist == "Artist Two"


def test_read_songs_german_headers(tmp_path):
    """read_songs recognizes German header names."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("Titel;Interpret\nLied Eins;Künstler Eins\nLied Zwei;Künstler Zwei\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 2
    assert songs[0].title == "Lied Eins"
    assert songs[0].artist == "Künstler Eins"


def test_read_songs_no_artist_column(tmp_path):
    """read_songs handles CSV without artist column."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title\nSong One\nSong Two\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 2
    assert songs[0].artist == ""
    assert songs[1].artist == ""


def test_read_songs_empty_title_in_skipped(tmp_path):
    """read_songs puts rows with empty title in skipped list."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\nSong One,Artist One\n,Artist Two\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 1
    assert len(skipped) == 1
    assert skipped[0]["row"] == 3
    assert skipped[0]["reason"] == "Kein Titel in dieser Zeile"


def test_read_songs_missing_title_column(tmp_path):
    """read_songs raises CsvError if title column is missing."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("artist,year\nArtist One,2021\n")

    with pytest.raises(CsvError) as exc_info:
        read_songs(csv_file)

    assert "Titel" in str(exc_info.value) or "title" in str(exc_info.value).lower()


def test_read_songs_nonexistent_file():
    """read_songs raises CsvError if file doesn't exist."""
    with pytest.raises(CsvError) as exc_info:
        read_songs(Path("/nonexistent/songs.csv"))

    assert "nicht gefunden" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()


def test_read_songs_with_bom(tmp_path):
    """read_songs handles BOM at file start."""
    csv_file = tmp_path / "songs.csv"
    # Write BOM + content
    content = "﻿title,artist\nSong One,Artist One\n"
    csv_file.write_text(content)

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 1
    assert songs[0].title == "Song One"


def test_read_songs_examples_file():
    """read_songs parses examples/songs.csv correctly."""
    examples_file = Path(__file__).resolve().parent.parent / "examples" / "songs.csv"

    songs, skipped = read_songs(examples_file)

    assert len(songs) == 6
    assert len(skipped) == 0
    # Check specific songs
    assert songs[0].title == "Bohemian Rhapsody"
    assert songs[0].artist == "Queen"
    assert songs[3].title == "Hallelujah"
    assert songs[3].artist == ""


def test_read_songs_row_numbers(tmp_path):
    """read_songs records correct 1-based row numbers."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\nSong One,Artist One\nSong Two,Artist Two\n")

    songs, skipped = read_songs(csv_file)

    assert songs[0].row == 2  # First data row is line 2 (after header)
    assert songs[1].row == 3


def test_read_songs_whitespace_stripping(tmp_path):
    """read_songs strips whitespace from title and artist."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\n  Song One  ,  Artist One  \n")

    songs, skipped = read_songs(csv_file)

    assert songs[0].title == "Song One"
    assert songs[0].artist == "Artist One"


def test_read_songs_empty_rows_skipped_silently(tmp_path):
    """read_songs silently skips completely empty rows."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\nSong One,Artist One\n\nSong Two,Artist Two\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 2
    assert songs[0].title == "Song One"
    assert songs[1].title == "Song Two"


def test_read_songs_alternative_header_names(tmp_path):
    """read_songs recognizes alternative header names."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("track,band\nSong One,Band One\nSong Two,Band Two\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 2
    assert songs[0].title == "Song One"
    assert songs[0].artist == "Band One"


def test_read_songs_comma_delimiter(tmp_path):
    """read_songs auto-detects comma delimiter."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist\nSong One,Artist One\nSong Two,Artist Two\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 2


def test_read_songs_semicolon_delimiter(tmp_path):
    """read_songs auto-detects semicolon delimiter."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title;artist\nSong One;Artist One\nSong Two;Artist Two\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 2
    assert songs[0].artist == "Artist One"


def test_read_songs_tab_delimiter(tmp_path):
    """read_songs auto-detects tab delimiter."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title\tartist\nSong One\tArtist One\nSong Two\tArtist Two\n")

    songs, skipped = read_songs(csv_file)

    assert len(songs) == 2
    assert songs[0].artist == "Artist One"


def test_read_songs_preserves_raw_dict(tmp_path):
    """read_songs preserves raw row data."""
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text("title,artist,year\nSong One,Artist One,2021\n")

    songs, skipped = read_songs(csv_file)

    assert songs[0].raw["title"] == "Song One"
    assert songs[0].raw["artist"] == "Artist One"
    assert songs[0].raw["year"] == "2021"
