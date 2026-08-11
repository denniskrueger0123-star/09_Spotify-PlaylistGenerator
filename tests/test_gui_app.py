"""Tests for the gui.app module."""

import time
from datetime import date, timedelta
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


@pytest.fixture(autouse=True)
def appdata_umleiten(tmp_path, monkeypatch):
    """kds_lizenz schreibt die Lizenzdatei in %APPDATA%. Ohne Umleitung läse
    und beschriebe ein Testlauf die echte Datei im Benutzerverzeichnis."""
    monkeypatch.setenv("APPDATA", str(tmp_path))


@pytest.fixture
def app(root, tmp_path):
    from spotify_playlist_generator.gui.app import App

    return App(root, settings_path=tmp_path / "settings.json")


def test_app_builds_five_tabs(app):
    """The main window has exactly five tabs with the expected labels."""
    tabs = app.notebook.tabs()
    assert len(tabs) == 5
    texts = [app.notebook.tab(t, "text") for t in tabs]
    assert any("Playlist erstellen" in t for t in texts)
    assert any("Ergebnis" in t for t in texts)
    assert any("Einstellungen" in t for t in texts)
    assert any("Hilfe" in t for t in texts)
    assert any("Über" in t for t in texts)


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


@pytest.fixture
def gueltige_lizenz(appdata_umleiten):
    """Richtet einen App-Schluessel ein und hinterlegt einen gültigen
    Lizenzschlüssel, damit ein Test bewusst die Sperre umgeht, um ein anderes
    Verhalten von _on_run zu prüfen. Stellt danach die echte (leere)
    Einrichtung dieser App wieder her."""
    import kds_lizenz

    from spotify_playlist_generator import lizenz_konfig

    fake_schluessel = b"\x22" * 32
    kds_lizenz.einrichten(
        produkt=lizenz_konfig.PRODUKT,
        app_schluessel=fake_schluessel,
        vorsilbe=lizenz_konfig.VORSILBE,
        ordner=lizenz_konfig.ORDNER,
    )
    gueltiger_schluessel = kds_lizenz.schluessel_erzeugen(
        "Testkunde", date.today() + timedelta(days=30)
    )
    kds_lizenz.lizenz_speichern(gueltiger_schluessel)
    yield
    kds_lizenz.einrichten(
        produkt=lizenz_konfig.PRODUKT,
        app_schluessel=lizenz_konfig.APP_SCHLUESSEL,
        vorsilbe=lizenz_konfig.VORSILBE,
        ordner=lizenz_konfig.ORDNER,
    )


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


def test_run_without_csv_warns(app, fake_messagebox, monkeypatch, gueltige_lizenz):
    """Running without CSV/name shows a warning and does not start the worker."""
    started = []
    monkeypatch.setattr(app.worker, "start", lambda *a, **kw: started.append((a, kw)))

    app._on_run()

    assert any(call[0] == "showwarning" for call in fake_messagebox.calls)
    assert started == []


def test_run_with_valid_input_starts_worker(app, fake_messagebox, monkeypatch, tmp_path, gueltige_lizenz):
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


def test_poll_keeps_running_until_a_final_message_arrives(app, monkeypatch):
    """Ein beendeter Thread darf das Abfragen nicht stoppen, solange die
    Abschlussmeldung noch aussteht – sonst friert die Anzeige ein."""
    monkeypatch.setattr(app.worker, "poll", lambda: [])
    monkeypatch.setattr(app.worker, "is_running", lambda: False)
    scheduled = []
    monkeypatch.setattr(app.root, "after", lambda ms, fn: scheduled.append(fn) or "job")

    app._poll_worker()

    assert scheduled, "ohne Abschlussmeldung muss weiter abgefragt werden"


def test_poll_stops_after_result(app, monkeypatch):
    """Nach dem Ergebnis wird kein weiterer Abruf mehr eingeplant."""
    result = GenerationResult(rows=[], playlist_url="")
    monkeypatch.setattr(app.worker, "poll", lambda: [("result", result)])
    scheduled = []
    monkeypatch.setattr(app.root, "after", lambda ms, fn: scheduled.append(fn) or "job")

    app._poll_worker()

    assert scheduled == []
    assert app._poll_job is None
    assert str(app.run_button["state"]) == "normal"


def test_run_without_client_id_shows_error(app, fake_messagebox, monkeypatch, tmp_path, gueltige_lizenz):
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


def test_run_without_csv_does_not_start_worker(app, fake_messagebox, monkeypatch, gueltige_lizenz):
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


