"""Snapshot: an immutable view of the renderable world state at the end of one
simulated tick.

The UI renders and inspects from snapshots, never from the live ``World``, so a
scrub to tick T restores ``snapshot[T]`` without re-simulating. A snapshot holds
only what the map/inspection need to draw tick T — the tick, its calendar year
(derived, for labels), and a frozen copy of the entities; region ownership, army
positions, and the Ring join as their systems land. The event *stream* is
delivered separately (the UI accumulates it), so snapshots stay small and don't
duplicate the growing log.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Optional

from .entities import Entity
from .world import World, year_of_tick


@dataclass(frozen=True)
class Snapshot:
    """Frozen renderable state for a single tick. Independent of later mutation.

    ``tick`` is the absolute clock value (the cache key); ``year`` is the calendar
    year it falls in, kept for the year-grained annals and the date label.
    """

    tick: int = 0
    year: int = 0
    entities: Dict[int, Entity] = field(default_factory=dict)

    def entity(self, entity_id: int) -> Optional[Entity]:
        """Look up an entity's state as of this snapshot's tick, or None."""
        return self.entities.get(entity_id)


def snapshot_world(world: World, tick: int) -> Snapshot:
    """Capture ``world``'s renderable state as an immutable snapshot for ``tick``.

    Entities are copied (``dataclasses.replace``) so the snapshot is unaffected
    by subsequent ticks; entity records hold only primitives, so a field copy is
    a complete decoupling. The year is derived from ``tick`` (the tick just
    simulated), not read off the world, which may already have rolled forward.
    """
    entities = {eid: replace(e) for eid, e in world.entities.items()}
    return Snapshot(tick=tick, year=year_of_tick(tick), entities=entities)
