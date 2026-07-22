"""The app's window chrome theme.

The sim never chooses a look — with no style/palette set, Qt drifts with the OS
appearance (macOS "Auto" flips to dark at sunset) and falls back to the platform
default light palette, which reads dated. This module pins one deliberate look.

The rest of the UI is already palette-driven: ``annals_style.py`` and the dossier
HTML paint from ``option.palette`` / ``palette(...)`` rather than hardcoding
colours, so setting one application palette here flows through every surface. We
use the *Fusion* style because — unlike the native macOS/Windows styles — it
honours a custom :class:`QPalette` on every platform.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# A dim slate palette. Kept as data so the two disabled-state tweaks below can
# reference the same tones. Named entries map straight onto QPalette roles.
_WINDOW = QColor(37, 38, 42)          # panel/toolbar ground
_BASE = QColor(28, 29, 33)            # text/list backgrounds (the annals, dossiers)
_ALT_BASE = QColor(45, 47, 52)        # zebra-striping in the annals list
_TEXT = QColor(223, 225, 230)         # primary foreground
_DIM_TEXT = QColor(150, 153, 160)     # disabled foreground
_BUTTON = QColor(52, 54, 60)
_ON_ACCENT = QColor(15, 16, 20)

# Antique bronze — the one accent. Drives selection highlight, HTML links (entity
# click-through), the illuminated year-dividers and dock titles. A warm gold that
# stays legible on the dark base, evoking gilt on a chronicle's vellum.
BRONZE = QColor(201, 162, 94)  # #c9a25e
_ACCENT = BRONZE

# The chronicle's serif voice for headers (year-dividers, dossier names, dock
# titles). A fallback chain of book faces shipped with macOS, ending in the
# generic ``serif`` so it degrades gracefully off-platform. Kept as a CSS string
# too, for the HTML dossiers rendered in the Codex's QTextBrowser.
SERIF_FAMILIES = ["Palatino", "Palatino Linotype", "Georgia", "Times New Roman"]
SERIF_CSS = "'Palatino','Palatino Linotype','Georgia',serif"


def serif_font(point_size: int | None = None, *, bold: bool = False) -> QFont:
    """A header font in the chronicle's serif voice (see :data:`SERIF_FAMILIES`)."""
    font = QFont()
    font.setFamilies(SERIF_FAMILIES)
    font.setStyleHint(QFont.Serif)
    if point_size is not None:
        font.setPointSize(point_size)
    font.setBold(bold)
    return font


def dark_palette() -> QPalette:
    """The Fusion dark palette used for the whole app."""
    p = QPalette()
    p.setColor(QPalette.Window, _WINDOW)
    p.setColor(QPalette.WindowText, _TEXT)
    p.setColor(QPalette.Base, _BASE)
    p.setColor(QPalette.AlternateBase, _ALT_BASE)
    p.setColor(QPalette.ToolTipBase, _BASE)
    p.setColor(QPalette.ToolTipText, _TEXT)
    p.setColor(QPalette.Text, _TEXT)
    p.setColor(QPalette.Button, _BUTTON)
    p.setColor(QPalette.ButtonText, _TEXT)
    p.setColor(QPalette.BrightText, QColor(232, 122, 106))
    p.setColor(QPalette.Link, _ACCENT)
    p.setColor(QPalette.LinkVisited, _ACCENT.darker(120))
    p.setColor(QPalette.Highlight, _ACCENT)
    p.setColor(QPalette.HighlightedText, _ON_ACCENT)
    p.setColor(QPalette.PlaceholderText, _DIM_TEXT)
    # Greyed-out (disabled) controls read the dim tone, not full-contrast text.
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        p.setColor(QPalette.Disabled, role, _DIM_TEXT)
    return p


def apply_dark_theme(app: QApplication) -> None:
    """Pin the app to a dark Fusion look, independent of the OS appearance.

    The dock titlebars are gilt separately, via custom title widgets on each dock
    (:meth:`MainWindow._gilt_titlebar`) — Fusion won't colour the native title
    text through a stylesheet, so the window owns those bars directly.
    """
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
