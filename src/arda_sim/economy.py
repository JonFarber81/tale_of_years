"""Construction & economy — tick phase 6 (build ticket 11's peacetime foil).

The built world changing where there is peace. Two things happen here:

* **Economy** — once a year each realm's ``treasury`` accrues income drawn from
  the land it holds: every owned tile yields by its terrain, and a settlement on
  an owned tile adds a little more (bigger settlements, more). Population is never
  stored — it is a derived aggregate (:func:`faction_population`) read off the same
  holdings. All integer, no RNG: income is a pure function of the map.

* **Construction** — a realm that chose the ``build`` intent in phase 2 spends its
  treasury on exactly one work per tick, priced against what it can afford:

  * **found / rebuild** a settlement at an owned *un-settled* location — a razed
    ``ruin`` (from war, ticket 11) or an empty ``pass`` — which rises to a ``town``,
    or, at a **border or a pass**, to a **fortress**; emits ``founding``;
  * **grow** an owned ``town`` into a ``city`` (a settlement tier up); emits
    ``settlement_grew``;
  * **open a road** from one of its settlements across owned ground, paving the
    slowest adjacent tile; emits ``road_opened``.

  A location whose region holds an enemy host is **contested** and skipped — "08
  builds where there is peace, 07 destroys where there is war". Costs are fixed
  integers, so a lean treasury genuinely gates building (razing bites). Canonicity
  leans the choice toward **restoration** (founding/rebuilding) over mere growth —
  a soft weight on the score, never on the price.

Like every territory-touching phase, construction reaches the map through the live
``world.grid`` handle (ADR-0004) and is a no-op when no grid is attached.
"""

from __future__ import annotations

import random
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from .armies import armies
from .entities import Event
from .factions import Faction, factions
from .tiles import Site, Terrain, TileGrid, UNOWNED
from .world import World

# Event types this phase emits.
FOUNDING_EVENT = "founding"  # a settlement/fortress founded or rebuilt at a location
SETTLEMENT_GREW_EVENT = "settlement_grew"  # a settlement grew a tier (town -> city)
ROAD_OPENED_EVENT = "road_opened"  # a road paved across a realm's own ground

# -- economy tuning (integer) ---------------------------------------------

# Yearly income a single owned tile yields, by its terrain. The fat lowlands feed
# a realm; mountains and marsh barely pay; water yields nothing. All integer.
_TERRAIN_YIELD: Dict[Terrain, int] = {
    Terrain.PLAINS: 3,
    Terrain.ROAD: 3,
    Terrain.FOREST: 2,
    Terrain.HILLS: 2,
    Terrain.BARREN: 1,
    Terrain.RIVER: 1,
    Terrain.MARSH: 1,
    Terrain.MOUNTAIN: 1,
    Terrain.LAKE: 0,
    Terrain.SEA: 0,
}

# A settlement on an owned tile adds this to its owner's income — the return on
# building, and what makes a razed land poorer until it is raised again.
_SETTLEMENT_YIELD: Dict[str, int] = {"city": 8, "town": 3, "fort": 1}

# Rough head-count weight of a settlement, for the derived population aggregate.
_SETTLEMENT_POP: Dict[str, int] = {"city": 40, "town": 12, "fort": 6}

# -- construction tuning (integer) ----------------------------------------

# What each work costs against the treasury. A fortress costs more than a town;
# growing a settled place into a city is the priciest ordinary work.
_COST_FOUND_TOWN = 40
_COST_FOUND_FORT = 60
_COST_GROW = 80
_COST_ROAD = 20

# Base desirability of each kind of work, before the canon lean and jitter. A
# realm reaches first for new ground, then for growth, then for roads.
_SCORE_FOUND = 60
_SCORE_GROW = 45
_SCORE_ROAD = 25

# Canonicity leans a realm toward restoration (founding/rebuilding) — added to the
# founding score at full canon, nothing at zero. A weight on the choice, not the price.
_CANON_BUILD = 30
_BUILD_JITTER = 15  # exclusive upper bound of the per-work RNG jitter

# Locations a realm may found on: an empty, un-settled owned place.
_UNSETTLED_KINDS = ("ruin", "pass")
# Settlements a road may run out from, and terrain a road may never be paved over.
_ROAD_ANCHORS = ("town", "city", "fort")
_UNPAVEABLE = (Terrain.ROAD, Terrain.SEA, Terrain.LAKE, Terrain.MOUNTAIN)


# =========================================================================
# The phase
# =========================================================================

def construction_economy(world: World, rng: random.Random) -> List[Event]:
    """Phase 6: accrue yearly income, then let each building realm raise one work.

    Deterministic given the world and RNG: income is RNG-free; construction
    processes realms in id order and draws integer jitter only for a work it can
    actually attempt. A no-op (and no RNG drawn) without a grid or with nobody
    building this tick.
    """
    grid = world.grid
    if grid is None:
        return []
    if world.month == 1:  # income is a once-a-year harvest (the clock is monthly)
        _accrue_income(world, grid)
    return _construct(world, grid, rng)


