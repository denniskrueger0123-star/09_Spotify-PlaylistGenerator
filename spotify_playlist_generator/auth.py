import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

from .config import AUTH_URL, SCOPES, TOKEN_URL, Config
from .errors import AuthError

DEFAULT_LOGIN_TIMEOUT = 180
REQUEST_TIMEOUT = (10, 30)  # (connect, read) Sekunden


def _generate_code_verifier() -> str:
    """
    Generate a code verifier for PKCE flow.
    Returns a 64-character string from secrets.token_urlsafe(64),
    limited to max 128 characters.
    """
    return secrets.token_urlsafe(64)[:128]


def _code_challenge(verifier: str) -> str:
    """
    Generate a code challenge from a code verifier.
    Uses SHA256 hash, then base64-urlsafe encoding without padding.
    """
    # SHA256 of the verifier
    digest = hashlib.sha256(verifier.encode()).digest()
    # Base64-urlsafe without padding (remove = signs)
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for the OAuth callback.
    Handles GET requests on /callback, parses code/error from query parameters,
    and stores them on the server object.
    """

    def do_GET(self):
        """Handle GET request."""
        if not self.path.startswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return

        # Parse query parameters
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        # Store code and error on server object for later retrieval
        self.server.callback_code = query_params.get("code", [None])[0]
        self.server.callback_error = query_params.get("error", [None])[0]
        self.server.callback_state = query_params.get("state", [None])[0]

        # Send response
        if self.server.callback_error:
            html = f"""
            <html>
            <head><title>Authentifizierungsfehler</title></head>
            <body>
            <h1>Authentifizierungsfehler</h1>
            <p>Fehler: {self.server.callback_error}</p>
            </body>
            </html>
            """
        else:
            html = """
            <html>
            <head><title>Anmeldung erfolgreich</title></head>
            <body>
            <h1>Anmeldung erfolgreich</h1>
            <p>Du kannst dieses Fenster jetzt schließen.</p>
            </body>
            </html>
            """

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        """Suppress HTTP server logging."""
        pass


@dataclass
class Token:
    """Represents a Spotify OAuth token."""

    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str = "Bearer"

    def is_expired(self, leeway: int = 60) -> bool:
        """
        Check if the token is expired (with optional leeway in seconds).
        Default leeway is 60 seconds.
        """
        return time.time() >= (self.expires_at - leeway)

    def to_dict(self) -> dict:
        """Convert token to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Token":
        """Create a Token from a dictionary."""
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=float(data["expires_at"]),
            token_type=data.get("token_type", "Bearer"),
        )


def load_token(path: Path) -> Optional[Token]:
    """
    Load a Token from a JSON file.
    Returns None if the file doesn't exist or is malformed (no crash).
    """
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Token.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        # File exists but is broken/unparseable
        return None


def save_token(path: Path, token: Token) -> None:
    """
    Save a Token to a JSON file.
    Creates parent directory if needed and sets file permissions to 0o600.
    """
    # Create parent directory
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON
    with open(path, "w", encoding="utf-8") as f:
        json.dump(token.to_dict(), f)

    # Set file permissions to 0o600
    os.chmod(path, 0o600)


def has_cached_token(path: Path) -> bool:
    """Prüft, ob ein brauchbarer Token im Cache liegt (ohne ihn zu erneuern)."""
    token = load_token(path)
    if token is None:
        return False

    if not token.is_expired():
        return True

    if token.refresh_token:
        return True

    return False


