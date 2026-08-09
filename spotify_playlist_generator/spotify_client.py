import threading
import time

import requests

from .config import API_BASE
from .errors import OperationCancelled, RateLimitError, SpotifyApiError

REQUEST_TIMEOUT = (10, 30)  # (connect, read) Sekunden
SLEEP_CHECK_INTERVAL = 1.0  # Sekunden zwischen Cancel-Prüfungen während Retry-Wartezeiten

# Seit der Web-API-Umstellung im Februar 2026 nimmt Spotify für Apps im
# Entwicklungsmodus höchstens 10 Suchtreffer pro Anfrage an. Größere Werte
# beantwortet die API mit einem Fehler, deshalb wird hier hart gedeckelt.
MAX_SEARCH_LIMIT = 10


def _explain_forbidden(payload: dict | None) -> str:
    """
    Baut aus einer 403-Antwort eine Meldung, die den Nutzer zur Ursache führt.

    403 ist seit der Umstellung im Februar/März 2026 der Sammelfehler für die
    Zugangsbeschränkungen des Entwicklungsmodus. Die häufigsten Ursachen werden
    deshalb mitgenannt, sonst steht der Nutzer vor einem nackten "Forbidden".
    """
    detail = ""
    if isinstance(payload, dict):
        error_info = payload.get("error")
        if isinstance(error_info, dict):
            detail = (error_info.get("message") or "").strip()
            reason = (error_info.get("reason") or "").strip()
            if reason:
                detail = f"{detail} ({reason})".strip()
        elif isinstance(error_info, str):
            detail = error_info.strip()

    message = "Spotify verweigert den Zugriff (403)."
    if detail:
        message += f" Meldung von Spotify: {detail}."
    message += (
        " Übliche Ursachen seit der API-Umstellung 2026: "
        "(1) Der Inhaber der Spotify-App braucht ein aktives Premium-Abo. "
        "(2) Im Entwicklungsmodus dürfen nur die im Dashboard eingetragenen "
        "Nutzerkonten (max. 5) die App verwenden – das angemeldete Konto muss "
        "unter 'User Management' stehen. "
        "(3) Das Kontingent des Entwicklungsmodus ist aufgebraucht."
    )
    return message


