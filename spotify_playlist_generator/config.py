import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

# Constants
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_TOKEN_PATH = Path.home() / ".spotify_playlist_generator" / "token.json"
SCOPES = "playlist-modify-public playlist-modify-private"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"


@dataclass(frozen=True)
class Config:
    """Configuration for Spotify Playlist Generator."""
    client_id: str
    redirect_uri: str
    token_path: Path


def load_dotenv(path: Path) -> dict[str, str]:
    """
    Load environment variables from a .env file.

    - Ignores empty lines and lines starting with #
    - Splits at the first = sign
    - Strips whitespace and surrounding quotes (" or ')
    - Returns empty dict if file does not exist
    """
    result = {}
    if not path.exists():
        return result

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Split at first =
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Remove surrounding quotes
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]

            result[key] = value

    return result


def load_config(env_file: Path | None = None) -> Config:
    """
    Load configuration from environment variables and .env file.

    Environment variables take precedence over .env file values.
    - Reads SPOTIFY_CLIENT_ID (required)
    - Reads SPOTIFY_REDIRECT_URI (optional, defaults to DEFAULT_REDIRECT_URI)
    - Reads SPOTIFY_TOKEN_PATH (optional, defaults to DEFAULT_TOKEN_PATH)

    Raises ConfigError if SPOTIFY_CLIENT_ID is not set.
    """
    if env_file is None:
        env_file = Path(".env")

    # Load from .env file
    env_vars = load_dotenv(env_file)

    # Environment variables take precedence
    client_id = os.environ.get("SPOTIFY_CLIENT_ID") or env_vars.get("SPOTIFY_CLIENT_ID", "")
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI") or env_vars.get("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    token_path_str = os.environ.get("SPOTIFY_TOKEN_PATH") or env_vars.get("SPOTIFY_TOKEN_PATH", str(DEFAULT_TOKEN_PATH))
    token_path = Path(token_path_str)

    if not client_id:
        raise ConfigError(
            "SPOTIFY_CLIENT_ID nicht gesetzt. "
            "Bitte kopiere .env.example zu .env und trage deine Spotify Client-ID ein. "
            "Du kannst eine App im Spotify-Dashboard erstellen: https://developer.spotify.com/dashboard"
        )

    return Config(
        client_id=client_id,
        redirect_uri=redirect_uri,
        token_path=token_path,
    )
