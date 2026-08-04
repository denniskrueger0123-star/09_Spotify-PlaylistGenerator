"""Tests for the gui.app module."""

import time
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from spotify_playlist_generator.auth import Token, save_token
from spotify_playlist_generator.config import Config
from spotify_playlist_generator.errors import ConfigError
from spotify_playlist_generator.gui import viewmodel as vm
from spotify_playlist_generator.matcher import DEFAULT_MIN_SCORE
from spotify_playlist_generator.pipeline import GenerationResult, ProgressEvent
from spotify_playlist_generator.report import ResultRow


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
    """The window title includes the application name and current version."""
    from spotify_playlist_generator import __version__

    assert root.title() == f"Spotify Playlist Generator — v{__version__}"


def _all_label_texts(widget):
    """Recursively collect the text of every ttk.Label under widget."""
    texts = []
    for child in widget.winfo_children():
        if isinstance(child, __import__("tkinter").ttk.Label):
            texts.append(child.cget("text"))
        texts.extend(_all_label_texts(child))
    return texts


def test_version_and_developer_are_visible(app, root):
    """The version number and developer name appear somewhere in the window."""
    from spotify_playlist_generator import __version__

    texts = _all_label_texts(root)
    assert any(__version__ in t for t in texts)
    assert any("Dennis Krüger" in t for t in texts)


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


def test_defaults(app):
    """Form variables start with the documented default values."""
    assert app.public_var.get() is False
    assert app.dry_run_var.get() is False
    assert app.limit_var.get() == 10
    assert app.min_score_var.get() == DEFAULT_MIN_SCORE
    assert app.market_var.get() == ""


class FakeMessagebox:
    """Records calls instead of showing real, blocking dialogs."""

    def __init__(self):
        self.calls = []

    def showwarning(self, title, message):
        self.calls.append(("showwarning", title, message))

    def showerror(self, title, message):
        self.calls.append(("showerror", title, message))

    def showinfo(self, title, message):
        self.calls.append(("showinfo", title, message))


@pytest.fixture
def fake_messagebox(monkeypatch):
    fake = FakeMessagebox()
    monkeypatch.setattr("spotify_playlist_generator.gui.app.messagebox", fake)
    return fake


def _make_result_row(status="found", spotify_url="https://open.spotify.com/track/abc"):
    return ResultRow(
        row=1,
        title="Song",
        artist="Artist",
        status=status,
        reason="" if status == "found" else "nicht gefunden",
        matched_title="Song" if status == "found" else "",
        matched_artists="Artist" if status == "found" else "",
        spotify_url=spotify_url if status == "found" else "",
        score=0.9 if status == "found" else 0.0,
    )


def test_run_without_csv_warns(app, fake_messagebox, monkeypatch):
    """Running without CSV/name shows a warning and does not start the worker."""
    started = []
    monkeypatch.setattr(app.worker, "start", lambda *a, **kw: started.append((a, kw)))

    app._on_run()

    assert any(call[0] == "showwarning" for call in fake_messagebox.calls)
    assert started == []


def test_run_with_valid_input_starts_worker(app, fake_messagebox, monkeypatch, tmp_path):
    """Valid input with a client ID starts the worker exactly once."""
    csv_path = tmp_path / "songs.csv"
    csv_path.write_text("title,artist\nSong,Artist\n", encoding="utf-8")
    app.csv_var.set(str(csv_path))
    app.name_var.set("Meine Playlist")
    app.client_id_var.set("client-123")

    calls = []
    monkeypatch.setattr(app.worker, "start", lambda config, params, **kw: calls.append((config, params)))

    app._on_run()

    assert len(calls) == 1
    _, params = calls[0]
    assert params.playlist_name == "Meine Playlist"


def test_run_without_client_id_shows_error(app, fake_messagebox, monkeypatch, tmp_path):
    """A missing client ID surfaces a ConfigError as an error dialog and switches tabs."""
    csv_path = tmp_path / "songs.csv"
    csv_path.write_text("title,artist\nSong,Artist\n", encoding="utf-8")
    app.csv_var.set(str(csv_path))
    app.name_var.set("Meine Playlist")
    app.client_id_var.set("")

    def fake_load_config(settings_path=None):
        raise ConfigError("keine Client-ID")

    monkeypatch.setattr("spotify_playlist_generator.gui.app.load_config", fake_load_config)

    app._on_run()

    assert any(call[0] == "showerror" for call in fake_messagebox.calls)
    assert app.notebook.index(app.notebook.select()) == 2


