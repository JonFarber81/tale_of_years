"""Character journeys — the general character-mover, before the Ring phase (ADR-0015).

A **journey** is a named character on the road: a destination site, a tile path
re-plotted toward it, and its own foot/horse pace. The **character-journeys** phase
advances every journeying character one tick along the least-cost path, reusing the
exact same pure primitives the marching host and the Nazgûl hunt use
(:func:`arda_sim.armies.find_path` / :func:`~arda_sim.armies.step_along_path`), so
the three movers can never price a step differently.

This module mirrors the Nazgûl Hunt (:mod:`arda_sim.sauron`) deliberately — a
transient :class:`Entity` mover with a tile position, a re-targetable path, and a
tombstone on arrival. It is, for now, a **prefactor**: no motive wires a journey
yet, so the phase is inert and every seeded run replays byte-for-byte. The seam a
future motive (and the tests) call to put a character on the road is
:func:`begin_journey`.

Determinism: like the Ring, the hunt, and Sauron's rise, the phase draws every
stochastic choice — none yet — from a **derived per-tick RNG**
(``seed_str|journeys|tick``), never the pipeline's shared stream (ADR-0008), so it
perturbs no other system's draws. All arithmetic is integer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from .armies import find_path, step_along_path
from .characters import Character
from .entities import Entity, EntityStatus, Event, register_entity_type
from .world import World

# Event this phase emits: a journeying character reached its destination site.
CHARACTER_ARRIVED_EVENT = "character_arrived"

# Default journey pace, miles/year. A character on foot or horse travels well
# below the Nine's _HUNT_PACE of 260 mi/yr — the wraiths ride faster than any
# traveller walks.
_JOURNEY_PACE = 120


@dataclass
class Journey(Entity):
    """A character on the road: one traveller's position, path, and destination.

    A transient mover (kind ``"journey"``) like an Army or a :class:`Hunt`: a tile
    position, a path re-plotted if the goal moves, its own pace, and the id of the
    character walking it. It only ever *moves*; arrival hands the character to its
    destination site and tombstones the record (status ``dead``).
    """

    char_id: int = 0
    col: int = 0
    row: int = 0
    dest_site_id: Optional[int] = None  # config-space site id the traveller seeks
    goal: List[int] = field(default_factory=list)  # the tile last plotted toward
    path: List[List[int]] = field(default_factory=list)
    move_points: int = 0
    miles_per_year: int = _JOURNEY_PACE

    @property
    def alive(self) -> bool:
        return self.status == EntityStatus.ACTIVE.value


register_entity_type("journey", Journey)


# =========================================================================
# Queries
# =========================================================================

def journeys(world: World, *, alive_only: bool = False) -> List[Journey]:
    """All Journey records in id order (optionally only those still on the road)."""
    result = [e for _id, e in sorted(world.entities.items()) if isinstance(e, Journey)]
    return [j for j in result if j.alive] if alive_only else result


# =========================================================================
# The seam — set a character travelling
# =========================================================================

def begin_journey(
    world: World,
    char: Character,
    dest_site_id: int,
    *,
    miles_per_year: int = _JOURNEY_PACE,
) -> Optional[Journey]:
    """Set ``char`` walking from its current site toward ``dest_site_id``.

    Resolves the character's current tile from its ``location_id`` site through
    ``world.grid``, plots a :func:`find_path` to the destination site's tile,
    creates and registers the Journey, and marks the character **abroad** (so the
    leader ladder skips it while away). Returns ``None`` — setting nothing on the
    character — if there is no grid, either endpoint is off-map, the character is
    already there, or no path exists.

    This is the seam a future motive (and the journey tests) call to put a
    character on the road; nothing wires it yet (ADR-0015 — the phase is inert).
    """
    grid = world.grid
    if grid is None:
        return None
    start_site = grid.site_by_id(char.location_id) if char.location_id is not None else None
    dest_site = grid.site_by_id(dest_site_id)
    if start_site is None or dest_site is None:
        return None
    if char.location_id == dest_site_id:
        return None  # already there
    path = find_path(grid, (start_site.col, start_site.row), (dest_site.col, dest_site.row))
    if not path:
        return None  # unreachable

    journey = Journey(
        id=world.next_id(),
        kind="journey",
        name=f"The journey of {char.name}",
        created_year=world.current_year,
        char_id=char.id,
        col=start_site.col,
        row=start_site.row,
        dest_site_id=dest_site_id,
        goal=[dest_site.col, dest_site.row],
        path=path,
        miles_per_year=miles_per_year,
    )
    world.entities[journey.id] = journey
    char.abroad = True
    return journey


# =========================================================================
# The phase — journeys advance (movement only), before the Ring phase
# =========================================================================

def character_journeys(world: World, rng: random.Random) -> List[Event]:
    """Advance every travelling character one tick along its path (ADR-0015).

    Ordered among the movers (armies' ``movement``, the Nine's ``hunt``) and
    **before** the Ring phase, so an arriving traveller is standing on the tile
    when the Ring phase looks. Draws **nothing** from the shared ``rng`` — pathing
    and stepping are the same pure helpers hosts and wraiths use — and this inert
    slice makes no draw at all; when motives land they take an isolated per-tick RNG
    (``seed_str|journeys|tick``) in the ADR-0008 pattern, never the shared stream.

    On arrival (the traveller's tile is the destination site's tile) the character
    is set down at its destination site, its abroad state cleared, and the Journey
    tombstoned, emitting a :data:`CHARACTER_ARRIVED_EVENT`. No events per step.
    """
    grid = world.grid
    if grid is None:
        return []
    # Isolated per-tick stream (ADR-0008): when motives land they must draw from
    # ``make_rng(f"{world.config.seed_str}|journeys|{world.tick}")`` — never the
    # shared pipeline ``rng`` — so adding characters rewrites no other history.
    # This slice advances only along a pre-plotted path, so it makes no draw at all.

    events: List[Event] = []
    for journey in journeys(world, alive_only=True):
        events.extend(_advance_journey(world, journey))
    return events


def _advance_journey(world: World, journey: Journey) -> List[Event]:
    """One tick of travel: retarget if the goal moved, step, arrive if on the tile."""
    grid = world.grid
    char = world.entities.get(journey.char_id)
    if not isinstance(char, Character) or not char.alive:
        return [_end_journey(world, journey)]  # traveller gone; set the road down

    dest_site = (
        grid.site_by_id(journey.dest_site_id)
        if journey.dest_site_id is not None
        else None
    )
    if dest_site is None:
        return [_end_journey(world, journey)]  # destination vanished off-map

    goal = [dest_site.col, dest_site.row]
    if journey.goal != goal:
        journey.goal = list(goal)
        journey.path = find_path(grid, (journey.col, journey.row), (dest_site.col, dest_site.row))
    if journey.path:
        journey.col, journey.row, journey.path, journey.move_points = step_along_path(
            grid, journey.col, journey.row, journey.path,
            journey.move_points, journey.miles_per_year,
        )

    if journey.col == dest_site.col and journey.row == dest_site.row:
        return [_arrive(world, journey, char, dest_site.id)]
    return []


def _arrive(world: World, journey: Journey, char: Character, site_id: int) -> Event:
    """Set the traveller down at its destination, clear abroad, and tombstone."""
    char.location_id = site_id
    char.abroad = False
    journey.status = EntityStatus.DEAD.value
    return world.new_event(
        type=CHARACTER_ARRIVED_EVENT,
        subject_ids=[char.id, journey.id],
        location_id=site_id,
        payload={"site_id": site_id},
    )


def _end_journey(world: World, journey: Journey) -> Event:
    """Call a journey off (traveller dead or destination gone): tombstone and clear.

    Sets the traveller down where the road stands and clears its abroad state so a
    still-living character is never stranded off the leader ladder.
    """
    journey.status = EntityStatus.DEAD.value
    char = world.entities.get(journey.char_id)
    grid = world.grid
    site = grid.site_at(journey.col, journey.row) if grid is not None else None
    if isinstance(char, Character) and char.alive:
        if site is not None:
            char.location_id = site.id
        char.abroad = False
    return world.new_event(
        type=CHARACTER_ARRIVED_EVENT,
        subject_ids=[journey.char_id, journey.id],
        location_id=site.id if site is not None else None,
        payload={"ended": True},
    )
