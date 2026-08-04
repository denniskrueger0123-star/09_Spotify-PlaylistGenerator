"""Führt den Suchlauf in einem Hintergrund-Thread aus."""

import queue
import threading

from ..errors import PlaylistGeneratorError
from ..pipeline import run_generation


class GenerationWorker:
    """Startet run_generation in einem Thread und meldet Ereignisse über eine Queue."""

    def __init__(self):
        self.queue = queue.Queue()
        self.cancel_event = threading.Event()
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config, params, runner=run_generation) -> None:
        self.cancel_event = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(config, params, runner), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self.cancel_event.set()

    def _run(self, config, params, runner):
        def progress(event):
            self.queue.put(("progress", event))

        try:
            result = runner(config, params, progress=progress, cancel=self.cancel_event)
        except PlaylistGeneratorError as exc:
            self.queue.put(("error", str(exc)))
        except Exception as exc:
            self.queue.put(("error", f"Unerwarteter Fehler: {exc}"))
        else:
            self.queue.put(("result", result))

    def poll(self) -> list:
        messages = []
        while True:
            try:
                messages.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return messages
