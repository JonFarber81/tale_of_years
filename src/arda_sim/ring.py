"""The One Ring — the gravitational centre (build ticket 13).

The Ring is a *single bespoke record* (:class:`Ring`), not one of a kind: there is
exactly one in a run, seeded quietly borne by Bilbo at the Shire's seat. It is
always somewhere definite — the **XOR invariant**: exactly one of ``bearer_id``
(a character carries it) and ``location_id`` (it lies at a site) is set, never
both and never neither. Everything the viewer needs to find it and read its
journey hangs off that record and the event log.

It changes hands by a small, closed set of **transfer modes**
(:class:`RingTransfer`) — inheritance, gift, theft, loss/drop, being found,
capture in war, or a deliberate errand toward a goal — each a canonicity-weighted
seeded roll fired from the phase that owns it. It carries two integer scalars:
``corruption`` (per-bearer, trait-modulated, grows while borne and **attenuates —
never resets** on transfer) and ``pull`` (global, spikes on use and decays). Low
corruption prolongs its bearer; high corruption may move them to *claim* it — a
transient high-corruption event here (terminal fates — Sauron reclaiming, a bearer
unmade into a wraith — are ticket 14's, deliberately stubbed).

Determinism: like every system this is reproducible from persisted state, but the
Ring draws from its **own per-tick RNG derived from ``(seed_str, tick)``** rather
than the pipeline's shared stream (see ADR-0008), so its stochastic life neither
perturbs nor is perturbed by how many armies happened to march that tick. The
record holds only JSON-clean primitives and round-trips bit-identically.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .armies import find_path, tick_speed
from .characters import Character, Role, ancestors, characters, children_of
from .entities import Entity, Event, register_entity_type
from .rng import make_rng
from .tiles import TileGrid
from .world import World

# Event types this phase emits.
RING_MOVED_EVENT = "ring_moved"  # the Ring advanced a tick along an errand
RING_TRANSFERRED_EVENT = "ring_transferred"  # it changed hands / was dropped / found
RING_CLAIMED_EVENT = "ring_claimed"  # a bearer, deep in corruption, claimed it (transient)


class RingTransfer(str, Enum):
    """How the Ring passed from one state of possession to the next.

    A closed set — the Ring never changes hands by any means outside it. Each is a
    canonicity-weighted seeded roll fired from the phase that owns that kind of
    event (inheritance answers a bearer's death, war-capture reads the field, …).
    """

    INHERITANCE = "inheritance"  # a dead bearer's heir takes it up (kinship-biased)
    GIFT = "gift"  # a bearer freely hands it on
    THEFT = "theft"  # taken by stealth from a living bearer
    LOSS = "loss"  # slips from a bearer and lies where it fell (→ unborne)
    FOUND = "found"  # picked up from where it lay (unborne → borne)
    WAR_CAPTURE = "war_capture"  # seized by a host that holds the ground it lay on
    ERRAND = "errand"  # sent deliberately toward a goal (movement, not a handover)

    def __str__(self) -> str:
        return self.value


# -- tuning (all integer) --------------------------------------------------

_SEED_CORRUPTION = 5  # the quiet Ring at seed — low, per the ticket
_SEED_PULL = 0

CORRUPTION_MAX = 100
_PULL_MAX = 100

# Corruption growth per borne tick: a base, pushed up by a grasping bearer
# (ambition+guile) and resisted by a steadfast one (wisdom+loyalty), floored at 1
# so it always creeps. Trait-modulated, integer-only.
_CORRUPT_BASE = 2
_CORRUPT_RESIST_DIV = 25

# On any transfer the taint attenuates to this percent of its value — it lingers
# on the Ring (marking that it has been borne hard) rather than resetting to nil.
_ATTENUATE_PCT = 60

# Pull: using the Ring spikes it; otherwise it ebbs each tick.
_PULL_USE_SPIKE = 18
_PULL_DECAY = 3

# Corruption bands (the ticket's low/mid/high behaviour).
_SECRECY_CORRUPTION = 35  # mid: the bearer hides, wanting neither to use nor lose it
_CLAIM_CORRUPTION = 80  # high: the bearer may claim it outright (transient here)

# Longevity: a borne Ring suppresses its bearer's natural death, strongest while
# corruption is low (it preserves), fading as corruption climbs. Returned as a
# permille multiplier on the annual death chance (1000 = no effect).
_LONGEVITY_FLOOR = 200  # ×0.20 death odds at zero corruption

# Loss / theft base odds (per borne tick, out of 1000), lifted by pull — a Ring
# that has been *used* is far likelier to slip away or be taken.
_LOSS_BASE_BP = 3
_THEFT_BASE_BP = 2
_PULL_RISK_SLOPE = 1  # extra bp of loss/theft per point of pull (pull caps at 100)

# A claim, once corruption is high enough, is itself a bounded roll each tick.
_CLAIM_BP = 40

_DEFAULT_MILES_PER_YEAR = 200  # the Ring travels at a walking-company's pace


@dataclass
class Ring(Entity):
    """The One Ring: a single tracked object with a definite place at all times.

    The **XOR invariant** binds ``bearer_id`` and ``location_id`` — exactly one is
    non-null. ``col``/``row`` is the Ring's tile for rendering and errand movement
    (kept in step with the bearer's seat while borne, frozen where it lies when
    not). ``corruption`` is the per-bearer taint; ``pull`` the global draw.
    ``goal_site_id``/``path``/``move_points`` drive a deliberate errand.
    ``bearer_history`` is the ordered roll of everyone who has borne it — the mark
    it leaves on former bearers, and the inspection journey.
    """

    bearer_id: Optional[int] = None
    location_id: Optional[int] = None
    col: int = 0
    row: int = 0
    corruption: int = _SEED_CORRUPTION
    pull: int = _SEED_PULL
    goal_site_id: Optional[int] = None
    path: List[List[int]] = field(default_factory=list)
    move_points: int = 0
    miles_per_year: int = _DEFAULT_MILES_PER_YEAR
    bearer_history: List[int] = field(default_factory=list)

    @property
    def borne(self) -> bool:
        """Whether the Ring is currently carried (vs. lying at a place)."""
        return self.bearer_id is not None

    @property
    def xor_ok(self) -> bool:
        """The core invariant: exactly one of bearer / location is set."""
        return (self.bearer_id is None) != (self.location_id is None)

    @property
    def on_errand(self) -> bool:
        return bool(self.path)


register_entity_type("ring", Ring)


# -- queries ---------------------------------------------------------------

def the_ring(world: World) -> Optional[Ring]:
    """The One Ring, or ``None`` in a run that never seeded it (headless/skeleton)."""
    for _id, entity in sorted(world.entities.items()):
        if isinstance(entity, Ring):
            return entity
    return None


def ring_timeline(world: World, ring_id: int) -> List[Event]:
    """Every event naming the Ring, oldest first — the inspection journey."""
    return sorted(
        (ev for ev in world.events if ring_id in ev.subject_ids),
        key=lambda ev: (ev.year, ev.id),
    )


def ring_longevity_factor(corruption: int) -> int:
    """Permille multiplier on a bearer's annual death chance (1000 = no effect).

    Strongest suppression at zero corruption (the Ring preserves its bearer),
    easing linearly back to no effect as corruption approaches the cap — so a
    long-untainted bearer is markedly prolonged, a deeply corrupted one no longer.
    Pure and integer; consumed by the phase-1 death roll without changing its draw
    count, so it never perturbs the shared RNG stream.
    """
    corruption = max(0, min(CORRUPTION_MAX, corruption))
    span = 1000 - _LONGEVITY_FLOOR
    return _LONGEVITY_FLOOR + span * corruption // CORRUPTION_MAX


# -- seeding ---------------------------------------------------------------

def seed_ring(world: World, grid: Optional[TileGrid] = None) -> Ring:
    """Seed the One Ring borne by the roster's Ring-bearer (Bilbo), low and quiet.

    The bearer is found by the canon ``RING_BEARER`` role, so it tracks the roster
    rather than a hard-coded name. Its tile is the bearer's seat (resolved through
    the grid when one is attached); with no grid it sits at ``(0, 0)`` until a map
    is present. Emits no event — the Ring predates play, like the rosters.
    """
    bearer = _seed_bearer(world)
    ring = Ring(
        id=world.next_id(),
        kind="ring",
        name="The One Ring",
        created_year=world.current_year,
        bearer_id=bearer.id if bearer is not None else None,
        location_id=None,
        corruption=_SEED_CORRUPTION,
        pull=_SEED_PULL,
        bearer_history=[bearer.id] if bearer is not None else [],
    )
    if bearer is not None:
        bearer.role = Role.RING_BEARER.value
        if grid is not None:
            _place_on_bearer_tile(ring, grid, bearer)
    else:
        # No bearer to hold it: lay it at the map's first site so the XOR holds.
        ring.location_id = grid.sites[0].id if grid and grid.sites else 0
        if grid and grid.sites:
            ring.col, ring.row = grid.sites[0].col, grid.sites[0].row
    world.entities[ring.id] = ring
    return ring


def _seed_bearer(world: World) -> Optional[Character]:
    """The roster's Ring-bearer at seed: the first living character so roled."""
    for char in characters(world, alive_only=True):
        if char.role == Role.RING_BEARER.value:
            return char
    return None


