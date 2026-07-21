"""Armies & movement — tick phase 4 (build ticket 10).

Hosts that muster and march. A faction that chose to raise force (phase 2's
``MUSTER`` or ``ATTACK`` intent) instantiates a single :class:`Army` at its seat,
sized from its territory-derived manpower pool and led by its ablest eligible
character. Phase 4 then advances every army **tile→tile** along a deterministic
path toward its objective by an integer movement budget (roads are cheap tiles,
rough ground dear ones — ADR-0001 superseded the old route layer), bleeding
integer **attrition** each tick it campaigns on harsh ground or off friendly
soil. An army that reaches its destination garrisons there; one bled to nothing
disbands.

Everything here is headless, integer-only, and deterministic under seed: muster
sizing is a pure function of faction state, pathfinding is a fixed-order Dijkstra,
and attrition is integer subtraction — no RNG and no float in an outcome-deciding
comparison (the float-determinism policy). Like the diplomacy phase, movement
reaches territory through the live ``world.grid`` handle and is a no-op when no
grid is attached (a reloaded world until ticket 12 re-attaches it — ADR-0004).

Army state that changes (the remaining ``path``) is mutated by **reassigning** a
fresh list, never in place, so a per-tick snapshot keeps the march as it stood
that tick rather than aliasing the live, still-advancing army (mirrors diplomacy).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import random

from . import TICKS_PER_YEAR
from .characters import RACE_CONFIG, Character, Race, Role, characters
from .entities import Entity, EntityStatus, Event, register_entity_type
from .factions import Faction, Intent, deciding_factions, factions
from .tiles import Terrain, TileGrid, UNOWNED, move_cost
from .world import World

# Event types this phase emits.
ARMY_MUSTERED_EVENT = "army_mustered"  # a host raised at its faction's seat
ARMY_ARRIVED_EVENT = "army_arrived"  # a host reached its objective
ARMY_DISBANDED_EVENT = "army_disbanded"  # a host bled to nothing on the march

# -- tuning (all integer) --------------------------------------------------

# Muster sizing: a base levy plus a slice of the faction's territory-derived
# military strength. Pure and RNG-free, so the same faction always raises the
# same host (the ticket's "muster sizing deterministic").
MUSTER_BASE = 500
MUSTER_PER_STRENGTH = 40

# March pace. A foot host makes ~180 miles a year; :func:`tick_speed` turns that
# into an integer per-tick effort budget spent against tile move-costs (a tile is
# ``miles_per_tile`` wide, plains cost 2 = the reference), so on open plains this
# rate clears one tile a month. Terrain does the rest: roads (cost 1) are quicker,
# hills/marsh/rivers slower — "route kind/terrain modulates speed".
DEFAULT_MILES_PER_YEAR = 180

# Per-tick integer attrition while a host is on the march (never while it sits in
# garrison). Harsh ground bites a flat toll; being off friendly soil bites a toll
# that *grows the longer the host stays away from a friendly seat* — the spec's
# "distance from friendly seats", tracked cheaply as consecutive ticks off home
# (``Army.supply_lag``) rather than a per-tick distance scan, so a host driven
# deep into hostile land bleeds progressively harder.
ATTR_HARSH = 30  # barren / marsh / bare mountain
ATTR_ROUGH = 15  # forest / hills / river crossings
ATTR_HOSTILE = 20  # per tick off friendly soil, ×supply_lag (capped)
ATTR_LAG_CAP = 5  # supply_lag saturates here, bounding the deep-in-hostile toll

# Hostility this deep (or an actual war) makes a mustered host march on the enemy
# seat; milder tempers raise only a standing garrison. Mirrors the diplomacy
# hostility threshold without importing it (kept a local movement knob).
_MARCH_HOSTILITY = 40

# Cost to enter an otherwise-impassable objective tile (a fortress on a mountain
# is still enterable by the host besieging it). Plains-equivalent, kept integer.
_OBJECTIVE_ENTER_COST = 2


def _enter_cost(grid: TileGrid, col: int, row: int) -> int:
    """Integer effort to step onto a tile — its terrain cost, or the objective
    fallback where that terrain is impassable (a seat on a mountain). Shared by
    pathfinding and stepping so the two can never price an objective differently.
    """
    step = grid.move_cost(col, row)
    return _OBJECTIVE_ENTER_COST if step is None else step


@dataclass
class Army(Entity):
    """A host on the map. Extends the entity base with a tile position and a march.

    Every cross-reference is an id: ``faction_id`` is the raising faction,
    ``leader_id`` its general (or ``None`` — leaderless hosts are allowed),
    ``target_faction_id`` the power it marches against, and ``dest_site_id`` the
    config-space site it is bound for (see :class:`~arda_sim.tiles.Site`). The
    host always stands on tile ``(col, row)``; ``path`` is the remaining tiles to
    its objective as ``[col, row]`` pairs (JSON-clean), consumed as it advances.
    ``move_points`` is the integer budget carried between ticks.
    """

    faction_id: Optional[int] = None
    leader_id: Optional[int] = None
    col: int = 0
    row: int = 0
    size: int = 0
    target_faction_id: Optional[int] = None
    dest_site_id: Optional[int] = None
    path: List[List[int]] = field(default_factory=list)
    move_points: int = 0
    miles_per_year: int = DEFAULT_MILES_PER_YEAR
    supply_lag: int = 0  # consecutive marching ticks off friendly soil (attrition depth)
    siege_progress: int = 0  # accumulated progress against the seat it besieges (ticket 11)
    prominence: int = 0  # salience input, read by chronicle.subject_prominence

    @property
    def alive(self) -> bool:
        """In play — not disbanded (tombstoned when bled to nothing)."""
        return self.status == EntityStatus.ACTIVE.value

    @property
    def in_transit(self) -> bool:
        """Whether the host still has tiles to march (vs. sitting in garrison)."""
        return bool(self.path)


register_entity_type("army", Army)


# -- pure sizing / pace helpers -------------------------------------------

def muster_size(faction: Faction) -> int:
    """The host a faction raises: a base levy plus a slice of its strength.

    Pure and deterministic — no RNG — so a faction of a given strength always
    fields the same number.
    """
    return MUSTER_BASE + max(0, faction.military_strength) * MUSTER_PER_STRENGTH


def tick_speed(miles_per_year: int, miles_per_tile: int) -> int:
    """Integer effort budget gained per tick from a miles/year march rate.

    Effort is spent against tile move-costs (plains = 2 = the reference), so the
    conversion is ``mpy × plains_cost ÷ (miles_per_tile × ticks_per_year)``, at
    least 1 so a host always eventually moves. All integer (float-determinism).
    """
    plains = move_cost(Terrain.PLAINS)
    return max(1, miles_per_year * plains // (miles_per_tile * TICKS_PER_YEAR))


# -- deterministic pathfinding --------------------------------------------

def find_path(
    grid: TileGrid, start: Tuple[int, int], goal: Tuple[int, int]
) -> List[List[int]]:
    """Cheapest tile path from ``start`` (exclusive) to ``goal`` (inclusive).

    A Dijkstra over passable tiles by integer terrain move-cost, in the grid's
    fixed neighbour order with an insertion counter breaking ties — so the same
    start/goal always yields the same path (reproducibility). The objective tile
    is enterable even if its terrain is impassable (a seat on a mountain). Returns
    ``[]`` if already there or unreachable. Never compares floats.
    """
    if start == goal:
        return []
    dist: Dict[Tuple[int, int], int] = {start: 0}
    prev: Dict[Tuple[int, int], Tuple[int, int]] = {}
    counter = 0
    heap: List[Tuple[int, int, Tuple[int, int]]] = [(0, 0, start)]
    while heap:
        d, _, cur = heapq.heappop(heap)
        if cur == goal:
            break
        if d > dist[cur]:
            continue
        cc, cr = cur
        for nc, nr in grid.neighbors(cc, cr):
            nxt = (nc, nr)
            is_goal = nxt == goal
            if not is_goal and not grid.passable(nc, nr):
                continue
            nd = d + _enter_cost(grid, nc, nr)  # goal may be impassable-but-enterable
            known = dist.get(nxt)
            if known is None or nd < known:
                dist[nxt] = nd
                prev[nxt] = cur
                counter += 1
                heapq.heappush(heap, (nd, counter, nxt))
    if goal not in prev:
        return []
    path: List[List[int]] = []
    cur = goal
    while cur != start:
        path.append([cur[0], cur[1]])
        cur = prev[cur]
    path.reverse()
    return path


# -- queries --------------------------------------------------------------

def armies(world: World, *, alive_only: bool = False) -> List[Army]:
    """All Army records in id order (optionally only those still in play)."""
    result = [e for _id, e in sorted(world.entities.items()) if isinstance(e, Army)]
    return [a for a in result if a.alive] if alive_only else result


def army_at(world: World, col: int, row: int) -> Optional[Army]:
    """The lowest-id living host standing on a tile, or ``None`` (map inspection)."""
    for army in armies(world, alive_only=True):
        if army.col == col and army.row == row:
            return army
    return None


def army_timeline(world: World, army_id: int) -> List[Event]:
    """Every event naming this host, oldest first — the inspection timeline."""
    return sorted(
        (ev for ev in world.events if army_id in ev.subject_ids),
        key=lambda ev: (ev.year, ev.id),
    )


# -- the phase ------------------------------------------------------------

def movement(world: World, rng: random.Random) -> List[Event]:
    """Phase 4: raise hosts from this year's intents, then advance every host.

    Deterministic given the world: factions and armies are both processed in id
    order and every step is integer. Draws no RNG (muster and movement are pure),
    so it never perturbs the shared stream. A no-op without a grid (ADR-0004).
    """
    grid = world.grid
    if grid is None:
        return []
    events: List[Event] = []
    events.extend(_muster(world, grid))
    for army in armies(world, alive_only=True):
        events.extend(_advance(world, grid, army))
    return events


# -- muster ---------------------------------------------------------------

def _muster(world: World, grid: TileGrid) -> List[Event]:
    """Raise a host for each faction that chose force and holds none yet."""
    events: List[Event] = []
    for faction in deciding_factions(world):
        intent = faction.current_intent.get("intent")
        if intent not in (Intent.MUSTER.value, Intent.ATTACK.value):
            continue
        if _has_army(world, faction.id):
            continue
        seat = _seat_tile(grid, faction)
        if seat is None:  # no capital to raise a host at (most cultures)
            continue
        events.append(_raise_army(world, grid, faction, seat))
    return events


def _raise_army(
    world: World, grid: TileGrid, faction: Faction, seat: Tuple[int, int]
) -> Event:
    """Instantiate a host at ``seat``, size it, lead it, and set its march."""
    leader = _muster_leader(world, faction)
    target = _march_target(world, faction)
    dest_site_id: Optional[int] = None
    path: List[List[int]] = []
    if target is not None:
        dest = _seat_tile(grid, target)
        if dest is not None:
            candidate = find_path(grid, seat, dest)
            if candidate:  # reachable — commit to the march
                dest_site_id = target.capital_location_id
                path = candidate
    army = Army(
        id=world.next_id(),
        kind="army",
        name=f"Host of {faction.name}",
        created_year=world.current_year,
        faction_id=faction.id,
        leader_id=leader.id if leader is not None else None,
        col=seat[0],
        row=seat[1],
        size=muster_size(faction),
        target_faction_id=target.id if (target is not None and path) else None,
        dest_site_id=dest_site_id,
        path=path,
        miles_per_year=DEFAULT_MILES_PER_YEAR,
        prominence=faction.prominence,
    )
    world.entities[army.id] = army
    if leader is not None and leader.role in (Role.NONE.value, Role.RANGER.value):
        leader.role = Role.GENERAL.value  # the ablest takes field command
    subjects = [army.id, faction.id]
    if leader is not None:
        subjects.append(leader.id)
    payload: Dict[str, object] = {"size": army.size, "faction_id": faction.id}
    if army.target_faction_id is not None:
        payload["target_faction_id"] = army.target_faction_id
    return world.new_event(
        type=ARMY_MUSTERED_EVENT,
        subject_ids=subjects,
        location_id=faction.capital_location_id,
        payload=payload,
    )


def _muster_leader(world: World, faction: Faction) -> Optional[Character]:
    """The faction's ablest field-eligible member (highest martial+leadership).

    Its standing ruler/heir stays home (rule and succession are theirs), and a
    character already leading a host is unavailable; ties break by lowest id.
    Returns ``None`` when no one is free — leaderless hosts are allowed.
    """
    taken = {a.leader_id for a in armies(world, alive_only=True) if a.leader_id}
    year = world.current_year
    best: Optional[Character] = None
    best_key: Optional[Tuple[int, int]] = None
    for char in characters(world, alive_only=True):
        if char.faction_id != faction.id or char.id in taken:
            continue
        if char.id == faction.leader_id:
            continue
        if char.role not in (Role.NONE.value, Role.RANGER.value, Role.GENERAL.value):
            continue
        if char.age(year) < RACE_CONFIG[Race(char.race)].maturity_age:
            continue
        martial = int(char.traits.get("martial", 0))
        leadership = int(char.traits.get("leadership", 0))
        key = (martial + leadership, -char.id)
        if best_key is None or key > best_key:
            best_key = key
            best = char
    return best


def _march_target(world: World, faction: Faction) -> Optional[Faction]:
    """The power a mustered host marches on: a war enemy, else the faction it most
    hates (past :data:`_MARCH_HOSTILITY`), else ``None`` — a standing garrison.

    Only an active, conquerable holder with a seat qualifies (providers hold no
    ground and are never a march objective); lowest id breaks ties.
    """
    for enemy_id in faction.at_war_with:  # already sorted ascending
        enemy = _faction(world, enemy_id)
        if _is_march_objective(enemy):
            return enemy
    intent_target = faction.current_intent.get("target_faction_id")
    if intent_target:
        target = _faction(world, intent_target)
        if _is_march_objective(target):
            return target
    worst: Optional[Faction] = None
    worst_disp: Optional[int] = None
    for other in factions(world, alive_only=True):
        if other.id == faction.id or not _is_march_objective(other):
            continue
        disp = faction.disposition_toward(other.id)
        if disp > -_MARCH_HOSTILITY:  # not hated deeply enough to march on
            continue
        if worst_disp is None or disp < worst_disp:  # strict: lowest id wins ties
            worst_disp = disp
            worst = other
    return worst


def _is_march_objective(target: Optional[Faction]) -> bool:
    """Whether a faction can be marched on: active, non-provider, with a seat."""
    return (
        target is not None
        and target.alive
        and not target.is_provider
        and target.capital_location_id is not None
    )


# -- advance --------------------------------------------------------------

def _advance(world: World, grid: TileGrid, army: Army) -> List[Event]:
    """March a host one tick along its path, apply attrition, resolve arrival.

    Movement spends an accrued integer budget against tile costs (several tiles a
    tick on roads, fewer on rough ground); a host only bleeds while it campaigns,
    never in garrison. The ``path`` is always reassigned as a fresh list so a
    snapshot taken this tick keeps the march as it stood.
    """
    events: List[Event] = []
    if not army.alive:  # a disbanded host is never advanced again
        return events
    marched = army.in_transit
    if marched:
        _step_along_path(grid, army)
        loss = _attrition(world, grid, army)
        if loss:
            army.size = max(0, army.size - loss)
    if army.size <= 0:  # bled to nothing on the road
        army.status = EntityStatus.DEAD.value
        events.append(
            world.new_event(
                type=ARMY_DISBANDED_EVENT,
                subject_ids=_army_subjects(army),
                location_id=None,  # mid-map, not at a named seat
                payload={"cause": "attrition", "faction_id": army.faction_id},
            )
        )
        return events
    if marched and not army.path and army.dest_site_id is not None:
        events.append(
            world.new_event(
                type=ARMY_ARRIVED_EVENT,
                subject_ids=_army_subjects(army),
                location_id=army.dest_site_id,
                payload={
                    "faction_id": army.faction_id,
                    "target_faction_id": army.target_faction_id,
                    "size": army.size,
                },
            )
        )
        army.dest_site_id = None  # now a garrison at the objective
    return events


def _step_along_path(grid: TileGrid, army: Army) -> None:
    """Spend this tick's budget to walk as far along ``path`` as it reaches."""
    points = army.move_points + tick_speed(army.miles_per_year, grid.miles_per_tile)
    col, row = army.col, army.row
    remaining = [list(tile) for tile in army.path]
    while remaining:
        nc, nr = remaining[0]
        cost = _enter_cost(grid, nc, nr)
        if points < cost:
            break
        points -= cost
        col, row = nc, nr
        remaining.pop(0)
    army.col, army.row = col, row
    army.move_points = points
    army.path = remaining  # fresh list (snapshot-safe)


