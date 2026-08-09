"""Tests für spotify_playlist_generator.gui.worker — laufen ohne tkinter."""

import queue

from spotify_playlist_generator.errors import CsvError
from spotify_playlist_generator.gui.worker import GenerationWorker


def _join(worker):
    assert worker._thread is not None
    worker._thread.join(timeout=5)


def test_worker_reports_result():
    worker = GenerationWorker()

    def runner(config, params, progress, cancel):
        return "ERGEBNIS"

    worker.start("config", "params", runner=runner)
    _join(worker)

    assert worker.poll() == [("result", "ERGEBNIS")]


def test_worker_forwards_progress_events():
    worker = GenerationWorker()

    def runner(config, params, progress, cancel):
        progress("E1")
        progress("E2")
        return "ERGEBNIS"

    worker.start("config", "params", runner=runner)
    _join(worker)

    messages = worker.poll()
    assert messages == [
        ("progress", "E1"),
        ("progress", "E2"),
        ("result", "ERGEBNIS"),
    ]


def test_worker_reports_pipeline_error():
    worker = GenerationWorker()

    def runner(config, params, progress, cancel):
        raise CsvError("kaputt")

    worker.start("config", "params", runner=runner)
    _join(worker)

    assert worker.poll() == [("error", "kaputt")]


def test_worker_reports_unexpected_error():
    worker = GenerationWorker()

    def runner(config, params, progress, cancel):
        raise ValueError("upsi")

    worker.start("config", "params", runner=runner)
    _join(worker)

    messages = worker.poll()
    assert len(messages) == 1
    kind, message = messages[0]
    assert kind == "error"
    assert message.startswith("Unerwarteter Fehler")
    assert "upsi" in message


def test_worker_always_reports_something():
    """Auch wenn der Lauf ohne Ergebnis endet, kommt genau eine Abschlussmeldung —
    die Oberfläche wartet darauf und bliebe sonst stehen."""
    worker = GenerationWorker()

    def runner(config, params, progress, cancel):
        return None

    worker.start("config", "params", runner=runner)
    _join(worker)

    messages = worker.poll()
    assert len(messages) == 1
    assert messages[0][0] in ("result", "error")


def test_worker_passes_config_and_params():
    worker = GenerationWorker()
    captured = {}

    def runner(config, params, progress, cancel):
        captured["config"] = config
        captured["params"] = params
        return None

    config = {"client_id": "abc"}
    params = {"playlist_name": "Meine Playlist"}
    worker.start(config, params, runner=runner)
    _join(worker)

    assert captured["config"] is config
    assert captured["params"] is params


def test_worker_cancel_sets_event():
    worker = GenerationWorker()
    captured = {}

    def runner(config, params, progress, cancel):
        captured["cancel"] = cancel
        return None

    worker.start("config", "params", runner=runner)
    _join(worker)

    worker.cancel()
    assert captured["cancel"].is_set()


def test_worker_start_creates_fresh_cancel_event():
    worker = GenerationWorker()

    def runner(config, params, progress, cancel):
        return None

    worker.start("config", "params", runner=runner)
    _join(worker)

    worker.cancel()
    assert worker.cancel_event.is_set()

    worker.start("config", "params", runner=runner)
    _join(worker)

    assert worker.cancel_event.is_set() is False


def test_is_running_false_before_start():
    worker = GenerationWorker()
    assert worker.is_running() is False


def test_is_running_false_after_finish():
    worker = GenerationWorker()

    def runner(config, params, progress, cancel):
        return None

    worker.start("config", "params", runner=runner)
    _join(worker)

    assert worker.is_running() is False


def test_poll_returns_empty_list_when_nothing_queued():
    worker = GenerationWorker()
    assert worker.poll() == []


def test_poll_drains_queue():
    worker = GenerationWorker()

    def runner(config, params, progress, cancel):
        progress("E1")
        return "ERGEBNIS"

    worker.start("config", "params", runner=runner)
    _join(worker)

    first = worker.poll()
    assert first == [("progress", "E1"), ("result", "ERGEBNIS")]

    second = worker.poll()
    assert second == []