# =========================================================================
# Economy — income off the land, population derived from it
# =========================================================================

def _income_map(grid: TileGrid) -> Dict[int, int]:
    """``faction id -> yearly income`` from every owned tile and settlement.

    The spec frames income as "sum of owned-region ``base_yield``". Regions are
    owned atomically (see factions.py), so summing per-*tile* terrain yield is that
    same figure computed from the tiles a region is made of — and it degrades
    gracefully to a partially-held region after a war splits it. When the substrate
    later authors a per-region ``base_yield`` scalar, it slots in here unchanged.
    """
    income: Dict[int, int] = {}
    for i, owner in enumerate(grid.owner):
        if owner == UNOWNED:
            continue
        income[owner] = income.get(owner, 0) + _TERRAIN_YIELD.get(grid.terrain[i], 0)
    for site in grid.sites:
        owner = grid.owner_at(site.col, site.row)
        if owner != UNOWNED:
            income[owner] = income.get(owner, 0) + _SETTLEMENT_YIELD.get(site.kind, 0)
    return income


def faction_income(world: World, grid: TileGrid) -> Dict[int, int]:
    """Yearly income per active, land-holding realm (the treasury accrual)."""
    result: Dict[int, int] = {}
    for fid, amount in _income_map(grid).items():
        faction = world.entities.get(fid)
        if isinstance(faction, Faction) and faction.alive and not faction.is_provider:
            result[fid] = amount
    return result


def _accrue_income(world: World, grid: TileGrid) -> None:
    """Add each realm's yearly income to its treasury (integer, RNG-free)."""
    for fid, amount in faction_income(world, grid).items():
        world.entities[fid].treasury += amount


def faction_population(world: World, grid: TileGrid, faction_id: int) -> int:
    """A realm's population as a *derived* aggregate — owned land plus its towns.

    Never stored (per the spec): computed on demand from the same holdings that
    feed income, so it can never drift from the map.
    """
    tiles = sum(1 for owner in grid.owner if owner == faction_id)
    settled = sum(
        _SETTLEMENT_POP.get(s.kind, 0)
        for s in grid.sites
        if grid.owner_at(s.col, s.row) == faction_id
    )
    return tiles + settled


# =========================================================================
# Construction — one work per building realm
# =========================================================================

def _construct(world: World, grid: TileGrid, rng: random.Random) -> List[Event]:
    """Let every realm that chose ``build`` this year raise one affordable work."""
    hosts_by_region = _hosts_by_region(world, grid)
    events: List[Event] = []
    for faction in factions(world, alive_only=True):
        if faction.is_provider or faction.current_intent.get("intent") != "build":
            continue
        event = _choose_work(world, grid, rng, faction, hosts_by_region)
        if event is not None:
            events.append(event)
    return events


class _Work(NamedTuple):
    """A candidate work: its score, its price, and the thunk that carries it out."""

    score: int
    cost: int
    do: Callable[[], Event]


def _choose_work(
    world: World,
    grid: TileGrid,
    rng: random.Random,
    faction: Faction,
    hosts_by_region: Dict[int, List[int]],
) -> Optional[Event]:
    """Pick and carry out this realm's best affordable work, or nothing.

    Candidates are gathered in fixed order (found, grow, road); each present one
    draws a single integer jitter, so the choice is reproducible under the seed.
    The highest-scoring work the treasury can pay for wins (ties break by order).
    """
    canonicity = world.config.canonicity
    candidates: List[_Work] = []

    found = _found_candidate(world, grid, rng, faction, hosts_by_region, canonicity)
    if found is not None:
        candidates.append(found)
    grow = _grow_candidate(world, grid, rng, faction, hosts_by_region)
    if grow is not None:
        candidates.append(grow)
    road = _road_candidate(world, grid, rng, faction, hosts_by_region)
    if road is not None:
        candidates.append(road)

    affordable = [c for c in candidates if c.cost <= faction.treasury]
    if not affordable:
        return None
    return max(affordable, key=lambda c: c.score).do()


def _found_candidate(
    world: World,
    grid: TileGrid,
    rng: random.Random,
    faction: Faction,
    hosts_by_region: Dict[int, List[int]],
    canonicity: float,
) -> Optional[_Work]:
    """Found or rebuild on the realm's lowest-id un-settled, uncontested location.

    A border or pass raises a **fortress**; anywhere else a **town**. Restoration
    carries a canon-weighted bonus, so canon-leaning realms rebuild first.
    """
    site = _first_owned_site(
        world, grid, faction, hosts_by_region,
        lambda s: s.kind in _UNSETTLED_KINDS,
    )
    if site is None:
        return None
    fortress = site.kind == "pass" or grid.is_border(site.col, site.row)
    kind = "fort" if fortress else "town"
    cost = _COST_FOUND_FORT if fortress else _COST_FOUND_TOWN
    rebuilt = site.kind == "ruin"
    score = _SCORE_FOUND + int(canonicity * _CANON_BUILD) + rng.randrange(_BUILD_JITTER)

    def do() -> Event:
        grid.set_site(site.id, kind, 1)
        faction.treasury -= cost
        return world.new_event(
            type=FOUNDING_EVENT,
            subject_ids=[faction.id],
            location_id=site.id,
            payload={"faction_id": faction.id, "kind": kind, "rebuilt": rebuilt},
        )

    return _Work(score, cost, do)


