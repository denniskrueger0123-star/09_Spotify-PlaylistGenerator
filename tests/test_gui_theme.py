"""Tests for the gui.theme module."""

import pytest

tk = pytest.importorskip("tkinter")
from tkinter import ttk

from spotify_playlist_generator.gui import theme


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


ALL_STYLE_NAMES = (
    "TFrame",
    "Card.TFrame",
    "TLabel",
    "Card.TLabel",
    "H1.TLabel",
    "H2.TLabel",
    "Muted.TLabel",
    "CardMuted.TLabel",
    "Ok.TLabel",
    "Warn.TLabel",
    "Danger.TLabel",
    "Value.TLabel",
    "TButton",
    "Accent.TButton",
    "TEntry",
    "TCheckbutton",
    "TCombobox",
    "TNotebook",
    "TNotebook.Tab",
    "Horizontal.TProgressbar",
    "Treeview",
    "Treeview.Heading",
    "Horizontal.TScale",
    "Vertical.TScrollbar",
)


def test_apply_theme_uses_clam(root):
    """apply_theme selects the clam theme as its base."""
    style = theme.apply_theme(root)
    assert style.theme_use() == "clam"


def test_root_background_is_dark(root):
    """apply_theme sets the window background to the dark theme colour."""
    theme.apply_theme(root)
    assert root.cget("background") == theme.BG


def test_all_expected_styles_have_background(root):
    """Every style used by the GUI has a non-empty background configured."""
    style = theme.apply_theme(root)
    for name in ALL_STYLE_NAMES:
        background = style.lookup(name, "background")
        assert background, f"{name} has no background configured"


def test_accent_button_uses_accent_colour(root):
    """The primary action button uses the Spotify-green accent colour."""
    style = theme.apply_theme(root)
    assert style.lookup("Accent.TButton", "background") == theme.ACCENT


def test_accent_button_hover_colour(root):
    """The accent button switches to the hover colour when active."""
    style = theme.apply_theme(root)
    mapped = dict(style.map("Accent.TButton")["background"])
    assert mapped.get("active") == theme.ACCENT_HOVER


def test_treeview_selection_uses_accent(root):
    """Selected rows in the results table use the accent colour."""
    style = theme.apply_theme(root)
    mapped = dict(style.map("Treeview")["background"])
    assert mapped.get("selected") == theme.ACCENT


def test_entry_field_background(root):
    """Text entry fields use the elevated surface colour."""
    style = theme.apply_theme(root)
    assert style.lookup("TEntry", "fieldbackground") == theme.SURFACE_HI


def test_tag_colors_keys():
    """tag_colors exposes exactly the three known result statuses."""
    colors = theme.tag_colors()
    assert set(colors.keys()) == {"found", "not_found", "error"}


def test_font_family_returns_string():
    """font_family always returns a non-empty font name."""
    family = theme.font_family()
    assert isinstance(family, str)
    assert family


def test_fonts_has_expected_keys():
    """fonts provides definitions for all font roles used by the GUI."""
    f = theme.fonts()
    assert set(f.keys()) == {"base", "small", "h1", "h2", "mono"}


def test_h1_font_is_bold():
    """The h1 heading font is bold."""
    f = theme.fonts()
    assert f["h1"][-1] == "bold"
