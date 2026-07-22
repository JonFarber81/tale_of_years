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


def index_table(headers: Iterable[str], rows: Iterable[Iterable[str]]) -> str:
    """A multi-column index table for the Codex's index pages (#17/#19/#20).

    Header cells and body cells are **pre-composed HTML** — the caller escapes
    any text and builds the links (a sort link on a header, an entity link in a
    cell), exactly as :func:`para` expects of its body. Headers wear the dimmed
    small label style; body cells the ordinary weight.
    """
    head = "".join(
        '<td style="color: %s; font-size: small; text-align: left; '
        'padding: 2px 14px 4px 0">%s</td>' % (DIM, cell)
        for cell in headers
    )
    body = "".join(
        "<tr>"
        + "".join(
            '<td style="padding: 2px 14px 2px 0">%s</td>' % cell for cell in row
        )
        + "</tr>"
        for row in rows
    )
    return (
        '<table cellspacing="0" cellpadding="0" style="margin-top: 8px">'
        f"<tr>{head}</tr>{body}</table>"
    )


def tab_strip(tabs: Iterable[Tuple[str, str, bool]]) -> str:
    """A dossier's internal tab strip (ADR-0014): ``codex://`` links, active flat.

    Each tab is ``(label, codex:// url, active?)``. The active tab renders as
    bold plain text (you are here); the rest as links, so activating one is an
    ordinary navigation and every tab sits in history. Adding a tab is a new
    entry, never new chrome — #20's Diplomacy and #25's Regions reuse this.
    An empty ``tabs`` renders nothing.
    """
    cells = [
        f"<b>{esc(label)}</b>"
        if active
        else f'<a href="{_escape(url, quote=True)}">{esc(label)}</a>'
        for label, url, active in tabs
    ]
    if not cells:
        return ""
    return para(
        f'<span style="color: {DIM}">' + " &nbsp;·&nbsp; ".join(cells) + "</span>"
    )


# The eight block glyphs a sparkline draws with, floor to ceiling.
_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: Iterable[float], width: int = 40) -> str:
    """A compact inline trend of a numeric series as block glyphs (the Ring page).

    Auto-scaled to the series' own min/max so the *shape* reads even when the
    absolute range is narrow — the Ring's corruption creeps, and a fixed 0..100
    scale would flatten that creep to a single low bar. A series longer than
    ``width`` is evenly sampled down to ``width`` points (endpoints preserved); a
    flat or single-point series renders at the floor, never blank; empty input
    yields the empty string.
    """
    seq = list(values)
    if not seq:
        return ""
    if len(seq) > width:
        step = (len(seq) - 1) / (width - 1) if width > 1 else 0
        seq = [seq[round(i * step)] for i in range(width)]
    lo, hi = min(seq), max(seq)
    span = hi - lo
    if span == 0:
        return _SPARK_BLOCKS[0] * len(seq)
    top = len(_SPARK_BLOCKS) - 1
    return "".join(_SPARK_BLOCKS[round((v - lo) / span * top)] for v in seq)


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
