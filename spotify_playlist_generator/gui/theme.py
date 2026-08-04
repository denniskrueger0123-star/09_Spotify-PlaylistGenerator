"""Farben, Schriften und ttk-Stile der Oberfläche."""

import sys
from tkinter import ttk

BG = "#121212"           # Fensterhintergrund
SURFACE = "#181818"      # Karten
SURFACE_HI = "#242424"   # Eingabefelder, Hover
BORDER = "#2F2F2F"
TEXT = "#FFFFFF"
TEXT_MUTED = "#B3B3B3"
ACCENT = "#1DB954"       # Spotify-Grün
ACCENT_HOVER = "#1ED760"
ACCENT_TEXT = "#000000"
OK = "#1DB954"
WARN = "#E8A33D"
DANGER = "#F15E6C"


def font_family() -> str:
    """Gibt die passende Standard-Schriftfamilie für die aktuelle Plattform zurück."""
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "Helvetica Neue"
    return "DejaVu Sans"


def fonts() -> dict[str, tuple]:
    """Gibt die in der Oberfläche verwendeten Schrift-Definitionen zurück."""
    family = font_family()
    mono_family = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"
    return {
        "base": (family, 10),
        "small": (family, 9),
        "h1": (family, 19, "bold"),
        "h2": (family, 11, "bold"),
        "mono": (mono_family, 9),
    }


def apply_theme(root) -> "ttk.Style":
    """Wendet das dunkle Farbschema und die ttk-Stile auf das Fenster an."""
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(background=BG)

    # Die Aufklapp-Liste der Combobox ist eine klassische Tk-Liste und
    # ignoriert ttk-Stile, daher wird sie separat eingefärbt.
    root.option_add("*TCombobox*Listbox.background", SURFACE_HI)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_TEXT)

    f = fonts()

    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=SURFACE)

    style.configure("TLabel", background=BG, foreground=TEXT, font=f["base"])
    style.configure("Card.TLabel", background=SURFACE, foreground=TEXT, font=f["base"])
    style.configure("H1.TLabel", background=BG, foreground=TEXT, font=f["h1"])
    style.configure("H2.TLabel", background=SURFACE, foreground=TEXT, font=f["h2"])
    style.configure("Muted.TLabel", background=BG, foreground=TEXT_MUTED, font=f["small"])
    style.configure("CardMuted.TLabel", background=SURFACE, foreground=TEXT_MUTED, font=f["small"])
    style.configure("Ok.TLabel", background=SURFACE, foreground=OK, font=f["small"])
    style.configure("Warn.TLabel", background=SURFACE, foreground=WARN, font=f["small"])
    style.configure("Danger.TLabel", background=SURFACE, foreground=DANGER, font=f["small"])
    style.configure("Value.TLabel", background=SURFACE, foreground=ACCENT, font=f["h1"])

    style.configure(
        "TButton",
        background=SURFACE_HI,
        foreground=TEXT,
        font=f["base"],
        borderwidth=0,
        focusthickness=0,
        padding=(14, 8),
        relief="flat",
    )
    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground=ACCENT_TEXT,
        font=f["h2"],
        borderwidth=0,
        focusthickness=0,
        padding=(22, 12),
        relief="flat",
    )

    style.configure(
        "TEntry",
        fieldbackground=SURFACE_HI,
        foreground=TEXT,
        insertcolor=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        borderwidth=1,
        padding=6,
    )

    style.configure(
        "TCheckbutton",
        background=SURFACE,
        foreground=TEXT,
        font=f["base"],
        focusthickness=0,
        indicatorcolor=SURFACE_HI,
    )

    style.configure(
        "TCombobox",
        fieldbackground=SURFACE_HI,
        background=SURFACE_HI,
        foreground=TEXT,
        arrowcolor=TEXT_MUTED,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=5,
    )

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 8, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background=BG,
        foreground=TEXT_MUTED,
        font=f["base"],
        padding=(18, 10),
        borderwidth=0,
    )

    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=SURFACE_HI,
        background=ACCENT,
        borderwidth=0,
        thickness=8,
        darkcolor=ACCENT,
        lightcolor=ACCENT,
    )

    style.configure(
        "Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=TEXT,
        font=f["base"],
        rowheight=26,
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        background=SURFACE_HI,
        foreground=TEXT_MUTED,
        font=f["small"],
        relief="flat",
        padding=(8, 6),
    )

    style.configure(
        "Horizontal.TScale",
        background=SURFACE,
        troughcolor=SURFACE_HI,
        borderwidth=0,
    )

    style.configure(
        "Vertical.TScrollbar",
        background=SURFACE_HI,
        troughcolor=BG,
        bordercolor=BG,
        arrowcolor=TEXT_MUTED,
        borderwidth=0,
    )

    style.map(
        "TButton",
        background=[("active", BORDER), ("disabled", SURFACE)],
        foreground=[("disabled", TEXT_MUTED)],
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_HOVER), ("disabled", BORDER)],
        foreground=[("disabled", TEXT_MUTED)],
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", SURFACE)],
        foreground=[("selected", TEXT)],
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", ACCENT_TEXT)],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", SURFACE_HI)],
        foreground=[("readonly", TEXT)],
    )
    style.map(
        "TCheckbutton",
        indicatorcolor=[("selected", ACCENT)],
        background=[("active", SURFACE)],
    )

    return style


def tag_colors() -> dict[str, str]:
    """Gibt die Farben für die Status-Zeilen der Ergebnistabelle zurück."""
    return {"found": OK, "not_found": WARN, "error": DANGER}
