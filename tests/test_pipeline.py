"""Tests for pipeline module."""

import threading

import pytest

from spotify_playlist_generator.config import Config
from spotify_playlist_generator.errors import OperationCancelled, SpotifyApiError
from spotify_playlist_generator.pipeline import GenerationParams, GenerationResult, run_generation
from spotify_playlist_generator.report import ResultRow


class _StubToken:
    access_token = "test-token"


class _StubAuth:
    def __init__(self):
        self.calls = 0

    def get_token(self):
        self.calls += 1
        return _StubToken()


class _StubClient:
    """Records calls and returns scripted search results.

    search_results may be:
    - a flat list of track dicts, returned identically for every call, or
    - a list of lists, one entry consumed per search_track call (in call order).

    search_error may be:
    - a single Exception instance, raised on every call, or
    - a list where each entry (None or an Exception) applies to one call in order.
    """

    def __init__(self, search_results=None, user=None, playlist=None, search_error=None):
        self._search_results = search_results if search_results is not None else []
        self._user = user if user is not None else {"id": "user1"}
        self._playlist = playlist if playlist is not None else {
            "id": "pl1",
            "external_urls": {"spotify": "https://open.spotify.com/playlist/pl1"},
        }
        self._search_error = search_error
        self.searches = []
        self.created = []
        self.added = []
        self._call_count = 0

    def current_user(self):
        return self._user

    def search_track(self, query, market=None, limit=10):
        self.searches.append({"query": query, "market": market, "limit": limit})
        index = self._call_count
        self._call_count += 1

        if self._search_error is not None:
            if isinstance(self._search_error, list):
                if index < len(self._search_error) and self._search_error[index] is not None:
                    raise self._search_error[index]
            else:
                raise self._search_error

        if self._search_results and isinstance(self._search_results[0], list):
            idx = min(index, len(self._search_results) - 1)
            return self._search_results[idx]

        return self._search_results

    def create_playlist(self, user_id, name, public=False, description=""):
        self.created.append({
            "user_id": user_id,
            "name": name,
            "public": public,
            "description": description,
        })
        return self._playlist

    def add_tracks(self, playlist_id, uris):
        self.added.append({"playlist_id": playlist_id, "uris": list(uris)})
        return len(uris)


def _track(name, artist, uri, url="https://open.spotify.com/track/x"):
    return {
        "uri": uri,
        "id": uri.split(":")[-1],
        "name": name,
        "artists": [{"name": artist}],
        "external_urls": {"spotify": url},
    }


def _config():
    return Config(client_id="cid", redirect_uri="http://127.0.0.1:8888/callback", token_path="/tmp/token.json")


def _write_csv(tmp_path, content):
    csv_file = tmp_path / "songs.csv"
    csv_file.write_text(content, encoding="utf-8")
    return csv_file


