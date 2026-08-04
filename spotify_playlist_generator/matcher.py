"""Track matching logic for Spotify search results."""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class TrackMatch:
    """A matched track from Spotify."""
    uri: str
    track_id: str
    name: str
    artists: str
    url: str
    score: float


DEFAULT_MIN_SCORE = 0.6


def normalize(text: str) -> str:
    """
    Normalize text for matching.

    Steps:
    1. Remove bracketed/parenthetical extras and everything after ' - '
    2. Unicode NFKD normalization and diacritic removal
    3. Lowercase
    4. Replace non-[a-z0-9 ] with spaces
    5. Collapse multiple spaces
    6. Strip
    """
    # Step 1: Remove parenthetical and bracketed content
    text = re.sub(r'\([^)]*\)', '', text)  # Remove (...)
    text = re.sub(r'\[[^\]]*\]', '', text)  # Remove [...]

    # Remove everything from ' - ' onwards
    if ' - ' in text:
        text = text.split(' - ')[0]

    # Step 2: Unicode NFKD normalization and remove diacritics
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    # Step 3: Lowercase
    text = text.lower()

    # Step 4: Replace non-[a-z0-9 ] with spaces
    text = re.sub(r'[^a-z0-9 ]', ' ', text)

    # Step 5: Collapse multiple spaces
    text = re.sub(r' +', ' ', text)

    # Step 6: Strip
    text = text.strip()

    return text


def similarity(a: str, b: str) -> float:
    """
    Calculate similarity between two strings using SequenceMatcher.

    Returns 0.0 if either normalized string is empty.
    """
    norm_a = normalize(a)
    norm_b = normalize(b)

    if not norm_a or not norm_b:
        return 0.0

    return SequenceMatcher(None, norm_a, norm_b).ratio()


def score_candidate(title: str, artist: str, cand_name: str, cand_artists: list[str]) -> float:
    """
    Score a candidate track.

    If artist is empty, score is based on title similarity only.
    Otherwise, score is 0.7 * title_sim + 0.3 * max(artist_sims).

    Result is rounded to 4 decimal places.
    """
    title_sim = similarity(title, cand_name)

    if not artist:
        return round(title_sim, 4)

    # Calculate artist similarity: max across all candidate artists
    artist_sims = [similarity(artist, cand_artist) for cand_artist in cand_artists]
    artist_sim = max(artist_sims) if artist_sims else 0.0

    score = 0.7 * title_sim + 0.3 * artist_sim
    return round(score, 4)


def build_queries(title: str, artist: str) -> list[str]:
    """
    Build a list of search queries in preference order.

    1. With artist: track:"<title>" artist:"<artist>", without: track:"<title>"
    2. Freetext: "<title> <artist>" or "<title>"

    Duplicates are removed while preserving order.
    """
    queries = []

    # Fielded queries
    if artist:
        queries.append(f'track:"{title}" artist:"{artist}"')
    queries.append(f'track:"{title}"')

    # Freetext queries
    if artist:
        freetext = f"{title} {artist}".strip()
    else:
        freetext = title.strip()
    queries.append(freetext)

    # Remove duplicates while preserving order
    seen = set()
    result = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            result.append(q)

    return result


def pick_best(title: str, artist: str, items: list[dict], min_score: float) -> TrackMatch | None:
    """
    Pick the best matching track from a list of candidates.

    Args:
        title: Song title to match
        artist: Artist name (can be empty string)
        items: List of Spotify track dicts
        min_score: Minimum score threshold

    Returns:
        TrackMatch with highest score if >= min_score, None otherwise
    """
    if not items:
        return None

    best_match = None
    best_score = -1

    for item in items:
        # Skip candidates without uri
        if not item.get('uri'):
            continue

        # Get candidate data
        cand_name = (item.get('name') or '')
        cand_artists_data = (item.get('artists') or [])
        cand_artists = [a.get('name', '') for a in cand_artists_data]

        # Calculate score
        score = score_candidate(title, artist, cand_name, cand_artists)

        # Update best if this is better
        if score > best_score:
            best_score = score
            best_match = item

    # Return None if no match found or score too low
    if best_match is None or best_score < min_score:
        return None

    # Build TrackMatch
    artists_str = ', '.join([a.get('name', '') for a in (best_match.get('artists') or [])])
    url = (best_match.get('external_urls') or {}).get('spotify', '')

    return TrackMatch(
        uri=best_match.get('uri', ''),
        track_id=best_match.get('id', ''),
        name=best_match.get('name', ''),
        artists=artists_str,
        url=url,
        score=best_score
    )
