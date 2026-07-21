"""Sauron's rise & canonical pressure — tick phase 7 (issue #5).

The rising Shadow that bends the era toward the books without ever scripting it.
Three things live here:

* **``sauron_strength``** — recomputed each phase 7 as
  ``canon_baseline(year) × canonicity + Σ emergent_deltas`` and cached on the
  dark realm's Faction record (zero on every other faction). The baseline
  encodes the canon ramp (arming since 2951, the climb toward the War-of-the-Ring
  window, Orodruin active ~3007); at ``canonicity = 0`` it flattens to the purely
  emergent deltas. The Ring's stirring and dark possession spike it; defeats and
  the loss of Dol Guldur or Minas Morgul check it. The value is consumed by the
  **next** tick's phases 2–4 (the spec's deliberate one-tick lag): it scales
  Mordor's musters (:func:`arda_sim.armies.muster_size`), provider commitment,
  Nazgûl activation (the phase-2 hunt intent), and the ``pull``-decay weighting
  (:mod:`arda_sim.ring`).

* **The nine Nazgûl** — named wraith Characters seeded to the dark realm
  (Witch-king and five at Minas Morgul, Khamûl and two at Dol Guldur), immortal
  while Sauron and the Ring endure, unmade with the Ring's destruction. They hunt
  through the normal phase flow: a phase-2 ``hunt_ring`` intent when strength and
  ``pull`` are both high, movement here as a :class:`Hunt` record with a search
  budget (phase 4½, after armies march), and a capture attempt resolved by the
  Ring phase — this module reads the Ring's ``pull`` and location but **never
  mutates the Ring record** (single-writer discipline, ADR-0008). Between hunts
  the wraiths are elite generals the ordinary muster ladder drafts.

* **Canon pressure** — the single global canonicity knob applied as *soft
  weighting only* to four forces: Sauron's rise (the baseline term), the Ring's
  stirring (ring.py's canonicity-weighted rolls), Free-Peoples alliance formation
  (diplomacy's pact odds), and character role-seeking (:func:`_role_seeking`
  here). It never fires an event directly and never touches a battle's dice.

Determinism: like the Ring, every stochastic choice here draws from a **derived
per-tick RNG** (``seed_str|sauron|tick``), never the pipeline's shared stream, so
this phase perturbs no other system's draws. All arithmetic is integer.
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
    characters,
    children_of,
    compute_prominence,
    RACE_CONFIG,
)
from .entities import Entity, EntityStatus, Event, register_entity_type
from .factions import Faction, Intent, compute_military_strength, factions
from .ring import RING_DESTROYED_FLAG, Ring, the_ring
from .rng import make_rng
from .tiles import UNOWNED
from .war import BATTLE_EVENT, CONQUEST_EVENT, extinguish_realm, owned_region_ids
from .world import World

# Event types this phase emits.
SAURON_RISE_EVENT = "sauron_grows"  # the Shadow's strength crossed a band
NAZGUL_HUNT_EVENT = "nazgul_hunt"  # the Nine rode out (or turned back)
ROLE_TAKEN_EVENT = "role_taken"  # a character took up a canon-shaped role

# -- the canon baseline (integer, permille-safe) ---------------------------
#
# Ascending (year, strength) breakpoints, linearly interpolated: the authored
# canon ramp. Sauron declared himself and began arming in 2951; the climb
# steepens toward Orodruin's awakening (~3007) and the War-of-the-Ring window.
_BASELINE: tuple = (
    (2900, 8),
    (2951, 25),
    (2980, 45),
    (3000, 60),
    (3007, 80),
    (3018, 100),
)

_STRENGTH_CAP = 150  # sauron_strength ceiling (baseline + every spike)
_DELTA_CAP = 60  # the emergent accumulator is bounded both ways
_BAND = 20  # strength band whose crossing is worth an annal entry

# Emergent delta contributions (integer, applied by the phase-7 event scan).
_DELTA_BATTLE_WON = 3
_DELTA_BATTLE_LOST = -6
_DELTA_CONQUEST_MADE = 10
_DELTA_CONQUERED = -40

# Stateless checks & spurs read off current state each recomputation.
_PULL_SPUR_DIV = 4  # +pull//4 while the Ring stirs
_RING_HELD_SPUR = 40  # the Ring in dark hands (a wraith bearing it home)
_VASSAL_LOST_CHECK = -20  # Dol Guldur fallen
_MORGUL_LOST_CHECK = -20  # Minas Morgul's ground no longer the dark realm's

# Provider commitment climbs toward the Shadow's strength (a canon-pressure
# consumption of the phase-7 scalar; diplomacy's pacts still deepen it too —
# named distinctly from diplomacy's _PROVIDER_STEP, which is the per-pact jump).
_COMMIT_CLIMB_STEP = 2  # per year, while below target
_COMMIT_MAX = 100

# Role-seeking (the fourth canon-pressure force): once a year each ruler's
# eldest unroled adult child may take up the heirship, canonicity-weighted.
_ROLE_SEEK_BP = 350  # of 1000, scaled by canonicity

# The hunt.
_HUNT_BUDGET_TICKS = 60  # five years in the saddle before the Nine turn back
_HUNT_PACE = 260  # miles/year — the Nine ride faster than any host marches
_SCENT_MIN = 10  # below this pull the quarry has gone quiet and the hunt ends

_ANCIENT = -3000  # birth year for beings older than reliable dating


@dataclass
class Hunt(Entity):
    """The Nine on the road: one hunting party's position, path, and patience.

    A transient mover (kind ``"hunt"``) like an Army: tile position, a path
    re-plotted as the quarry moves, an integer effort budget, and the wraith
    characters riding with it. It only ever *moves*; the seizure itself is rolled
    by the Ring phase (single-writer). Tombstoned (status ``dead``) when it ends.
    """

    wraith_ids: List[int] = field(default_factory=list)
    col: int = 0
    row: int = 0
    goal: List[int] = field(default_factory=list)  # the tile last plotted toward
    path: List[List[int]] = field(default_factory=list)
    move_points: int = 0
    miles_per_year: int = _HUNT_PACE
    search_budget: int = _HUNT_BUDGET_TICKS

    @property
    def alive(self) -> bool:
        return self.status == EntityStatus.ACTIVE.value


register_entity_type("hunt", Hunt)


# =========================================================================
# Queries
# =========================================================================

def dark_realm(world: World) -> Optional[Faction]:
    """The realm of the Shadow — the faction the Nazgûl serve.

    Resolved through the wraiths' own faction bond (stable even after leadership
    changes), falling back to the realm whose leader bears the Dark Lord's title.
    ``None`` in a run seeded without the Shadow (headless/skeleton).
    """
    for char in characters(world):
        if char.race == Race.WRAITH.value and char.faction_id is not None:
            entity = world.entities.get(char.faction_id)
            if isinstance(entity, Faction):
                return entity
    return _realm_of_the_dark_lord(world)


def nazgul(world: World, *, alive_only: bool = False) -> List[Character]:
    """The nine wraiths in id order (optionally only those not yet unmade)."""
    return [
        c
        for c in characters(world, alive_only=alive_only)
        if c.race == Race.WRAITH.value
    ]


def hunts(world: World, *, alive_only: bool = False) -> List[Hunt]:
    """All Hunt records in id order (optionally only the one still riding)."""
    result = [e for _id, e in sorted(world.entities.items()) if isinstance(e, Hunt)]
    return [h for h in result if h.alive] if alive_only else result


def canon_baseline(year: int) -> int:
    """The authored canon strength for a year — the ramp emergence bends around.

    Piecewise-linear over :data:`_BASELINE`, clamped flat at both ends. Pure and
    integer, so the phase-7 formula never touches a float.
    """
    if year <= _BASELINE[0][0]:
        return _BASELINE[0][1]
    for (y0, v0), (y1, v1) in zip(_BASELINE, _BASELINE[1:]):
        if year <= y1:
            return v0 + (v1 - v0) * (year - y0) // (y1 - y0)
    return _BASELINE[-1][1]


def compute_sauron_strength(world: World, realm: Faction) -> int:
    """The phase-7 formula: ``canon_baseline(year) × canonicity + Σ deltas``.

    The Σ is the realm's bounded emergent accumulator plus the stateless checks
    and spurs read off current state: the Ring's stirring (+pull slice), the Ring
    in dark hands, a fallen dark vassal (Dol Guldur), and Minas Morgul's ground
    lost. Pure given the world — recomputable, testable, integer.
    """
    canon_pm = int(max(0.0, min(1.0, world.config.canonicity)) * 1000)
    base = canon_baseline(world.current_year) * canon_pm // 1000
    delta = realm.sauron_delta

    ring = the_ring(world)
    if isinstance(ring, Ring) and ring.status == EntityStatus.ACTIVE.value:
        delta += ring.pull // _PULL_SPUR_DIV
        if ring.bearer_id is not None:
            bearer = world.entities.get(ring.bearer_id)
            if getattr(bearer, "faction_id", None) == realm.id:
                delta += _RING_HELD_SPUR

    for vassal in factions(world):
        if vassal.overlord_faction_id == realm.id and not vassal.alive:
            delta += _VASSAL_LOST_CHECK
            break  # one check, however many banners fell

    if _morgul_lost(world, realm):
        delta += _MORGUL_LOST_CHECK

    return max(0, min(_STRENGTH_CAP, base + delta))


# The flag marking that the dark realm has at some point held Minas Morgul's
# ground — a *loss* requires a prior holding (the seed paints Ithilien Gondor's,
# so the check only bites once the Shadow has taken and then lost the vale).
MORGUL_HELD_FLAG = "morgul_held"


def _track_morgul(world: World, realm: Faction) -> None:
    """Record (once) that the dark realm holds Minas Morgul's ground."""
    if world.flags.get(MORGUL_HELD_FLAG):
        return
    if _morgul_owner(world) == realm.id:
        world.flags[MORGUL_HELD_FLAG] = True


