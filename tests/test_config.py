"""Tests for config module."""

import os
from pathlib import Path

import pytest

from spotify_playlist_generator.config import (
    DEFAULT_REDIRECT_URI,
    DEFAULT_TOKEN_PATH,
    Config,
    load_config,
    load_dotenv,
)
from spotify_playlist_generator.errors import ConfigError


def test_load_dotenv_basic(tmp_path):
    """load_dotenv reads key=value pairs from .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY1=value1\nKEY2=value2\n")

    result = load_dotenv(env_file)

    assert result == {"KEY1": "value1", "KEY2": "value2"}


def test_load_dotenv_with_comments(tmp_path):
    """load_dotenv ignores lines starting with #."""
    env_file = tmp_path / ".env"
    env_file.write_text("# This is a comment\nKEY=value\n# Another comment\n")

    result = load_dotenv(env_file)

    assert result == {"KEY": "value"}


def test_load_dotenv_with_empty_lines(tmp_path):
    """load_dotenv ignores empty lines."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY1=value1\n\nKEY2=value2\n")

    result = load_dotenv(env_file)

    assert result == {"KEY1": "value1", "KEY2": "value2"}


def test_load_dotenv_with_double_quotes(tmp_path):
    """load_dotenv removes surrounding double quotes."""
    env_file = tmp_path / ".env"
    env_file.write_text('KEY="value"\n')

    result = load_dotenv(env_file)

    assert result == {"KEY": "value"}


def test_load_dotenv_with_single_quotes(tmp_path):
    """load_dotenv removes surrounding single quotes."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY='value'\n")

    result = load_dotenv(env_file)

    assert result == {"KEY": "value"}


def test_load_dotenv_equals_in_value(tmp_path):
    """load_dotenv splits at first = only."""
    env_file = tmp_path / ".env"
    env_file.write_text("KEY=value=with=equals\n")

    result = load_dotenv(env_file)

    assert result == {"KEY": "value=with=equals"}


def test_load_dotenv_whitespace_stripping(tmp_path):
    """load_dotenv strips whitespace around keys and values."""
    env_file = tmp_path / ".env"
    env_file.write_text("  KEY  =  value  \n")

    result = load_dotenv(env_file)

    assert result == {"KEY": "value"}


def test_load_dotenv_nonexistent_file():
    """load_dotenv returns empty dict if file doesn't exist."""
    result = load_dotenv(Path("/nonexistent/path/.env"))

    assert result == {}


def test_load_dotenv_partial_quotes(tmp_path):
    """load_dotenv only removes matching surrounding quotes."""
    env_file = tmp_path / ".env"
    env_file.write_text('KEY="value\n')

    result = load_dotenv(env_file)

    # Should not remove unmatched quote
    assert result == {"KEY": '"value'}


def test_load_config_with_client_id(monkeypatch, tmp_path):
    """load_config creates Config with SPOTIFY_CLIENT_ID."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    monkeypatch.delenv("SPOTIFY_TOKEN_PATH", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("SPOTIFY_CLIENT_ID=test_client_id\n")

    config = load_config(env_file)

    assert config.client_id == "test_client_id"
    assert config.redirect_uri == DEFAULT_REDIRECT_URI
    assert config.token_path == DEFAULT_TOKEN_PATH


def test_load_config_missing_client_id(monkeypatch, tmp_path):
    """load_config raises ConfigError if SPOTIFY_CLIENT_ID is missing."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    monkeypatch.delenv("SPOTIFY_TOKEN_PATH", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("")

    with pytest.raises(ConfigError) as exc_info:
        load_config(env_file)

    assert "SPOTIFY_CLIENT_ID" in str(exc_info.value)


def test_load_config_environ_takes_precedence(monkeypatch, tmp_path):
    """os.environ has precedence over .env file."""
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "env_client_id")
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    monkeypatch.delenv("SPOTIFY_TOKEN_PATH", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("SPOTIFY_CLIENT_ID=file_client_id\n")

    config = load_config(env_file)

    assert config.client_id == "env_client_id"


def test_load_config_custom_redirect_uri(monkeypatch, tmp_path):
    """load_config reads SPOTIFY_REDIRECT_URI from environ or .env."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    monkeypatch.delenv("SPOTIFY_TOKEN_PATH", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("SPOTIFY_CLIENT_ID=test_id\nSPOTIFY_REDIRECT_URI=http://custom:9999/callback\n")

    config = load_config(env_file)

    assert config.redirect_uri == "http://custom:9999/callback"


def test_load_config_custom_token_path(monkeypatch, tmp_path):
    """load_config reads SPOTIFY_TOKEN_PATH from environ or .env."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    monkeypatch.delenv("SPOTIFY_TOKEN_PATH", raising=False)

    custom_token_path = "/custom/path/token.json"
    env_file = tmp_path / ".env"
    env_file.write_text(f"SPOTIFY_CLIENT_ID=test_id\nSPOTIFY_TOKEN_PATH={custom_token_path}\n")

    config = load_config(env_file)

    assert str(config.token_path) == custom_token_path


def test_load_config_environ_token_path_precedence(monkeypatch, tmp_path):
    """os.environ SPOTIFY_TOKEN_PATH takes precedence over .env."""
    custom_token_path = "/env/path/token.json"
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    monkeypatch.setenv("SPOTIFY_TOKEN_PATH", custom_token_path)

    env_file = tmp_path / ".env"
    env_file.write_text("SPOTIFY_CLIENT_ID=test_id\nSPOTIFY_TOKEN_PATH=/other/path/token.json\n")

    config = load_config(env_file)

    assert str(config.token_path) == custom_token_path


def test_load_config_default_env_file(monkeypatch, tmp_path):
    """load_config uses .env in current directory by default."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    monkeypatch.delenv("SPOTIFY_TOKEN_PATH", raising=False)

    # When env_file is None, it defaults to Path(".env")
    # Since the file doesn't exist, it should try to read from it but get nothing
    # So this should raise ConfigError
    with pytest.raises(ConfigError):
        load_config(None)
