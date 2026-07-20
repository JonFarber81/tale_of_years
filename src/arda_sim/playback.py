"""Playback: forward-only simulation with a snapshot-per-year cache.

The sim only ever runs forward. Every simulated year is cached as a
:class:`Snapshot`, so scrubbing back to an already-simulated year restores a
stored snapshot instantly (never a replay). Seeking past the frontier
fast-forwards by simulating the missing years.

This is the headless seam the Qt UI drives: it has no Qt dependency and is fully
testable on its own — drive it, then assert on frontier, cached snapshots, and
the per-year event stream.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from . import START_YEAR
from .entities import Event
from .pipeline import run_tick
from .snapshot import Snapshot, snapshot_world
from .world import World


class Playback:
    """Owns a live ``World`` plus the cache of per-year snapshots."""

    def __init__(self, world: World) -> None:
        self._world = world
        self._snapshots: Dict[int, Snapshot] = {}
        # Last simulated year. Nothing simulated yet, so the frontier sits one
        # year before the first year the world will simulate.
        self._frontier = world.current_year - 1

    @property
    def frontier(self) -> int:
        """The most recent simulated year (``start - 1`` before the first tick)."""
        return self._frontier

    @property
    def first_year(self) -> int:
        """The earliest year that can ever be scrubbed to."""
        return START_YEAR

    @property
    def world(self) -> World:
        """The live world. The UI should render from snapshots, not this."""
        return self._world

    def advance_year(self) -> Tuple[Snapshot, List[Event]]:
        """Simulate the next year; cache and return its snapshot and events."""
        year = self._world.current_year
        events = run_tick(self._world)
        snapshot = snapshot_world(self._world, year)
        self._snapshots[year] = snapshot
        self._frontier = year
        return snapshot, events

    def has_snapshot(self, year: int) -> bool:
        """Whether year ``year`` has been simulated and cached."""
        return year in self._snapshots

    def restore(self, year: int) -> Snapshot:
        """Return the cached snapshot for an already-simulated ``year``.

        This is the instant scrub path — no replay. Raises if ``year`` is outside
        the simulated range; callers scrub only within ``[first_year, frontier]``.
        """
        if year not in self._snapshots:
            raise KeyError(
                f"year {year} is not within the simulated frontier "
                f"[{self.first_year}, {self.frontier}]"
            )
        return self._snapshots[year]

    def fast_forward_to(self, year: int) -> List[Tuple[Snapshot, List[Event]]]:
        """Simulate forward until ``year`` is reached; return each year advanced.

        A no-op (empty list) if ``year`` is already within the frontier — you
        restore those from the cache instead.
        """
        advanced: List[Tuple[Snapshot, List[Event]]] = []
        while self._frontier < year:
            advanced.append(self.advance_year())
        return advanced