# -- the phase -------------------------------------------------------------

def ring_system(world: World, rng: random.Random) -> List[Event]:
    """The Ring phase: advance the Ring's own life for this tick.

    Runs after war (phase 5) so it can answer a bearer felled this tick — by
    lifecycle (phase 1) or violence (phase 5) — and read who now holds the ground
    a fallen Ring lies on. Draws from a per-tick RNG *derived from the run seed*,
    never the shared ``rng``, so it perturbs nothing else (ADR-0008). A pure no-op
    on a run with no Ring (headless/skeleton).
    """
    ring = the_ring(world)
    if ring is None:
        return []
    r = _tick_rng(world)
    events: List[Event] = []
    if ring.borne:
        bearer = world.entities.get(ring.bearer_id)
        if not isinstance(bearer, Character) or not bearer.alive:
            events.extend(_on_bearer_fallen(world, ring, r))
        else:
            events.extend(_borne_tick(world, ring, bearer, r))
    else:
        events.extend(_unborne_tick(world, ring, r))
    _decay_pull(ring)
    return events


def _tick_rng(world: World) -> random.Random:
    """The Ring's own reproducible RNG for this tick, off the run seed + clock."""
    return make_rng(f"{world.config.seed_str}|ring|{world.tick}")


# -- borne life ------------------------------------------------------------

