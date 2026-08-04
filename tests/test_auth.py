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

class _TokenCheckResponse:
    """Fake token-endpoint response carrying an OAuth error payload."""

    def __init__(self, status_code=400, payload=None, raise_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._payload


class _TokenCheckSession:
    """Session whose post() returns a fixed response and records the call."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.posts = []

    def post(self, url, data=None, **kwargs):
        self.posts.append({"url": url, "data": data, "kwargs": kwargs})
        if self._error is not None:
            raise self._error
        return self._response


def test_check_credentials_empty_client_id_fails():
    """An empty client ID is rejected without any network call."""
    config = Config(client_id="", redirect_uri="http://127.0.0.1:8888/callback",
                    token_path=Path("/tmp/t.json"), client_secret="")
    session = _TokenCheckSession(_TokenCheckResponse())

    outcome = check_credentials(config, session=session)

    assert outcome.status == CHECK_INVALID
    assert session.posts == []


def test_check_credentials_invalid_client_is_rejected():
    """invalid_client means Spotify does not know this client ID."""
    session = _TokenCheckSession(_TokenCheckResponse(401, {"error": "invalid_client"}))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_INVALID


def test_check_credentials_truncated_id_is_rejected():
    """A half-deleted client ID must be reported as invalid, never as accepted."""
    config = Config(client_id="7919cf77251c", redirect_uri="http://127.0.0.1:8888/callback",
                    token_path=Path("/tmp/t.json"), client_secret="")
    session = _TokenCheckSession(_TokenCheckResponse(400, {"error": "invalid_client"}))

    outcome = check_credentials(config, session=session)

    assert outcome.status == CHECK_INVALID
    assert outcome.ok is False


def test_check_credentials_invalid_grant_proves_client_id_is_valid():
    """invalid_grant means only our deliberately bogus code was refused: the ID is good."""
    session = _TokenCheckSession(
        _TokenCheckResponse(400, {"error": "invalid_grant",
                                  "error_description": "Invalid authorization code"})
    )

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_OK


def test_check_credentials_reports_redirect_uri_mismatch():
    """A redirect-URI complaint is surfaced specifically."""
    session = _TokenCheckSession(
        _TokenCheckResponse(400, {"error": "invalid_grant",
                                  "error_description": "Invalid redirect URI"})
    )

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_INVALID
    assert "Redirect URI" in outcome.message


def test_check_credentials_unknown_error_is_inconclusive():
    """An unfamiliar OAuth error must not be turned into a pass or a fail."""
    session = _TokenCheckSession(_TokenCheckResponse(400, {"error": "server_error"}))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_UNKNOWN


def test_check_credentials_non_json_response_is_inconclusive():
    """An HTML error page must never be read as a green light."""
    session = _TokenCheckSession(_TokenCheckResponse(200, raise_json=True))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_UNKNOWN
    assert outcome.ok is False


def test_check_credentials_empty_payload_is_inconclusive():
    """A 200 with no error field is not proof of a valid client ID."""
    session = _TokenCheckSession(_TokenCheckResponse(200, {}))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_UNKNOWN


def test_check_credentials_handles_no_network():
    """A connection failure is inconclusive, not a verdict on the client ID."""
    session = _TokenCheckSession(error=requests.exceptions.ConnectionError("no route"))

    outcome = check_credentials(_make_config(), session=session)

    assert outcome.status == CHECK_UNKNOWN
    assert "Verbindung" in outcome.message


def test_check_credentials_sends_timeout_and_client_id():
    """The check cannot hang and sends the client ID being tested."""
    session = _TokenCheckSession(_TokenCheckResponse(400, {"error": "invalid_grant"}))

    check_credentials(_make_config(), session=session)

    assert session.posts[0]["kwargs"]["timeout"] is not None
    assert session.posts[0]["data"]["client_id"] == "cid"
