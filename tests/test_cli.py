"""Tests for the CLI module."""

import pytest

import spotify_playlist_generator.cli as cli_module
import spotify_playlist_generator.settings as settings_module
from spotify_playlist_generator.errors import SpotifyApiError
from spotify_playlist_generator.pipeline import GenerationResult, ProgressEvent
from spotify_playlist_generator.report import ResultRow


def _row(row=2, status="found", title="Song One", artist="Artist One"):
    return ResultRow(row=row, title=title, artist=artist, status=status,
                     reason="" if status == "found" else "Grund",
                     matched_title="M", matched_artists="A",
                     spotify_url="https://example.com/t", score=0.9)


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path):
    """Keep the real user settings file out of these tests."""
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", tmp_path / "no-settings.json")


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "songs.csv"
    path.write_text("title,artist\n")
    return path


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_id")
    path = tmp_path / ".env"
    path.write_text("")
    return path


def _base_args(csv_file, env_file, name="My Playlist"):
    return ["--csv", str(csv_file), "--name", name, "--env-file", str(env_file)]


def test_main_prints_song_messages(monkeypatch, capsys, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        progress(ProgressEvent(kind="song", message="[1/2] A … gefunden"))
        return GenerationResult(rows=[_row()])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    cli_module.main(_base_args(csv_file, env_file))

    captured = capsys.readouterr()
    assert "[1/2] A … gefunden" in captured.out.splitlines()


def test_main_prints_info_with_leading_blank_line(monkeypatch, capsys, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        progress(ProgressEvent(kind="info", message="Playlist erstellt: https://x"))
        return GenerationResult(rows=[_row()])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    cli_module.main(_base_args(csv_file, env_file))

    captured = capsys.readouterr()
    assert "\nPlaylist erstellt: https://x\n" in captured.out


def test_main_ignores_auth_start_done_events(monkeypatch, capsys, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        progress(ProgressEvent(kind="auth", message="AUTH_TEXT_MARKER"))
        progress(ProgressEvent(kind="start", message="START_TEXT_MARKER"))
        progress(ProgressEvent(kind="done", message="DONE_TEXT_MARKER"))
        return GenerationResult(rows=[_row()])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    cli_module.main(_base_args(csv_file, env_file))

    captured = capsys.readouterr()
    assert "AUTH_TEXT_MARKER" not in captured.out
    assert "START_TEXT_MARKER" not in captured.out
    assert "DONE_TEXT_MARKER" not in captured.out


def test_main_returns_exit_code_zero_when_all_found(monkeypatch, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        return GenerationResult(rows=[_row(status="found")])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    assert cli_module.main(_base_args(csv_file, env_file)) == 0


def test_main_returns_exit_code_one_when_not_found(monkeypatch, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        return GenerationResult(rows=[_row(status="not_found")])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    assert cli_module.main(_base_args(csv_file, env_file)) == 1


def test_main_prints_summary(monkeypatch, capsys, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        return GenerationResult(rows=[_row(status="found")])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    cli_module.main(_base_args(csv_file, env_file))

    captured = capsys.readouterr()
    assert "Gesamt:" in captured.out
    assert "Gefunden:" in captured.out


def test_main_writes_report_when_requested(monkeypatch, tmp_path, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        return GenerationResult(rows=[_row(status="found")])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    report_path = tmp_path / "r.csv"
    args = _base_args(csv_file, env_file) + ["--report", str(report_path)]

    cli_module.main(args)

    assert report_path.exists()
    header = report_path.read_text().splitlines()[0]
    assert header.startswith("row,title,artist,status")


def test_main_does_not_write_report_by_default(monkeypatch, tmp_path, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        return GenerationResult(rows=[_row(status="found")])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    cli_module.main(_base_args(csv_file, env_file))

    csv_files = list(tmp_path.glob("*.csv"))
    # only the input csv_file itself should exist, no report csv
    assert csv_files == [csv_file]


def test_main_passes_all_params(monkeypatch, tmp_path, csv_file, env_file):
    captured_params = {}

    def fake_run_generation(config, params, progress=None, **kwargs):
        captured_params["params"] = params
        return GenerationResult(rows=[_row(status="found")])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    args = _base_args(csv_file, env_file) + [
        "--description", "My Desc",
        "--public",
        "--market", "DE",
        "--min-score", "0.8",
        "--limit", "25",
        "--dry-run",
    ]

    cli_module.main(args)

    params = captured_params["params"]
    assert params.playlist_name == "My Playlist"
    assert params.description == "My Desc"
    assert params.public is True
    assert params.market == "DE"
    assert params.min_score == 0.8
    assert params.limit == 25
    assert params.dry_run is True


def test_main_default_params(monkeypatch, csv_file, env_file):
    captured_params = {}

    def fake_run_generation(config, params, progress=None, **kwargs):
        captured_params["params"] = params
        return GenerationResult(rows=[_row(status="found")])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    cli_module.main(_base_args(csv_file, env_file))

    params = captured_params["params"]
    assert params.description == ""
    assert params.public is False
    assert params.market is None
    assert params.dry_run is False
    assert params.limit == 10
    assert params.min_score == cli_module.matcher.DEFAULT_MIN_SCORE


def test_main_token_path_override(monkeypatch, tmp_path, csv_file, env_file):
    captured_config = {}

    def fake_run_generation(config, params, progress=None, **kwargs):
        captured_config["config"] = config
        return GenerationResult(rows=[_row(status="found")])

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    token_path = tmp_path / "t.json"
    args = _base_args(csv_file, env_file) + ["--token-path", str(token_path)]

    cli_module.main(args)

    assert captured_config["config"].token_path == token_path


def test_main_config_error_returns_2(monkeypatch, capsys, tmp_path, csv_file):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    missing_env = tmp_path / "nonexistent.env"

    args = ["--csv", str(csv_file), "--name", "My Playlist", "--env-file", str(missing_env)]

    result = cli_module.main(args)

    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.startswith("Fehler: ")


def test_main_keyboard_interrupt_returns_130(monkeypatch, capsys, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    result = cli_module.main(_base_args(csv_file, env_file))

    captured = capsys.readouterr()
    assert result == 130
    assert "Abgebrochen vom Benutzer" in captured.err


def test_main_spotify_error_returns_2(monkeypatch, capsys, csv_file, env_file):
    def fake_run_generation(config, params, progress=None, **kwargs):
        raise SpotifyApiError("kaputt")

    monkeypatch.setattr(cli_module, "run_generation", fake_run_generation)

    result = cli_module.main(_base_args(csv_file, env_file))

    captured = capsys.readouterr()
    assert result == 2
    assert "Fehler: kaputt" in captured.err