def test_current_config_prefers_form(app):
    """Filled-in form fields take precedence over the usual config loading."""
    app.client_id_var.set("form-client-id")
    app.client_secret_var.set("form-secret")
    app.redirect_var.set("http://127.0.0.1:1234/callback")
    app.token_path_var.set("/tmp/token.json")

    config = app._current_config()

    assert config == Config(
        client_id="form-client-id",
        redirect_uri="http://127.0.0.1:1234/callback",
        token_path=Path("/tmp/token.json"),
        client_secret="form-secret",
    )


def test_reset_run_state_clears_everything(app):
    """Resetting run state clears the table, log and button states."""
    app.tree.insert("", "end", values=vm.result_row_values(_make_result_row()))
    app.log_text.configure(state="normal")
    app.log_text.insert("end", "vorheriger Lauf\n")
    app.log_text.configure(state="disabled")
    app.chip_values["found"].configure(text="5")
    app.run_button.configure(state="normal")
    app.cancel_button.configure(state="disabled")

    app._reset_run_state()

    assert app.tree.get_children("") == ()
    assert all(chip.cget("text") == "0" for chip in app.chip_values.values())
    assert str(app.run_button.cget("state")) == "disabled"
    assert str(app.cancel_button.cget("state")) == "normal"


def test_handle_progress_start_sets_maximum(app):
    """A 'start' progress event configures the progress bar maximum."""
    app._handle_progress(ProgressEvent(kind="start", total=7))

    assert app.progress["maximum"] == 7


def test_handle_progress_song_appends_row(app):
    """A 'song' progress event with a row appends exactly one table entry."""
    row = _make_result_row()
    event = ProgressEvent(kind="song", index=1, total=2, message="[1/2] Song", row=row)

    app._handle_progress(event)

    assert len(app.tree.get_children("")) == 1
    assert app.progress["value"] == 1


def test_handle_progress_song_records_url(app):
    """A found row with a Spotify URL is recorded for double-click opening."""
    row = _make_result_row(spotify_url="https://open.spotify.com/track/xyz")
    event = ProgressEvent(kind="song", index=1, total=1, message="…", row=row)

    app._handle_progress(event)

    assert list(app.row_urls.values()) == ["https://open.spotify.com/track/xyz"]


def test_handle_progress_song_without_url_not_recorded(app):
    """A row without a Spotify URL is not recorded in row_urls."""
    row = _make_result_row(status="not_found")
    event = ProgressEvent(kind="song", index=1, total=1, message="…", row=row)

    app._handle_progress(event)

    assert app.row_urls == {}


def test_handle_result_updates_chips(app):
    """The result chips reflect the counts of a mixed result."""
    result = GenerationResult(rows=[
        _make_result_row(status="found"),
        _make_result_row(status="found"),
        _make_result_row(status="not_found"),
        _make_result_row(status="error"),
    ])

    app._handle_result(result)

    assert app.chip_values["total"].cget("text") == "4"
    assert app.chip_values["found"].cget("text") == "2"
    assert app.chip_values["not_found"].cget("text") == "1"
    assert app.chip_values["error"].cget("text") == "1"


def test_handle_result_enables_buttons(app):
    """With rows and a playlist URL, both result buttons become enabled."""
    result = GenerationResult(
        rows=[_make_result_row(status="found")],
        playlist_url="https://open.spotify.com/playlist/abc",
    )

    app._handle_result(result)

    assert str(app.save_report_button.cget("state")) == "normal"
    assert str(app.open_playlist_button.cget("state")) == "normal"


def test_handle_result_cancelled_status(app):
    """A cancelled result is reflected in the status line."""
    result = GenerationResult(rows=[_make_result_row()], cancelled=True)

    app._handle_result(result)

    assert "Abgebrochen" in app.status_label.cget("text")


