"""Hauptfenster der grafischen Oberfläche."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
from pathlib import Path

from ..auth import has_cached_token, reset_token
from ..config import Config, DEFAULT_REDIRECT_URI, DEFAULT_TOKEN_PATH, load_config
from ..errors import PlaylistGeneratorError
from ..matcher import DEFAULT_MIN_SCORE
from ..report import write_report
from ..settings import load_settings, save_settings
from . import theme
from . import viewmodel as vm
from .worker import GenerationWorker

APP_TITLE = "Spotify Playlist Generator"
SUBTITLE = "CSV rein, Playlist raus."
DASHBOARD_URL = "https://developer.spotify.com/dashboard"


class App:
    """Hauptfenster der Anwendung mit den drei Reitern."""

    def __init__(self, root, settings_path=None):
        self.root = root
        self.settings_path = settings_path
        self.style = theme.apply_theme(root)

        root.title(APP_TITLE)
        root.geometry("1020x820")
        root.minsize(880, 640)

        self.result = None
        self.row_urls = {}
        self.sort_reverse = {}

        self.csv_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.public_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.market_var = tk.StringVar(value="")
        self.min_score_var = tk.DoubleVar(value=DEFAULT_MIN_SCORE)
        self.limit_var = tk.IntVar(value=10)
        self.client_id_var = tk.StringVar()
        self.client_secret_var = tk.StringVar()
        self.redirect_var = tk.StringVar()
        self.token_path_var = tk.StringVar()

        self.worker = GenerationWorker()
        self._poll_job = None

        self._build()
        self._load_settings_into_form()

    def _card(self, parent, title):
        """Legt eine Karte mit Überschrift an und gibt (karte, inhalt) zurück."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=18)
        card.pack(fill="x", pady=(0, 14))
        ttk.Label(card, text=title, style="H2.TLabel").pack(anchor="w", pady=(0, 12))
        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        return card, body

    def _build(self):
        outer = ttk.Frame(self.root, style="TFrame")
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="TFrame", padding=(24, 20, 24, 8))
        header.pack(fill="x")

        titlerow = ttk.Frame(header, style="TFrame")
        titlerow.pack(anchor="w")
        ttk.Label(titlerow, text="●", style="H1.TLabel", foreground=theme.ACCENT).pack(side="left")
        ttk.Label(titlerow, text=APP_TITLE, style="H1.TLabel").pack(side="left", padx=(10, 0))

        ttk.Label(header, text=SUBTITLE, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        self._build_run_tab()
        self._build_result_tab()
        self._build_settings_tab()

    def _build_run_tab(self):
        tab = ttk.Frame(self.notebook, style="TFrame", padding=16)
        self.notebook.add(tab, text="  Playlist erstellen  ")

        _, body = self._card(tab, "1 · CSV-Datei")
        row = ttk.Frame(body, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.csv_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Durchsuchen …", command=self._on_browse).pack(side="left", padx=(10, 0))
        self.csv_info_label = ttk.Label(body, text="Noch keine Datei gewählt", style="CardMuted.TLabel")
        self.csv_info_label.pack(anchor="w", pady=(10, 0))

        _, body = self._card(tab, "2 · Playlist")
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Name", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=4)
        ttk.Label(body, text="Beschreibung", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.desc_var).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=4)
        checks = ttk.Frame(body, style="Card.TFrame")
        checks.grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Checkbutton(checks, text="Öffentlich sichtbar", variable=self.public_var).pack(side="left")
        ttk.Checkbutton(
            checks, text="Trockenlauf – nichts anlegen", variable=self.dry_run_var
        ).pack(side="left", padx=(20, 0))

        card = ttk.Frame(tab, style="Card.TFrame", padding=18)
        card.pack(fill="x", pady=(0, 14))
        self.advanced_open = False
        self.advanced_button = ttk.Button(
            card, text="▸  Erweiterte Einstellungen", command=self._toggle_advanced
        )
        self.advanced_button.pack(anchor="w")
        self.advanced_body = ttk.Frame(card, style="Card.TFrame")
        self.advanced_body.columnconfigure(1, weight=1)

        ttk.Label(self.advanced_body, text="Markt", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", pady=6
        )
        ttk.Combobox(
            self.advanced_body,
            values=list(vm.MARKETS),
            textvariable=self.market_var,
            state="readonly",
            width=8,
        ).grid(row=0, column=1, sticky="w", padx=(12, 0), pady=6)

        ttk.Label(self.advanced_body, text="Mindest-Score", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=6
        )
        score_row = ttk.Frame(self.advanced_body, style="Card.TFrame")
        score_row.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=6)
        ttk.Scale(
            score_row,
            from_=0.0,
            to=1.0,
            variable=self.min_score_var,
            orient="horizontal",
            command=self._on_score_change,
        ).pack(side="left", fill="x", expand=True)
        self.score_label = ttk.Label(score_row, style="Card.TLabel", width=5)
        self.score_label.pack(side="left", padx=(10, 0))

        ttk.Label(self.advanced_body, text="Treffer pro Suche", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=6
        )
        ttk.Spinbox(self.advanced_body, from_=1, to=50, textvariable=self.limit_var, width=6).grid(
            row=2, column=1, sticky="w", padx=(12, 0), pady=6
        )

        self._on_score_change(None)

        # Unten verankert, damit dieser Bereich nie aus dem Fenster rutscht
        bottom = ttk.Frame(tab, style="TFrame")
        bottom.pack(side="bottom", fill="x")

        actions = ttk.Frame(bottom, style="TFrame")
        actions.pack(fill="x", pady=(4, 0))
        self.run_button = ttk.Button(actions, text="Playlist erstellen", style="Accent.TButton", command=self._on_run)
        self.run_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Abbrechen", command=self._on_cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(bottom, mode="determinate", style="Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(16, 6))

        self.status_label = ttk.Label(bottom, text="Bereit", style="Muted.TLabel")
        self.status_label.pack(anchor="w")

        self.log_text = tk.Text(tab, height=5, relief="flat", borderwidth=0,
                                 background=theme.SURFACE, foreground=theme.TEXT_MUTED,
                                 insertbackground=theme.TEXT, font=theme.fonts()["mono"],
                                 state="disabled", wrap="none", highlightthickness=0)
        self.log_text.pack(side="bottom", fill="both", expand=True, pady=(12, 12))

    def _build_result_tab(self):
        tab = ttk.Frame(self.notebook, style="TFrame", padding=16)
        self.notebook.add(tab, text="  Ergebnis  ")

        chips = ttk.Frame(tab, style="TFrame")
        chips.pack(fill="x", pady=(0, 14))
        self.chip_values = {}
        for key, caption in (
            ("total", "Gesamt"),
            ("found", "Gefunden"),
            ("not_found", "Nicht gefunden"),
            ("error", "Fehler"),
        ):
            chip = ttk.Frame(chips, style="Card.TFrame", padding=16)
            chip.pack(side="left", fill="x", expand=True, padx=(0, 10) if key != "error" else (0, 0))
            value = ttk.Label(chip, text="0", style="Value.TLabel")
            value.pack(anchor="w")
            ttk.Label(chip, text=caption, style="CardMuted.TLabel").pack(anchor="w")
            self.chip_values[key] = value

        holder = ttk.Frame(tab, style="Card.TFrame", padding=12)
        holder.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            holder, columns=vm.RESULT_COLUMNS, show="headings", selectmode="browse"
        )
        widths = {"row": 60, "title": 210, "artist": 170, "status": 120, "matched": 260, "score": 70}
        for col, head in zip(vm.RESULT_COLUMNS, vm.RESULT_HEADINGS):
            self.tree.heading(
                col, text=head, command=lambda c=col: self._sort_by(c),
                anchor="e" if col in ("row", "score") else "w",
            )
            if col in ("row", "score"):
                self.tree.column(col, width=widths[col], anchor="e", stretch=False)
            else:
                self.tree.column(col, width=widths[col], stretch=True)

        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        for status, colour in theme.tag_colors().items():
            self.tree.tag_configure(status, foreground=colour)

        self.tree.bind("<Double-1>", self._on_row_double_click)

        buttons = ttk.Frame(tab, style="TFrame")
        buttons.pack(fill="x", pady=(14, 0))
        self.save_report_button = ttk.Button(
            buttons, text="Report als CSV speichern …", command=self._on_save_report, state="disabled"
        )
        self.save_report_button.pack(side="left")
        self.open_playlist_button = ttk.Button(
            buttons, text="Playlist in Spotify öffnen", command=self._on_open_playlist, state="disabled"
        )
        self.open_playlist_button.pack(side="left", padx=(10, 0))

    def _build_settings_tab(self):
        tab = ttk.Frame(self.notebook, style="TFrame", padding=16)
        self.notebook.add(tab, text="  Einstellungen  ")

        _, body = self._card(tab, "Spotify-Zugang")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Client ID", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(body, textvariable=self.client_id_var).grid(
            row=0, column=1, sticky="ew", padx=(12, 0), pady=6
        )

        ttk.Label(body, text="Client Secret", style="Card.TLabel").grid(
            row=1, column=0, sticky="w", pady=6
        )
        ttk.Entry(body, textvariable=self.client_secret_var, show="•").grid(
            row=1, column=1, sticky="ew", padx=(12, 0), pady=6
        )

        ttk.Label(
            body,
            text=(
                "Optional – für den PKCE-Flow dieser App nicht nötig. "
                "Nur ausfüllen, wenn deine Spotify-App ein Secret verlangt."
            ),
            style="CardMuted.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(body, text="Redirect URI", style="Card.TLabel").grid(
            row=3, column=0, sticky="w", pady=6
        )
        ttk.Entry(body, textvariable=self.redirect_var).grid(
            row=3, column=1, sticky="ew", padx=(12, 0), pady=6
        )

        ttk.Label(
            body,
            text="Muss im Spotify-Dashboard exakt so eingetragen sein.",
            style="CardMuted.TLabel",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(body, text="Token-Datei", style="Card.TLabel").grid(
            row=5, column=0, sticky="w", pady=6
        )
        ttk.Entry(body, textvariable=self.token_path_var, state="readonly").grid(
            row=5, column=1, sticky="ew", padx=(12, 0), pady=6
        )

        _, body = self._card(tab, "Anmeldung")
        self.login_status_label = ttk.Label(body, text="", style="CardMuted.TLabel")
        self.login_status_label.pack(anchor="w", pady=(0, 12))

        button_row = ttk.Frame(body, style="Card.TFrame")
        button_row.pack(anchor="w")
        ttk.Button(
            button_row,
            text="Einstellungen speichern",
            style="Accent.TButton",
            command=self._on_save_settings,
        ).pack(side="left")
        ttk.Button(
            button_row, text="Anmeldung zurücksetzen", command=self._on_reset_login
        ).pack(side="left", padx=(10, 0))
        ttk.Button(
            button_row, text="Spotify Dashboard öffnen", command=self._on_open_dashboard
        ).pack(side="left", padx=(10, 0))

        self.settings_status_label = ttk.Label(body, text="", style="CardMuted.TLabel")
        self.settings_status_label.pack(anchor="w", pady=(12, 0))

    def _log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, text):
        self.status_label.configure(text=text)

    def _on_browse(self):
        path = filedialog.askopenfilename(
            title="CSV-Datei auswählen",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        self._set_csv(path)

    def _set_csv(self, path_text):
        self.csv_var.set(path_text)
        info = vm.describe_csv(Path(path_text))
        self.csv_info_label.configure(
            text=info.message, style="Ok.TLabel" if info.ok else "Danger.TLabel"
        )
        if info.ok and not self.name_var.get().strip():
            self.name_var.set(vm.default_playlist_name(Path(path_text)))

    def _on_score_change(self, _event):
        self.score_label.configure(text=f"{self.min_score_var.get():.2f}")

    def _toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.advanced_body.pack(fill="x", pady=(14, 0))
            self.advanced_button.configure(text="▾  Erweiterte Einstellungen")
        else:
            self.advanced_body.pack_forget()
            self.advanced_button.configure(text="▸  Erweiterte Einstellungen")

    def _sort_by(self, column):
        index = vm.RESULT_COLUMNS.index(column)
        entries = [(self.tree.item(i, "values"), i) for i in self.tree.get_children("")]
        entries.sort(key=lambda pair: vm.sort_key(pair[0], index), reverse=self.sort_reverse.get(column, False))
        for position, (_, item) in enumerate(entries):
            self.tree.move(item, "", position)
        self.sort_reverse[column] = not self.sort_reverse.get(column, False)

    def _on_row_double_click(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        item = selection[0]
        url = self.row_urls.get(item)
        if url:
            webbrowser.open(url)

    def _on_save_report(self):
        if self.result is None or not self.result.rows:
            return
        path = filedialog.asksaveasfilename(
            title="Report speichern", defaultextension=".csv", filetypes=[("CSV-Dateien", "*.csv")]
        )
        if not path:
            return
        try:
            write_report(Path(path), self.result.rows)
        except OSError as exc:
            messagebox.showerror("Fehler", f"Report konnte nicht gespeichert werden: {exc}")
            return
        self._set_status(f"Report gespeichert: {path}")

    def _on_open_playlist(self):
        if self.result and self.result.playlist_url:
            webbrowser.open(self.result.playlist_url)

    def _on_open_dashboard(self):
        webbrowser.open(DASHBOARD_URL)

    def _load_settings_into_form(self):
        data = load_settings(self.settings_path)
        self.client_id_var.set(data.get("client_id", ""))
        self.client_secret_var.set(data.get("client_secret", ""))
        self.redirect_var.set(data.get("redirect_uri", "") or DEFAULT_REDIRECT_URI)
        self.token_path_var.set(data.get("token_path", "") or str(DEFAULT_TOKEN_PATH))
        self._refresh_login_status()

    def _refresh_login_status(self):
        path = Path(self.token_path_var.get())
        if has_cached_token(path):
            text = "Angemeldet – ein gültiger Zugang ist gespeichert."
            style = "Ok.TLabel"
        else:
            text = "Nicht angemeldet – die Anmeldung startet beim ersten Lauf im Browser."
            style = "CardMuted.TLabel"
        self.login_status_label.configure(text=text, style=style)

    def _on_save_settings(self):
        data = {
            "client_id": self.client_id_var.get(),
            "client_secret": self.client_secret_var.get(),
            "redirect_uri": self.redirect_var.get(),
            "token_path": self.token_path_var.get(),
        }
        try:
            save_settings(data, self.settings_path)
        except OSError as exc:
            messagebox.showerror("Fehler", f"Einstellungen konnten nicht gespeichert werden: {exc}")
            return
        self.settings_status_label.configure(text="Gespeichert.", style="Ok.TLabel")
        self._refresh_login_status()

    def _on_reset_login(self):
        reset_token(Path(self.token_path_var.get()))
        self.settings_status_label.configure(text="Anmeldung zurückgesetzt.", style="Ok.TLabel")
        self._refresh_login_status()

    def _current_config(self):
        """
        Baut die Konfiguration für einen Lauf.

        Ausgefüllte Felder im Einstellungen-Reiter haben Vorrang; ist dort keine
        Client-ID hinterlegt, greift die übliche Ladereihenfolge aus Umgebung,
        settings.json und .env.
        """
        client_id = self.client_id_var.get().strip()
        if client_id:
            return Config(
                client_id=client_id,
                redirect_uri=self.redirect_var.get().strip() or DEFAULT_REDIRECT_URI,
                token_path=Path(self.token_path_var.get().strip() or str(DEFAULT_TOKEN_PATH)),
                client_secret=self.client_secret_var.get().strip(),
            )
        return load_config(settings_path=self.settings_path)

    def _on_run(self):
        """Startet den Suchlauf im Hintergrund."""
        if self.worker.is_running():
            return

        errors = vm.validate(self.csv_var.get(), self.name_var.get())
        if errors:
            messagebox.showwarning("Eingaben unvollständig", "\n".join(errors))
            return

        try:
            config = self._current_config()
        except PlaylistGeneratorError as exc:
            messagebox.showerror("Keine Zugangsdaten", str(exc))
            self.notebook.select(self.notebook.tabs()[2])
            return

        params = vm.build_params(
            self.csv_var.get(), self.name_var.get(),
            description=self.desc_var.get(), public=self.public_var.get(),
            market=self.market_var.get(), min_score=self.min_score_var.get(),
            limit=self.limit_var.get(), dry_run=self.dry_run_var.get(),
        )

        self._reset_run_state()
        self.worker.start(config, params)
        self._poll_worker()

    def _reset_run_state(self):
        """Setzt Tabelle, Kennzahlen, Protokoll und Buttons für einen neuen Lauf zurück."""
        self.result = None
        self.row_urls.clear()
        self.tree.delete(*self.tree.get_children(""))
        for value in self.chip_values.values():
            value.configure(text="0")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.progress.configure(value=0, maximum=100)
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.save_report_button.configure(state="disabled")
        self.open_playlist_button.configure(state="disabled")
        self._set_status("Wird gestartet …")

    def _poll_worker(self):
        """Holt Meldungen des Hintergrund-Threads und plant den nächsten Abruf."""
        for kind, payload in self.worker.poll():
            if kind == "progress":
                self._handle_progress(payload)
            elif kind == "result":
                self._handle_result(payload)
            elif kind == "error":
                self._handle_error(payload)
        if self.worker.is_running():
            self._poll_job = self.root.after(80, self._poll_worker)
        else:
            self._poll_job = None

    def _handle_progress(self, event):
        if event.kind == "auth":
            self._set_status("Anmeldung bei Spotify … bitte das Browserfenster beachten.")
        elif event.kind == "start":
            self.progress.configure(maximum=max(event.total, 1), value=0)
            self._set_status(f"Suche läuft … ({event.total} Song(s))")
        elif event.kind == "song":
            self.progress.configure(value=event.index)
            self._set_status(event.message)
            self._log(event.message)
            if event.row is not None:
                self._append_result_row(event.row)
        elif event.kind == "info":
            self._log(event.message)
        elif event.kind == "done":
            pass

    def _append_result_row(self, row):
        item = self.tree.insert("", "end", values=vm.result_row_values(row), tags=(row.status,))
        if row.spotify_url:
            self.row_urls[item] = row.spotify_url

    def _handle_result(self, result):
        self.result = result
        for key, value in result.counts.items():
            self.chip_values[key].configure(text=str(value))
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if result.rows:
            self.save_report_button.configure(state="normal")
        if result.playlist_url:
            self.open_playlist_button.configure(state="normal")
            self._log(f"Playlist erstellt: {result.playlist_url}")
        if result.cancelled:
            self._set_status("Abgebrochen.")
        else:
            self._set_status(vm.summary_line(result.rows))
        if result.rows:
            self.notebook.select(self.notebook.tabs()[1])

    def _handle_error(self, message):
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self._set_status("Abgebrochen wegen eines Fehlers.")
        self._log(message)
        messagebox.showerror("Fehler", message)

    def _on_cancel(self):
        """Fordert den Abbruch des laufenden Vorgangs an."""
        self.worker.cancel()
        self.cancel_button.configure(state="disabled")
        self._set_status("Abbruch angefordert – der aktuelle Song wird noch beendet …")


def main() -> int:
    """Startet die grafische Oberfläche."""
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
