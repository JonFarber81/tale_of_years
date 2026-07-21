"""The Annals feed model: a virtualized list of dated events.

Backs a ``QListView`` (which only realizes visible rows, so the feed stays
responsive across centuries). Two things decide whether an event shows:

* a **scrub cap** — a year the viewer has scrubbed *behind*, hiding later events
  so the feed reflects the year on screen (events arrive in year order);
* an **:class:`~arda_sim.chronicle.AnnalsFilter`** — the four query indices plus
  an importance threshold; the feed **defaults to important-only** and reveals
  everything on :meth:`show_all` (build ticket 06).

A ``_visible`` list of source indices is maintained so rows map straight through
to the filtered-and-capped subset; it is held **newest-first** (row 0 is the most
recent event), extended at the front as years tick, and rebuilt only when the cap
or filter changes.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List, Mapping, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ..chronicle import AnnalsFilter, show_all_filter
from ..entities import Event


def render_event(event: Event) -> str:
    """One-line chronicle text for an event.

    Uses the chronicle-rendered ``Event.text`` when present (build ticket 06);
    falls back to a structured placeholder for types with no template yet.
    """
    body = event.text if event.text else f"[{event.type}]"
    return f"TA {event.year}: {body}"


class AnnalsModel(QAbstractListModel):
    """Event list with a scrub cap and an importance/index filter (important-only
    by default)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._events: List[Event] = []
        self._cap_year: Optional[int] = None  # None = no scrub cap
        self._filter = AnnalsFilter()  # defaults to important-only
        self._faction_of: Mapping[int, int] = {}  # subject id -> faction id
        self._visible: List[int] = []  # source indices that currently show

    # -- Qt model interface ----------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._visible)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        return render_event(self._events[self._visible[index.row()]])

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
        # Newest-first: reverse the batch so the most recent event lands at row 0,
        # then insert the whole batch ahead of the existing rows.
        new_visible.reverse()
        self.beginInsertRows(QModelIndex(), 0, len(new_visible) - 1)
        self._visible[:0] = new_visible
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

    def _rebuild(self) -> None:
        self.beginResetModel()
        self._visible = [
            i for i, e in enumerate(self._events) if self._is_visible(e)
        ][::-1]
        self.endResetModel()