def test_handle_error_shows_message(app, fake_messagebox):
    """An error message is shown and the run button is re-enabled."""
    app._handle_error("boom")

    assert any(call[0] == "showerror" for call in fake_messagebox.calls)
    assert str(app.run_button.cget("state")) == "normal"


def test_cancel_sets_worker_flag(app):
    """Cancelling sets the worker's cancel event and disables the cancel button."""
    app._on_cancel()

    assert app.worker.cancel_event.is_set() is True
    assert str(app.cancel_button.cget("state")) == "disabled"


def test_run_without_csv_does_not_start_worker(app, fake_messagebox, monkeypatch):
    """An invalid form must warn and never reach the worker."""
    started = []
    monkeypatch.setattr(app.worker, "start", lambda *a, **k: started.append(a))

    app.csv_var.set("")
    app.name_var.set("")
    app._on_run()

    assert started == []
    assert app.worker.is_running() is False


# --- Client-ID-Prüfung ---

from spotify_playlist_generator.auth import CHECK_INVALID, CHECK_OK, CHECK_UNKNOWN


class _CheckOutcome:
    def __init__(self, status, message):
        self.status = status
        self.message = message

    @property
    def ok(self):
        return self.status == CHECK_OK


def _run_check_synchronously(app, outcome):
    """Runs the credential check with a stub checker and drains the Tk event loop."""
    app._on_check_credentials(checker=lambda config: outcome)
    deadline = time.time() + 3
    while app.settings_status_label.cget("text") == "Prüfe Client ID …" and time.time() < deadline:
        app.root.update()
        time.sleep(0.01)
    app.root.update()


def test_check_credentials_success_shows_ok(app):
    """A successful check shows the message in the OK style."""
    app.client_id_var.set("some-client-id")

    _run_check_synchronously(app, _CheckOutcome(CHECK_OK, "Alles in Ordnung."))

    assert app.settings_status_label.cget("text") == "Alles in Ordnung."
    assert str(app.settings_status_label.cget("style")) == "Ok.TLabel"
    assert str(app.check_button.cget("state")) == "normal"


def test_check_credentials_failure_shows_danger(app):
    """A failed check shows the message in the danger style."""
    app.client_id_var.set("bad-id")

    _run_check_synchronously(app, _CheckOutcome(CHECK_INVALID, "Client ID abgelehnt."))

    assert app.settings_status_label.cget("text") == "Client ID abgelehnt."
    assert str(app.settings_status_label.cget("style")) == "Danger.TLabel"
    assert str(app.check_button.cget("state")) == "normal"


def test_check_credentials_uses_form_values(app):
    """The check is run against the values currently entered in the form."""
    app.client_id_var.set("form-client-id")
    app.redirect_var.set("http://127.0.0.1:9999/callback")
    seen = []

    def checker(config):
        seen.append(config)
        return _CheckOutcome(CHECK_OK, "ok")

    app._on_check_credentials(checker=checker)
    deadline = time.time() + 3
    while not seen and time.time() < deadline:
        app.root.update()
        time.sleep(0.01)
    app.root.update()

    assert seen[0].client_id == "form-client-id"
    assert seen[0].redirect_uri == "http://127.0.0.1:9999/callback"


def test_check_credentials_unknown_shows_warning_not_ok(app):
    """An inconclusive check is shown as a warning, never as a green all-clear."""
    app.client_id_var.set("some-id")

    _run_check_synchronously(app, _CheckOutcome(CHECK_UNKNOWN, "Nicht eindeutig prüfbar."))

    assert app.settings_status_label.cget("text") == "Nicht eindeutig prüfbar."
    assert str(app.settings_status_label.cget("style")) == "Warn.TLabel"


def test_cancelled_run_with_playlist_mentions_it_in_status(app):
    """When a cancelled run already created a playlist, the status says so and the link works."""
    result = GenerationResult(
        rows=[ResultRow(row=1, title="t", artist="a", status="found", reason="",
                        matched_title="t", matched_artists="a",
                        spotify_url="https://open.spotify.com/track/1", score=1.0)],
        playlist_url="https://open.spotify.com/playlist/abc",
        playlist_id="abc",
        cancelled=True,
    )

    app._handle_result(result)

    assert "angelegt" in app.status_label.cget("text")
    assert str(app.open_playlist_button.cget("state")) == "normal"