class SpotifyClient:
    """Client for Spotify Web API with automatic retry logic."""

    def __init__(self, token_provider, session: requests.Session | None = None,
                 max_retries: int = 5, sleep=time.sleep, cancel: threading.Event | None = None,
                 notify=None):
        """
        Initialize SpotifyClient.

        Args:
            token_provider: Callable without arguments that returns a valid access token string.
            session: Optional requests.Session for testing (injected dependency).
            max_retries: Maximum retry attempts for rate-limited requests.
            sleep: Injected sleep function for testing.
            cancel: Optional Event that, when set, interrupts a retry wait immediately
                instead of sleeping through the full backoff/Retry-After duration.
            notify: Optionaler Callback für Statustexte, etwa während einer Wartezeit
                nach einer Drosselung durch Spotify.
        """
        self._token_provider = token_provider
        self._session = session if session is not None else requests.Session()
        self._max_retries = max_retries
        self._sleep = sleep
        self._cancel = cancel
        self._notify = notify

    def _say(self, text: str) -> None:
        """Meldet einen Statustext, sofern ein Empfänger gesetzt ist."""
        if self._notify is not None:
            self._notify(text)

    def _sleep_or_cancel(self, seconds: float) -> None:
        """Sleeps in <=1s steps, raising OperationCancelled as soon as cancel is set."""
        if self._cancel is not None and self._cancel.is_set():
            raise OperationCancelled("Vorgang abgebrochen")
        if seconds <= 0:
            self._sleep(seconds)
            return
        remaining = seconds
        while remaining > 0:
            chunk = min(SLEEP_CHECK_INTERVAL, remaining)
            self._sleep(chunk)
            remaining -= chunk
            if self._cancel is not None and self._cancel.is_set():
                raise OperationCancelled("Vorgang abgebrochen")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """
        Make an HTTP request to the Spotify API with automatic retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/me", "/search")
            **kwargs: Additional arguments to pass to session.request

        Returns:
            Parsed JSON response as dict, or {} if response is empty or 204.

        Raises:
            RateLimitError: If rate limited after max_retries attempts.
            SpotifyApiError: For other API errors.
        """
        url = API_BASE + path
        attempt = 0
        retry_count = 0
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)

        while True:
            # Get fresh token for each attempt
            token = self._token_provider()
            headers = kwargs.get("headers", {})
            headers["Authorization"] = f"Bearer {token}"
            kwargs["headers"] = headers

            try:
                response = self._session.request(method, url, **kwargs)
            except requests.exceptions.Timeout:
                raise SpotifyApiError(
                    "Zeitüberschreitung: Spotify hat nicht rechtzeitig geantwortet. "
                    "Prüfe deine Internetverbindung und versuche es erneut."
                )
            except requests.exceptions.RequestException as exc:
                raise SpotifyApiError(f"Netzwerkfehler bei der Verbindung zu Spotify: {exc}")

            # Success
            if response.status_code < 400:
                # Handle 204 No Content or empty body
                if response.status_code == 204 or not response.text:
                    return {}
                return response.json()

            # Rate limit (429)
            if response.status_code == 429:
                if retry_count >= self._max_retries:
                    raise RateLimitError(
                        f"Rate limited after {self._max_retries} retries",
                        status_code=429
                    )
                # Parse Retry-After header
                retry_after = response.headers.get("Retry-After", "1")
                try:
                    sleep_seconds = int(retry_after)
                except (ValueError, TypeError):
                    sleep_seconds = 1
                self._say(
                    f"Spotify drosselt die Anfragen. Warte {sleep_seconds} Sekunde(n) "
                    f"und versuche es erneut (Versuch {retry_count + 1} von {self._max_retries})."
                )
                self._sleep_or_cancel(sleep_seconds)
                retry_count += 1
                continue

            # Server errors (500, 502, 503, 504) - exponential backoff
            if response.status_code in (500, 502, 503, 504):
                if attempt >= self._max_retries:
                    payload = None
                    try:
                        payload = response.json()
                    except (ValueError, requests.exceptions.JSONDecodeError):
                        pass
                    raise SpotifyApiError(
                        f"Spotify API error: {response.status_code}",
                        status_code=response.status_code,
                        payload=payload
                    )
                sleep_seconds = 2 ** attempt
                self._say(
                    f"Spotify antwortet gerade nicht (HTTP {response.status_code}). "
                    f"Neuer Versuch in {sleep_seconds} Sekunde(n)."
                )
                self._sleep_or_cancel(sleep_seconds)
                attempt += 1
                continue

            # Unauthorized (401) - retry once with fresh token
            if response.status_code == 401:
                if attempt == 0:
                    # Try once more with a fresh token call
                    attempt = 1
                    continue
                else:
                    # Already retried once
                    payload = None
                    try:
                        payload = response.json()
                    except (ValueError, requests.exceptions.JSONDecodeError):
                        pass
                    raise SpotifyApiError(
                        "Unauthorized: Invalid or expired token",
                        status_code=401,
                        payload=payload
                    )

            # Other error status codes (4xx, 5xx)
            payload = None
            try:
                payload = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                pass

            if response.status_code == 403:
                raise SpotifyApiError(
                    _explain_forbidden(payload),
                    status_code=403,
                    payload=payload,
                )

            # Extract error message from payload if available
            message = f"Spotify API error: {response.status_code}"
            if payload and isinstance(payload, dict):
                if "error" in payload:
                    error_info = payload["error"]
                    if isinstance(error_info, dict) and "message" in error_info:
                        message = error_info["message"]
                    elif isinstance(error_info, str):
                        message = error_info

            raise SpotifyApiError(
                message,
                status_code=response.status_code,
                payload=payload
            )

    def current_user(self) -> dict:
        """
        Get current user profile.

        Returns:
            User profile dictionary.
        """
        return self._request("GET", "/me")

    def search_track(self, query: str, market: str | None = None, limit: int = 10) -> list[dict]:
        """
        Search for tracks.

        Args:
            query: Search query string.
            market: Optional market code (e.g., 'DE', 'US').
            limit: Maximum number of results (default 10). Wird auf den von
                Spotify erlaubten Höchstwert MAX_SEARCH_LIMIT gedeckelt, damit
                ein zu großer Wert die Suche nicht komplett scheitern lässt.

        Returns:
            List of track dictionaries from the search results.
        """
        params = {
            "q": query,
            "type": "track",
            "limit": max(1, min(int(limit), MAX_SEARCH_LIMIT)),
        }
        if market is not None:
            params["market"] = market

        response = self._request("GET", "/search", params=params)
        tracks = response.get("tracks") or {}
        if isinstance(tracks, list):
            # Neuere Antwortform: tracks ist bereits die Trefferliste.
            return tracks
        return tracks.get("items") or []

    def create_playlist(self, name: str, public: bool = False,
                        description: str = "") -> dict:
        """
        Create a new playlist for the logged-in user.

        Nutzt POST /me/playlists. Der frühere Weg über
        POST /users/{user_id}/playlists wurde von Spotify im Februar 2026
        entfernt und antwortet seit dem 9. März 2026 mit HTTP 403.

        Args:
            name: Name of the playlist.
            public: Whether the playlist is public (default False).
            description: Optional playlist description.

        Returns:
            Playlist dictionary.
        """
        body = {
            "name": name,
            "public": public,
            "description": description,
        }
        return self._request("POST", "/me/playlists", json=body)

    def add_tracks(self, playlist_id: str, uris: list[str]) -> int:
        """
        Add tracks to a playlist.

        Tracks are added in batches of at most 100 URIs per request.

        Schreibt auf POST /playlists/{id}/items. Der frühere Pfad
        /playlists/{id}/tracks wurde mit der Umstellung im Februar 2026
        umbenannt.

        Args:
            playlist_id: The playlist ID.
            uris: List of track URIs to add.

        Returns:
            Number of tracks added.
        """
        if not uris:
            return 0

        total_added = 0
        batch_size = 100

        for i in range(0, len(uris), batch_size):
            batch = uris[i:i + batch_size]
            path = f"/playlists/{playlist_id}/items"
            body = {"uris": batch}
            self._request("POST", path, json=body)
            total_added += len(batch)

        return total_added
