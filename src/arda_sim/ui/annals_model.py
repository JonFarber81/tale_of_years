"""The Annals feed model: a virtualized list of dated events.

Backs a ``QListView`` (which only realizes visible rows, so the feed stays
responsive across centuries). Events accumulate as years tick; a scrub cap hides
events from years the viewer has scrubbed *behind*, so the feed always reflects
the year currently on screen. Events arrive in year order, so the cap is a simple
count found by bisecting on year.
"""

from __future__ import annotations

import bisect
from typing import List, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ..entities import Event


def render_event(event: Event) -> str:
    """One-line chronicle text for an event.

    Uses ``Event.text`` once systems render prose (ticket 11); until then, a
    readable placeholder from the structured fields.
    """
    if event.text:
        return f"TA {event.year}: {event.text}"
    return f"TA {event.year}: [{event.type}]"


class AnnalsModel(QAbstractListModel):
    """Append-only event list with a year-based visibility cap for scrubbing."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._events: List[Event] = []
        self._years: List[int] = []  # parallel to _events, for bisect
        self._cap_year: Optional[int] = None  # None = show everything

    # -- Qt model interface ----------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self._visible_count()

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        return render_event(self._events[index.row()])

    # -- feed updates ----------------------------------------------------

    def append_events(self, events: List[Event]) -> None:
        """Append newly-emitted events (assumed to be at/after the last year)."""
        if not events:
            return
        start = len(self._events)
        self.beginInsertRows(QModelIndex(), start, start + len(events) - 1)
        self._events.extend(events)
        self._years.extend(e.year for e in events)
        self.endInsertRows()

    def set_cap_year(self, year: Optional[int]) -> None:
        """Hide events after ``year`` (a scrub); ``None`` reveals all events."""
        if year == self._cap_year:
            return
        self.beginResetModel()
        self._cap_year = year
        self.endResetModel()

    # -- internals -------------------------------------------------------

    def _visible_count(self) -> int:
        if self._cap_year is None:
            return len(self._events)
        # events with year <= cap; _years is non-decreasing, so bisect_right.
        return bisect.bisect_right(self._years, self._cap_year)
