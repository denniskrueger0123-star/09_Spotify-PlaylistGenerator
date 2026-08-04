"""Tests for matcher module."""

import pytest

from spotify_playlist_generator.matcher import (
    DEFAULT_MIN_SCORE,
    build_queries,
    normalize,
    pick_best,
    score_candidate,
)


def test_normalize_removes_parenthetical_extras():
    """normalize removes content in parentheses."""
    result = normalize("Bohemian Rhapsody (Remastered 2011)")
    assert result == "bohemian rhapsody"


def test_normalize_removes_bracketed_extras():
    """normalize removes content in brackets."""
    result = normalize("Song [Live Version]")
    assert result == "song"


def test_normalize_removes_suffix_after_dash():
    """normalize removes everything after ' - '."""
    result = normalize("Song - Remastered")
    assert result == "song"


def test_normalize_removes_diacritics():
    """normalize removes diacritical marks."""
    result = normalize("Björk")
    assert result == "bjork"


def test_normalize_lowercases():
    """normalize converts to lowercase."""
    result = normalize("HELLO WORLD")
    assert result == "hello world"


def test_normalize_removes_special_chars():
    """normalize removes special characters."""
    result = normalize("Hello@World#123")
    assert result == "hello world 123"


def test_normalize_collapses_spaces():
    """normalize collapses multiple spaces."""
    result = normalize("Hello    World")
    assert result == "hello world"


def test_normalize_strips():
    """normalize strips leading/trailing whitespace."""
    result = normalize("  hello world  ")
    assert result == "hello world"


def test_score_candidate_without_artist():
    """score_candidate without artist uses only title similarity."""
    score = score_candidate("Song One", "", "Song One", ["Artist"])
    assert score > 0.9  # Should be very high for exact match
    assert score == 1.0


def test_score_candidate_with_artist():
    """score_candidate with artist weights title 70% and artist 30%."""
    score = score_candidate("Song One", "Artist One", "Song One", ["Artist One"])
    assert score > 0.9  # Should be high for exact match


def test_score_candidate_partial_match():
    """score_candidate produces reasonable scores for partial matches."""
    score = score_candidate("Song One", "Artist A", "Song One", ["Artist B"])
    assert 0 < score < 1


def test_score_candidate_rounding_with_artist():
    """score_candidate rounds to 4 decimal places with artist matching."""
    # Exact value from coordinator: unrounded = 0.9454545454545453
    score = score_candidate("Bohemian Rhapsody", "Queen", "Bohemian Rapsody", ["Quen"])
    assert score == 0.9455


def test_score_candidate_rounding_without_artist():
    """score_candidate rounds to 4 decimal places without artist."""
    # Exact value from coordinator: unrounded = 0.6060606060606061
    score = score_candidate("Hallelujah", "", "Hallelujah Live Version", [])
    assert score == 0.6061


def test_score_candidate_empty_artist_list():
    """score_candidate handles empty artist list."""
    # With empty artist list, artist_sim is 0.0, so result is 0.7 * title_sim
    # For exact match on title: score_candidate("Song", "Artist", "Song", [])
    # title_sim = 1.0, so result = 0.7 * 1.0 = 0.7
    score = score_candidate("Song", "Artist", "Song", [])
    assert score == 0.7


def test_build_queries_with_artist():
    """build_queries returns fielded queries with artist first."""
    queries = build_queries("Song One", "Artist One")
    assert len(queries) >= 2
    assert queries[0] == 'track:"Song One" artist:"Artist One"'
    assert queries[1] == 'track:"Song One"'


def test_build_queries_without_artist():
    """build_queries without artist skips artist fielded query."""
    queries = build_queries("Song One", "")
    assert len(queries) >= 1
    assert 'track:"Song One" artist:' not in queries[0]
    assert queries[0] == 'track:"Song One"'


def test_build_queries_no_duplicates():
    """build_queries removes duplicate entries."""
    # If title and artist are same after normalization, queries should still not duplicate
    queries = build_queries("Song", "")
    unique_queries = set(queries)
    assert len(queries) == len(unique_queries)


def test_build_queries_order_preserved():
    """build_queries preserves order of unique queries."""
    queries = build_queries("Song One", "Artist One")
    # First should be fielded with artist
    assert "artist:" in queries[0]
    # Second should be fielded without artist
    assert "artist:" not in queries[1]