def test_language_switch_translates_every_registered_label(app):
    """
    Umschalten auf Englisch übersetzt alle vorgemerkten Beschriftungen.

    Der Test vergleicht gegen die Wörterbücher selbst, damit eine neu
    hinzugefügte Beschriftung, die beim Umschalten vergessen wird, auffällt.
    """
    from spotify_playlist_generator import i18n

    app.lang_var.set("en")
    app._on_language_change()

    for widget, key in app._tr_widgets:
        assert widget.cget("text") == i18n.TEXTS["en"][key], f"{key} blieb deutsch"


def test_language_switch_updates_tab_labels(app):
    """Die Beschriftungen der beiden neuen Reiter folgen der Sprachwahl."""
    app.lang_var.set("en")
    app._on_language_change()
    texts = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
    assert any("Help" in t for t in texts)
    assert any("About" in t for t in texts)

    app.lang_var.set("de")
    app._on_language_change()
    texts = [app.notebook.tab(t, "text") for t in app.notebook.tabs()]
    assert any("Hilfe" in t for t in texts)
    assert any("Über" in t for t in texts)


def test_language_choice_survives_restart(root, tmp_path):
    """Die gewählte Sprache steht beim nächsten Start wieder da."""
    from spotify_playlist_generator.gui.app import App

    settings_path = tmp_path / "settings.json"
    first = App(root, settings_path=settings_path)
    first.lang_var.set("en")
    first._on_language_change()

    second_root = tk.Toplevel(root)
    second = App(second_root, settings_path=settings_path)
    assert second.lang_var.get() == "en"


def test_help_text_changes_with_language(app):
    """Der Hilfetext wird beim Umschalten neu aufgebaut."""
    deutsch = app.help_text.get("1.0", "end")
    app.lang_var.set("en")
    app._on_language_change()
    englisch = app.help_text.get("1.0", "end")

    assert "Einmalige Einrichtung" in deutsch
    assert "One-time setup" in englisch
    assert deutsch != englisch


def test_license_card_shows_not_eingerichtet_at_start(app):
    """Ohne App-Schlüssel (Auslieferungszustand dieses Repos) steht in der
    Lizenzkarte die eigene Meldung dafür - nicht 'keine Lizenz hinterlegt'.
    Das ist mein Versäumnis beim Bauen, nicht das des Nutzers."""
    from spotify_playlist_generator import i18n

    assert app.license_status_label.cget("text") == i18n.TEXTS["de"]["lizenz.nicht_eingerichtet"]


def test_menu_has_lizenz_entry_under_hilfe(app):
    """Der Menüpunkt Lizenz … sitzt unter Hilfe, wie beauftragt."""
    from spotify_playlist_generator import i18n

    assert app.menubar.entrycget(0, "label") == i18n.TEXTS["de"]["menu.hilfe"]
    assert app.help_menu.entrycget(0, "label") == i18n.TEXTS["de"]["menu.lizenz"]


def test_run_blocked_without_app_schluessel(app, fake_messagebox, monkeypatch):
    """Ohne App-Schlüssel bleibt der gesamte Suchlauf gesperrt - mit der
    eigenen Meldung, nicht der für eine fehlende Kundenlizenz."""
    from spotify_playlist_generator import i18n

    csv_path = Path(app.csv_var.get() or "x")
    started = []
    monkeypatch.setattr(app.worker, "start", lambda *a, **kw: started.append((a, kw)))

    app._on_run()

    assert started == []
    assert fake_messagebox.calls[0][0] == "showerror"
    assert fake_messagebox.calls[0][2] == i18n.TEXTS["de"]["lizenz.nicht_eingerichtet"]


def test_run_blocked_with_expired_license(app, fake_messagebox, monkeypatch, tmp_path):
    """Ein abgelaufener Schlüssel sperrt den Suchlauf mit einer anderen
    Meldung als eine ganz fehlende Lizenz."""
    import kds_lizenz

    from spotify_playlist_generator import i18n, lizenz_konfig

    kds_lizenz.einrichten(
        produkt=lizenz_konfig.PRODUKT,
        app_schluessel=b"\x33" * 32,
        vorsilbe=lizenz_konfig.VORSILBE,
        ordner=lizenz_konfig.ORDNER,
    )
    try:
        abgelaufen = kds_lizenz.schluessel_erzeugen("Kunde", date.today() - timedelta(days=1))
        kds_lizenz.lizenz_speichern(abgelaufen)

        started = []
        monkeypatch.setattr(app.worker, "start", lambda *a, **kw: started.append((a, kw)))

        app._on_run()

        assert started == []
        title, message = fake_messagebox.calls[0][1], fake_messagebox.calls[0][2]
        assert i18n.TEXTS["de"]["lizenz.nicht_eingerichtet"] not in message
    finally:
        kds_lizenz.einrichten(
            produkt=lizenz_konfig.PRODUKT,
            app_schluessel=lizenz_konfig.APP_SCHLUESSEL,
            vorsilbe=lizenz_konfig.VORSILBE,
            ordner=lizenz_konfig.ORDNER,
        )


