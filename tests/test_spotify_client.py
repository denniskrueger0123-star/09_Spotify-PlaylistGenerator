"""Tests for spotify_client module."""

import json
import threading

import pytest
import requests

from spotify_playlist_generator.errors import OperationCancelled, RateLimitError, SpotifyApiError
from spotify_playlist_generator.spotify_client import MAX_SEARCH_LIMIT, SpotifyClient


class FakeResponse:
    """Fake response object for testing."""

    def __init__(self, status_code, json_data=None, headers=None, text=None):
        self.status_code = status_code
        self.json_data = json_data or {}
        self.headers = headers or {}
        # If text is not provided and we have json_data, use the JSON representation
        if text is None:
            self.text = json.dumps(self.json_data) if self.json_data else ""
        else:
            self.text = text

    def json(self):
        """Return JSON data."""
        if isinstance(self.json_data, Exception):
            raise self.json_data
        return self.json_data


class FakeSession:
    """Fake session that replays predefined responses."""

    def __init__(self, responses):
        """
        Initialize with a list of responses.

        Args:
            responses: List of FakeResponse objects to return in order.
        """
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        """Record call and return next response."""
        self.calls.append({
            "method": method,
            "url": url,
            "kwargs": kwargs
        })
        if not self.responses:
            raise RuntimeError("FakeSession: No more responses available")
        return self.responses.pop(0)


def dummy_sleep(seconds):
    """Dummy sleep function that does nothing."""
    pass


