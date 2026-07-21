"""Playback: forward-only simulation with a snapshot-per-tick cache.

The sim only ever runs forward. Every simulated tick (one month) is cached as a
:class:`Snapshot`, so scrubbing back to an already-simulated tick restores a
stored snapshot instantly (never a replay). Seeking past the frontier
fast-forwards by simulating the missing ticks.

This is the headless seam the Qt UI drives: it has no Qt dependency and is fully
testable on its own — drive it, then assert on frontier, cached snapshots, and
the per-tick event stream.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .entities import Event
from .pipeline import run_tick
from .snapshot import Snapshot, snapshot_world
from .world import World


class Playback:
    """Owns a live ``World`` plus the cache of per-tick snapshots."""

    def __init__(self, world: World) -> None:
        self._world = world
        self._snapshots: Dict[int, Snapshot] = {}
        # Last simulated tick. Nothing simulated yet, so the frontier sits one
        # tick before the first tick the world will simulate.
        self._frontier = world.tick - 1

    @property
    def frontier(self) -> int:
        """The most recent simulated tick (``first_tick - 1`` before the first)."""
        return self._frontier

    @property
    def first_tick(self) -> int:
        """The earliest tick that can ever be scrubbed to."""
        return 0

    @property
    def world(self) -> World:
        """The live world. The UI should render from snapshots, not this."""
        return self._world

    def advance(self) -> Tuple[Snapshot, List[Event]]:
        """Simulate the next tick; cache and return its snapshot and events."""
        tick = self._world.tick
        events = run_tick(self._world)
        snapshot = snapshot_world(self._world, tick)
        self._snapshots[tick] = snapshot
        self._frontier = tick
        return snapshot, events

    def has_snapshot(self, tick: int) -> bool:
        """Whether tick ``tick`` has been simulated and cached."""
        return tick in self._snapshots

    def restore(self, tick: int) -> Snapshot:
        """Return the cached snapshot for an already-simulated ``tick``.

        This is the instant scrub path — no replay. Raises if ``tick`` is outside
        the simulated range; callers scrub only within ``[first_tick, frontier]``.
        """
        if tick not in self._snapshots:
            raise KeyError(
                f"tick {tick} is not within the simulated frontier "
                f"[{self.first_tick}, {self.frontier}]"
            )
        return self._snapshots[tick]

    def fast_forward_to(self, tick: int) -> List[Tuple[Snapshot, List[Event]]]:
        """Simulate forward until ``tick`` is reached; return each tick advanced.

        A no-op (empty list) if ``tick`` is already within the frontier — you
        restore those from the cache instead.
        """
        advanced: List[Tuple[Snapshot, List[Event]]] = []
        while self._frontier < tick:
            advanced.append(self.advance())
        return advanced
