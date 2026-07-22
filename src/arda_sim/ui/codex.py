"""The Codex: one browser pane where everything is a page (ADR-0014, #36).

Every non-map surface — dossiers, index tables, search results — renders in a
single pane, addressed by an internal ``codex://<kind>/<id>`` scheme. This
module owns the shell's three parts:

* :class:`CodexAddress` / :class:`CodexHistory` — the address scheme and the
  back/forward stack, pure and Qt-free;
* :func:`search_matches` / :func:`render_search_page` — the omnibox's matching
  and its results *page* (results are a page like any other, so a search sits
  in history and its hits are ordinary links);
* :class:`CodexPane` — the widget: a header row (back/forward, omnibox, index
  links) over a :class:`QTextBrowser`.

The pane knows nothing about the world: it takes a ``render`` callable mapping
an address to dossier HTML (or ``None`` for a dead link) — the window owns the
kind→renderer registry, since the dossier builders read its snapshot state.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Callable, Iterable, List, Optional, Tuple, Union

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .dossier_html import DIM, banner, dim_para, para

_SCHEME = "codex"

# A match offered by the omnibox: display name, a dim detail line, and where
# the hit navigates. The tuple (not a class) keeps window-side composition flat.
SearchMatch = Tuple[str, str, "CodexAddress"]


@dataclass(frozen=True)
class CodexAddress:
    """One page's address: ``codex://<kind>/<ident>``.

    ``kind`` picks the renderer (faction, host, site, tile, event, ring,
    index, search); ``ident`` is the renderer's to interpret — an entity id,
    a ``col,row`` pair, an index name, or a raw search query. Everything after
    the kind's slash belongs to the ident, so queries may carry slashes.
    """

    kind: str
    ident: str

    @property
    def url(self) -> str:
        return f"{_SCHEME}://{self.kind}/{self.ident}"

    @classmethod
    def parse(cls, url: str) -> Optional["CodexAddress"]:
        prefix = f"{_SCHEME}://"
        if not url.startswith(prefix):
            return None
        kind, _, ident = url[len(prefix):].partition("/")
        if not kind or not ident:
            return None
        return cls(kind, ident)


class CodexHistory:
    """A browser-style back/forward stack of addresses. Pure state.

    ``visit`` is a navigation (a click): it truncates any forward branch,
    exactly like a web browser. ``back``/``forward`` move the cursor and
    return the new current address, or ``None`` at either end (the cursor
    stays put). Revisiting the current address is a no-op, so a re-click
    never buries the back stack under duplicates.
    """

    def __init__(self) -> None:
        self._entries: List[CodexAddress] = []
        self._cursor = -1  # index into _entries; -1 = nothing visited

    @property
    def current(self) -> Optional[CodexAddress]:
        return self._entries[self._cursor] if self._cursor >= 0 else None

    def can_back(self) -> bool:
        return self._cursor > 0

    def can_forward(self) -> bool:
        return 0 <= self._cursor < len(self._entries) - 1

    def visit(self, address: CodexAddress) -> None:
        if address == self.current:
            return
        del self._entries[self._cursor + 1:]
        self._entries.append(address)
        self._cursor += 1

    def back(self) -> Optional[CodexAddress]:
        if not self.can_back():
            return None
        self._cursor -= 1
        return self.current

    def forward(self) -> Optional[CodexAddress]:
        if not self.can_forward():
            return None
        self._cursor += 1
        return self.current


def search_matches(
    query: str, candidates: Iterable[SearchMatch]
) -> List[SearchMatch]:
    """The omnibox's matching: case-insensitive substring over *names*.

    Names only — the detail line is display context, not an index; matching it
    would surface every entity in a realm for that realm's name. Prefix hits
    rank before interior hits (each group keeps the candidates' given order),
    so typing a name's start floats it to the top. A blank query matches
    nothing rather than everything.
    """
    needle = query.strip().lower()
    if not needle:
        return []
    prefix: List[SearchMatch] = []
    interior: List[SearchMatch] = []
    for candidate in candidates:
        haystack = candidate[0].lower()
        if haystack.startswith(needle):
            prefix.append(candidate)
        elif needle in haystack:
            interior.append(candidate)
    return prefix + interior


def render_search_page(query: str, matches: List[SearchMatch]) -> str:
    """The search-results page: every hit an ordinary ``codex://`` link."""
    parts = [banner("Search", query)]
    if not matches:
        parts.append(dim_para("Nothing in the record answers."))
        return "".join(parts)
    lines = [
        f'<a href="{escape(addr.url, quote=True)}">{escape(name, quote=False)}</a>'
        f' &nbsp;<span style="color: {DIM}">{escape(detail, quote=False)}</span>'
        for name, detail, addr in matches
    ]
    parts.append(para("<br>".join(lines)))
    return "".join(parts)


class CodexPane(QWidget):
    """The Codex widget: back/forward + omnibox + index links over a browser.

    ``render`` maps an address to page HTML (``None`` renders a dead-link
    page).
    """

    #: The index pages in header order — stub renderers until #17/#19/#20.
    INDEXES = ("armies", "factions", "wars")

    def __init__(
        self,
        render: Callable[[CodexAddress], Optional[str]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._render = render
        self.history = CodexHistory()

        self._back = QToolButton(self)
        self._back.setText("◀")
        self._back.setToolTip("Back (Alt+Left)")
        self._back.clicked.connect(self.go_back)
        self._forward = QToolButton(self)
        self._forward.setText("▶")
        self._forward.setToolTip("Forward (Alt+Right)")
        self._forward.clicked.connect(self.go_forward)

        self.omnibox = QLineEdit(self)
        self.omnibox.setPlaceholderText("Search the record…  (Ctrl+F)")
        self.omnibox.setClearButtonEnabled(True)
        self.omnibox.returnPressed.connect(self._on_search)

        index_links = QLabel(
            " · ".join(
                f'<a href="codex://index/{name}">{name.title()}</a>'
                for name in self.INDEXES
            ),
            self,
        )
        index_links.setTextFormat(Qt.RichText)
        index_links.linkActivated.connect(self.open_url)

        header = QHBoxLayout()
        header.setContentsMargins(4, 4, 4, 0)
        header.setSpacing(4)
        header.addWidget(self._back)
        header.addWidget(self._forward)
        header.addWidget(self.omnibox, 1)
        header.addWidget(index_links)

        self.browser = QTextBrowser(self)
        self.browser.setOpenLinks(False)  # codex:// is ours, never the OS's
        self.browser.setPlaceholderText(
            "Select something on the map, an annals entry, or search above."
        )
        self.browser.anchorClicked.connect(self.open_url)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(header)
        layout.addWidget(self.browser)

        # Browser-standard keys, window-wide: browsing is the window's mode,
        # not a focus-local nicety. Ctrl+F claims the omnibox for #18's finder.
        QShortcut(QKeySequence("Alt+Left"), self, self.go_back)
        QShortcut(QKeySequence("Alt+Right"), self, self.go_forward)
        QShortcut(QKeySequence.Find, self, self._focus_omnibox)

        self._sync_buttons()

    # -- navigation ------------------------------------------------------

    def navigate(self, address: CodexAddress) -> None:
        """Go to a page: render it, enter it into history."""
        self.history.visit(address)
        self._show(address)

    def open_url(self, url: Union[str, QUrl]) -> None:
        """Navigate to a ``codex://`` url (string or QUrl); ignore others."""
        address = CodexAddress.parse(
            url.toString() if isinstance(url, QUrl) else url
        )
        if address is not None:
            self.navigate(address)

    def go_back(self) -> None:
        address = self.history.back()
        if address is not None:
            self._show(address)

    def go_forward(self) -> None:
        address = self.history.forward()
        if address is not None:
            self._show(address)

    def _show(self, address: CodexAddress) -> None:
        html = self._render(address)
        if html is None:
            html = banner("Codex", "No such page") + dim_para(
                f"Nothing answers to {address.url} in the displayed year."
            )
        self.browser.setHtml(html)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self._back.setEnabled(self.history.can_back())
        self._forward.setEnabled(self.history.can_forward())

    # -- omnibox ---------------------------------------------------------

    def _on_search(self) -> None:
        query = self.omnibox.text().strip()
        if query:
            self.navigate(CodexAddress("search", query))

    def _focus_omnibox(self) -> None:
        self.omnibox.setFocus()
        self.omnibox.selectAll()