def test_search_track_success():
    """search_track returns items from successful response."""
    response_data = {
        "tracks": {
            "items": [
                {
                    "uri": "spotify:track:1",
                    "id": "1",
                    "name": "Song One",
                    "artists": [{"name": "Artist One"}]
                },
                {
                    "uri": "spotify:track:2",
                    "id": "2",
                    "name": "Song Two",
                    "artists": [{"name": "Artist Two"}]
                }
            ]
        }
    }
    session = FakeSession([FakeResponse(200, response_data)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    items = client.search_track("query")

    assert len(items) == 2
    assert items[0]["name"] == "Song One"
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "GET"


def test_search_track_empty_result():
    """search_track returns empty list when no tracks found."""
    response_data = {"tracks": {"items": []}}
    session = FakeSession([FakeResponse(200, response_data)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    items = client.search_track("nonexistent")

    assert items == []


def test_search_track_missing_tracks_field():
    """search_track returns empty list if tracks field is missing."""
    response_data = {}
    session = FakeSession([FakeResponse(200, response_data)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    items = client.search_track("query")

    assert items == []


def test_rate_limit_429_retry_with_sleep():
    """429 response triggers retry and sleep is called."""
    sleep_calls = []

    def tracking_sleep(seconds):
        sleep_calls.append(seconds)

    response_data = {"tracks": {"items": [{"uri": "spotify:track:1", "id": "1", "name": "Song"}]}}
    session = FakeSession([
        FakeResponse(429, headers={"Retry-After": "0"}),
        FakeResponse(200, response_data)
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=tracking_sleep, max_retries=5)

    items = client.search_track("query")

    assert len(items) == 1
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 0


def test_rate_limit_429_persistent_error():
    """Persistent 429 after max_retries raises RateLimitError."""
    session = FakeSession([
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(429, headers={"Retry-After": "1"}),
        FakeResponse(429, headers={"Retry-After": "1"}),
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep, max_retries=5)

    with pytest.raises(RateLimitError) as exc_info:
        client.search_track("query")

    assert exc_info.value.status_code == 429


def test_server_error_500_retry():
    """500 error triggers exponential backoff and retry."""
    sleep_calls = []

    def tracking_sleep(seconds):
        sleep_calls.append(seconds)

    response_data = {"tracks": {"items": [{"uri": "spotify:track:1", "id": "1", "name": "Song"}]}}
    session = FakeSession([
        FakeResponse(500),
        FakeResponse(200, response_data)
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=tracking_sleep, max_retries=5)

    items = client.search_track("query")

    assert len(items) == 1
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 1  # 2^0 = 1


def test_server_error_502_retry():
    """502 error triggers retry."""
    response_data = {"tracks": {"items": [{"uri": "spotify:track:1"}]}}
    session = FakeSession([
        FakeResponse(502),
        FakeResponse(200, response_data)
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep, max_retries=5)

    items = client.search_track("query")

    assert len(items) == 1


def test_server_error_503_retry():
    """503 error triggers retry."""
    response_data = {"tracks": {"items": [{"uri": "spotify:track:1"}]}}
    session = FakeSession([
        FakeResponse(503),
        FakeResponse(200, response_data)
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep, max_retries=5)

    items = client.search_track("query")

    assert len(items) == 1


def test_server_error_504_retry():
    """504 error triggers retry."""
    response_data = {"tracks": {"items": [{"uri": "spotify:track:1"}]}}
    session = FakeSession([
        FakeResponse(504),
        FakeResponse(200, response_data)
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep, max_retries=5)

    items = client.search_track("query")

    assert len(items) == 1


def test_unauthorized_401_retry_once():
    """401 triggers exactly one token_provider() call and retry."""
    token_calls = []

    def tracking_token_provider():
        token_calls.append(1)
        return "new_token"

    response_data = {"tracks": {"items": [{"uri": "spotify:track:1"}]}}
    session = FakeSession([
        FakeResponse(401),
        FakeResponse(200, response_data)
    ])
    client = SpotifyClient(tracking_token_provider, session=session, sleep=dummy_sleep)

    items = client.search_track("query")

    assert len(items) == 1
    assert len(token_calls) == 2  # Initial + one retry


def test_unauthorized_401_persistent_error():
    """Persistent 401 raises SpotifyApiError."""
    session = FakeSession([
        FakeResponse(401),
        FakeResponse(401)
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    with pytest.raises(SpotifyApiError) as exc_info:
        client.search_track("query")

    assert exc_info.value.status_code == 401


def test_not_found_404_error():
    """404 response raises SpotifyApiError."""
    session = FakeSession([FakeResponse(404)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    with pytest.raises(SpotifyApiError) as exc_info:
        client.search_track("query")

    assert exc_info.value.status_code == 404


def test_add_tracks_single_batch():
    """add_tracks with < 100 URIs creates 1 request."""
    session = FakeSession([FakeResponse(200, {})])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    uris = [f"spotify:track:{i}" for i in range(50)]
    added = client.add_tracks("playlist_id", uris)

    assert added == 50
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "POST"


def test_add_tracks_multiple_batches():
    """add_tracks with 101 URIs creates exactly 2 requests."""
    session = FakeSession([
        FakeResponse(200, {}),
        FakeResponse(200, {})
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    uris = [f"spotify:track:{i}" for i in range(101)]
    added = client.add_tracks("playlist_id", uris)

    assert added == 101
    assert len(session.calls) == 2


def test_add_tracks_three_batches():
    """add_tracks with 250 URIs creates 3 requests."""
    session = FakeSession([
        FakeResponse(200, {}),
        FakeResponse(200, {}),
        FakeResponse(200, {})
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    uris = [f"spotify:track:{i}" for i in range(250)]
    added = client.add_tracks("playlist_id", uris)

    assert added == 250
    assert len(session.calls) == 3


def test_add_tracks_empty_list():
    """add_tracks with empty list creates 0 requests."""
    session = FakeSession([])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    added = client.add_tracks("playlist_id", [])

    assert added == 0
    assert len(session.calls) == 0


def test_add_tracks_batch_size():
    """add_tracks sends exactly 100 URIs per request."""
    session = FakeSession([
        FakeResponse(200, {}),
        FakeResponse(200, {})
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    uris = [f"spotify:track:{i}" for i in range(101)]
    client.add_tracks("playlist_id", uris)

    # Check first batch has 100 URIs
    first_call = session.calls[0]
    first_batch = first_call["kwargs"]["json"]["uris"]
    assert len(first_batch) == 100

    # Check second batch has 1 URI
    second_call = session.calls[1]
    second_batch = second_call["kwargs"]["json"]["uris"]
    assert len(second_batch) == 1


def test_current_user():
    """current_user makes GET request to /me."""
    response_data = {"id": "user123", "display_name": "Test User"}
    session = FakeSession([FakeResponse(200, response_data)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    user = client.current_user()

    assert user["id"] == "user123"
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "GET"
    assert "/me" in session.calls[0]["url"]


def test_create_playlist():
    """create_playlist makes POST request with correct body."""
    response_data = {
        "id": "playlist123",
        "name": "Test Playlist",
        "public": False
    }
    session = FakeSession([FakeResponse(200, response_data)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    playlist = client.create_playlist("Test Playlist", public=False, description="Test")

    assert playlist["id"] == "playlist123"
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["kwargs"]["json"]["name"] == "Test Playlist"


def test_create_playlist_uses_me_endpoint():
    """Der alte Pfad /users/{id}/playlists wurde 2026 entfernt und antwortet mit 403."""
    session = FakeSession([FakeResponse(200, {"id": "pl1"})])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    client.create_playlist("Test Playlist")

    url = session.calls[0]["url"]
    assert url.endswith("/me/playlists")
    assert "/users/" not in url


def test_add_tracks_uses_items_endpoint():
    """Playlist-Inhalte werden seit Februar 2026 auf /items geschrieben, nicht /tracks."""
    session = FakeSession([FakeResponse(200, {})])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    client.add_tracks("pl1", ["spotify:track:1"])

    assert session.calls[0]["url"].endswith("/playlists/pl1/items")


def test_search_track_limit_is_capped():
    """Ein zu großer Wert wird gedeckelt, statt die Suche an Spotify scheitern zu lassen."""
    session = FakeSession([FakeResponse(200, {"tracks": {"items": []}})])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    client.search_track("query", limit=50)

    assert session.calls[0]["kwargs"]["params"]["limit"] == MAX_SEARCH_LIMIT


def test_search_track_accepts_tracks_as_list():
    """Liefert Spotify die Treffer direkt als Liste, wird das ebenfalls verstanden."""
    session = FakeSession([FakeResponse(200, {"tracks": [{"uri": "spotify:track:1"}]})])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    items = client.search_track("query")

    assert items == [{"uri": "spotify:track:1"}]


def test_403_error_names_the_common_causes():
    """Ein 403 erklärt Premium-Pflicht, Nutzerliste und Kontingent statt nur 'Forbidden'."""
    payload = {"error": {"status": 403, "message": "Forbidden", "reason": "PREMIUM_REQUIRED"}}
    session = FakeSession([FakeResponse(403, payload)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    with pytest.raises(SpotifyApiError) as exc_info:
        client.search_track("query")

    message = str(exc_info.value)
    assert exc_info.value.status_code == 403
    assert "PREMIUM_REQUIRED" in message
    assert "Premium" in message
    assert "User Management" in message


def test_204_no_content_response():
    """Response with 204 No Content returns empty dict."""
    session = FakeSession([FakeResponse(204)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    result = client.current_user()

    assert result == {}


def test_empty_response_body():
    """Response with empty text returns empty dict."""
    session = FakeSession([FakeResponse(200, text="")])
    session.responses[0].text = ""
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    result = client.current_user()

    assert result == {}


def test_api_error_with_payload():
    """SpotifyApiError includes payload from response."""
    error_payload = {"error": {"message": "Invalid request"}}
    session = FakeSession([FakeResponse(400, error_payload)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    with pytest.raises(SpotifyApiError) as exc_info:
        client.search_track("query")

    assert exc_info.value.status_code == 400
    assert exc_info.value.payload is not None


def test_rate_limit_default_retry_after():
    """429 without Retry-After header defaults to 1 second."""
    sleep_calls = []

    def tracking_sleep(seconds):
        sleep_calls.append(seconds)

    response_data = {"tracks": {"items": []}}
    session = FakeSession([
        FakeResponse(429, headers={}),
        FakeResponse(200, response_data)
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=tracking_sleep)

    client.search_track("query")

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 1


def test_authorization_header_set():
    """Authorization header is set correctly."""
    session = FakeSession([FakeResponse(200, {"tracks": {"items": []}})])
    client = SpotifyClient(lambda: "test_token_123", session=session, sleep=dummy_sleep)

    client.search_track("query")

    assert len(session.calls) == 1
    headers = session.calls[0]["kwargs"].get("headers", {})
    assert headers["Authorization"] == "Bearer test_token_123"


def test_search_with_market_parameter():
    """search_track includes market parameter when provided."""
    session = FakeSession([FakeResponse(200, {"tracks": {"items": []}})])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    client.search_track("query", market="DE", limit=8)

    assert len(session.calls) == 1
    params = session.calls[0]["kwargs"].get("params", {})
    assert params["market"] == "DE"
    assert params["limit"] == 8


def test_request_has_default_timeout():
    """Every request carries a timeout so a hanging connection can't block forever."""
    session = FakeSession([FakeResponse(200, {"tracks": {"items": []}})])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    client.search_track("query")

    assert session.calls[0]["kwargs"]["timeout"] is not None


class HangingSession:
    """Session whose request() simulates a network timeout."""

    def request(self, method, url, **kwargs):
        raise requests.exceptions.Timeout("Connection timed out")


def test_timeout_raises_spotify_api_error_instead_of_hanging():
    """A network timeout is converted into a catchable SpotifyApiError, not an unhandled hang."""
    client = SpotifyClient(lambda: "token", session=HangingSession(), sleep=dummy_sleep)

    with pytest.raises(SpotifyApiError):
        client.search_track("query")


class UnreachableSession:
    """Session whose request() simulates a general connection failure."""

    def request(self, method, url, **kwargs):
        raise requests.exceptions.ConnectionError("Name or service not known")


def test_connection_error_raises_spotify_api_error():
    """A DNS/connection failure is converted into a catchable SpotifyApiError."""
    client = SpotifyClient(lambda: "token", session=UnreachableSession(), sleep=dummy_sleep)

    with pytest.raises(SpotifyApiError):
        client.search_track("query")


def test_rate_limit_retry_wait_is_interrupted_by_cancel():
    """Cancel set mid-retry-wait aborts immediately instead of sleeping through Retry-After."""
    cancel = threading.Event()
    sleep_calls = []

    def tracking_sleep(seconds):
        sleep_calls.append(seconds)
        cancel.set()  # simulate the user clicking "Abbrechen" during the wait

    session = FakeSession([
        FakeResponse(429, headers={"Retry-After": "60"}),
        FakeResponse(200, {"tracks": {"items": []}}),
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=tracking_sleep, cancel=cancel)

    with pytest.raises(OperationCancelled):
        client.search_track("query")

    # Only slept one 1s chunk before the cancel was picked up, not the full 60s.
    assert sleep_calls == [1]


def test_server_error_backoff_is_interrupted_by_cancel():
    """Cancel set mid-backoff-wait aborts immediately instead of sleeping through it."""
    cancel = threading.Event()
    cancel.set()
    session = FakeSession([FakeResponse(500)])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep, cancel=cancel)

    with pytest.raises(OperationCancelled):
        client.search_track("query")


def test_no_cancel_event_behaves_like_before():
    """Without a cancel event, retries behave exactly as before (no OperationCancelled)."""
    session = FakeSession([
        FakeResponse(429, headers={"Retry-After": "0"}),
        FakeResponse(200, {"tracks": {"items": []}}),
    ])
    client = SpotifyClient(lambda: "token", session=session, sleep=dummy_sleep)

    items = client.search_track("query")

    assert items == []