def test_run_allowed_with_valid_license(app, fake_messagebox, monkeypatch, tmp_path, gueltige_lizenz):
    """Mit einer gültigen Lizenz läuft der Suchlauf ganz normal an - die
    Sperre greift nur, wenn sie soll."""
    csv_path = tmp_path / "songs.csv"
    csv_path.write_text("title,artist\nSong,Artist\n", encoding="utf-8")
    app.csv_var.set(str(csv_path))
    app.name_var.set("Meine Playlist")
    app.client_id_var.set("client-123")

    calls = []
    monkeypatch.setattr(app.worker, "start", lambda config, params, **kw: calls.append((config, params)))

    app._on_run()

    assert len(calls) == 1


def test_dialog_reused_not_duplicated(app):
    """Ein zweites Öffnen hebt den bestehenden Dialog an statt einen neuen zu bauen."""
    app._open_license_dialog()
    erster = app.license_dialog
    app._open_license_dialog()
    assert app.license_dialog is erster


def test_activate_garbage_key_shows_warning_never_crashes(app, fake_messagebox):
    """Müll im Eingabefeld führt zu einer Warnung, nie zu einer Ausnahme."""
    from tkinter import ttk

    status_label = ttk.Label(app.root)
    info_label = ttk.Label(app.root)

    app._on_activate_license("###👾 kein Schlüssel 5000" + "x" * 500, status_label, info_label)

    assert any(call[0] == "showwarning" for call in fake_messagebox.calls)


def test_activate_expired_key_not_saved(app, fake_messagebox, tmp_path):
    """Ein abgelaufener Schlüssel wird beim Aktivieren abgelehnt und nicht
    gespeichert - er überschreibt keinen vorhandenen gültigen Schlüssel."""
    import kds_lizenz

    from tkinter import ttk

    from spotify_playlist_generator import lizenz_konfig

    kds_lizenz.einrichten(
        produkt=lizenz_konfig.PRODUKT,
        app_schluessel=b"\x44" * 32,
        vorsilbe=lizenz_konfig.VORSILBE,
        ordner=lizenz_konfig.ORDNER,
    )
    try:
        abgelaufen = kds_lizenz.schluessel_erzeugen("Kunde", date.today() - timedelta(days=1))
        status_label = ttk.Label(app.root)
        info_label = ttk.Label(app.root)

        app._on_activate_license(abgelaufen, status_label, info_label)

        assert any(call[0] == "showwarning" for call in fake_messagebox.calls)
        zustand, lic = kds_lizenz.status()
        assert zustand == "fehlt"
    finally:
        kds_lizenz.einrichten(
            produkt=lizenz_konfig.PRODUKT,
            app_schluessel=lizenz_konfig.APP_SCHLUESSEL,
            vorsilbe=lizenz_konfig.VORSILBE,
            ordner=lizenz_konfig.ORDNER,
        )


def test_activate_valid_key_saves_and_refreshes_display(app, fake_messagebox, tmp_path):
    """Ein gültiger Schlüssel wird gespeichert, und die Über-Karte zeigt sofort
    den neuen Zustand."""
    import kds_lizenz

    from tkinter import ttk

    from spotify_playlist_generator import i18n, lizenz_konfig

    kds_lizenz.einrichten(
        produkt=lizenz_konfig.PRODUKT,
        app_schluessel=b"\x55" * 32,
        vorsilbe=lizenz_konfig.VORSILBE,
        ordner=lizenz_konfig.ORDNER,
    )
    try:
        gueltig = kds_lizenz.schluessel_erzeugen("Frau Beispiel", date.today() + timedelta(days=10))
        status_label = ttk.Label(app.root)
        info_label = ttk.Label(app.root)

        app._on_activate_license(gueltig, status_label, info_label)

        assert any(call[0] == "showinfo" for call in fake_messagebox.calls)
        assert app.license_status_label.cget("text") == i18n.TEXTS["de"]["lizenz.status.gueltig"]
        assert "Frau Beispiel" in app.license_info_label.cget("text")
    finally:
        kds_lizenz.einrichten(
            produkt=lizenz_konfig.PRODUKT,
            app_schluessel=lizenz_konfig.APP_SCHLUESSEL,
            vorsilbe=lizenz_konfig.VORSILBE,
            ordner=lizenz_konfig.ORDNER,
        )