def reset_token(path: Path) -> None:
    """Löscht den zwischengespeicherten Token, damit sich der Nutzer neu anmelden kann."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


CHECK_OK = "ok"
CHECK_INVALID = "invalid"
CHECK_UNKNOWN = "unknown"


@dataclass(frozen=True)
class CredentialCheck:
    """
    Ergebnis einer Vorabprüfung der Zugangsdaten.

    status ist bewusst dreiwertig: Nur ein eindeutiges Signal von Spotify führt zu
    CHECK_OK oder CHECK_INVALID. Alles Unerwartete bleibt CHECK_UNKNOWN, damit die
    Prüfung nie fälschlich Entwarnung gibt.
    """
    status: str
    message: str

    @property
    def ok(self) -> bool:
        return self.status == CHECK_OK


def check_credentials(config: Config, session: Optional[requests.Session] = None) -> CredentialCheck:
    """
    Prüft Client ID und Redirect URI, ohne einen vollständigen Login auszulösen.

    Stellt dieselbe Anfrage wie der echte Login (inklusive PKCE-Parameter), folgt der
    Weiterleitung aber nicht. Bewertet wird ausschließlich der OAuth-Parameter `error`
    in der Rückleitung; jede andere Antwort gilt als "nicht eindeutig prüfbar".
    """
    if not config.client_id.strip():
        return CredentialCheck(CHECK_INVALID, "Keine Client ID eingetragen.")

    session = session or requests.Session()
    verifier = _generate_code_verifier()
    params = {
        "client_id": config.client_id,
        "response_type": "code",
        "redirect_uri": config.redirect_uri,
        "scope": SCOPES,
        "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "S256",
    }

    try:
        response = session.get(
            AUTH_URL, params=params, allow_redirects=False, timeout=REQUEST_TIMEOUT
        )
    except requests.exceptions.Timeout:
        return CredentialCheck(CHECK_UNKNOWN, "Zeitüberschreitung – Spotify war nicht erreichbar.")
    except requests.RequestException as exc:
        return CredentialCheck(CHECK_UNKNOWN, f"Keine Verbindung zu Spotify: {exc}")

    location = response.headers.get("Location", "")
    error = ""
    if location:
        error = (parse_qs(urlparse(location).query).get("error", [""])[0] or "").strip()

    if error:
        if "redirect_uri" in error.lower():
            return CredentialCheck(
                CHECK_INVALID,
                "Die Redirect URI passt nicht zu den Angaben im Spotify-Dashboard.",
            )
        return CredentialCheck(
            CHECK_INVALID,
            f"Spotify lehnt die Angaben ab ({error}). Client ID und Redirect URI im Dashboard prüfen.",
        )

    # Ohne Fehlerparameter gilt nur eine echte Weiterleitung als Bestätigung.
    if response.status_code in (301, 302, 303, 307, 308) and location:
        return CredentialCheck(
            CHECK_OK, "Client ID und Redirect URI werden von Spotify akzeptiert."
        )

    return CredentialCheck(
        CHECK_UNKNOWN,
        f"Konnte nicht eindeutig geprüft werden (unerwartete Antwort {response.status_code}). "
        "Das sagt nichts über die Gültigkeit der Client ID aus.",
    )


class SpotifyAuth:
    """
    Handles OAuth2 authentication with Spotify using PKCE flow.
    """

    def __init__(self, config: Config, session: Optional[requests.Session] = None,
                 login_timeout: int = DEFAULT_LOGIN_TIMEOUT):
        """
        Initialize SpotifyAuth.

        Args:
            config: Config object with client_id, redirect_uri, token_path
            session: Optional requests.Session object (for testing or reuse)
            login_timeout: Timeout in Sekunden, wie lange auf den Browser-Rückruf gewartet wird
        """
        self.config = config
        self.session = session or requests.Session()
        self.login_timeout = login_timeout

    def _exchange_code(self, code: str, verifier: str) -> Token:
        """
        Exchange authorization code for an access token.

        Args:
            code: Authorization code from OAuth callback
            verifier: Code verifier used for PKCE

        Returns:
            Token object

        Raises:
            AuthError: If the exchange fails
        """
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.config.client_id,
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "code_verifier": verifier,
        }

        if self.config.client_secret:
            payload["client_secret"] = self.config.client_secret

        try:
            response = self.session.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            raise AuthError(
                f"Authentifizierungsaustausch fehlgeschlagen: {e}"
            )

        try:
            data = response.json()
        except json.JSONDecodeError:
            raise AuthError("Ungültige Antwort vom Token-Endpunkt")

        if "error" in data:
            raise AuthError(f"Token-Fehler: {data.get('error_description', data['error'])}")

        # Validate required fields
        if "access_token" not in data or "expires_in" not in data:
            raise AuthError(f"Unerwartete Token-Antwort: erforderliche Felder fehlen")

        return Token(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=time.time() + data["expires_in"],
            token_type=data.get("token_type", "Bearer"),
        )

    def _refresh(self, token: Token) -> Token:
        """
        Refresh an access token using the refresh token.

        Args:
            token: Token object with valid refresh_token

        Returns:
            New Token object

        Raises:
            AuthError: If refresh fails
        """
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.config.client_id,
            "refresh_token": token.refresh_token,
        }

        if self.config.client_secret:
            payload["client_secret"] = self.config.client_secret

        try:
            response = self.session.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            raise AuthError(
                f"Token-Aktualisierung fehlgeschlagen: {e}"
            )

        if response.status_code != 200:
            raise AuthError(f"Token-Aktualisierung fehlgeschlagen (HTTP {response.status_code})")

        try:
            data = response.json()
        except json.JSONDecodeError:
            raise AuthError("Ungültige Antwort vom Token-Endpunkt")

        if "error" in data:
            raise AuthError(f"Token-Fehler: {data.get('error_description', data['error'])}")

        # Validate required fields
        if "access_token" not in data or "expires_in" not in data:
            raise AuthError(f"Unerwartete Token-Antwort: erforderliche Felder fehlen")

        # Keep old refresh_token if no new one was returned
        new_refresh_token = data.get("refresh_token", token.refresh_token)

        return Token(
            access_token=data["access_token"],
            refresh_token=new_refresh_token,
            expires_at=time.time() + data["expires_in"],
            token_type=data.get("token_type", "Bearer"),
        )

    def _run_login_flow(self) -> Token:
        """
        Run the full OAuth2 login flow with PKCE.

        1. Generates code verifier and challenge
        2. Generates state parameter
        3. Opens authorization URL in browser and prints to console
        4. Starts HTTP server to receive callback
        5. Exchanges code for token
        6. Validates state

        Returns:
            Token object

        Raises:
            AuthError: If any step fails
        """
        # Generate PKCE parameters
        verifier = _generate_code_verifier()
        challenge = _code_challenge(verifier)

        # Generate state parameter
        state = secrets.token_urlsafe(32)

        # Build authorization URL
        auth_params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": SCOPES,
            "state": state,
        }

        auth_url = AUTH_URL + "?" + "&".join(
            f"{k}={requests.utils.quote(str(v), safe='')}"
            for k, v in auth_params.items()
        )

        # Print URL to console (in case browser doesn't open)
        print(f"\nÖffne diese URL im Browser:\n{auth_url}\n")

        # Try to open browser
        webbrowser.open(auth_url)

        # Parse redirect_uri to get host and port
        parsed = urlparse(self.config.redirect_uri)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8888

        # Start HTTP server
        server = HTTPServer((host, port), _CallbackHandler)
        server.callback_code = None
        server.callback_error = None
        server.callback_state = None
        server.timeout = self.login_timeout
        server.timed_out = False
        server.handle_timeout = lambda: setattr(server, "timed_out", True)

        print(f"Warte auf Rückruf auf {host}:{port}...")

        try:
            # Handle exactly one request
            server.handle_request()
        finally:
            server.server_close()

        if server.timed_out:
            raise AuthError(
                f"Zeitüberschreitung: Innerhalb von {self.login_timeout} Sekunden "
                "kam keine Antwort von Spotify zurück. Bitte erneut versuchen."
            )

        # Check for error in callback
        if server.callback_error:
            raise AuthError(f"Authentifizierung abgelehnt: {server.callback_error}")

        if not server.callback_code:
            raise AuthError("Kein Authentifizierungscode empfangen")

        # Validate state
        if server.callback_state != state:
            raise AuthError("State-Parameter stimmt nicht überein (möglicher CSRF-Angriff)")

        # Exchange code for token
        return self._exchange_code(server.callback_code, verifier)

    def get_token(self) -> Token:
        """
        Get a valid access token.

        Tries to load from cache first. If cached token is valid, returns it.
        If cached token is expired, tries to refresh it.
        If refresh fails or no cached token exists, runs full login flow.
        Always saves the result before returning.

        Returns:
            Valid Token object

        Raises:
            AuthError: If authentication fails
        """
        # Try to load cached token
        token = load_token(self.config.token_path)

        if token is not None:
            # Check if still valid
            if not token.is_expired():
                save_token(self.config.token_path, token)
                return token

            # Try to refresh
            try:
                token = self._refresh(token)
                save_token(self.config.token_path, token)
                return token
            except AuthError:
                # Refresh failed, fall back to full login
                pass

        # No valid cached token, run full login flow
        token = self._run_login_flow()
        save_token(self.config.token_path, token)
        return token