def _morgul_lost(world: World, realm: Faction) -> bool:
    """Whether Minas Morgul, once the dark realm's, is now held against it."""
    if not world.flags.get(MORGUL_HELD_FLAG):
        return False
    owner = _morgul_owner(world)
    return owner is not None and owner != UNOWNED and owner != realm.id


def _morgul_owner(world: World) -> Optional[int]:
    """The faction owning Minas Morgul's tile, ``UNOWNED``, or ``None`` off-map."""
    grid = world.grid
    if grid is None:
        return None
    site_id = grid.site_id_of("Minas Morgul")
    site = grid.site_by_id(site_id) if site_id is not None else None
    if site is None:
        return None
    return grid.owner_at(site.col, site.row)


# =========================================================================
# Seeding — the Nine
# =========================================================================

# (name, home site, title, traits) for the nine. The Witch-king and five ride
# from Minas Morgul; Khamûl and two hold Dol Guldur (the spec's placement).
_NAZGUL_SEEDS: tuple = (
    ("The Witch-king of Angmar", "Minas Morgul", "Lord of the Nazgûl",
     {"martial": 95, "leadership": 90, "guile": 85, "ambition": 80}),
    ("Khamûl the Easterling", "Dol Guldur", "Shadow of the East",
     {"martial": 85, "leadership": 75, "guile": 80}),
    ("The Third of the Nine", "Dol Guldur", None, {"martial": 78, "leadership": 68}),
    ("The Fourth of the Nine", "Dol Guldur", None, {"martial": 78, "leadership": 68}),
    ("The Fifth of the Nine", "Minas Morgul", None, {"martial": 76, "leadership": 66}),
    ("The Sixth of the Nine", "Minas Morgul", None, {"martial": 76, "leadership": 66}),
    ("The Seventh of the Nine", "Minas Morgul", None, {"martial": 74, "leadership": 64}),
    ("The Eighth of the Nine", "Minas Morgul", None, {"martial": 74, "leadership": 64}),
    ("The Ninth of the Nine", "Minas Morgul", None, {"martial": 72, "leadership": 62}),
)


