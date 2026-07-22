"""HTML primitives for the Inspection dock's dossiers.

The shared dossier anatomy (inspection-ui ticket 01): every selection kind —
faction, host, site, tile, event — renders through the same three primitives,
so the eye always knows where to land:

* :func:`banner` — a small dimmed kind-tag over the subject's name in large
  bold, with an identity-colored accent bar (the subject's map color, an
  event's bucket color, or neutral);
* :func:`stat_grid` — compact label/value rows, dimmed small labels,
  full-weight values;
* :func:`section` — a small-caps dimmed section header replacing the old
  ASCII ``──`` rules.

Pure string functions over Qt's rich-text HTML subset (tables and inline
styles; no divs-with-borders), so they test without a widget. Interpolated
names and prose are escaped — a site called ``R&D <keep>`` must render, not
break the markup.
"""

from __future__ import annotations

from html import escape as _escape
from typing import Iterable, Tuple

# Mid-gray that stays legible on light and dark palettes (labels, kind-tags).
DIM = "#8a8578"
# The accent for subjects with no identity color (unowned ground, unmapped).
NEUTRAL_ACCENT = "#9c9588"


def esc(text: object) -> str:
    """Escape arbitrary text for interpolation into dossier HTML."""
    return _escape(str(text), quote=False)


def banner(kind_tag: str, name: str, accent: str = NEUTRAL_ACCENT) -> str:
    """The dossier's headline: kind-tag over the name, with an accent bar.

    The accent is a narrow colored table cell — Qt's rich text has no
    border-left, so the bar is real layout, not CSS.
    """
    return (
        '<table cellspacing="0" cellpadding="0" width="100%"><tr>'
        f'<td width="5" bgcolor="{accent}">&nbsp;</td>'
        '<td style="padding-left: 8px">'
        f'<span style="color: {DIM}; font-size: small">{esc(kind_tag.upper())}</span><br>'
        f'<span style="font-size: x-large; font-weight: bold">{esc(name)}</span>'
        "</td></tr></table>"
    )


def stat_grid(pairs: Iterable[Tuple[str, object]]) -> str:
    """Compact label/value rows; a None value drops its row."""
    rows = [
        '<tr><td style="color: %s; font-size: small; padding-right: 12px">%s</td>'
        '<td style="font-weight: 600">%s</td></tr>' % (DIM, esc(label), esc(value))
        for label, value in pairs
        if value is not None
    ]
    if not rows:
        return ""
    return (
        '<table cellspacing="0" cellpadding="1" style="margin-top: 6px">'
        + "".join(rows)
        + "</table>"
    )


def section(title: str) -> str:
    """A small-caps dimmed section header with breathing room above."""
    return (
        f'<p style="color: {DIM}; font-size: small; margin-bottom: 0px; '
        f'margin-top: 12px"><b>{esc(title.upper())}</b></p>'
    )


def para(html_body: str) -> str:
    """A body paragraph; the caller escapes/composes the inner HTML."""
    return f'<p style="margin-top: 4px; margin-bottom: 4px">{html_body}</p>'


def dim_para(text: str) -> str:
    """A dimmed aside paragraph (escaped) — notices, locators, stub blurbs."""
    return para(f'<span style="color: {DIM}">{esc(text)}</span>')


def text_lines(text: str) -> str:
    """Escape a plain multi-line text block into a single paragraph."""
    return para("<br>".join(esc(line) for line in text.splitlines()))


def pre_block(text: str) -> str:
    """An indentation-preserving block (bloodlines) in the UI font."""
    return (
        '<pre style="font-family: inherit; margin-top: 4px; margin-bottom: 4px">'
        f"{esc(text)}</pre>"
    )
