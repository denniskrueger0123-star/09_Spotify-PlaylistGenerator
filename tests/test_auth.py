"""Tests for auth module."""

import time
from pathlib import Path

import pytest

import requests

from spotify_playlist_generator import auth as auth_module
from spotify_playlist_generator.auth import (
    CHECK_INVALID,
    CHECK_OK,
    CHECK_UNKNOWN,
    AuthError,
    SpotifyAuth,
    Token,
    check_credentials,
    has_cached_token,
    reset_token,
    save_token,
)
from spotify_playlist_generator.config import Config


class _StubResponse:
    """Fake response object that mimics a successful token endpoint reply."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "x"

    def json(self):
        """Return the stored JSON payload."""
        return self._payload

    def raise_for_status(self):
        """No-op: stub responses never raise."""
        pass


class _StubSession:
    """Fake session that records posted data and returns a fixed response."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self._status_code = status_code
        self.posts = []

    def post(self, url, data=None, **kwargs):
        """Record the call and return the stubbed response."""
        self.posts.append({"url": url, "data": data, "kwargs": kwargs})
        return _StubResponse(self._payload, self._status_code)


def _make_config(client_secret="", token_path=None):
    """Build a Config for tests, with or without a client secret."""
    return Config(
        client_id="cid",
        redirect_uri="http://127.0.0.1:8888/callback",
        token_path=token_path or Path("/tmp/does-not-matter-token.json"),
        client_secret=client_secret,
    )


_TOKEN_PAYLOAD = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}


# --- Client Secret ---

def test_exchange_code_includes_secret_when_set():
    """_exchange_code sends client_secret in the payload when configured."""
    config = _make_config(client_secret="geheim")
    session = _StubSession(_TOKEN_PAYLOAD)
    sa = SpotifyAuth(config, session=session)

    sa._exchange_code("code", "verifier")

    assert session.posts[0]["data"]["client_secret"] == "geheim"


def test_exchange_code_sets_request_timeout():
    """_exchange_code passes a timeout so a hanging token endpoint can't block forever."""
    config = _make_config()
    session = _StubSession(_TOKEN_PAYLOAD)
    sa = SpotifyAuth(config, session=session)

    sa._exchange_code("code", "verifier")

    assert session.posts[0]["kwargs"]["timeout"] is not None


def test_refresh_sets_request_timeout():
    """_refresh passes a timeout so a hanging token endpoint can't block forever."""
    config = _make_config()
    session = _StubSession(_TOKEN_PAYLOAD)
    sa = SpotifyAuth(config, session=session)
    token = Token(access_token="old", refresh_token="rt", expires_at=0.0)

    sa._refresh(token)

    assert session.posts[0]["kwargs"]["timeout"] is not None


def test_exchange_code_omits_secret_when_empty():
    """_exchange_code does not include client_secret when not configured."""
    config = _make_config(client_secret="")
    session = _StubSession(_TOKEN_PAYLOAD)
    sa = SpotifyAuth(config, session=session)

    sa._exchange_code("code", "verifier")

    assert "client_secret" not in session.posts[0]["data"]


def test_refresh_includes_secret_when_set():
    """_refresh sends client_secret in the payload when configured."""
    config = _make_config(client_secret="geheim")
    session = _StubSession(_TOKEN_PAYLOAD)
    sa = SpotifyAuth(config, session=session)
    token = Token(access_token="old", refresh_token="rt", expires_at=0.0)

    sa._refresh(token)

    assert session.posts[0]["data"]["client_secret"] == "geheim"


def test_refresh_omits_secret_when_empty():
    """_refresh does not include client_secret when not configured."""
    config = _make_config(client_secret="")
    session = _StubSession(_TOKEN_PAYLOAD)
    sa = SpotifyAuth(config, session=session)
    token = Token(access_token="old", refresh_token="rt", expires_at=0.0)

    sa._refresh(token)

    assert "client_secret" not in session.posts[0]["data"]


# --- has_cached_token ---

def test_has_cached_token_no_file(tmp_path):
    """has_cached_token returns False when there is no token file."""
    path = tmp_path / "token.json"

    assert has_cached_token(path) is False


def test_has_cached_token_valid(tmp_path):
    """has_cached_token returns True for a non-expired token."""
    path = tmp_path / "token.json"
    token = Token(access_token="at", refresh_token="rt", expires_at=time.time() + 3600)
    save_token(path, token)

    assert has_cached_token(path) is True


def test_has_cached_token_expired_with_refresh(tmp_path):
    """has_cached_token returns True for an expired token with a refresh_token."""
    path = tmp_path / "token.json"
    token = Token(access_token="at", refresh_token="rt", expires_at=time.time() - 3600)
    save_token(path, token)

    assert has_cached_token(path) is True


