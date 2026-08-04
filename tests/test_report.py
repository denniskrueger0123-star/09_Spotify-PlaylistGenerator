"""Tests for report module."""

import csv
from pathlib import Path

import pytest

from spotify_playlist_generator.report import (
    ResultRow,
    format_summary,
    summarize,
    write_report,
)


def test_write_report_creates_file(tmp_path):
    """write_report writes report file."""
    report_file = tmp_path / "report.csv"
    rows = [
        ResultRow(
            row=2,
            title="Song One",
            artist="Artist One",
            status="found",
            reason="",
            matched_title="Song One",
            matched_artists="Artist One",
            spotify_url="https://spotify.com/1",
            score=0.95
        )
    ]

    write_report(report_file, rows)

    assert report_file.exists()


def test_write_report_contains_header(tmp_path):
    """write_report includes CSV header."""
    report_file = tmp_path / "report.csv"
    rows = [
        ResultRow(
            row=2,
            title="Song",
            artist="Artist",
            status="found",
            reason="",
            matched_title="Song",
            matched_artists="Artist",
            spotify_url="https://spotify.com/1",
            score=0.95
        )
    ]

    write_report(report_file, rows)

    with open(report_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        assert "row" in reader.fieldnames
        assert "title" in reader.fieldnames
        assert "status" in reader.fieldnames


def test_write_report_readable_by_dictreader(tmp_path):
    """write_report output is readable by csv.DictReader."""
    report_file = tmp_path / "report.csv"
    rows = [
        ResultRow(
            row=2,
            title="Song One",
            artist="Artist One",
            status="found",
            reason="",
            matched_title="Song One",
            matched_artists="Artist One",
            spotify_url="https://spotify.com/1",
            score=0.95
        ),
        ResultRow(
            row=3,
            title="Song Two",
            artist="Artist Two",
            status="not_found",
            reason="No match found",
            matched_title="",
            matched_artists="",
            spotify_url="",
            score=0.0
        )
    ]

    write_report(report_file, rows)

    with open(report_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        read_rows = list(reader)

    assert len(read_rows) == 2
    assert read_rows[0]["title"] == "Song One"
    assert read_rows[0]["status"] == "found"
    assert read_rows[1]["title"] == "Song Two"
    assert read_rows[1]["status"] == "not_found"


def test_write_report_creates_parent_directory(tmp_path):
    """write_report creates parent directory if needed."""
    report_file = tmp_path / "reports" / "subdir" / "report.csv"
    rows = [
        ResultRow(
            row=2,
            title="Song",
            artist="Artist",
            status="found",
            reason="",
            matched_title="Song",
            matched_artists="Artist",
            spotify_url="https://spotify.com/1",
            score=0.95
        )
    ]

    write_report(report_file, rows)

    assert report_file.exists()
    assert report_file.parent.exists()


def test_write_report_utf8_encoding(tmp_path):
    """write_report writes with UTF-8 encoding."""
    report_file = tmp_path / "report.csv"
    rows = [
        ResultRow(
            row=2,
            title="Björk",
            artist="Künstler",
            status="found",
            reason="",
            matched_title="Björk",
            matched_artists="Künstler",
            spotify_url="https://spotify.com/1",
            score=0.95
        )
    ]

    write_report(report_file, rows)

    with open(report_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Björk" in content
    assert "Künstler" in content


def test_summarize_all_found():
    """summarize counts correctly for all found."""
    rows = [
        ResultRow(2, "S1", "A1", "found", "", "S1", "A1", "url", 0.95),
        ResultRow(3, "S2", "A2", "found", "", "S2", "A2", "url", 0.95),
    ]

    summary = summarize(rows)

    assert summary["found"] == 2
    assert summary["not_found"] == 0
    assert summary["error"] == 0
    assert summary["total"] == 2


def test_summarize_mixed_status():
    """summarize counts correctly for mixed status."""
    rows = [
        ResultRow(2, "S1", "A1", "found", "", "S1", "A1", "url", 0.95),
        ResultRow(3, "S2", "A2", "not_found", "No match", "", "", "", 0.0),
        ResultRow(4, "S3", "A3", "error", "Network error", "", "", "", 0.0),
    ]

    summary = summarize(rows)

    assert summary["found"] == 1
    assert summary["not_found"] == 1
    assert summary["error"] == 1
    assert summary["total"] == 3


def test_summarize_empty_list():
    """summarize handles empty list."""
    summary = summarize([])

    assert summary["found"] == 0
    assert summary["not_found"] == 0
    assert summary["error"] == 0
    assert summary["total"] == 0


def test_format_summary_all_found():
    """format_summary returns success message when all found."""
    rows = [
        ResultRow(2, "S1", "A1", "found", "", "S1", "A1", "url", 0.95),
        ResultRow(3, "S2", "A2", "found", "", "S2", "A2", "url", 0.95),
    ]

    result = format_summary(rows)

    assert "2" in result  # Total
    assert "Gefunden" in result or "found" in result.lower()
    assert "erfolgreich" in result.lower()


def test_format_summary_with_problems():
    """format_summary lists problematic songs."""
    rows = [
        ResultRow(2, "S1", "A1", "found", "", "S1", "A1", "url", 0.95),
        ResultRow(3, "S2", "A2", "not_found", "No match", "", "", "", 0.0),
    ]

    result = format_summary(rows)

    assert "Zeile 3" in result
    assert "S2" in result


def test_format_summary_includes_row_number():
    """format_summary includes row numbers for problems."""
    rows = [
        ResultRow(5, "Bad Song", "Bad Artist", "not_found", "No match", "", "", "", 0.0),
    ]

    result = format_summary(rows)

    assert "Zeile 5" in result


def test_format_summary_includes_reason():
    """format_summary includes reason for each problem."""
    rows = [
        ResultRow(3, "S1", "A1", "error", "Connection timeout", "", "", "", 0.0),
    ]

    result = format_summary(rows)

    assert "Connection timeout" in result


def test_format_summary_includes_artist():
    """format_summary includes artist when present."""
    rows = [
        ResultRow(3, "Song", "Artist Name", "not_found", "No match", "", "", "", 0.0),
    ]

    result = format_summary(rows)

    assert "Artist Name" in result


def test_format_summary_no_artist():
    """format_summary handles missing artist gracefully."""
    rows = [
        ResultRow(3, "Song", "", "not_found", "No match", "", "", "", 0.0),
    ]

    result = format_summary(rows)

    assert "Zeile 3" in result
    assert "Song" in result


def test_format_summary_multiline_output():
    """format_summary produces multiline output."""
    rows = [
        ResultRow(2, "S1", "A1", "found", "", "S1", "A1", "url", 0.95),
        ResultRow(3, "S2", "A2", "not_found", "No match", "", "", "", 0.0),
    ]

    result = format_summary(rows)

    assert "\n" in result


def test_write_report_multiple_rows(tmp_path):
    """write_report handles multiple rows correctly."""
    report_file = tmp_path / "report.csv"
    rows = [
        ResultRow(i+2, f"Song {i}", f"Artist {i}", "found", "", f"Song {i}", f"Artist {i}", f"url{i}", 0.9+i*0.01)
        for i in range(5)
    ]

    write_report(report_file, rows)

    with open(report_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        read_rows = list(reader)

    assert len(read_rows) == 5


def test_format_summary_statistics():
    """format_summary includes complete statistics."""
    rows = [
        ResultRow(2, "S1", "A1", "found", "", "S1", "A1", "url", 0.95),
        ResultRow(3, "S2", "A2", "found", "", "S2", "A2", "url", 0.95),
        ResultRow(4, "S3", "A3", "not_found", "No match", "", "", "", 0.0),
        ResultRow(5, "S4", "A4", "error", "Error", "", "", "", 0.0),
    ]

    result = format_summary(rows)

    assert "Gesamt" in result and "4" in result  # Total
    assert "Gefunden" in result and "2" in result  # Found
    assert "Nicht gefunden" in result and "1" in result  # Not found
    assert "Fehler" in result and "1" in result  # Errors
