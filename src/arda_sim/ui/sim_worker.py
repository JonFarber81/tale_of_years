"""The sim worker: drives :class:`Playback` on a background thread.

Lives in a ``QThread`` (moved there by the main window) so the simulation never
blocks the UI. It owns a ``QTimer`` for auto-play; play/pause/step/speed/seek are
slots invoked cross-thread. Each advanced year is published via ``yearAdvanced``;
the main window consumes ``(year, snapshot, events)`` on the GUI thread.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ..entities import Event
from ..playback import Playback
from ..snapshot import Snapshot

_DEFAULT_TICKS_PER_SEC = 2.0


class SimWorker(QObject):
    """Thread-affine driver around a headless ``Playback``."""

    # (Snapshot, list[Event]) — object-typed so Qt passes them through as-is. The
    # year is read off the snapshot; it is not a separate signal argument.
    yearAdvanced = Signal(object, object)
    frontierChanged = Signal(int)

    def __init__(self, playback: Playback) -> None:
        super().__init__()
        self._playback = playback
        self._timer: Optional[QTimer] = None  # created in the worker thread by setup()
        self._interval_ms = int(1000 / _DEFAULT_TICKS_PER_SEC)

    @Slot()
    def setup(self) -> None:
        """Create the timer in the worker thread. Call once after moveToThread."""
        self._timer = QTimer()
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._advance_one)

    @Slot()
    def play(self) -> None:
        self._timer.start(self._interval_ms)

    @Slot()
    def pause(self) -> None:
        self._timer.stop()

    @Slot()
    def step(self) -> None:
        """Advance exactly one year (independent of play state)."""
        self._advance_one()

    @Slot(float)
    def set_speed(self, ticks_per_sec: float) -> None:
        """Set auto-play rate; takes effect immediately if already playing."""
        self._interval_ms = max(1, int(1000 / max(ticks_per_sec, 0.001)))
        if self._timer.isActive():
            self._timer.start(self._interval_ms)

    @Slot(int)
    def seek(self, year: int) -> None:
        """Scrub to ``year``: restore instantly within the frontier, else
        fast-forward the sim to reach it.
        """
        if year <= self._playback.frontier:
            snapshot = self._playback.restore(year)
            # A scrub emits no new events; the view caps its annals at this year.
            self.yearAdvanced.emit(snapshot, [])
        else:
            for snapshot, events in self._playback.fast_forward_to(year):
                self._publish(snapshot, events)

    # -- internals -------------------------------------------------------

    def _advance_one(self) -> None:
        snapshot, events = self._playback.advance_year()
        self._publish(snapshot, events)

    def _publish(self, snapshot: Snapshot, events: List[Event]) -> None:
        # Frontier first, so a GUI-thread consumer sees the new frontier before
        # the snapshot that reached it (both signals are queued in this order).
        self.frontierChanged.emit(self._playback.frontier)
        self.yearAdvanced.emit(snapshot, events)
