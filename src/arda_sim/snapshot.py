"""Snapshot: an immutable view of the renderable world state at the end of one
simulated year.

The UI renders and inspects from snapshots, never from the live ``World``, so a
scrub to year T restores ``snapshot[T]`` without re-simulating. A snapshot holds
only what the map/inspection need to draw year T — currently just the year and a
frozen copy of the entities; region ownership, army positions, and the Ring join
as their systems land. The event *stream* is delivered separately (the UI
accumulates it), so snapshots stay small and don't duplicate the growing log.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Optional

from .entities import Entity
from .world import World


@dataclass(frozen=True)
class Snapshot:
    """Frozen renderable state for a single year. Independent of later mutation."""

    year: int
    entities: Dict[int, Entity] = field(default_factory=dict)

    def entity(self, entity_id: int) -> Optional[Entity]:
        """Look up an entity's state as of this snapshot's year, or None."""
        return self.entities.get(entity_id)


def snapshot_world(world: World, year: int) -> Snapshot:
    """Capture ``world``'s renderable state as an immutable snapshot for ``year``.

    Entities are copied (``dataclasses.replace``) so the snapshot is unaffected
    by subsequent ticks; entity records hold only primitives, so a field copy is
    a complete decoupling.
    """
    entities = {eid: replace(e) for eid, e in world.entities.items()}
    return Snapshot(year=year, entities=entities)