def seed_nazgul(world: World) -> List[Character]:
    """Seed the nine Nazgûl as named wraith Characters of the dark realm.

    Called by :func:`arda_sim.factions.seed_world` once factions and the grid
    exist (home sites resolve through ``world.grid``). Wraiths are seeded as
    generals — the ordinary muster ladder then drafts them to lead hosts between
    hunts. Emits no events (the Nine predate play, like the rosters).
    """
    realm = _realm_of_the_dark_lord(world)
    grid = world.grid
    wraiths: List[Character] = []
    for name, home, title, traits in _NAZGUL_SEEDS:
        location_id = grid.site_id_of(home) if grid is not None else None
        wraiths.append(
            add_character(
                world,
                name=name,
                race=Race.WRAITH,
                birth_year=_ANCIENT,
                sex="M",
                role=Role.GENERAL,
                location_id=location_id,
                faction_id=realm.id if realm is not None else None,
                title=title,
                traits=traits,
            )
        )
    return wraiths


def _realm_of_the_dark_lord(world: World) -> Optional[Faction]:
    """The faction whose seeded leader bears the Dark Lord's title (Mordor)."""
    for faction in factions(world):
        leader = world.entities.get(faction.leader_id) if faction.leader_id else None
        if isinstance(leader, Character) and leader.title == DARK_LORD_TITLE:
            return faction
    return None