def test_pick_best_exact_match():
    """pick_best selects exact match."""
    items = [
        {
            "uri": "spotify:track:123",
            "id": "123",
            "name": "Song One",
            "artists": [{"name": "Artist One"}],
            "external_urls": {"spotify": "https://example.com/track1"}
        }
    ]
    match = pick_best("Song One", "Artist One", items, DEFAULT_MIN_SCORE)
    assert match is not None
    assert match.name == "Song One"
    assert match.score > 0.9


def test_pick_best_multiple_candidates():
    """pick_best chooses best match from multiple candidates."""
    items = [
        {
            "uri": "spotify:track:1",
            "id": "1",
            "name": "Song One",
            "artists": [{"name": "Artist Two"}],
            "external_urls": {"spotify": "https://example.com/1"}
        },
        {
            "uri": "spotify:track:2",
            "id": "2",
            "name": "Song One",
            "artists": [{"name": "Artist One"}],
            "external_urls": {"spotify": "https://example.com/2"}
        }
    ]
    match = pick_best("Song One", "Artist One", items, DEFAULT_MIN_SCORE)
    assert match is not None
    assert match.track_id == "2"  # Second one should be chosen


def test_pick_best_below_min_score():
    """pick_best returns None if best score is below min_score."""
    items = [
        {
            "uri": "spotify:track:123",
            "id": "123",
            "name": "Completely Different",
            "artists": [{"name": "Other Artist"}],
            "external_urls": {"spotify": "https://example.com/track1"}
        }
    ]
    match = pick_best("Song One", "Artist One", items, 0.9)
    assert match is None


def test_pick_best_empty_list():
    """pick_best returns None for empty candidate list."""
    match = pick_best("Song One", "Artist One", [], DEFAULT_MIN_SCORE)
    assert match is None


def test_pick_best_skips_no_uri():
    """pick_best skips candidates without uri."""
    items = [
        {
            "id": "1",
            "name": "Song One",
            "artists": [{"name": "Artist One"}]
            # No uri field
        },
        {
            "uri": "spotify:track:2",
            "id": "2",
            "name": "Song One",
            "artists": [{"name": "Artist One"}],
            "external_urls": {"spotify": "https://example.com/2"}
        }
    ]
    match = pick_best("Song One", "Artist One", items, DEFAULT_MIN_SCORE)
    # Should skip first (no uri) and use second
    assert match is not None
    assert match.track_id == "2"


def test_pick_best_handles_missing_fields():
    """pick_best handles missing optional fields gracefully."""
    items = [
        {
            "uri": "spotify:track:123",
            "id": "123",
            "name": "Song One",
            # Missing artists
            # Missing external_urls
        }
    ]
    match = pick_best("Song One", "", items, DEFAULT_MIN_SCORE)
    assert match is not None
    assert match.artists == ""
    assert match.url == ""


def test_pick_best_multiple_artists():
    """pick_best handles multiple artists correctly."""
    items = [
        {
            "uri": "spotify:track:123",
            "id": "123",
            "name": "Song One",
            "artists": [
                {"name": "Artist One"},
                {"name": "Artist Two"}
            ],
            "external_urls": {"spotify": "https://example.com/track1"}
        }
    ]
    match = pick_best("Song One", "Artist One", items, DEFAULT_MIN_SCORE)
    assert match is not None
    assert "Artist One" in match.artists


def test_pick_best_score_accuracy():
    """pick_best stores correct score in TrackMatch."""
    items = [
        {
            "uri": "spotify:track:123",
            "id": "123",
            "name": "Song One",
            "artists": [{"name": "Artist One"}],
            "external_urls": {"spotify": "https://example.com/track1"}
        }
    ]
    match = pick_best("Song One", "Artist One", items, DEFAULT_MIN_SCORE)
    assert match.score > 0  # Has a score
    assert isinstance(match.score, float)


def test_normalize_combined_cleanup():
    """normalize combines multiple cleanup steps correctly."""
    result = normalize("Héllo Wörld (Remix) - Extended")
    assert result == "hello world"
    assert "[" not in result
    assert "(" not in result
    assert "-" not in result
