"""Character journeys — the general character-mover, before the Ring phase (ADR-0015).

A **journey** is a named character on the road: a destination site, a tile path
re-plotted toward it, and its own foot/horse pace. The **character-journeys** phase
advances every journeying character one tick along the least-cost path, reusing the
exact same pure primitives the marching host and the Nazgûl hunt use
(:func:`arda_sim.armies.find_path` / :func:`~arda_sim.armies.step_along_path`), so
the three movers can never price a step differently.

This module mirrors the Nazgûl Hunt (:mod:`arda_sim.sauron`) deliberately — a
transient :class:`Entity` mover with a tile position, a re-targetable path, and a
tombstone on arrival. The seam a motive (or a test) calls to put a character on the
road is :func:`begin_journey`. The first motive wired is **ring-seeking** (issue
#54): a Ring left unborne draws a generated **seeker** from the nearest free realm
who journeys to its tile, takes it up (a ``found`` transfer), and carries it home —
the tracer that flips the playtest harness off ~100 % ``lying_lost``.

Determinism: like the Ring, the hunt, and Sauron's rise, the phase draws every
stochastic choice from a **derived per-tick RNG** (``seed_str|journeys|tick``),
never the pipeline's shared stream (ADR-0008), so it perturbs no other system's
draws — a run whose Ring never strands touches the stream not at all. All
arithmetic is integer.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from .armies import find_path, step_along_path
from .characters import (
    DARK_LORD_TITLE,
    Character,
    Race,
    Role,
    add_character,
    living_faction_names,
)
from .entities import Entity, EntityStatus, Event, register_entity_type
from .factions import Faction, People, factions
from .naming import generate_name
from .ring import Ring, RingTransfer, send_on_errand, the_ring, transfer_ring
from .rng import make_rng
from .sauron import dark_realm
from .world import World

# Event this phase emits: a journeying character reached its destination site.
CHARACTER_ARRIVED_EVENT = "character_arrived"

# The closed motive set (ADR-0015). The tracer wires the first: a **ring-seeking**
# journey toward a stirring or lost Ring. The carry home once the Ring is in hand
# rides the Ring's own errand (a bearer carries it), not a second journey.
RING_SEEKING = "ring_seeking"

# The broad race a generated seeker takes when its realm has no living leader to
# copy — the folk-to-race fallback (Race is finer than People; Men default to MAN).
_PEOPLE_RACE = {
    People.MEN.value: Race.MAN,
    People.ELVES.value: Race.ELF,
    People.DWARVES.value: Race.DWARF,
    People.HOBBITS.value: Race.HOBBIT,
    People.ORCS.value: Race.ORC,
}

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
    motive: str = ""  # why the traveller set out (a motive; "" = plain travel)
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
    motive: str = "",
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
        motive=motive,
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
    events: List[Event] = []
    for journey in journeys(world, alive_only=True):
        events.extend(_advance_journey(world, journey))
    # The ring-seeking motive (ADR-0015). Its every stochastic choice draws from an
    # **isolated per-tick stream** (ADR-0008) — never the shared pipeline ``rng`` —
    # so seeding a seeker rewrites no war/diplomacy history. A borne Ring (the seed
    # state) makes this a no-op, so an unstranded run touches the stream not at all.
    r = make_rng(f"{world.config.seed_str}|journeys|{world.tick}")
    events.extend(_seek_the_ring(world, r))
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
        return _arrive(world, journey, char, dest_site.id)
    return []


def _arrive(world: World, journey: Journey, char: Character, site_id: int) -> List[Event]:
    """Set the traveller down at its destination, clear abroad, and tombstone.

    A ring-seeking arrival then reaches for the Ring where it lies (see
    :func:`_take_up_ring`); every other motive just sets the traveller down.
    """
    char.location_id = site_id
    char.abroad = False
    journey.status = EntityStatus.DEAD.value
    events = [
        world.new_event(
            type=CHARACTER_ARRIVED_EVENT,
            subject_ids=[char.id, journey.id],
            location_id=site_id,
            payload={"site_id": site_id},
        )
    ]
    if journey.motive == RING_SEEKING:
        events.extend(_take_up_ring(world, char, site_id))
    return events


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


# =========================================================================
# The ring-seeking motive — the tracer bullet (ADR-0015, issue #54)
# =========================================================================

def _unborne_ring(world: World) -> Optional[Ring]:
    """The One Ring iff it is in play and lying unborne — the seekable state."""
    ring = the_ring(world)
    if ring is None or ring.status != EntityStatus.ACTIVE.value or ring.borne:
        return None
    return ring


def _seek_the_ring(world: World, r: random.Random) -> List[Event]:
    """If the Ring lies unborne, send one generated seeker journeying toward it.

    The free-peoples counterpart to the Nazgûl hunt: the nearest plausible free
    realm generates a **seeker** (a notable) at its seat and sets it on the road to
    the Ring's tile, to take the Ring up on arrival (see :func:`_take_up_ring`). A
    **bounded** race — at most one seeker on the road at a time for the tracer — so a
    lost Ring draws someone rather than lying untouched forever. Every draw is from
    the passed **isolated** ``r`` (ADR-0008); the shared stream is never touched.

    A no-op unless the Ring is in play, unborne, at a resolvable site, and no seeker
    is already seeking it. Returns no events — the seeker's arrival and pickup are
    the visible beats, not its setting out.
    """
    grid = world.grid
    if grid is None:
        return []
    ring = _unborne_ring(world)
    if ring is None or ring.location_id is None:
        return []
    if any(j.motive == RING_SEEKING for j in journeys(world, alive_only=True)):
        return []  # one seeker on the road at a time (the bounded race)
    ring_site = grid.site_by_id(ring.location_id)
    if ring_site is None:
        return []
    realm = _nearest_free_realm(world, ring_site.col, ring_site.row)
    if realm is None:
        return []
    seeker = _spawn_seeker(world, realm, r)
    if seeker is None:
        return []
    begin_journey(world, seeker, ring_site.id, motive=RING_SEEKING)
    return []


def _take_up_ring(world: World, char: Character, site_id: int) -> List[Event]:
    """A seeker on the Ring's tile takes it up (``found``) and carries it home.

    Physical acquisition (ADR-0015): only a character standing where the Ring lies
    may take it. A no-op if a rival won the race first (the Ring is already borne)
    or the Ring is not on this tile. On pickup the seeker becomes an ordinary bearer
    and the Ring is set on an **errand** back to the seeker's own realm's seat — its
    own single carry mechanism, so bearer and Ring travel as one and a Ring dropped
    en route falls on the road, never back on the empty tile it was rescued from.
    The Ring leaves the empty place for a populated seat; on arrival the ordinary
    borne-tick rolls (corruption, further errands, claim, thrall) take over.
    """
    ring = _unborne_ring(world)
    if ring is None or ring.location_id != site_id:
        return []
    event = transfer_ring(world, ring, to_bearer=char, mode=RingTransfer.FOUND)
    seat = _home_seat(world, char)
    if seat is not None and seat != site_id:
        send_on_errand(world, ring, seat)  # the Ring carries its bearer home
    return [event]


def _nearest_free_realm(world: World, col: int, row: int) -> Optional[Faction]:
    """The free realm whose seat lies nearest a tile — the plausible sender.

    Free = a landed (non-provider) realm still in play that is neither the Shadow's
    own nor led by the Dark Lord, and that holds a seat to send from. Ranked by
    squared seat-to-Ring distance with an id tie-break, so the choice is
    deterministic; a realm whose seat *is* the tile is skipped (its residents, if
    any, would find the Ring themselves — a seeker needs a road to travel).
    """
    grid = world.grid
    dark = dark_realm(world)
    dark_id = dark.id if dark is not None else None
    best: Optional[Faction] = None
    best_key: Optional[tuple] = None
    for fac in factions(world, alive_only=True):
        if fac.is_provider or fac.id == dark_id or fac.capital_location_id is None:
            continue
        leader = world.entities.get(fac.leader_id) if fac.leader_id is not None else None
        if isinstance(leader, Character) and leader.title == DARK_LORD_TITLE:
            continue
        site = grid.site_by_id(fac.capital_location_id) if grid is not None else None
        if site is None or (site.col == col and site.row == row):
            continue
        key = ((site.col - col) ** 2 + (site.row - row) ** 2, fac.id)
        if best_key is None or key < best_key:
            best_key, best = key, fac
    return best


def _spawn_seeker(world: World, realm: Faction, r: random.Random) -> Optional[Character]:
    """Generate a grown notable of ``realm`` at its seat — the seeker who will ride.

    Its race copies the realm's living leader (else the folk-to-race fallback), its
    name is culture-authentic and disambiguated against the realm's living members,
    and its every stochastic detail is drawn from the isolated ``r`` so no shared
    history shifts. Returns ``None`` only if the realm has no seat to stand it on.
    """
    if realm.capital_location_id is None:
        return None
    leader = world.entities.get(realm.leader_id) if realm.leader_id is not None else None
    if isinstance(leader, Character):
        race = Race(leader.race)
    else:
        race = _PEOPLE_RACE.get(realm.people, Race.MAN)
    sex = "M" if r.randrange(2) == 0 else "F"
    name = generate_name(
        realm.naming_culture, sex, r.getrandbits(32), living_faction_names(world, realm.id)
    )
    birth_year = world.current_year - (20 + r.randrange(40))  # a grown adult
    return add_character(
        world,
        name=name,
        race=race,
        birth_year=birth_year,
        sex=sex,
        role=Role.NONE,
        location_id=realm.capital_location_id,
        faction_id=realm.id,
    )


def _home_seat(world: World, char: Character) -> Optional[int]:
    """The seat of the character's own realm (where a homecoming seeker heads)."""
    faction = world.entities.get(char.faction_id) if char.faction_id is not None else None
    return getattr(faction, "capital_location_id", None) if faction is not None else None
