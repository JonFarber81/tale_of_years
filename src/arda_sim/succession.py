"""Dynasties & succession — the passing of crowns (build ticket 08).

When the character holding a faction's ``leader_id`` dies or departs, this phase
resolves the heir under the realm's :class:`~arda_sim.factions.SuccessionRule` and
hands over the seat; a line with no heir *fails*, and the realm is either absorbed
by its strongest bordering faction or fragments into unowned land, leaving a
**dormant claim** on a tombstoned faction so a fallen realm (Arnor) can be
restored generations later.

There is no ``Dynasty`` entity: the heir walk is a query over the character
kinship id-fields (``parent_ids``), reusing :mod:`arda_sim.characters`' bloodline
queries. Territory changes hands through ``world.grid`` (ADR-0004) — the same seam
war's conquest reuses in ticket 11 — so this is still a pure
``system(world, rng) -> events`` with the grid reached through the world.

The phase runs right after :func:`arda_sim.characters.aging_births_deaths`, so a
death rolled this tick is answered by a succession in the *same* tick. It is a
no-op (and draws no RNG) on any tick where no leader-holder fell, which keeps a
run and its reload bit-identical.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from .characters import (
    Character,
    Role,
    ancestors,
    characters,
    children_of,
    compute_prominence as _char_prominence,
)
from .entities import Entity, EntityStatus, Event
from .factions import (
    Faction,
    SuccessionRule,
    compute_military_strength,
    compute_prominence as _faction_prominence,
    factions,
)
from .tiles import UNOWNED, TileGrid
from .world import World

# Event types this phase emits.
SUCCESSION_EVENT = "succession"  # the seat passed to an heir
LINE_FAILED_EVENT = "line_failed"  # no heir — the ruling line is extinguished
ABSORPTION_EVENT = "absorption"  # a failed realm's land taken by a neighbour

# The kin-walk rules resolve an heir from the bloodline; ELECTIVE elects a member
# outright. Grouped so the phase reads by behaviour, not by enumerating members.
_KIN_RULES = frozenset(
    {
        SuccessionRule.AGNATIC_PRIMOGENITURE.value,
        SuccessionRule.STEWARDSHIP.value,
        SuccessionRule.DWARF_LINE_OF_DURIN.value,
    }
)


# =========================================================================
# The phase
# =========================================================================

def succession(world: World, rng: random.Random) -> List[Event]:
    """Phase: resolve every realm whose leader fell this tick (or earlier).

    Deterministic: factions are processed in id order; RNG is drawn only to break
    a genuine tie in an election, so a tick with no vacancy is a pure no-op.
    """
    events: List[Event] = []
    grid = world.grid
    for faction in _factions_with_vacant_seat(world):
        leader = _entity(world, faction.leader_id)
        heir = _resolve_heir(world, faction, rng)
        if heir is not None:
            events.append(_install_heir(world, faction, heir, leader, grid))
        else:
            events.extend(_fail_line(world, faction, leader, grid))
    return events


def _factions_with_vacant_seat(world: World) -> List[Faction]:
    """Active factions whose ``leader_id`` points at a character no longer in play.

    A faction seeded *without* a leader (Dol Guldur, the cultures) has nothing to
    lose and never triggers — only a realm that *had* a leader and lost them does.
    """
    vacant: List[Faction] = []
    for faction in factions(world, alive_only=True):
        if faction.leader_id is None:
            continue
        leader = _entity(world, faction.leader_id)
        if not isinstance(leader, Character) or not leader.alive:
            vacant.append(faction)
    return vacant


# =========================================================================
# Heir resolution
# =========================================================================

def presumptive_heir(world: World, faction: Faction) -> Optional[Character]:
    """The kin who *would* inherit this seat as the record stands (CONTEXT.md).

    A pure, rng-free preview of succession — the senior living descendant, else
    the nearest living collateral — for a kin-succession realm. An **ELECTIVE**
    seat draws the RNG to elect and so has no fixed heir to show: it returns
    ``None`` rather than fabricating one. Distinct from :func:`_resolve_heir`,
    which enacts the real handover (and may elect); this only *reads* the line,
    so the Dynasty view can badge an heir without perturbing a run.
    """
    if faction.succession_rule == SuccessionRule.ELECTIVE.value:
        return None
    return _kin_heir(world, faction.leader_id)


def _resolve_heir(
    world: World, faction: Faction, rng: random.Random
) -> Optional[Character]:
    """The next holder of the seat under this realm's rule, or ``None`` on failure.

    ELECTIVE realms elect outright; the bloodline rules walk kin first (the same
    rng-free walk :func:`presumptive_heir` previews) and fall back to an election
    only when no living kin remain.
    """
    if faction.succession_rule == SuccessionRule.ELECTIVE.value:
        return _elect(world, faction, rng)
    if faction.succession_rule in _KIN_RULES:
        heir = presumptive_heir(world, faction)
        if heir is not None:
            return heir
    # Kin exhausted (or an unknown rule): fall back to an election of the realm's
    # own people before the line is declared failed.
    return _elect(world, faction, rng)


def _kin_heir(world: World, leader_id: Optional[int]) -> Optional[Character]:
    """Agnatic-primogeniture heir: the senior living descendant, else collateral.

    First the leader's own descendants; if none survive, widen to each forebear's
    line in turn (siblings, then cousins, …), nearest ancestor first. Seniority is
    *nearest generation, male-preferring, eldest* — a deterministic total order.
    """
    if leader_id is None:
        return None
    direct = _living_descendants_ranked(world, leader_id, exclude_id=leader_id)
    if direct:
        return direct[0]
    for forebear in ancestors(world, leader_id):  # nearest first
        collateral = _living_descendants_ranked(world, forebear.id, exclude_id=leader_id)
        if collateral:
            return collateral[0]
    return None


def _living_descendants_ranked(
    world: World, root_id: int, exclude_id: int
) -> List[Character]:
    """Living descendants of ``root_id`` (excluding ``exclude_id``), most senior first.

    Breadth-first so generation depth is known; the sort key
    ``(depth, sex_rank, birth_year, id)`` encodes nearest-generation, then
    male-preferring, then eldest, then a stable id tie-break.
    """
    ranked: List[tuple] = []
    frontier = [(child, 1) for child in children_of(world, root_id)]
    seen = {root_id}
    while frontier:
        char, depth = frontier.pop(0)
        if char.id in seen:
            continue
        seen.add(char.id)
        if char.id != exclude_id and char.alive:
            sex_rank = 0 if char.sex == "M" else 1
            ranked.append((depth, sex_rank, char.birth_year, char.id, char))
        frontier.extend((c, depth + 1) for c in children_of(world, char.id))
    ranked.sort(key=lambda t: t[:4])
    return [t[4] for t in ranked]


def _elect(world: World, faction: Faction, rng: random.Random) -> Optional[Character]:
    """Elect the worthiest living member of the realm (highest prominence).

    The candidate pool is the faction's own living members other than the fallen
    leader. Ties at the top prominence are broken by the seeded RNG, so a genuine
    contest is reproducible rather than always resolving to the lowest id.
    """
    pool = [
        c
        for c in characters(world, alive_only=True)
        if c.faction_id == faction.id and c.id != faction.leader_id
    ]
    if not pool:
        return None
    best = max(c.prominence for c in pool)
    top = sorted((c for c in pool if c.prominence == best), key=lambda c: c.id)
    if len(top) == 1:
        return top[0]
    return top[rng.randrange(len(top))]


# =========================================================================
# Success — install the heir
# =========================================================================

def _install_heir(
    world: World,
    faction: Faction,
    heir: Character,
    leader: Optional[Entity],
    grid: Optional[TileGrid],
) -> Event:
    """Seat the heir: crown, title, membership, and refreshed derived scalars."""
    former_id = faction.leader_id
    faction.leader_id = heir.id
    heir.role = Role.RULER.value
    heir.faction_id = faction.id
    # The office's title passes to an heir who holds none of their own (a Steward
    # of Gondor stays a Steward; a nameless heir inherits the crown's style).
    inherited_title = getattr(leader, "title", None)
    if inherited_title and not heir.title:
        heir.title = inherited_title
    heir.prominence = _char_prominence(heir)
    _refresh_faction_scalars(world, faction, heir, grid)

    payload: Dict[str, object] = {
        "rule": faction.succession_rule,
        "former_leader_id": former_id,
        "faction_id": faction.id,
    }
    if heir.title:
        payload["title"] = heir.title
    subjects = [heir.id, faction.id]
    if former_id is not None:
        subjects.append(former_id)
    return world.new_event(
        type=SUCCESSION_EVENT,
        subject_ids=subjects,
        location_id=faction.capital_location_id,
        payload=payload,
    )


# =========================================================================
# Failure — the line is extinguished
# =========================================================================

def _fail_line(
    world: World,
    faction: Faction,
    leader: Optional[Entity],
    grid: Optional[TileGrid],
) -> List[Event]:
    """No heir: extinguish the line, hand its land to a neighbour (or fragment it),
    and tombstone the faction with a dormant claim over the regions it held.
    """
    events: List[Event] = []
    region_ids = _owned_region_ids(grid, faction.id) if grid is not None else []

    events.append(
        world.new_event(
            type=LINE_FAILED_EVENT,
            subject_ids=[faction.id],
            location_id=faction.capital_location_id,
            payload={
                "rule": faction.succession_rule,
                "former_leader_id": faction.leader_id,
            },
        )
    )

    absorber = _strongest_bordering_faction(world, faction, grid) if grid is not None else None
    if absorber is not None:
        _transfer_all_tiles(grid, faction.id, absorber.id)
        _refresh_faction_scalars(world, absorber, _entity(world, absorber.leader_id), grid)
        events.append(
            world.new_event(
                type=ABSORPTION_EVENT,
                subject_ids=[faction.id, absorber.id],
                location_id=faction.capital_location_id,
                payload={"absorber_faction_id": absorber.id, "regions": region_ids},
            )
        )
    elif grid is not None:
        _transfer_all_tiles(grid, faction.id, UNOWNED)  # fragmentation: land goes wild

    # Tombstone: the faction leaves play but its record (and dormant claim) persist,
    # so references still resolve and the realm stays restorable (ADR intent).
    faction.status = EntityStatus.DEAD.value
    faction.military_strength = 0
    faction.claim_region_ids = sorted(set(faction.claim_region_ids) | set(region_ids))
    return events


# =========================================================================
# Territory helpers (read/write world.grid)
# =========================================================================

def _owned_region_ids(grid: TileGrid, faction_id: int) -> List[int]:
    """The config-space region ids the faction holds any tile of (sorted)."""
    ids = set()
    for i, owner in enumerate(grid.owner):
        if owner == faction_id:
            rid = grid.region_of[i]
            if rid:
                ids.add(rid)
    return sorted(ids)


def _owned_tile_count(grid: Optional[TileGrid], faction_id: int) -> int:
    if grid is None:
        return 0
    return sum(1 for owner in grid.owner if owner == faction_id)


def _strongest_bordering_faction(
    world: World, faction: Faction, grid: TileGrid
) -> Optional[Faction]:
    """The strongest *active* faction whose land touches this realm's, or ``None``.

    Borders are derived from the grid (never stored); among all factions bordering
    any tile this realm owns, the one with the greatest cached
    ``military_strength`` wins, id breaking ties.
    """
    neighbour_ids = set()
    for row in range(grid.height):
        for col in range(grid.width):
            if grid.owner_at(col, row) != faction.id:
                continue
            for nc, nr in grid.neighbors(col, row):
                other = grid.owner_at(nc, nr)
                if other != UNOWNED and other != faction.id:
                    neighbour_ids.add(other)
    candidates = [
        f
        for nid in neighbour_ids
        if isinstance((f := _entity(world, nid)), Faction) and f.alive
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda f: (f.military_strength, f.id))


def _transfer_all_tiles(grid: TileGrid, from_id: int, to_id: int) -> None:
    """Flip every tile owned by ``from_id`` to ``to_id`` (conquest-like transfer)."""
    grid.owner = [to_id if owner == from_id else owner for owner in grid.owner]


def _refresh_faction_scalars(
    world: World, faction: Faction, leader: Optional[Entity], grid: Optional[TileGrid]
) -> None:
    """Recompute a faction's derived strength/prominence after a change of seat
    or territory — the same formulas seeding uses, so nothing drifts.
    """
    tiles = _owned_tile_count(grid, faction.id)
    faction.military_strength = compute_military_strength(faction, tiles, leader)
    faction.prominence = _faction_prominence(faction, tiles, leader)


def _entity(world: World, entity_id: Optional[int]) -> Optional[Entity]:
    return world.entities.get(entity_id) if entity_id is not None else None
