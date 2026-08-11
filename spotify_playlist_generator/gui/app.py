"""Hauptfenster der grafischen Oberfläche."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
from pathlib import Path
from typing import NamedTuple

import queue
import threading

from .. import __version__
from .. import i18n
from .. import lizenz
from ..auth import (
    CHECK_INVALID,
    CHECK_OK,
    CHECK_UNKNOWN,
    CredentialCheck,
    check_credentials,
    has_cached_token,
    reset_token,
)
from ..config import Config, DEFAULT_REDIRECT_URI, DEFAULT_TOKEN_PATH, load_config
from ..errors import PlaylistGeneratorError
from ..matcher import DEFAULT_MIN_SCORE
from ..report import write_report
from ..settings import load_settings, save_settings
from ..spotify_client import MAX_SEARCH_LIMIT
from . import theme
from . import branding
from . import viewmodel as vm
from .worker import GenerationWorker

APP_TITLE = "Spotify Playlist Generator"
SUBTITLE = "CSV rein, Playlist raus."
DEVELOPER = "Dennis Krüger"
COMPANY = "Krüger Digital Solutions"
DASHBOARD_URL = "https://developer.spotify.com/dashboard"
REPO_URL = "https://github.com/denniskrueger0123-star/09_Spotify-PlaylistGenerator"

# Ab hier wird aus der beiläufigen Lizenzanzeige eine Warnung. Vier Wochen
# reichen, um eine Verlängerung zu besorgen, ohne dass die Anzeige monatelang
# mahnt und dabei aufhört, aufzufallen.
LIZENZ_WARNUNG_TAGE = 30

# Stilnamen je Zustandsfarbe: (Kopfzeile auf Fensterhintergrund, Karte).
ZUSTANDSFARBEN = {
    "ok": ("OkBg.TLabel", "Ok.TLabel"),
    "warn": ("WarnBg.TLabel", "Warn.TLabel"),
    "danger": ("DangerBg.TLabel", "Danger.TLabel"),
    "muted": ("Muted.TLabel", "CardMuted.TLabel"),
}


class LizenzAnzeige(NamedTuple):
    """Was die Oberfläche über den Lizenzzustand anzeigt.

    chip     kurze Fassung für die Kopfzeile
    karte    Statuszeile im Reiter Über
    banner   Hinweis über den Karten im Reiter Playlist erstellen ("" wenn frei)
    farbe    Schlüssel in ZUSTANDSFARBEN
    zusatz   Kunde und Ablaufdatum, sofern eine Lizenz gelesen werden konnte
    gesperrt True, solange der Suchlauf nicht laufen darf
    """

    chip: str
    karte: str
    banner: str
    farbe: str
    zusatz: str
    gesperrt: bool


class App:
    """Hauptfenster der Anwendung mit den drei Reitern."""

    def __init__(self, root, settings_path=None):
        self.root = root
        self.settings_path = settings_path
        self.style = theme.apply_theme(root)

        root.title(f"{APP_TITLE} — v{__version__}")
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

        # Internationalisierung und Lizenzierung
        # Die Sprache steht fest, bevor irgendein Fensterteil gebaut wird. Sonst
        # entstünden Beschriftungen in der Standardsprache, die erst beim ersten
        # Umschalten korrigiert würden.
        self.lang_var = tk.StringVar(
            value=load_settings(settings_path).get("language", i18n.DEFAULT_LANGUAGE)
        )
        self._logo_image = None
        self._mark_image = None
        self.license_dialog = None

        # Beschriftungen, die der Sprachwahl folgen: (Widget, Textschlüssel).
        # Ohne diese Liste müsste jede einzelne Stelle beim Umschalten von Hand
        # nachgezogen werden, und vergessene Stellen blieben unbemerkt stehen.
        self._tr_widgets = []

        self.worker = GenerationWorker()
        self._poll_job = None
        self._check_queue = queue.Queue()

        self._build()
        self._build_menu()
        self._load_settings_into_form()

    def _card(self, parent, title):
        """Legt eine Karte mit Überschrift an und gibt (karte, inhalt) zurück."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=18)
        card.pack(fill="x", pady=(0, 14))
        ttk.Label(card, text=title, style="H2.TLabel").pack(anchor="w", pady=(0, 12))
        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        return card, body

    def _tr(self, widget, key):
        """Setzt die Beschriftung und merkt sie für spätere Sprachwechsel vor."""
        self._tr_widgets.append((widget, key))
        widget.configure(text=i18n.t(self.lang_var.get(), key))
        return widget

    def _card_tr(self, parent, key):
        """Wie _card, aber die Überschrift folgt der gewählten Sprache."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=18)
        card.pack(fill="x", pady=(0, 14))
        self._tr(ttk.Label(card, style="H2.TLabel"), key).pack(anchor="w", pady=(0, 12))
        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        return card, body

    def _scrollable(self, parent):
        """
        Gibt einen Rahmen zurück, dessen Inhalt bei Bedarf gerollt werden kann.

        Der Über-Reiter ist höher als ein 820 Pixel hohes Fenster. Ohne Rollbalken
        lägen der Knopf zum Speichern des Lizenzschlüssels und die Links unterhalb
        des Fensterrands und wären schlicht nicht erreichbar.
        """
        canvas = tk.Canvas(parent, background=theme.BG, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="TFrame")

        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)

        inner.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        # Der Inhalt soll die volle Breite nutzen und nicht auf seiner Wunschbreite
        # kleben, sonst stehen die Karten schmal am linken Rand.
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=event.width),
        )

        def rollen(event):
            if getattr(event, "num", 0) == 4:
                schritte = -1
            elif getattr(event, "num", 0) == 5:
                schritte = 1
            else:
                schritte = -1 if getattr(event, "delta", 0) > 0 else 1
            canvas.yview_scroll(schritte, "units")

        # Das Mausrad wird nur gebunden, solange der Zeiger über diesem Bereich
        # steht. Sonst würde es auch in den anderen Reitern mitrollen.
        def binden(_event):
            for folge in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                canvas.bind_all(folge, rollen)

        def loesen(_event):
            for folge in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                canvas.unbind_all(folge)

        canvas.bind("<Enter>", binden)
        canvas.bind("<Leave>", loesen)

        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        return inner

    def _language_switch(self, parent):
        """Baut die Zeile mit dem Sprachumschalter oben in einem Reiter."""
        row = ttk.Frame(parent, style="TFrame")
        row.pack(fill="x", pady=(0, 12))
        self._tr(ttk.Label(row, style="Card.TLabel"), "lang.label").pack(side="left")

        buttons = ttk.Frame(row, style="TFrame")
        buttons.pack(side="right")
        for value, caption in (("de", "Deutsch"), ("en", "English")):
            ttk.Radiobutton(
                buttons, text=caption, variable=self.lang_var, value=value,
                command=self._on_language_change,
            ).pack(side="left", padx=(10, 0) if value == "en" else (0, 0))
        return row

    def _build(self):
        outer = ttk.Frame(self.root, style="TFrame")
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="TFrame", padding=(24, 20, 24, 8))
        header.pack(fill="x")

        topline = ttk.Frame(header, style="TFrame")
        topline.pack(fill="x")

        titlerow = ttk.Frame(topline, style="TFrame")
        titlerow.pack(side="left")

        # Das kompakte Firmenzeichen steht vor dem Titel und ist damit auf jedem
        # Reiter zu sehen, ohne Platz zu kosten. Fehlt die Datei, tritt der
        # grüne Punkt an seine Stelle — die Kopfzeile darf nicht davon abhängen.
        mark = branding.load_mark()
        if mark:
            # Die Referenz muss am Objekt hängen bleiben, sonst räumt Python das
            # Bild weg und tkinter zeigt eine leere Fläche.
            self._mark_image = mark
            ttk.Label(titlerow, image=mark, style="TLabel").pack(side="left", pady=(4, 0))
        else:
            ttk.Label(titlerow, text="●", style="H1.TLabel", foreground=theme.ACCENT).pack(side="left")

        ttk.Label(titlerow, text=APP_TITLE, style="H1.TLabel").pack(side="left", padx=(10, 0))
        ttk.Label(
            titlerow, text=f"v{__version__}", style="Muted.TLabel"
        ).pack(side="left", padx=(10, 0), pady=(6, 0))

        # Der Lizenzzustand steht dauerhaft in der Kopfzeile und nicht erst in
        # einer Meldung beim Start eines Laufs. Wer keine gültige Lizenz hat,
        # soll das sehen, bevor er seine CSV-Datei heraussucht — nicht danach.
        self.license_chip = ttk.Label(topline, text="", style="Muted.TLabel", cursor="hand2")
        self.license_chip.pack(side="right", pady=(8, 0))
        self.license_chip.bind("<Button-1>", lambda _event: self._open_license_dialog())

        ttk.Label(
            header, text=f"{SUBTITLE}  ·  Entwickler: {DEVELOPER}", style="Muted.TLabel"
        ).pack(anchor="w", pady=(2, 0))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        self._build_run_tab()
        self._build_result_tab()
        self._build_settings_tab()
        self._build_help_tab()
        self._build_about_tab()

        # Erst hier, wenn alle Anzeigestellen stehen: Kopfzeile, Banner im
        # Reiter Playlist erstellen, Karte im Reiter Über.
        self._refresh_license_display()

    def _build_menu(self):
        """Menüleiste mit dem Eintrag Lizenz …, dem vierten Weg zum Lizenzdialog.

        Bewusst ein Eintrag oberster Ebene und kein Untermenü unter "Hilfe":
        die Anwendung hat bereits einen Reiter mit diesem Namen, und zwei
        verschiedene Dinge namens "Hilfe" schicken den Nutzer an die falsche
        Stelle — genau dorthin, wo nichts über Lizenzen steht.
        """
        self.menubar = tk.Menu(self.root, tearoff=0)
        self.menubar.add_command(
            label=i18n.t(self.lang_var.get(), "menu.lizenz"),
            command=self._open_license_dialog,
        )
        self.root.config(menu=self.menubar)

    def _build_run_tab(self):
        tab = ttk.Frame(self.notebook, style="TFrame", padding=16)
        self.notebook.add(tab, text="  Playlist erstellen  ")

        # Hinweisbalken bei fehlender oder abgelaufener Lizenz. Er wird gleich
        # hier gepackt, damit er über den Karten sitzt; _refresh_license_display
        # blendet ihn aus, sobald eine gültige Lizenz vorliegt.
        self.license_banner = ttk.Frame(tab, style="Card.TFrame", padding=18)
        self.license_banner.pack(fill="x", pady=(0, 14))
        banner_row = ttk.Frame(self.license_banner, style="Card.TFrame")
        banner_row.pack(fill="x")
        self.license_banner_label = ttk.Label(banner_row, text="", style="Danger.TLabel")
        self.license_banner_label.pack(side="left")
        self._tr(
            ttk.Button(banner_row, command=self._open_license_dialog), "lizenz.banner.knopf"
        ).pack(side="right")

        card, body = self._card(tab, "1 · CSV-Datei")
        # Merker für das Wiedereinblenden des Balkens an der richtigen Stelle:
        # ein erneutes pack() ohne before würde ihn ans Ende hängen.
        self._run_first_card = card
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
        ttk.Spinbox(
            self.advanced_body, from_=1, to=MAX_SEARCH_LIMIT,
            textvariable=self.limit_var, width=6,
        ).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=6)

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
        self.check_button = ttk.Button(
            button_row, text="Client ID prüfen", command=self._on_check_credentials
        )
        self.check_button.pack(side="left", padx=(10, 0))
        ttk.Button(
            button_row, text="Anmeldung zurücksetzen", command=self._on_reset_login
        ).pack(side="left", padx=(10, 0))
        ttk.Button(
            button_row, text="Spotify Dashboard öffnen", command=self._on_open_dashboard
        ).pack(side="left", padx=(10, 0))

        self.settings_status_label = ttk.Label(body, text="", style="CardMuted.TLabel")
        self.settings_status_label.pack(anchor="w", pady=(12, 0))

        _, body = self._card(tab, "Über")
        ttk.Label(
            body, text=f"Version {__version__}", style="Card.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            body, text=f"Entwickler: {DEVELOPER}", style="CardMuted.TLabel"
        ).pack(anchor="w", pady=(4, 0))

    def _build_help_tab(self):
        """Hilfe-Reiter mit zweisprachigen Hilfetexten."""
        # Der Reiter wird über sein eigenes Widget angesprochen, nicht über einen
        # Index: notebook.add liefert keinen zurück, und Indizes verschieben sich,
        # sobald jemand einen weiteren Reiter davor einfügt.
        tab = ttk.Frame(self.notebook, style="TFrame", padding=16)
        self.help_tab = tab
        self.notebook.add(tab, text=i18n.t(self.lang_var.get(), "tab.help"))

        self._language_switch(tab)

        # Text-Widget mit Bildlaufleiste
        text_frame = ttk.Frame(tab, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True)

        self.help_text = tk.Text(
            text_frame, height=10, relief="flat", borderwidth=0,
            background=theme.SURFACE, foreground=theme.TEXT_MUTED,
            insertbackground=theme.TEXT, font=theme.fonts()["base"],
            state="disabled", wrap="word", highlightthickness=0
        )
        self.help_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.help_text.yview)
        scroll.pack(side="right", fill="y")
        self.help_text.configure(yscrollcommand=scroll.set)

        # Textmarken für verschiedene Abschnitte
        self.help_text.tag_configure("h1", font=(theme.fonts()["base"][0], theme.fonts()["base"][1] + 8, "bold"),
                                     foreground=theme.TEXT, spacing1=18)
        self.help_text.tag_configure("h2", font=(theme.fonts()["base"][0], theme.fonts()["base"][1] + 2, "bold"),
                                     foreground=theme.ACCENT, spacing1=12)
        self.help_text.tag_configure("p", foreground=theme.TEXT_MUTED, spacing3=6)
        self.help_text.tag_configure("li", foreground=theme.TEXT_MUTED, lmargin1=24, lmargin2=24)

        # Hilfetexte rendern
        self._render_help()

    def _build_about_tab(self):
        """Über-Reiter mit Branding, Lizenz und Links."""
        tab = ttk.Frame(self.notebook, style="TFrame", padding=16)
        self.about_tab = tab
        self.notebook.add(tab, text=i18n.t(self.lang_var.get(), "tab.about"))

        self._language_switch(tab)
        tab = self._scrollable(tab)

        # Karte Krüger Digital Solutions mit Logo
        _, body = self._card_tr(tab, "about.company")
        logo = branding.load_logo()
        if logo:
            # Die Referenz muss am Objekt hängen bleiben, sonst räumt Python das Bild
            # weg und tkinter zeigt eine leere Fläche.
            self._logo_image = logo
            ttk.Label(body, image=logo).pack(anchor="w", pady=(0, 12))
        else:
            ttk.Label(body, text="KDS", style="H1.TLabel").pack(anchor="w")
            ttk.Label(body, text="KRÜGER DIGITAL SOLUTIONS", style="CardMuted.TLabel").pack(anchor="w", pady=(2, 0))

        # Karte Programm
        _, body = self._card_tr(tab, "about.program")
        self._tr(ttk.Label(body, style="Card.TLabel"), "about.version").pack(anchor="w")
        ttk.Label(body, text=__version__, style="CardMuted.TLabel").pack(anchor="w", pady=(0, 12))

        self._tr(ttk.Label(body, style="Card.TLabel"), "about.developer").pack(anchor="w")
        ttk.Label(body, text=DEVELOPER, style="CardMuted.TLabel").pack(anchor="w", pady=(0, 12))

        self._tr(ttk.Label(body, style="Card.TLabel"), "about.company_label").pack(anchor="w")
        ttk.Label(body, text=COMPANY, style="CardMuted.TLabel").pack(anchor="w")

        # Karte Lizenz. Nur Anzeige — die Eingabe passiert im Lizenzdialog
        # (Menü Hilfe -> Lizenz …), damit es genau eine Stelle zum Aktivieren gibt.
        _, body = self._card_tr(tab, "about.license")
        self.license_status_label = ttk.Label(body, text="", style="CardMuted.TLabel")
        self.license_status_label.pack(anchor="w", pady=(0, 12))

        self.license_info_label = ttk.Label(body, text="", style="CardMuted.TLabel")
        self.license_info_label.pack(anchor="w", pady=(0, 12))

        self._tr(
            ttk.Button(body, command=self._open_license_dialog), "lizenz.verwalten"
        ).pack(anchor="w")

        # Karte Links
        _, body = self._card_tr(tab, "about.links")
        self._tr(
            ttk.Button(body, command=lambda: webbrowser.open(REPO_URL)), "about.repo"
        ).pack(anchor="w", pady=(0, 8))
        self._tr(
            ttk.Button(body, command=lambda: webbrowser.open(DASHBOARD_URL)), "about.dashboard"
        ).pack(anchor="w")


    def _render_help(self):
        """Füllt das Hilfe-Text-Widget mit den lokalisierten Inhalten."""
        lang = self.lang_var.get()
        sections = i18n.HELP_SECTIONS.get(lang, [])

        self.help_text.configure(state="normal")
        self.help_text.delete("1.0", "end")

        for art, text in sections:
            if art == "li":
                # Aufzählungszeichen voranstellen
                self.help_text.insert("end", "•  " + text + "\n", art)
            else:
                self.help_text.insert("end", text + "\n", art)

        self.help_text.configure(state="disabled")

    def _on_language_change(self):
        """Reagiert auf Sprachenwechsel: GUI aktualisieren."""
        lang = self.lang_var.get()

        # Hilfe neu rendern
        self._render_help()

        # Alle vorgemerkten Beschriftungen nachziehen
        for widget, key in self._tr_widgets:
            widget.configure(text=i18n.t(lang, key))

        # Über-Reiter aktualisieren
        self._refresh_license_display()

        # Reiterbeschriftungen aktualisieren
        self.notebook.tab(self.help_tab, text=i18n.t(lang, "tab.help"))
        self.notebook.tab(self.about_tab, text=i18n.t(lang, "tab.about"))

        # Menübeschriftung aktualisieren
        self.menubar.entryconfigure(0, label=i18n.t(lang, "menu.lizenz"))

        # Sprache speichern
        settings = load_settings(self.settings_path)
        settings["language"] = lang
        save_settings(settings, self.settings_path)

    def _lizenz_auskunft(self):
        """Alles, was die Oberfläche über die Lizenz anzeigen muss, an einer Stelle.

        Drei Stellen zeigen denselben Zustand — die Kopfzeile, der Balken im
        Reiter Playlist erstellen und die Karte im Reiter Über. Würde jede für
        sich entscheiden, liefen sie früher oder später auseinander.

        Eine App ohne App-Schlüssel bekommt eine eigene Meldung statt der für
        FEHLT: das ist ein Versäumnis beim Bauen, nicht das des Nutzers.
        """
        lang = self.lang_var.get()

        if not lizenz.eingerichtet():
            return LizenzAnzeige(
                chip=i18n.t(lang, "lizenz.chip.ohne_schluessel"),
                karte=i18n.t(lang, "lizenz.nicht_eingerichtet"),
                banner=i18n.t(lang, "lizenz.banner.ohne_schluessel"),
                farbe="danger",
                zusatz="",
                gesperrt=True,
            )

        zustand, lic = lizenz.status()

        if zustand == lizenz.GUELTIG:
            datum = lic.ablauf.strftime("%d.%m.%Y")
            tage = lic.tage_rest()
            # Kurz vor Ablauf wird aus der beiläufigen Anzeige eine Warnung.
            # Wer erst am Ablauftag davon erfährt, steht ohne Vorlauf da.
            if tage <= LIZENZ_WARNUNG_TAGE:
                chip = i18n.t(lang, "lizenz.chip.laeuft_ab").format(tage=tage)
                farbe = "warn"
            else:
                chip = i18n.t(lang, "lizenz.chip.gueltig").format(datum=datum)
                farbe = "ok"
            karte = i18n.t(lang, "lizenz.status.gueltig")
            banner = ""
            gesperrt = False
        elif zustand == lizenz.ABGELAUFEN:
            datum = lic.ablauf.strftime("%d.%m.%Y")
            chip = i18n.t(lang, "lizenz.chip.abgelaufen")
            karte = i18n.t(lang, "lizenz.status.abgelaufen").format(datum=datum)
            banner = i18n.t(lang, "lizenz.banner.abgelaufen").format(datum=datum)
            farbe = "warn"
            gesperrt = True
        else:  # FEHLT
            chip = i18n.t(lang, "lizenz.chip.fehlt")
            karte = i18n.t(lang, "lizenz.status.fehlt")
            banner = i18n.t(lang, "lizenz.banner.fehlt")
            # Bewusst nicht gedämpft: eine fehlende Lizenz sperrt den Lauf, und
            # ein grauer Hinweis in der Kopfzeile geht neben dem Titel unter.
            farbe = "warn"
            gesperrt = True

        zusatz = ""
        if lic is not None:
            zusatz = i18n.t(lang, "about.licensed_to") + ": " + lic.kunde + "\n"
            zusatz += i18n.t(lang, "about.valid_until") + ": " + lic.ablauf.strftime("%d.%m.%Y")

        return LizenzAnzeige(
            chip=chip, karte=karte, banner=banner, farbe=farbe,
            zusatz=zusatz, gesperrt=gesperrt,
        )

    def _refresh_license_display(self):
        """Zieht Kopfzeile, Hinweisbalken, Über-Karte und Startknopf nach."""
        anzeige = self._lizenz_auskunft()
        chip_stil, karten_stil = ZUSTANDSFARBEN[anzeige.farbe]

        self.license_chip.configure(text=anzeige.chip, style=chip_stil)
        self.license_status_label.configure(text=anzeige.karte, style=karten_stil)
        self.license_info_label.configure(text=anzeige.zusatz)

        if anzeige.gesperrt:
            self.license_banner_label.configure(text=anzeige.banner, style=karten_stil)
            # winfo_manager statt winfo_ismapped: in einem noch nicht
            # dargestellten Fenster ist nichts "mapped", der Balken würde dann
            # bei jedem Durchlauf neu gepackt.
            if not self.license_banner.winfo_manager():
                self.license_banner.pack(fill="x", pady=(0, 14), before=self._run_first_card)
        else:
            self.license_banner.pack_forget()

        # Der Startknopf bleibt gesperrt, statt den Nutzer erst nach dem Klick
        # abzuweisen. Während eines Laufs ist er ohnehin aus anderen Gründen
        # gesperrt — dann bleibt diese Entscheidung beim Lauf.
        if not self.worker.is_running():
            self.run_button.configure(state="disabled" if anzeige.gesperrt else "normal")

    def _dialog_status_zeigen(self, status_label, info_label):
        """Schreibt den aktuellen Lizenzzustand in die beiden Zeilen des Dialogs."""
        anzeige = self._lizenz_auskunft()
        _, karten_stil = ZUSTANDSFARBEN[anzeige.farbe]
        status_label.configure(text=anzeige.karte, style=karten_stil)
        info_label.configure(text=anzeige.zusatz)

    def _open_license_dialog(self):
        """Öffnet den Lizenzdialog; ein bereits offener wird nur angehoben."""
        if self.license_dialog is not None and self.license_dialog.winfo_exists():
            self.license_dialog.lift()
            self.license_dialog.focus_force()
            return

        lang = self.lang_var.get()
        dialog = tk.Toplevel(self.root)
        dialog.title(i18n.t(lang, "lizenz.dialog_titel"))
        dialog.configure(background=theme.BG)
        dialog.geometry("480x280")
        dialog.transient(self.root)
        self.license_dialog = dialog

        frame = ttk.Frame(dialog, style="TFrame", padding=18)
        frame.pack(fill="both", expand=True)

        status_label = ttk.Label(frame, text="", style="CardMuted.TLabel")
        status_label.pack(anchor="w", pady=(0, 12))
        info_label = ttk.Label(frame, text="", style="CardMuted.TLabel")
        info_label.pack(anchor="w", pady=(0, 12))

        ttk.Label(frame, text=i18n.t(lang, "lizenz.eingabefeld"), style="Card.TLabel").pack(anchor="w")
        entry = tk.Text(frame, height=4, relief="flat", borderwidth=1,
                         background=theme.SURFACE, foreground=theme.TEXT,
                         insertbackground=theme.TEXT, font=theme.fonts()["mono"],
                         wrap="char", highlightthickness=0)
        entry.pack(fill="x", pady=(6, 12))

        def aktivieren():
            self._on_activate_license(entry.get("1.0", "end"), status_label, info_label)

        ttk.Button(
            frame, text=i18n.t(lang, "lizenz.aktivieren"), style="Accent.TButton", command=aktivieren
        ).pack(anchor="w")

        self._dialog_status_zeigen(status_label, info_label)

    def _on_activate_license(self, eingabe, status_label, info_label):
        """Prüft und speichert einen im Lizenzdialog eingegebenen Schlüssel.

        Ein abgelaufener Schlüssel wird nicht gespeichert - sonst überschreibt
        ein Kunde beim Ausprobieren seinen noch gültigen Schlüssel.
        schluessel_pruefen meldet jeden Fehler als None statt als Ausnahme;
        darauf verlässt sich diese Methode und fängt nichts zusätzlich ab.
        """
        lang = self.lang_var.get()
        lic = lizenz.schluessel_pruefen(eingabe)

        if lic is None:
            messagebox.showwarning(
                i18n.t(lang, "lizenz.dialog_titel"), i18n.t(lang, "lizenz.abgelehnt_ungueltig")
            )
            return

        if lic.abgelaufen():
            messagebox.showwarning(
                i18n.t(lang, "lizenz.dialog_titel"), i18n.t(lang, "lizenz.abgelehnt_abgelaufen")
            )
            return

        lizenz.lizenz_speichern(eingabe)
        self._dialog_status_zeigen(status_label, info_label)
        self._refresh_license_display()
        messagebox.showinfo(i18n.t(lang, "lizenz.dialog_titel"), i18n.t(lang, "lizenz.aktiviert"))

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

    def _on_check_credentials(self, checker=check_credentials):
        """Prüft die Zugangsdaten im Hintergrund, damit das Fenster bedienbar bleibt."""
        self.check_button.configure(state="disabled")
        self.settings_status_label.configure(text="Prüfe Client ID …", style="CardMuted.TLabel")

        config = Config(
            client_id=self.client_id_var.get().strip(),
            redirect_uri=self.redirect_var.get().strip() or DEFAULT_REDIRECT_URI,
            token_path=Path(self.token_path_var.get().strip() or str(DEFAULT_TOKEN_PATH)),
            client_secret=self.client_secret_var.get().strip(),
        )

        def work():
            try:
                outcome = checker(config)
            except Exception as exc:
                outcome = CredentialCheck(CHECK_UNKNOWN, f"Prüfung fehlgeschlagen: {exc}")
            self._check_queue.put(outcome)

        threading.Thread(target=work, daemon=True).start()
        self._poll_credential_check()

    def _poll_credential_check(self):
        """Holt das Prüfergebnis im Hauptthread ab — tkinter ist nicht thread-sicher."""
        try:
            outcome = self._check_queue.get_nowait()
        except queue.Empty:
            self.root.after(50, self._poll_credential_check)
            return

        self.check_button.configure(state="normal")
        styles = {CHECK_OK: "Ok.TLabel", CHECK_INVALID: "Danger.TLabel", CHECK_UNKNOWN: "Warn.TLabel"}
        self.settings_status_label.configure(
            text=outcome.message, style=styles.get(outcome.status, "Warn.TLabel")
        )

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

    def _lizenz_pruefen_fuer_lauf(self):
        """Prüft vor einem Suchlauf, ob eine gültige Lizenz vorliegt.

        Gesperrt wird der gesamte Suchlauf, auch der Trockenlauf - er ist die
        eine Kernfunktion, für die bezahlt wird. Eine App ohne App-Schlüssel
        bekommt eine eigene Meldung statt der für eine fehlende Lizenz: das
        ist ein Versäumnis beim Bauen, nicht das des Nutzers.
        """
        lang = self.lang_var.get()
        if not lizenz.eingerichtet():
            messagebox.showerror(
                i18n.t(lang, "lizenz.gesperrt_titel"), i18n.t(lang, "lizenz.nicht_eingerichtet")
            )
            return False

        zustand, lic = lizenz.status()
        if zustand != lizenz.GUELTIG:
            if zustand == lizenz.ABGELAUFEN:
                text = i18n.t(lang, "lizenz.status.abgelaufen").format(
                    datum=lic.ablauf.strftime("%d.%m.%Y")
                )
            else:
                text = i18n.t(lang, "lizenz.status.fehlt")
            messagebox.showwarning(
                i18n.t(lang, "lizenz.gesperrt_titel"),
                text + "\n\n" + i18n.t(lang, "lizenz.gesperrt_hinweis"),
            )
            return False

        return True

    def _on_run(self):
        """Startet den Suchlauf im Hintergrund."""
        if self.worker.is_running():
            return

        if not self._lizenz_pruefen_fuer_lauf():
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
        """
        Holt Meldungen des Hintergrund-Threads und plant den nächsten Abruf.

        Abgebrochen wird erst, wenn eine Abschlussmeldung angekommen ist – nicht
        schon, wenn der Thread nicht mehr läuft. Sonst könnte eine Meldung, die
        zwischen dem Leeren der Warteschlange und dem Thread-Ende eintrifft,
        verloren gehen und die Oberfläche bliebe bedienungslos stehen.
        """
        finished = False
        for kind, payload in self.worker.poll():
            if kind == "progress":
                self._handle_progress(payload)
            elif kind == "result":
                self._handle_result(payload)
                finished = True
            elif kind == "error":
                self._handle_error(payload)
                finished = True
        if finished:
            self._poll_job = None
        else:
            self._poll_job = self.root.after(80, self._poll_worker)

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
        self._release_run_button()
        self.cancel_button.configure(state="disabled")
        if result.rows:
            self.save_report_button.configure(state="normal")
        if result.playlist_url:
            self.open_playlist_button.configure(state="normal")
            self._log(f"Playlist erstellt: {result.playlist_url}")
        if result.cancelled:
            if result.playlist_url:
                self._set_status(
                    "Abgebrochen – die Playlist wurde bereits angelegt und ist "
                    "möglicherweise unvollständig."
                )
            else:
                self._set_status("Abgebrochen.")
        else:
            self._set_status(vm.summary_line(result.rows))
        if result.rows:
            self.notebook.select(self.notebook.tabs()[1])

    def _release_run_button(self):
        """Gibt den Startknopf nach einem Lauf frei — sofern die Lizenz das zulässt.

        Ein schlichtes state="normal" würde eine abgelaufene Lizenz übergehen,
        die während des Laufs abgelaufen ist oder von Anfang an fehlte, weil der
        Lauf über einen anderen Weg angestoßen wurde.
        """
        self.run_button.configure(
            state="disabled" if self._lizenz_auskunft().gesperrt else "normal"
        )

    def _handle_error(self, message):
        self._release_run_button()
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
