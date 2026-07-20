"""The ``World`` spine: the single authoritative state container for a run.

Holds id-keyed entity records plus run-level fields (current year, a single
seeded RNG, the monotonic id counter, run config, and the append-only event
log). One never-reused integer id space covers everything addressable —
entities and events alike.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import (
    DEFAULT_SCENARIO_ID,
    DEFAULT_SCENARIO_VERSION,
    START_YEAR,
)
from .entities import Entity, EntityStatus, Event
from .rng import make_rng


@dataclass
class RunConfig:
    """Immutable run identity: what, plus how canon-leaning. Never mutated after
    construction; distinct from per-tick mutable state.
    """

    seed_str: str
    canonicity: float = 1.0
    scenario_id: str = DEFAULT_SCENARIO_ID
    scenario_version: int = DEFAULT_SCENARIO_VERSION


@dataclass
class World:
    """Authoritative run state. Plain, id-keyed, and directly serializable."""

    config: RunConfig
    current_year: int = START_YEAR
    id_counter: int = 1
    entities: Dict[int, Entity] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)
    # The seeded RNG is a live object, not persisted as-is; its getstate() is
    # what serializes. Excluded from equality so two worlds compare on state.
    rng: random.Random = field(default_factory=lambda: random.Random(0), compare=False)

    @classmethod
    def new_run(
        cls,
        seed_str: str,
        canonicity: float = 1.0,
        scenario_id: str = DEFAULT_SCENARIO_ID,
        scenario_version: int = DEFAULT_SCENARIO_VERSION,
    ) -> "World":
        """Start a fresh run from a seed string, with the RNG seeded from it."""
        config = RunConfig(
            seed_str=seed_str,
            canonicity=canonicity,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
        )
        return cls(config=config, rng=make_rng(seed_str))

    # -- id space ---------------------------------------------------------

    def next_id(self) -> int:
        """Allocate the next monotonic id. Ids are never reused."""
        new_id = self.id_counter
        self.id_counter += 1
        return new_id

    # -- entities ---------------------------------------------------------

    def add_entity(
        self, kind: str, name: str, status: str = EntityStatus.ACTIVE.value
    ) -> Entity:
        """Create and register an entity with a fresh id at the current year."""
        entity = Entity(
            id=self.next_id(),
            kind=kind,
            name=name,
            created_year=self.current_year,
            status=status,
        )
        self.entities[entity.id] = entity
        return entity

    # -- events -----------------------------------------------------------

    def new_event(
        self,
        type: str,
        subject_ids: Optional[List[int]] = None,
        location_id: Optional[int] = None,
        importance: int = 0,
        payload: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
    ) -> Event:
        """Build an event stamped with a fresh id and the current year.

        Does not append it — a system returns its events and the pipeline
        appends them, keeping the log strictly append-only in phase order.
        """
        return Event(
            id=self.next_id(),
            year=self.current_year,
            type=type,
            subject_ids=list(subject_ids) if subject_ids else [],
            location_id=location_id,
            importance=importance,
            payload=dict(payload) if payload else {},
            text=text,
        )

    def append_event(self, event: Event) -> None:
        """Append an emitted event to the immutable log."""
        self.events.append(event)
