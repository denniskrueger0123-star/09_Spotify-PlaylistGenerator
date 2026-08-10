"""Tests for internationalization module."""

import pytest

from spotify_playlist_generator.i18n import (
    DEFAULT_LANGUAGE,
    HELP_SECTIONS,
    LANGUAGES,
    TEXTS,
    t,
)


def test_languages_are_defined():
    """LANGUAGES contains supported language codes."""
    assert "de" in LANGUAGES
    assert "en" in LANGUAGES


def test_texts_have_all_languages():
    """TEXTS dict has entries for all LANGUAGES."""
    for lang in LANGUAGES:
        assert lang in TEXTS


def test_texts_have_same_keys_in_all_languages():
    """All language dicts in TEXTS have identical key sets."""
    keys_by_lang = {lang: set(TEXTS[lang].keys()) for lang in LANGUAGES}

    # All sets should be equal
    first_lang = LANGUAGES[0]
    for lang in LANGUAGES[1:]:
        assert keys_by_lang[lang] == keys_by_lang[first_lang], \
            f"Keys differ between {first_lang} and {lang}"


def test_no_empty_text_values():
    """No text value is empty."""
    for lang in LANGUAGES:
        for key, value in TEXTS[lang].items():
            assert value and value.strip(), f"Empty value for {lang}.{key}"


def test_help_sections_have_all_languages():
    """HELP_SECTIONS dict has entries for all LANGUAGES."""
    for lang in LANGUAGES:
        assert lang in HELP_SECTIONS


def test_help_sections_have_no_empty_texts():
    """No help section has empty text."""
    for lang in LANGUAGES:
        for art, text in HELP_SECTIONS[lang]:
            assert text and text.strip(), f"Empty text in {lang}: {art}"


def test_help_sections_only_allowed_types():
    """Help section types are only allowed values."""
    allowed_types = {"h1", "h2", "p", "li"}
    for lang in LANGUAGES:
        for art, text in HELP_SECTIONS[lang]:
            assert art in allowed_types, f"Unknown type {art} in {lang}"


def test_t_with_unknown_language_returns_german():
    """t() falls back to German for unknown language."""
    result = t("xx", "about.developer")

    assert result == t("de", "about.developer")


def test_t_with_unknown_key_returns_key():
    """t() returns the key itself for unknown keys."""
    result = t("de", "unknown.key.xyz")

    assert result == "unknown.key.xyz"


def test_t_with_valid_language_and_key_returns_text():
    """t() returns the correct text for valid language and key."""
    result = t("de", "about.developer")

    assert result == "Entwickler"


def test_t_english_version():
    """t() returns English text correctly."""
    result = t("en", "about.developer")

    assert result == "Developer"


def test_help_sections_are_tuples():
    """HELP_SECTIONS entries are tuples."""
    for lang in LANGUAGES:
        for entry in HELP_SECTIONS[lang]:
            assert isinstance(entry, tuple)
            assert len(entry) == 2