def _attrition(world: World, grid: TileGrid, army: Army) -> int:
    """Integer strength lost this tick from harsh ground and depth off friendly soil.

    Harsh terrain bites a flat toll; being off a friendly seat bites a toll that
    grows with ``supply_lag`` — the run of marching ticks since the host last
    stood on friendly ground — capped at :data:`ATTR_LAG_CAP`. So a host one tile
    past the border bleeds lightly and one driven deep bleeds hard ("a host deep
    in hostile/barren land bleeds"). ``supply_lag`` resets the moment it regains
    friendly soil. Updates the counter in place (a scalar — snapshot-safe).
    """
    terrain = grid.terrain_at(army.col, army.row)
    loss = 0
    if terrain in (Terrain.BARREN, Terrain.MARSH, Terrain.MOUNTAIN):
        loss += ATTR_HARSH
    elif terrain in (Terrain.FOREST, Terrain.HILLS, Terrain.RIVER):
        loss += ATTR_ROUGH
    if grid.owner_at(army.col, army.row) not in _friendly_ids(world, army.faction_id):
        army.supply_lag = min(army.supply_lag + 1, ATTR_LAG_CAP)
        loss += ATTR_HOSTILE * army.supply_lag
    else:
        army.supply_lag = 0
    return loss


def _friendly_ids(world: World, faction_id: Optional[int]) -> set:
    """Faction ids whose soil a host treats as home: its own, its allies, its liege
    and its vassals. Wilderness (unowned) is never friendly — distance from a
    friendly seat is what bleeds a host on the march."""
    faction = _faction(world, faction_id)
    if faction is None:
        return set()
    friendly = {faction.id}
    friendly.update(faction.treaties)
    if faction.overlord_faction_id is not None:
        friendly.add(faction.overlord_faction_id)
    for other in factions(world):
        if other.overlord_faction_id == faction.id:
            friendly.add(other.id)
    return friendly


# -- lookup helpers -------------------------------------------------------

def _army_subjects(army: Army) -> List[int]:
    """The host's event subjects: itself, then its faction when it has one."""
    return [army.id, army.faction_id] if army.faction_id else [army.id]


def _has_army(world: World, faction_id: int) -> bool:
    """Whether this faction already fields a living host (the one-host cap)."""
    return any(a.faction_id == faction_id for a in armies(world, alive_only=True))


def _seat_tile(grid: TileGrid, faction: Faction) -> Optional[Tuple[int, int]]:
    """The ``(col, row)`` of a faction's capital site, or ``None`` if it has none."""
    if faction.capital_location_id is None:
        return None
    site = grid.site_by_id(faction.capital_location_id)
    return (site.col, site.row) if site is not None else None


def _faction(world: World, faction_id: Optional[int]) -> Optional[Faction]:
    if faction_id is None:
        return None
    entity = world.entities.get(faction_id)
    return entity if isinstance(entity, Faction) else None
