#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "Python wurde nicht gefunden. Bitte Python 3.11 oder neuer installieren." >&2
    exit 1
fi

if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Python 3.11 oder neuer wird benoetigt." >&2
    exit 1
fi

if ! "$PY" -c 'import tkinter' >/dev/null 2>&1; then
    echo "tkinter fehlt. Unter Debian/Ubuntu: sudo apt install python3-tk" >&2
    exit 1
fi

VENV=".venv"
if [ ! -x "$VENV/bin/python" ]; then
    echo "Richte die Arbeitsumgebung ein. Das dauert nur beim ersten Start ..."
    "$PY" -m venv "$VENV"
fi

MARKER="$VENV/.abhaengigkeiten.txt"
if ! cmp -s "$MARKER" requirements.txt; then
    echo "Installiere die benoetigten Pakete ..."
    "$VENV/bin/python" -m pip install --upgrade pip --quiet
    "$VENV/bin/python" -m pip install -r requirements.txt --quiet
    cp requirements.txt "$MARKER"
fi

exec "$VENV/bin/python" -m spotify_playlist_generator.gui