def _grow_candidate(
    world: World,
    grid: TileGrid,
    rng: random.Random,
    faction: Faction,
    hosts_by_region: Dict[int, List[int]],
) -> Optional[_Work]:
    """Grow the realm's lowest-id uncontested ``town`` into a ``city``."""
    site = _first_owned_site(
        world, grid, faction, hosts_by_region, lambda s: s.kind == "town"
    )
    if site is None:
        return None
    score = _SCORE_GROW + rng.randrange(_BUILD_JITTER)

    def do() -> Event:
        grid.set_site(site.id, "city", 2)
        faction.treasury -= _COST_GROW
        return world.new_event(
            type=SETTLEMENT_GREW_EVENT,
            subject_ids=[faction.id],
            location_id=site.id,
            payload={"faction_id": faction.id, "from": "town", "to": "city"},
        )

    return _Work(score, _COST_GROW, do)


def _road_candidate(
    world: World,
    grid: TileGrid,
    rng: random.Random,
    faction: Faction,
    hosts_by_region: Dict[int, List[int]],
) -> Optional[_Work]:
    """Pave the slowest owned tile next to one of the realm's settlements.

    Skips a settlement whose region holds an enemy host — roads, like foundings and
    growth, are only laid where there is peace.
    """
    best: Optional[Tuple[int, int, Site]] = None  # (move-cost, tile index, anchor)
    for site in grid.sites:
        if site.kind not in _ROAD_ANCHORS:
            continue
        if grid.owner_at(site.col, site.row) != faction.id:
            continue
        if _region_contested(world, grid, faction, site, hosts_by_region):
            continue
        for nc, nr in grid.neighbors(site.col, site.row):
            if grid.owner_at(nc, nr) != faction.id:
                continue
            terrain = grid.terrain_at(nc, nr)
            if terrain in _UNPAVEABLE or grid.site_at(nc, nr) is not None:
                continue
            cost = grid.move_cost(nc, nr) or 0
            idx = grid.index(nc, nr)
            if best is None or (cost, -idx) > (best[0], -best[1]):
                best = (cost, idx, site)
    if best is None:
        return None
    _mcost, idx, anchor = best
    score = _SCORE_ROAD + rng.randrange(_BUILD_JITTER)
    col, row = idx % grid.width, idx // grid.width

    def do() -> Event:
        grid.pave(idx)
        faction.treasury -= _COST_ROAD
        return world.new_event(
            type=ROAD_OPENED_EVENT,
            subject_ids=[faction.id],
            location_id=anchor.id,
            payload={"faction_id": faction.id, "col": col, "row": row},
        )

    return _Work(score, _COST_ROAD, do)


# =========================================================================
# Contested-ground / ownership helpers
# =========================================================================

def _first_owned_site(
    world: World,
    grid: TileGrid,
    faction: Faction,
    hosts_by_region: Dict[int, List[int]],
    predicate: Callable[[Site], bool],
) -> Optional[Site]:
    """The lowest-id site the realm owns that fits ``predicate`` and sits in peace."""
    best: Optional[Site] = None
    for site in grid.sites:
        if not predicate(site):
            continue
        if grid.owner_at(site.col, site.row) != faction.id:
            continue
        if _region_contested(world, grid, faction, site, hosts_by_region):
            continue
        if best is None or site.id < best.id:
            best = site
    return best


def _region_contested(
    world: World,
    grid: TileGrid,
    faction: Faction,
    site: Site,
    hosts_by_region: Dict[int, List[int]],
) -> bool:
    """Whether an enemy host stands in the region this site belongs to."""
    region_id = grid.region_of[grid.index(site.col, site.row)]
    for host_faction_id in hosts_by_region.get(region_id, ()):  # type: ignore[arg-type]
        if _is_enemy(world, faction, host_faction_id):
            return True
    return False


def _hosts_by_region(world: World, grid: TileGrid) -> Dict[int, List[int]]:
    """``region id -> faction ids fielding a host there`` (contested-ground index)."""
    index: Dict[int, List[int]] = {}
    for army in armies(world, alive_only=True):
        region_id = grid.region_of[grid.index(army.col, army.row)]
        if army.faction_id is not None:
            index.setdefault(region_id, []).append(army.faction_id)
    return index


def _is_enemy(world: World, faction: Faction, other_id: int) -> bool:
    """Whether ``other_id`` is a host the realm is at war with (directly or via a
    provider's patron)."""
    if faction.is_at_war_with(other_id):
        return True
    other = world.entities.get(other_id)
    if isinstance(other, Faction) and other.is_provider:
        patron = world.entities.get(other.allegiance_faction_id) if other.allegiance_faction_id else None
        if isinstance(patron, Faction) and faction.is_at_war_with(patron.id):
            return True
    return False
