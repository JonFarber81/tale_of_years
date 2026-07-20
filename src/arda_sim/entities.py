"""Serializable record types: the entity base and the Event.

Every record is a plain dataclass. All cross-entity references are integer ids
(never object pointers), so the whole world is a plain tree with no cycles that
serializes directly to JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EntityStatus(str, Enum):
    """How an entity relates to play. Tombstoned entities are never deleted, so
    references to them always resolve.
    """

    ACTIVE = "active"
    DEAD = "dead"  # natural or violent death
    DEPARTED = "departed"  # Elves sailing West
    DESTROYED = "destroyed"  # the One Ring at Mount Doom; the Nazgûl unmade with it

    def __str__(self) -> str:  # keep JSON/text output as the bare value
        return self.value


@dataclass
class Entity:
    """Base fields shared by every addressable game record.

    Game-specific record types (character, faction, region, ...) arrive in later
    tickets; the walking skeleton uses this base directly so the id space, the
    tick loop, and persistence can be exercised before any game logic exists.
    """

    id: int
    kind: str
    name: str
    created_year: int
    status: str = EntityStatus.ACTIVE.value


@dataclass
class Event:
    """An immutable dated record emitted by a system after it mutates state.

    Events never drive state (the sim is not event-sourced); they are the
    readable chronicle plus the query surface (by subject, faction, year, type).
    """

    id: int
    year: int
    type: str
    subject_ids: List[int] = field(default_factory=list)
    location_id: Optional[int] = None
    importance: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)
    text: Optional[str] = None
