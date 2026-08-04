"""Tests for the gui.app module."""

import time

import pytest

tk = pytest.importorskip("tkinter")

from spotify_playlist_generator.auth import Token, save_token
from spotify_playlist_generator.gui import viewmodel as vm
from spotify_playlist_generator.matcher import DEFAULT_MIN_SCORE


@pytest.fixture
def root():
    """A hidden Tk root, skipped when no display is available."""
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display: {exc}")
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def app(root, tmp_path):
    from spotify_playlist_generator.gui.app import App

    return App(root, settings_path=tmp_path / "settings.json")


def test_app_builds_three_tabs(app):
    """The main window has exactly three tabs with the expected labels."""
    tabs = app.notebook.tabs()
    assert len(tabs) == 3
    texts = [app.notebook.tab(t, "text") for t in tabs]
    assert any("Playlist erstellen" in t for t in texts)
    assert any("Ergebnis" in t for t in texts)
    assert any("Einstellungen" in t for t in texts)


def test_window_title(app, root):
    """The window title matches the application name."""
    assert root.title() == "Spotify Playlist Generator"


def test_set_csv_valid_file(app, tmp_path):
    """Selecting a valid CSV file updates the info label as OK."""
    csv_path = tmp_path / "songs.csv"
    csv_path.write_text("title,artist\nSong,Artist\n", encoding="utf-8")

    app._set_csv(str(csv_path))

    assert app.csv_var.get() == str(csv_path)
    assert "erkannt" in app.csv_info_label.cget("text")
    assert app.csv_info_label.cget("style") == "Ok.TLabel"


def test_set_csv_invalid_file(app, tmp_path):
    """Selecting a nonexistent CSV file marks the info label as an error."""
    missing = tmp_path / "missing.csv"

    app._set_csv(str(missing))

    assert app.csv_info_label.cget("style") == "Danger.TLabel"


def test_set_csv_suggests_playlist_name(app, tmp_path):
    """An empty playlist name is filled in from the CSV file name."""
    csv_path = tmp_path / "my_playlist.csv"
    csv_path.write_text("title,artist\nSong,Artist\n", encoding="utf-8")

    assert app.name_var.get() == ""
    app._set_csv(str(csv_path))

    assert app.name_var.get() == "my_playlist"


def test_set_csv_keeps_existing_name(app, tmp_path):
    """A pre-filled playlist name is not overwritten by CSV selection."""
    csv_path = tmp_path / "my_playlist.csv"
    csv_path.write_text("title,artist\nSong,Artist\n", encoding="utf-8")

    app.name_var.set("Bestehender Name")
    app._set_csv(str(csv_path))

    assert app.name_var.get() == "Bestehender Name"


def test_score_label_follows_variable(app):
    """The score label reflects the current value of the min_score variable."""
    app.min_score_var.set(0.85)
    app._on_score_change(None)

    assert app.score_label.cget("text") == "0.85"


def test_toggle_advanced(app):
    """Toggling advanced settings twice flips the open state and button text."""
    assert app.advanced_open is False

    app._toggle_advanced()
    assert app.advanced_open is True
    assert "▾" in app.advanced_button.cget("text")

    app._toggle_advanced()
    assert app.advanced_open is False
    assert "▸" in app.advanced_button.cget("text")


def test_result_tree_has_expected_columns(app):
    """The result table exposes exactly the columns from the viewmodel."""
    assert tuple(app.tree["columns"]) == vm.RESULT_COLUMNS


def test_settings_roundtrip(root, tmp_path):
    """Saved settings can be read back by a fresh App instance."""
    from spotify_playlist_generator.gui.app import App

    settings_path = tmp_path / "settings.json"
    app1 = App(root, settings_path=settings_path)
    app1.client_id_var.set("my-client-id")
    app1.client_secret_var.set("my-secret")
    app1.redirect_var.set("http://127.0.0.1:9999/callback")
    app1.token_path_var.set(str(tmp_path / "token.json"))
    app1._on_save_settings()

    app2 = App(root, settings_path=settings_path)

    assert app2.client_id_var.get() == "my-client-id"
    assert app2.client_secret_var.get() == "my-secret"
    assert app2.redirect_var.get() == "http://127.0.0.1:9999/callback"
    assert app2.token_path_var.get() == str(tmp_path / "token.json")


def test_settings_status_after_save(app):
    """Saving settings updates the status label to confirm success."""
    app._on_save_settings()

    assert app.settings_status_label.cget("text") == "Gespeichert."


def test_reset_login_removes_token_file(app, tmp_path):
    """Resetting the login deletes the cached token file."""
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    app.token_path_var.set(str(token_path))

    app._on_reset_login()

    assert not token_path.exists()


def test_login_status_reflects_token(root, tmp_path):
    """The login status text differs depending on whether a token is cached."""
    from spotify_playlist_generator.gui.app import App

    settings_path = tmp_path / "settings.json"
    app_no_token = App(root, settings_path=settings_path)
    app_no_token.token_path_var.set(str(tmp_path / "no_token.json"))
    app_no_token._refresh_login_status()
    text_without = app_no_token.login_status_label.cget("text")

    token_path = tmp_path / "token.json"
    token = Token(access_token="abc", refresh_token="def", expires_at=time.time() + 3600)
    save_token(token_path, token)

    app_no_token.token_path_var.set(str(token_path))
    app_no_token._refresh_login_status()
    text_with = app_no_token.login_status_label.cget("text")

    assert text_without != text_with


def test_run_and_cancel_are_placeholders(app):
    """The run and cancel handlers are still placeholders and do nothing."""
    assert app._on_run() is None
    assert app._on_cancel() is None


def test_defaults(app):
    """Form variables start with the documented default values."""
    assert app.public_var.get() is False
    assert app.dry_run_var.get() is False
    assert app.limit_var.get() == 10
    assert app.min_score_var.get() == DEFAULT_MIN_SCORE
    assert app.market_var.get() == ""
