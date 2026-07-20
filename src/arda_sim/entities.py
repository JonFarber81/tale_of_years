"""Serializable record types: the entity base and the Event.

Every record is a plain dataclass. All cross-entity references are integer ids
(never object pointers), so the whole world is a plain tree with no cycles that
serializes directly to JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, Dict, List, Optional, Type


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


# Registry of entity ``kind`` -> dataclass, so a saved entity rehydrates as the
# right subtype (a Character carries fields the base Entity lacks). Subtypes
# register themselves on import; unknown kinds fall back to the base Entity.
ENTITY_TYPES: Dict[str, Type[Entity]] = {}


def register_entity_type(kind: str, cls: Type[Entity]) -> None:
    """Register ``cls`` as the concrete type for entities of this ``kind``."""
    ENTITY_TYPES[kind] = cls


def entity_from_dict(data: Dict[str, Any]) -> Entity:
    """Rehydrate an entity dict to its registered subtype (or the base Entity).

    Only keys matching the target dataclass's fields are passed, so a save made
    by newer code with extra fields still loads into older code (forward-lenient).
    """
    cls = ENTITY_TYPES.get(data.get("kind", ""), Entity)
    allowed = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in allowed})


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