# =========================================================================
# Phase 4½ — the hunt rides (movement only; the Ring phase resolves capture)
# =========================================================================

def nazgul_hunt(world: World, rng: random.Random) -> List[Event]:
    """Advance any riding hunt toward the Ring, and loose a new one on the
    phase-2 ``hunt_ring`` intent.

    Runs after armies march (the spec's phase-4 seam) and before war, drawing no
    RNG at all — pathing and stepping are the same pure helpers hosts use — so
    the shared stream is untouched. The hunt tracks the Ring's *tile* (reading
    ``pull`` and location only, never writing the record); the capture attempt is
    the Ring phase's, after war has resolved the field.
    """
    grid = world.grid
    if grid is None:
        return []
    events: List[Event] = []
    ring = the_ring(world)
    realm = dark_realm(world)

    for hunt in hunts(world, alive_only=True):
        events.extend(_advance_hunt(world, hunt, ring, realm))

    if _should_ride(world, realm, ring):
        events.extend(_begin_hunt(world, realm))
    return events


def _should_ride(
    world: World, realm: Optional[Faction], ring: Optional[Ring]
) -> bool:
    """Whether a fresh hunt rides out: the dark realm chose the hunt this phase 2,
    the Ring is in play, and no hunt is already on the road."""
    if realm is None or not realm.alive:
        return False
    if realm.current_intent.get("intent") != Intent.HUNT.value:
        return False
    if ring is None or ring.status != EntityStatus.ACTIVE.value:
        return False
    return not hunts(world, alive_only=True)


def _begin_hunt(world: World, realm: Faction) -> List[Event]:
    """Gather the available wraiths and set them riding from their seat."""
    grid = world.grid
    riders = [w for w in nazgul(world, alive_only=True) if w.faction_id == realm.id]
    if not riders:
        return []
    start = None
    lead = riders[0]
    if lead.location_id is not None and grid is not None:
        site = grid.site_by_id(lead.location_id)
        if site is not None:
            start = (site.col, site.row)
    if start is None:
        return []  # nowhere to ride from
    hunt = Hunt(
        id=world.next_id(),
        kind="hunt",
        name="The Hunt of the Nine",
        created_year=world.current_year,
        wraith_ids=[w.id for w in riders],
        col=start[0],
        row=start[1],
    )
    world.entities[hunt.id] = hunt
    return [
        world.new_event(
            type=NAZGUL_HUNT_EVENT,
            subject_ids=[hunt.id, realm.id, lead.id],
            location_id=lead.location_id,
            payload={"phase": "begun", "riders": len(riders)},
        )
    ]


def _advance_hunt(
    world: World, hunt: Hunt, ring: Optional[Ring], realm: Optional[Faction]
) -> List[Event]:
    """One tick of the chase: retarget on the quarry's tile, ride, spend patience."""
    grid = world.grid
    if ring is None or ring.status != EntityStatus.ACTIVE.value:
        return [_end_hunt(world, hunt, "quarry_gone")]
    if realm is not None and _ring_in_dark_hands(world, ring, realm):
        return [_end_hunt(world, hunt, "quarry_taken")]
    if ring.pull < _SCENT_MIN:
        return [_end_hunt(world, hunt, "lost_scent")]

    goal = [ring.col, ring.row]
    if hunt.goal != goal:
        hunt.goal = list(goal)
        hunt.path = find_path(grid, (hunt.col, hunt.row), (ring.col, ring.row))
    if hunt.path:
        hunt.col, hunt.row, hunt.path, hunt.move_points = step_along_path(
            grid, hunt.col, hunt.row, hunt.path, hunt.move_points, hunt.miles_per_year
        )
    hunt.search_budget -= 1
    on_quarry = hunt.col == ring.col and hunt.row == ring.row
    if hunt.search_budget <= 0 and not on_quarry:
        return [_end_hunt(world, hunt, "search_spent")]
    return []