def _borne_tick(
    world: World, ring: Ring, bearer: Character, r: random.Random
) -> List[Event]:
    """A tick with a living bearer: creep corruption, advance any errand, and roll
    the disturbances a carried Ring invites (claim, loss, theft)."""
    events: List[Event] = []
    _track_bearer_tile(world, ring, bearer)
    _grow_corruption(ring, bearer)
    events.extend(_advance_errand(world, ring, bearer))
    events.extend(_maybe_claim(world, ring, bearer, r))
    events.extend(_maybe_slip_away(world, ring, bearer, r))
    return events


def _grow_corruption(ring: Ring, bearer: Character) -> None:
    """Creep the per-bearer taint up by a trait-modulated, floored integer step."""
    ring.corruption = min(CORRUPTION_MAX, ring.corruption + corruption_growth(bearer))


def corruption_growth(bearer: Character) -> int:
    """Per-tick corruption increment for a bearer: a base lifted by a grasping
    temper (ambition+guile) and resisted by a steadfast one (wisdom+loyalty)."""
    traits = bearer.traits
    grasp = int(traits.get("ambition", 50)) + int(traits.get("guile", 50))
    resist = int(traits.get("wisdom", 50)) + int(traits.get("loyalty", 50))
    return max(1, _CORRUPT_BASE + (grasp - resist) // _CORRUPT_RESIST_DIV)


def _maybe_claim(
    world: World, ring: Ring, bearer: Character, r: random.Random
) -> List[Event]:
    """Deep in corruption, a bearer may *claim* the Ring — a transient event here.

    A non-Sauron claim is a high-corruption flare, not a resolution: pull spikes
    and the annals mark it, but the bearer holds on. Terminal fates (a claimant
    unmade, Sauron drawn to reclaim) are ticket 14's — left for #5 to complete.
    """
    if ring.corruption < _CLAIM_CORRUPTION:
        return []
    if r.randrange(1000) >= _CLAIM_BP:
        return []
    use_ring(ring)  # a claim is the loudest use of all
    return [
        world.new_event(
            type=RING_CLAIMED_EVENT,
            subject_ids=[ring.id, bearer.id],
            location_id=_bearer_site(world, bearer),
            payload={
                "bearer_id": bearer.id,
                "corruption": ring.corruption,
                "pull": ring.pull,
                # A marker for ticket 14: whether this claimant is the Dark Lord.
                "terminal": False,
            },
        )
    ]


def _maybe_slip_away(
    world: World, ring: Ring, bearer: Character, r: random.Random
) -> List[Event]:
    """Roll whether the Ring is lost or stolen this tick — odds lifted by pull.

    High pull raises loss/theft odds (the ticket's "danger it draws"), never
    autonomous movement. A mid-corruption bearer clutches it in secrecy, which
    dampens loss but not theft. One bounded roll decides at most one outcome.
    """
    risk = ring.pull * _PULL_RISK_SLOPE
    loss_bp = _LOSS_BASE_BP + risk
    if ring.corruption >= _SECRECY_CORRUPTION:
        loss_bp //= 2  # secrecy: held close, less apt to be simply dropped
    theft_bp = _THEFT_BASE_BP + risk
    roll = r.randrange(1000)
    if roll < loss_bp:
        return [_drop(world, ring, bearer)]
    if roll < loss_bp + theft_bp:
        thief = _nearest_taker(world, bearer)
        if thief is not None:
            return [transfer_ring(world, ring, to_bearer=thief, mode=RingTransfer.THEFT)]
    return []


# -- unborne life ----------------------------------------------------------

def _unborne_tick(world: World, ring: Ring, r: random.Random) -> List[Event]:
    """A tick with the Ring lying at a place: it never moves itself, but a host on
    the ground may seize it (war-capture), else a passer-by may find it."""
    events: List[Event] = []
    captor = _host_leader_on_tile(world, ring)
    if captor is not None:
        events.append(
            transfer_ring(world, ring, to_bearer=captor, mode=RingTransfer.WAR_CAPTURE)
        )
        return events
    finder = _finder_at_site(world, ring, r)
    if finder is not None:
        events.append(
            transfer_ring(world, ring, to_bearer=finder, mode=RingTransfer.FOUND)
        )
    return events


# -- inheritance on a fallen bearer ---------------------------------------

def _on_bearer_fallen(world: World, ring: Ring, r: random.Random) -> List[Event]:
    """The bearer died or departed: pass the Ring to an heir, or let it fall.

    Inheritance is kinship-biased and canonicity-weighted (:func:`inheritance_heir`)
    — the Bilbo→heir *tendency*, never a scripted hand-off. With no heir at all it
    drops where the bearer stood, to be found or captured later.
    """
    heir = inheritance_heir(world, ring, r)
    if heir is not None:
        return [transfer_ring(world, ring, to_bearer=heir, mode=RingTransfer.INHERITANCE)]
    fallen = world.entities.get(ring.bearer_id)
    site_id = _bearer_site(world, fallen) if isinstance(fallen, Character) else None
    return [_drop_to_site(world, ring, site_id)]


def inheritance_heir(
    world: World, ring: Ring, r: random.Random
) -> Optional[Character]:
    """Choose the next bearer when the current one falls, kinship-first.

    Candidates are ranked most-canon-first (the fallen bearer's nearest living
    kin, then collateral kin, then the bearer's own folk). Under high canonicity
    the canon heir is taken outright; as canonicity drops a weighted roll can hand
    it to a less-expected claimant — the divergence the ticket asks for.
    """
    fallen = world.entities.get(ring.bearer_id)
    if not isinstance(fallen, Character):
        return None
    pool = heir_candidates(world, fallen)
    if not pool:
        return None
    canonicity = world.config.canonicity
    if r.randrange(1000) < int(max(0.0, min(1.0, canonicity)) * 1000):
        return pool[0]  # the canon heir
    return pool[r.randrange(len(pool))]  # may diverge to another claimant


def heir_candidates(world: World, fallen: Character) -> List[Character]:
    """Living heir candidates for a fallen bearer, most-canon (nearest kin) first.

    Nearest living descendants, then collateral kin up the ancestral lines, then
    the bearer's remaining folk (same faction, else same race) — a deterministic
    order with an id tie-break, so the "canon heir" is well-defined and the pool
    is stable for a weighted low-canon roll.
    """
    ranked: List[Character] = []
    seen = {fallen.id}

    def _add(char: Optional[Character]) -> None:
        if isinstance(char, Character) and char.alive and char.id not in seen:
            seen.add(char.id)
            ranked.append(char)

    for child in sorted(children_of(world, fallen.id), key=_kin_key):
        _add(child)
    for forebear in ancestors(world, fallen.id):  # nearest first
        for kin in sorted(children_of(world, forebear.id), key=_kin_key):
            _add(kin)
    # Then the bearer's remaining folk (same faction, else same race), ranked
    # after all kin. Kin lead, so the canon heir is ``pool[0]``; the folk widen the
    # pool a low-canon roll can wander into, rather than being ignored outright.
    folk = [
        c
        for c in characters(world, alive_only=True)
        if c.id != fallen.id
        and (c.faction_id == fallen.faction_id if fallen.faction_id else c.race == fallen.race)
    ]
    for kin in sorted(folk, key=_kin_key):
        _add(kin)
    return ranked


def _kin_key(char: Character):
    """Seniority order among candidates: male-preferring, eldest, then id."""
    return (0 if char.sex == "M" else 1, char.birth_year, char.id)


# =========================================================================
# The transfer primitive — the one place the XOR invariant is enforced
# =========================================================================

def transfer_ring(
    world: World,
    ring: Ring,
    *,
    to_bearer: Optional[Character] = None,
    to_location: Optional[int] = None,
    mode: RingTransfer,
) -> Event:
    """Move the Ring to a new possession state, keeping the XOR invariant.

    Exactly one of ``to_bearer`` / ``to_location`` must be given. The taint
    **attenuates** (never resets), the former bearer is marked (kept in
    ``bearer_history`` and stripped of the Ring-bearer role), the new bearer is
    roled and the Ring re-placed on the map. Emits one ``ring_transferred`` event
    carrying the mode and both ends of the handover.
    """
    if (to_bearer is None) == (to_location is None):
        raise ValueError("transfer_ring needs exactly one of to_bearer / to_location")
    former_id = ring.bearer_id
    former = world.entities.get(former_id) if former_id is not None else None
    if isinstance(former, Character) and former.role == Role.RING_BEARER.value:
        former.role = Role.NONE.value  # a former bearer is marked by history, not role

    ring.corruption = ring.corruption * _ATTENUATE_PCT // 100  # attenuate, never reset
    ring.goal_site_id = None
    ring.path = []
    ring.move_points = 0

    subjects = [ring.id]
    payload: Dict[str, object] = {"mode": mode.value}
    if former_id is not None:
        payload["from_bearer_id"] = former_id
        subjects.append(former_id)
    location_id: Optional[int] = None
    if to_bearer is not None:
        ring.bearer_id = to_bearer.id
        ring.location_id = None
        to_bearer.role = Role.RING_BEARER.value
        if to_bearer.id not in ring.bearer_history:
            ring.bearer_history.append(to_bearer.id)
        _place_on_character(world, ring, to_bearer)
        payload["to_bearer_id"] = to_bearer.id
        subjects.append(to_bearer.id)
        location_id = _bearer_site(world, to_bearer)
    else:
        ring.bearer_id = None
        ring.location_id = to_location
        _place_on_site(world, ring, to_location)
        payload["to_location_id"] = to_location
        location_id = to_location
    return world.new_event(
        type=RING_TRANSFERRED_EVENT,
        subject_ids=subjects,
        location_id=location_id,
        payload=payload,
    )


def _drop(world: World, ring: Ring, bearer: Character) -> Event:
    """A bearer loses the Ring where they stand — it lies unborne at their seat."""
    return _drop_to_site(world, ring, _bearer_site(world, bearer))


def _drop_to_site(world: World, ring: Ring, site_id: Optional[int]) -> Event:
    """Lay the Ring down at a site (or, lacking one, where it already is)."""
    if site_id is None:
        # No site to fall at: pin it to its current tile as a placeless location.
        site = _site_at(world, ring.col, ring.row)
        site_id = site.id if site is not None else _ANY_SITE
    return transfer_ring(world, ring, to_location=site_id, mode=RingTransfer.LOSS)


_ANY_SITE = 0  # sentinel location id when the Ring falls off any known site


# =========================================================================
# Errand movement (phase-4-style passenger travel, run in the Ring phase)
# =========================================================================

def send_on_errand(world: World, ring: Ring, goal_site_id: int) -> bool:
    """Set the Ring on a deliberate errand toward a goal site (borne only).

    Plots a tile path from where it is to the goal and marks the errand; the
    per-tick advance then walks it on a miles/year budget. Unborne, it does not
    move (the ticket), so this is a no-op without a bearer or a grid.
    """
    grid = world.grid
    if grid is None or not ring.borne:
        return False
    dest = grid.site_by_id(goal_site_id)
    if dest is None:
        return False
    path = find_path(grid, (ring.col, ring.row), (dest.col, dest.row))
    ring.goal_site_id = goal_site_id
    ring.path = path
    ring.move_points = 0
    return True


def _advance_errand(world: World, ring: Ring, bearer: Character) -> List[Event]:
    """Walk the Ring one tick along an errand, emitting ``ring_moved`` when it steps.

    A passenger on the bearer's miles/year budget (the ticket's phase-4 seam),
    spending integer effort against tile costs. Using the Ring to travel *spikes
    pull* — the danger the errand draws. When it reaches the goal the bearer's seat
    moves with it. No errand, no grid → nothing happens.
    """
    grid = world.grid
    if grid is None or not ring.on_errand:
        return []
    start = (ring.col, ring.row)
    _step_along_path(world, ring)
    if (ring.col, ring.row) == start:
        return []  # not enough budget to clear the next tile this tick
    use_ring(ring)  # an active errand is a use — pull rises
    arrived = not ring.path
    site = _site_at(world, ring.col, ring.row)
    if arrived:
        ring.goal_site_id = None
        if site is not None:
            bearer.location_id = site.id  # the bearer arrives with it
    return [
        world.new_event(
            type=RING_MOVED_EVENT,
            subject_ids=[ring.id, bearer.id],
            location_id=site.id if site is not None else None,
            payload={
                "col": ring.col,
                "row": ring.row,
                "arrived": arrived,
                "pull": ring.pull,
            },
        )
    ]


def _step_along_path(world: World, ring: Ring) -> None:
    """Spend this tick's movement budget to walk as far along ``path`` as it reaches."""
    grid = world.grid
    if grid is None:
        return
    points = ring.move_points + tick_speed(ring.miles_per_year, grid.miles_per_tile)
    col, row = ring.col, ring.row
    remaining = [list(tile) for tile in ring.path]
    while remaining:
        nc, nr = remaining[0]
        step = grid.move_cost(nc, nr)
        cost = 2 if step is None else step  # an impassable goal tile is still enterable
        if points < cost:
            break
        points -= cost
        col, row = nc, nr
        remaining.pop(0)
    ring.col, ring.row = col, row
    ring.move_points = points
    ring.path = remaining  # fresh list (snapshot-safe)


# =========================================================================
# Pull
# =========================================================================

def use_ring(ring: Ring) -> None:
    """Register a *use* of the Ring: pull spikes (capped)."""
    ring.pull = min(_PULL_MAX, ring.pull + _PULL_USE_SPIKE)


def _decay_pull(ring: Ring) -> None:
    """The world's attention ebbs a little each tick the Ring is not used."""
    ring.pull = max(0, ring.pull - _PULL_DECAY)


# =========================================================================
# Placement helpers (keep col/row in step with possession)
# =========================================================================

def _track_bearer_tile(world: World, ring: Ring, bearer: Character) -> None:
    """Keep an idle borne Ring on its bearer's seat (an errand overrides this)."""
    if ring.on_errand:
        return
    _place_on_character(world, ring, bearer)


def _place_on_character(world: World, ring: Ring, bearer: Character) -> None:
    grid = world.grid
    if grid is not None:
        _place_on_bearer_tile(ring, grid, bearer)


def _place_on_bearer_tile(ring: Ring, grid: TileGrid, bearer: Character) -> None:
    site = grid.site_by_id(bearer.location_id) if bearer.location_id is not None else None
    if site is not None:
        ring.col, ring.row = site.col, site.row


def _place_on_site(world: World, ring: Ring, site_id: Optional[int]) -> None:
    grid = world.grid
    if grid is None or site_id is None:
        return
    site = grid.site_by_id(site_id)
    if site is not None:
        ring.col, ring.row = site.col, site.row


def _bearer_site(world: World, bearer: Optional[Character]) -> Optional[int]:
    """The site id a bearer stands at (their ``location_id``), or ``None``."""
    if not isinstance(bearer, Character):
        return None
    return bearer.location_id


def _site_at(world: World, col: int, row: int):
    grid = world.grid
    return grid.site_at(col, row) if grid is not None else None


# =========================================================================
# Actors near the Ring (thieves, finders, captors)
# =========================================================================

def _nearest_taker(world: World, bearer: Character) -> Optional[Character]:
    """A plausible thief: a living character sharing the bearer's seat, lowest id.

    Someone must be *there* to take it — theft is opportunistic, not teleporting a
    ring across the map. Excludes the bearer themselves.
    """
    return _other_character_at_site(world, bearer.location_id, exclude_id=bearer.id)


def _finder_at_site(world: World, ring: Ring, r: random.Random) -> Optional[Character]:
    """Whoever chances on a dropped Ring at its site — if anyone is there.

    A found Ring is a rare thing: only rolled when a character shares the tile,
    and only on a bounded chance so it can lie unclaimed for a while.
    """
    if ring.location_id is None:
        return None
    if r.randrange(1000) >= _LOSS_BASE_BP * 4:  # finding is uncommon
        return None
    return _other_character_at_site(world, ring.location_id, exclude_id=None)


def _other_character_at_site(
    world: World, site_id: Optional[int], exclude_id: Optional[int]
) -> Optional[Character]:
    if site_id is None:
        return None
    best: Optional[Character] = None
    for char in characters(world, alive_only=True):
        if char.id == exclude_id or char.location_id != site_id:
            continue
        if best is None or char.id < best.id:
            best = char
    return best


def _host_leader_on_tile(world: World, ring: Ring) -> Optional[Character]:
    """The general of a host standing on a dropped Ring's tile — the war-captor.

    Reads the field *after* war has resolved this tick (the Ring phase runs after
    phase 5), so a host that has just seized the ground the Ring lies on takes it.
    """
    from .armies import armies  # local import: armies has no ring dependency

    for army in armies(world, alive_only=True):
        if army.col == ring.col and army.row == ring.row and army.leader_id is not None:
            leader = world.entities.get(army.leader_id)
            if isinstance(leader, Character) and leader.alive:
                return leader
    return None
