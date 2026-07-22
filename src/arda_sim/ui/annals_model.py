"""The Annals feed model: a virtualized list of dated events.

Backs a ``QListView`` (which only realizes visible rows, so the feed stays
responsive across centuries). Two things decide whether an event shows:

* a **scrub cap** — a year the viewer has scrubbed *behind*, hiding later events
  so the feed reflects the year on screen (events arrive in year order);
* an **:class:`~arda_sim.chronicle.AnnalsFilter`** — the four query indices plus
  an importance threshold; the feed **defaults to important-only** and reveals
  everything on :meth:`show_all` (build ticket 06).

Rows come in two kinds: a **year header** (``TA NNNN``) followed by that year's
**event** rows, so the feed groups under year dividers instead of repeating the
year on every line. The row list is held **newest-first** (row 0 is the newest
year's header), extended at the front as years tick, and rebuilt only when the
cap or filter changes. Event rows expose their :class:`~arda_sim.entities.Event`
through :data:`EventRole` so the delegate (and later, click handling) reads
structure, not parsed strings; header rows return ``None`` there.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List, Mapping, Optional, Tuple

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ..chronicle import AnnalsFilter, show_all_filter
from ..entities import Event

# Custom role: the Event behind an event row (None for a year-header row).
EventRole = int(Qt.ItemDataRole.UserRole) + 1

# Row kinds in the internal row list.
_HEADER = "header"  # value = the year
_EVENT = "event"  # value = index into self._events


def render_event(event: Event) -> str:
    """One-line chronicle text for an event.

    Uses the chronicle-rendered ``Event.text`` when present (build ticket 06);
    falls back to a structured placeholder for types with no template yet.
    """
    body = event.text if event.text else f"[{event.type}]"
    return f"TA {event.year}: {body}"


def _event_body(event: Event) -> str:
    """The event's sentence without the year prefix (the header row carries it)."""
    return event.text if event.text else f"[{event.type}]"


class AnnalsModel(QAbstractListModel):
    """Event list with a scrub cap and an importance/index filter (important-only
    by default), grouped under year-header rows."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._events: List[Event] = []
        self._cap_year: Optional[int] = None  # None = no scrub cap
        self._filter = AnnalsFilter()  # defaults to important-only
        self._faction_of: Mapping[int, int] = {}  # subject id -> faction id
        # Visible rows, newest-first: ("header", year) | ("event", source index).
        self._rows: List[Tuple[str, int]] = []

    # -- Qt model interface ----------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        kind, value = self._rows[index.row()]
        if role == EventRole:
            return self._events[value] if kind == _EVENT else None
        if role == Qt.DisplayRole:
            if kind == _HEADER:
                return f"TA {value}"
            return _event_body(self._events[value])
        return None

    # -- row introspection (delegate/tests) --------------------------------

    def is_header(self, row: int) -> bool:
        """Whether ``row`` is a year-divider header rather than an event."""
        return self._rows[row][0] == _HEADER

    def event_at(self, row: int) -> Optional[Event]:
        """The event behind ``row`` (None for a header row)."""
        kind, value = self._rows[row]
        return self._events[value] if kind == _EVENT else None

    def visible_event_count(self) -> int:
        """How many *event* rows show (headers excluded)."""
        return sum(1 for kind, _ in self._rows if kind == _EVENT)

    def event_by_id(self, event_id: int) -> Optional[Event]:
        """The received event with this id, visible or filtered out, or None.

        The Codex's event pages (#36) resolve ``codex://event/<id>`` through
        this: the feed is the one place every delivered event is retained.
        """
        return next((e for e in self._events if e.id == event_id), None)

    # -- feed updates ----------------------------------------------------

    def append_events(self, events: List[Event]) -> None:
        """Append newly-emitted events (assumed to be at/after the last year)."""
        if not events:
            return
        base = len(self._events)
        new_visible = [
            base + offset for offset, e in enumerate(events) if self._is_visible(e)
        ]
        self._events.extend(events)
        if not new_visible:
            return
        block = self._rows_for(new_visible)
        # The block's oldest year may already head the feed; drop the stale
        # header so the year keeps a single divider.
        oldest_year = self._events[new_visible[0]].year
        if self._rows and self._rows[0] == (_HEADER, oldest_year):
            self.beginRemoveRows(QModelIndex(), 0, 0)
            del self._rows[0]
            self.endRemoveRows()
        self.beginInsertRows(QModelIndex(), 0, len(block) - 1)
        self._rows[:0] = block
        self.endInsertRows()

    def raw_count(self) -> int:
        """Total events received, ignoring the cap and filter (for tests/status)."""
        return len(self._events)

    # -- scrub cap -------------------------------------------------------

    def set_cap_year(self, year: Optional[int]) -> None:
        """Hide events after ``year`` (a scrub); ``None`` reveals all years."""
        if year == self._cap_year:
            return
        self._cap_year = year
        self._rebuild()

    # -- filtering -------------------------------------------------------

    def set_filter(self, annals_filter: AnnalsFilter) -> None:
        """Replace the active filter and rebuild the visible set."""
        self._filter = annals_filter
        self._rebuild()

    def set_min_importance(self, threshold: int) -> None:
        """Raise/lower just the importance threshold, keeping index filters."""
        self.set_filter(replace(self._filter, min_importance=threshold))

    def show_all(self) -> None:
        """Reveal every event: no threshold, no index constraints."""
        self.set_filter(show_all_filter())

    def important_only(self) -> None:
        """Return to the default important-only view."""
        self.set_filter(AnnalsFilter())

    def set_faction_index(self, faction_of: Optional[Mapping[int, int]]) -> None:
        """Supply the subject→faction map that a faction filter resolves through."""
        self._faction_of = faction_of or {}
        self._rebuild()

    @property
    def filter(self) -> AnnalsFilter:
        return self._filter

    # -- internals -------------------------------------------------------

    def _is_visible(self, event: Event) -> bool:
        if self._cap_year is not None and event.year > self._cap_year:
            return False
        return self._filter.matches(event, self._faction_of)

    def _rows_for(self, visible: List[int]) -> List[Tuple[str, int]]:
        """Newest-first rows for ascending source indices, with year headers."""
        rows: List[Tuple[str, int]] = []
        current_year: Optional[int] = None
        for i in reversed(visible):
            year = self._events[i].year
            if year != current_year:
                rows.append((_HEADER, year))
                current_year = year
            rows.append((_EVENT, i))
        return rows

    def _rebuild(self) -> None:
        self.beginResetModel()
        self._rows = self._rows_for(
            [i for i, e in enumerate(self._events) if self._is_visible(e)]
        )
        self.endResetModel()