def _ring_in_dark_hands(world: World, ring: Ring, realm: Faction) -> bool:
    """Whether the Ring's bearer already serves the dark realm (hunt fulfilled)."""
    if ring.bearer_id is None:
        return False
    bearer = world.entities.get(ring.bearer_id)
    return getattr(bearer, "faction_id", None) == realm.id


def _end_hunt(world: World, hunt: Hunt, reason: str) -> Event:
    """Call a hunt off: tombstone it and set its riders down where it stands."""
    hunt.status = EntityStatus.DEAD.value
    grid = world.grid
    site = grid.site_at(hunt.col, hunt.row) if grid is not None else None
    if site is not None:
        for wid in hunt.wraith_ids:
            wraith = world.entities.get(wid)
            if isinstance(wraith, Character) and wraith.alive:
                wraith.location_id = site.id
    return world.new_event(
        type=NAZGUL_HUNT_EVENT,
        subject_ids=[hunt.id] + list(hunt.wraith_ids[:1]),
        location_id=site.id if site is not None else None,
        payload={"phase": "ended", "reason": reason},
    )


# =========================================================================
# Phase 7 — the rise (and, after the Fire, the fall)
# =========================================================================

def sauron_rise(world: World, rng: random.Random) -> List[Event]:
    """Phase 7: recompute ``sauron_strength`` and apply the canon pressure.

    Never musters, moves, or fights (the phase-flow contract): it writes the
    scalars the *next* tick's phases 2–4 consume. Draws only from its own derived
    per-tick RNG, so the shared stream is untouched whatever canonicity is. With
    the Ring destroyed it instead drives the Shadow's collapse, tick by tick,
    down to the ordinary extinction seam.
    """
    realm = dark_realm(world)
    if realm is None:
        return []
    if world.flags.get(RING_DESTROYED_FLAG):
        return _collapse(world, realm)
    if not realm.alive:
        return []

    events: List[Event] = []
    _update_delta(world, realm)
    _track_morgul(world, realm)
    previous = realm.sauron_strength
    realm.sauron_strength = compute_sauron_strength(world, realm)
    if realm.sauron_strength // _BAND != previous // _BAND:
        events.append(
            world.new_event(
                type=SAURON_RISE_EVENT,
                subject_ids=[realm.id],
                location_id=realm.capital_location_id,
                payload={"strength": realm.sauron_strength, "previous": previous},
            )
        )
    _scale_providers(world, realm)
    events.extend(_role_seeking(world))
    return events


def _update_delta(world: World, realm: Faction) -> None:
    """Fold this tick's (and any unseen) war fortunes into the emergent accumulator.

    Scans the append-only event log past the realm's watermark — each battle or
    conquest counts exactly once, however the tick unfolded — then decays the
    accumulator one step toward zero at each year boundary and clamps it.
    """
    delta = realm.sauron_delta
    fresh: List[Event] = []
    for ev in reversed(world.events):
        if ev.id <= realm.sauron_events_seen:
            break
        fresh.append(ev)
    for ev in reversed(fresh):  # chronological
        payload = ev.payload or {}
        if ev.type == BATTLE_EVENT:
            if payload.get("winner_faction_id") == realm.id:
                delta += _DELTA_BATTLE_WON
            elif payload.get("loser_faction_id") == realm.id:
                delta += _DELTA_BATTLE_LOST
        elif ev.type == CONQUEST_EVENT:
            if payload.get("conqueror_faction_id") == realm.id:
                delta += _DELTA_CONQUEST_MADE
            elif ev.subject_ids and ev.subject_ids[0] == realm.id:
                delta += _DELTA_CONQUERED
    realm.sauron_events_seen = world.id_counter - 1
    if world.month == 1 and delta != 0:  # old fortunes fade
        delta += 1 if delta < 0 else -1
    realm.sauron_delta = max(-_DELTA_CAP, min(_DELTA_CAP, delta))


