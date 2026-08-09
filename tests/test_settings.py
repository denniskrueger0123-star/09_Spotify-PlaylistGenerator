"""Tests for settings module."""

import os

import pytest

import spotify_playlist_generator.settings as settings_module
from spotify_playlist_generator.settings import (
    clear_settings,
    load_settings,
    save_settings,
)


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path):
    """Keep the real user settings file out of these tests."""
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", tmp_path / "no-settings.json")


def test_load_settings_missing_file_returns_empty(tmp_path):
    """load_settings returns an empty dict if the file doesn't exist."""
    path = tmp_path / "settings.json"

    result = load_settings(path)

    assert result == {}


def test_load_settings_broken_json_returns_empty(tmp_path):
    """load_settings returns an empty dict instead of raising on broken JSON."""
    path = tmp_path / "settings.json"
    path.write_text("das ist kein json{{")

    result = load_settings(path)

    assert result == {}


def test_load_settings_non_dict_returns_empty(tmp_path):
    """load_settings returns an empty dict if the JSON root is not an object."""
    path = tmp_path / "settings.json"
    path.write_text("[1,2,3]")

    result = load_settings(path)

    assert result == {}


def test_load_settings_filters_unknown_keys(tmp_path):
    """load_settings only keeps keys listed in SETTINGS_KEYS."""
    path = tmp_path / "settings.json"
    path.write_text('{"client_id": "abc", "hacker": "x"}')

    result = load_settings(path)

    assert result == {"client_id": "abc"}


def test_load_settings_strips_and_drops_empty(tmp_path):
    """load_settings strips values and drops entries that become empty."""
    path = tmp_path / "settings.json"
    path.write_text('{"client_id": "  abc  ", "client_secret": "   "}')

    result = load_settings(path)

    assert result == {"client_id": "abc"}
    assert "client_secret" not in result


def test_save_and_load_roundtrip(tmp_path):
    """save_settings followed by load_settings returns the same data."""
    path = tmp_path / "settings.json"
    data = {
        "client_id": "abc",
        "client_secret": "def",
        "redirect_uri": "http://localhost/callback",
        "token_path": "/tmp/token.json",
    }

    save_settings(data, path)
    result = load_settings(path)

    assert result == data


def test_save_settings_creates_parent_dir(tmp_path):
    """save_settings creates missing parent directories."""
    path = tmp_path / "a" / "b" / "settings.json"

    save_settings({"client_id": "abc"}, path)

    assert path.exists()
    assert load_settings(path) == {"client_id": "abc"}


def test_save_settings_drops_empty_values(tmp_path):
    """save_settings does not persist empty or whitespace-only values."""
    path = tmp_path / "settings.json"

    save_settings({"client_id": "abc", "client_secret": "   "}, path)

    result = load_settings(path)

    assert result == {"client_id": "abc"}


@pytest.mark.skipif(os.name == "nt", reason="POSIX only")
def test_save_settings_permissions(tmp_path):
    """save_settings restricts file permissions to 0600."""
    path = tmp_path / "settings.json"

    save_settings({"client_id": "abc"}, path)

    assert oct(path.stat().st_mode)[-3:] == "600"


def test_clear_settings_removes_file(tmp_path):
    """clear_settings deletes an existing settings file."""
    path = tmp_path / "settings.json"
    save_settings({"client_id": "abc"}, path)
    assert path.exists()

    clear_settings(path)

    assert not path.exists()


def test_clear_settings_missing_file_no_error(tmp_path):
    """clear_settings does not raise if the file doesn't exist."""
    path = tmp_path / "settings.json"

    clear_settings(path)  # Should not raise


def test_save_and_load_language_setting(tmp_path):
    """language setting is saved and loaded correctly."""
    path = tmp_path / "settings.json"
    data = {"client_id": "abc", "language": "en"}

    save_settings(data, path)
    result = load_settings(path)

    assert result["language"] == "en"


def test_invalid_language_is_rejected(tmp_path):
    """Invalid language value is rejected when loading."""
    path = tmp_path / "settings.json"
    path.write_text('{"client_id": "abc", "language": "invalid_lang"}')

    result = load_settings(path)

    # Invalid language should not be in result
    assert "language" not in result
    # But valid key should still be there
    assert result["client_id"] == "abc"


def test_valid_languages_are_accepted(tmp_path):
    """Valid language values (de, en) are accepted."""
    path = tmp_path / "settings.json"

    for lang in ["de", "en"]:
        path.write_text(f'{{"client_id": "abc", "language": "{lang}"}}')

        result = load_settings(path)

        assert result["language"] == lang
