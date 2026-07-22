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

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# A dim slate palette. Kept as data so the two disabled-state tweaks below can
# reference the same tones. Named entries map straight onto QPalette roles.
_WINDOW = QColor(37, 38, 42)          # panel/toolbar ground
_BASE = QColor(28, 29, 33)            # text/list backgrounds (the annals, dossiers)
_ALT_BASE = QColor(45, 47, 52)        # zebra-striping in the annals list
_TEXT = QColor(223, 225, 230)         # primary foreground
_DIM_TEXT = QColor(150, 153, 160)     # disabled foreground
_BUTTON = QColor(52, 54, 60)
_ACCENT = QColor(94, 149, 224)        # highlight + HTML links (entity click-through)
_ON_ACCENT = QColor(15, 16, 20)


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
    """Pin the app to a dark Fusion look, independent of the OS appearance."""
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
