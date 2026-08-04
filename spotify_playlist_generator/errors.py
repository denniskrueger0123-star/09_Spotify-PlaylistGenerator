class PlaylistGeneratorError(Exception):
    """Base exception for all Spotify Playlist Generator errors."""
    pass


class ConfigError(PlaylistGeneratorError):
    """Raised when configuration is invalid or missing."""
    pass


class CsvError(PlaylistGeneratorError):
    """Raised when CSV file cannot be read or is malformed."""
    pass


class AuthError(PlaylistGeneratorError):
    """Raised when authentication fails."""
    pass


class SpotifyApiError(PlaylistGeneratorError):
    """Raised when Spotify API returns an error response."""

    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class RateLimitError(SpotifyApiError):
    """Raised when Spotify API rate limit is exceeded."""
    pass