def test_run_generation_all_found(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\nSong Two,Artist Two\n")
    client = _StubClient(search_results=[
        [_track("Song One", "Artist One", "spotify:track:1")],
        [_track("Song Two", "Artist Two", "spotify:track:2")],
    ])

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    assert result.counts["found"] == 2
    assert result.exit_code == 0


def test_run_generation_not_found_sets_exit_code_one(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(search_results=[])

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    assert result.rows[0].status == "not_found"
    assert result.rows[0].reason == "Kein passender Track gefunden"
    assert result.exit_code == 1


def test_run_generation_skipped_rows_become_error_rows(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "Titel;Interpret\n;Künstler Eins\nLied Zwei;Künstler Zwei\n",
    )
    client = _StubClient(search_results=[_track("Lied Zwei", "Künstler Zwei", "spotify:track:2")])

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    skipped_rows = [r for r in result.rows if r.status == "error" and r.row == 2]
    assert len(skipped_rows) == 1
    assert skipped_rows[0].artist == "Künstler Eins"


def test_run_generation_dedupes_uris(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "title,artist\nSong One,Artist One\nSong One,Artist One\n",
    )
    client = _StubClient(search_results=[_track("Song One", "Artist One", "spotify:track:1")])

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    run_generation(_config(), params, client=client, auth=_StubAuth())

    assert len(client.added) == 1
    assert client.added[0]["uris"] == ["spotify:track:1"]


def test_run_generation_dry_run_creates_no_playlist(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(search_results=[_track("Song One", "Artist One", "spotify:track:1")])

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist", dry_run=True)
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    assert client.created == []
    assert result.playlist_url == ""


def test_run_generation_creates_playlist_with_params(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(search_results=[_track("Song One", "Artist One", "spotify:track:1")])

    params = GenerationParams(
        csv_path=csv_path,
        playlist_name="My Playlist",
        public=True,
        description="A description",
    )
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    assert len(client.created) == 1
    created = client.created[0]
    assert created["name"] == "My Playlist"
    assert created["public"] is True
    assert created["description"] == "A description"
    assert result.playlist_url == "https://open.spotify.com/playlist/pl1"


def test_run_generation_no_uris_skips_playlist(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(search_results=[])

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    run_generation(_config(), params, client=client, auth=_StubAuth())

    assert client.created == []


def test_run_generation_cancel_stops_early(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(search_results=[_track("Song One", "Artist One", "spotify:track:1")])
    cancel = threading.Event()
    cancel.set()

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    result = run_generation(_config(), params, client=client, auth=_StubAuth(), cancel=cancel)

    assert result.cancelled is True
    assert result.rows == []
    assert client.created == []


def test_run_generation_cancel_during_retry_wait_stops_cleanly(tmp_path):
    """A cancel raised mid-request (e.g. during a rate-limit retry wait) ends the run
    as a normal cancellation, not as an error row for that song."""
    csv_path = _write_csv(
        tmp_path,
        "title,artist\nSong One,Artist One\nSong Two,Artist Two\n",
    )
    client = _StubClient(
        search_results=[[_track("Song One", "Artist One", "spotify:track:1")]],
        search_error=[None, OperationCancelled("Vorgang abgebrochen")],
    )

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    assert result.cancelled is True
    assert len(result.rows) == 1  # Song One made it in, Song Two's cancel stopped the loop
    assert result.rows[0].status == "found"
    assert client.created == []


def test_run_generation_api_error_is_isolated_per_song(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "title,artist\nSong One,Artist One\nSong Two,Artist Two\n",
    )
    client = _StubClient(search_error=[
        SpotifyApiError("boom"),
        None,
    ])
    # Since search_error list contains a None as second entry, our stub needs
    # search_results as fallback for the non-error call.
    client._search_results = [_track("Song Two", "Artist Two", "spotify:track:2")]

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    assert result.rows[0].status == "error"
    assert result.rows[1].status == "found"


def test_run_generation_missing_user_id_raises(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(
        search_results=[_track("Song One", "Artist One", "spotify:track:1")],
        user={},
    )

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    with pytest.raises(SpotifyApiError, match="Benutzerprofil"):
        run_generation(_config(), params, client=client, auth=_StubAuth())


def test_run_generation_missing_playlist_id_raises(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(
        search_results=[_track("Song One", "Artist One", "spotify:track:1")],
        playlist={},
    )

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    with pytest.raises(SpotifyApiError, match="Playlist konnte nicht erstellt werden"):
        run_generation(_config(), params, client=client, auth=_StubAuth())


def test_run_generation_missing_external_urls_gives_empty_url(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(
        search_results=[_track("Song One", "Artist One", "spotify:track:1")],
        playlist={"id": "pl1", "external_urls": None},
    )

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    assert result.playlist_url == ""


def test_run_generation_second_query_used_when_first_empty(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(search_results=[
        [],
        [_track("Song One", "Artist One", "spotify:track:1")],
    ])

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    result = run_generation(_config(), params, client=client, auth=_StubAuth())

    assert result.rows[0].status == "found"
    assert len(client.searches) == 2


def test_run_generation_emits_progress_events(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        "title,artist\nSong One,Artist One\nSong Two,Artist Two\n",
    )
    client = _StubClient(search_results=[_track("Song One", "Artist One", "spotify:track:1")])
    events = []

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    run_generation(_config(), params, client=client, auth=_StubAuth(), progress=events.append)

    auth_events = [e for e in events if e.kind == "auth"]
    start_events = [e for e in events if e.kind == "start"]
    song_events = [e for e in events if e.kind == "song"]

    assert len(auth_events) == 1
    assert len(start_events) == 1
    assert start_events[0].total == 2
    assert len(song_events) == 2
    assert [e.index for e in song_events] == [1, 2]
    assert all(e.row is not None for e in song_events)
    assert events[-1].kind == "done"


def test_run_generation_song_message_format(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(search_results=[_track("Song One", "Artist One", "spotify:track:1")])
    events = []

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    run_generation(_config(), params, client=client, auth=_StubAuth(), progress=events.append)

    song_events = [e for e in events if e.kind == "song"]
    assert song_events[0].message == "[1/1] Song One — Artist One … gefunden"


def test_run_generation_authenticates_once_before_loop(tmp_path):
    csv_path = _write_csv(tmp_path, "title,artist\nSong One,Artist One\n")
    client = _StubClient(search_results=[_track("Song One", "Artist One", "spotify:track:1")])
    stub_auth = _StubAuth()
    events = []

    params = GenerationParams(csv_path=csv_path, playlist_name="My Playlist")
    run_generation(_config(), params, client=client, auth=stub_auth, progress=events.append)

    assert stub_auth.calls >= 1
    auth_index = next(i for i, e in enumerate(events) if e.kind == "auth")
    song_index = next(i for i, e in enumerate(events) if e.kind == "song")
    assert auth_index < song_index


def test_counts_and_exit_code_properties():
    rows = [
        ResultRow(row=1, title="A", artist="", status="found", reason="",
                  matched_title="A", matched_artists="", spotify_url="", score=1.0),
        ResultRow(row=2, title="B", artist="", status="not_found", reason="x",
                  matched_title="", matched_artists="", spotify_url="", score=0.0),
        ResultRow(row=3, title="C", artist="", status="error", reason="y",
                  matched_title="", matched_artists="", spotify_url="", score=0.0),
    ]
    result = GenerationResult(rows=rows)

    counts = result.counts
    assert counts == {"found": 1, "not_found": 1, "error": 1, "total": 3}
    assert result.exit_code == 1

    ok_result = GenerationResult(rows=[rows[0]])
    assert ok_result.exit_code == 0