def _scale_providers(world: World, realm: Faction) -> None:
    """Once a year, draw the dark realm's gateway peoples toward its strength.

    Commitment climbs (never falls — diplomacy and collapse own the falls) toward
    a target equal to the Shadow's strength, a few points a year. The issue's
    "strength scales provider commitment", deterministic and integer.
    """
    if world.month != 1:
        return
    target = min(_COMMIT_MAX, realm.sauron_strength)
    for provider in factions(world, alive_only=True):
        if not provider.is_provider or provider.allegiance_faction_id != realm.id:
            continue
        if provider.commitment < target:
            provider.commitment = min(target, provider.commitment + _COMMIT_CLIMB_STEP)


def _role_seeking(world: World) -> List[Event]:
    """The fourth canon-pressure force: characters drift toward canon-shaped roles.

    Once a year, each living ruler's eldest unroled adult child may take up the
    heirship on a canonicity-weighted roll (so lines stay tidy in a canon-leaning
    world and fray in a chaotic one). Draws from this phase's derived RNG only.
    """
    if world.month != 1:
        return []
    canon_pm = int(max(0.0, min(1.0, world.config.canonicity)) * 1000)
    bp = _ROLE_SEEK_BP * canon_pm // 1000
    if bp <= 0:
        return []
    r = make_rng(f"{world.config.seed_str}|sauron|{world.tick}")
    events: List[Event] = []
    for faction in factions(world, alive_only=True):
        leader = world.entities.get(faction.leader_id) if faction.leader_id else None
        if not isinstance(leader, Character) or not leader.alive:
            continue
        candidate = _eldest_unroled_child(world, leader)
        if candidate is None:
            continue
        if r.randrange(1000) >= bp:
            continue
        candidate.role = Role.HEIR.value
        candidate.prominence = compute_prominence(candidate)
        events.append(
            world.new_event(
                type=ROLE_TAKEN_EVENT,
                subject_ids=[candidate.id, faction.id],
                location_id=candidate.location_id,
                payload={"role": candidate.role, "faction_id": faction.id},
            )
        )
    return events


def _eldest_unroled_child(world: World, leader: Character) -> Optional[Character]:
    """The leader's eldest living, mature child still without any role."""
    year = world.current_year
    pool = [
        c
        for c in children_of(world, leader.id)
        if c.alive
        and c.role == Role.NONE.value
        and c.age(year) >= RACE_CONFIG[Race(c.race)].maturity_age
    ]
    pool.sort(key=lambda c: (c.birth_year, c.id))
    return pool[0] if pool else None


# =========================================================================
# The fall — Mordor's collapse once the Ring is destroyed
# =========================================================================

# Per-tick fraction of the dark realm's remaining tiles that crumble to
# wilderness (at least one), so the realm is gone within a couple of years.
_COLLAPSE_SHED_DIV = 10
_COLLAPSE_PROVIDER_STEP = 10  # yearly desertion of the gateway peoples


def _collapse(world: World, realm: Faction) -> List[Event]:
    """The aftermath of destruction: the Shadow's works unravel tick by tick.

    Strength zeroes, the gateway peoples desert, and the dark realm's ground
    crumbles to wilderness a slice a tick until nothing is left — at which point
    the ordinary extinction seam tombstones it (peace made, hosts disbanded,
    dormant claim kept), exactly as a conquered realm leaves play.
    """
    events: List[Event] = []
    realm.sauron_strength = 0
    realm.sauron_delta = 0
    if world.month == 1:
        for provider in factions(world, alive_only=True):
            if provider.is_provider and provider.allegiance_faction_id == realm.id:
                provider.commitment = max(0, provider.commitment - _COLLAPSE_PROVIDER_STEP)
    grid = world.grid
    if grid is None or not realm.alive:
        return events

    region_ids = owned_region_ids(grid, realm.id)
    owned = [i for i, owner in enumerate(grid.owner) if owner == realm.id]
    if not owned:
        events.extend(extinguish_realm(world, realm, region_ids))
        return events
    shed = max(1, len(owned) // _COLLAPSE_SHED_DIV)
    for idx in owned[:shed]:
        grid.set_owner(idx % grid.width, idx // grid.width, UNOWNED)
    remaining = len(owned) - shed
    leader = world.entities.get(realm.leader_id) if realm.leader_id else None
    realm.military_strength = compute_military_strength(realm, remaining, leader)
    if remaining <= 0:
        events.extend(extinguish_realm(world, realm, region_ids))
    return events