def test_has_cached_token_expired_without_refresh(tmp_path):
    """has_cached_token returns False for an expired token without a refresh_token."""
    path = tmp_path / "token.json"
    token = Token(access_token="at", refresh_token="", expires_at=time.time() - 3600)
    save_token(path, token)

    assert has_cached_token(path) is False


# --- reset_token ---

def test_reset_token_removes_file(tmp_path):
    """reset_token deletes an existing token file."""
    path = tmp_path / "token.json"
    token = Token(access_token="at", refresh_token="rt", expires_at=time.time() + 3600)
    save_token(path, token)

    reset_token(path)

    assert not path.exists()


def test_reset_token_missing_file_no_error(tmp_path):
    """reset_token does not raise when the file does not exist."""
    path = tmp_path / "does-not-exist.json"

    reset_token(path)  # should not raise


# --- Login timeout ---

class _FakeHTTPServer:
    """Fake HTTPServer that simulates a timed-out handle_request call."""

    def __init__(self, addr, handler):
        pass

    def handle_request(self):
        """Simulate a timeout by invoking handle_timeout."""
        self.handle_timeout()

    def server_close(self):
        """No-op close."""
        pass


def test_run_login_flow_raises_on_timeout(monkeypatch, tmp_path):
    """_run_login_flow raises AuthError when the callback server times out."""
    monkeypatch.setattr(auth_module.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(auth_module, "HTTPServer", _FakeHTTPServer)

    config = _make_config(token_path=tmp_path / "token.json")
    sa = SpotifyAuth(config, login_timeout=5)

    with pytest.raises(AuthError, match="Zeitüberschreitung"):
        sa._run_login_flow()


# --- check_credentials ---

class _CheckResponse:
    """Fake response for the authorize endpoint check."""

    def __init__(self, status_code=302, location=""):
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}


class _CheckSession:
    """Session whose get() returns a fixed response and records the call."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    def get(self, url, params=None, **kwargs):
        self.calls.append({"url": url, "params": params, "kwargs": kwargs})
        if self._error is not None:
            raise self._error
        return self._response


def test_check_credentials_empty_client_id_fails():
    """An empty client ID is rejected without any network call."""
    config = _make_config()
    config = Config(client_id="", redirect_uri=config.redirect_uri,
                    token_path=config.token_path, client_secret="")
    session = _CheckSession(_CheckResponse())

    outcome = check_credentials(config, session=session)

    assert outcome.status == CHECK_INVALID
    assert session.calls == []


def test_check_credentials_accepts_redirect_to_login():
    """A redirect without an error parameter means Spotify accepted the client ID."""
    session = _CheckSession(_CheckResponse(302, "https://accounts.spotify.com/login?continue=x"))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_OK


def test_check_credentials_detects_invalid_client_id():
    """An OAuth error parameter means the client ID is not accepted."""
    session = _CheckSession(_CheckResponse(302, "https://example.com/cb?error=invalid_client"))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_INVALID


def test_check_credentials_detects_redirect_uri_mismatch():
    """A redirect_uri error is reported with a specific message."""
    session = _CheckSession(_CheckResponse(302, "https://example.com/cb?error=invalid_redirect_uri"))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_INVALID
    assert "Redirect URI" in outcome.message


def test_check_credentials_handles_no_network():
    """A connection failure is reported instead of raising."""
    session = _CheckSession(error=requests.exceptions.ConnectionError("no route"))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_UNKNOWN
    assert "Verbindung" in outcome.message


def test_check_credentials_sends_timeout():
    """The check passes a timeout so it cannot hang forever."""
    session = _CheckSession(_CheckResponse(302, "https://accounts.spotify.com/login"))

    check_credentials(_make_config(), session=session)

    assert session.calls[0]["kwargs"]["timeout"] is not None


def test_check_credentials_unexpected_200_is_not_a_pass():
    """A 200 (e.g. an HTML error page) must NOT be reported as a valid client ID."""
    session = _CheckSession(_CheckResponse(200, ""))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_UNKNOWN
    assert outcome.ok is False


def test_check_credentials_ignores_error_substring_elsewhere_in_url():
    """The word 'error' outside the OAuth error parameter must not fail the check."""
    session = _CheckSession(
        _CheckResponse(302, "https://accounts.spotify.com/login?continue=https%3A%2F%2Ferror_page")
    )

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_OK


def test_check_credentials_sends_pkce_params_like_the_real_login():
    """The check mirrors the real login request so its verdict is meaningful."""
    session = _CheckSession(_CheckResponse(302, "https://accounts.spotify.com/login?continue=x"))

    check_credentials(_make_config(), session=session)

    params = session.calls[0]["params"]
    assert params["code_challenge_method"] == "S256"
    assert params["code_challenge"]
