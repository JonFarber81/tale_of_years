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
from .factions import (
    Faction,
    Intent,
    People,
    deciding_factions,
    faction_march_speed,
    factions,
)
from .tiles import Terrain, TileGrid, UNOWNED, move_cost
from .world import World

# Event types this phase emits.
ARMY_MUSTERED_EVENT = "army_mustered"  # a host raised at its faction's seat
ARMY_ARRIVED_EVENT = "army_arrived"  # a host reached its objective
ARMY_DISBANDED_EVENT = "army_disbanded"  # a host bled to nothing on the march

# -- tuning (all integer) --------------------------------------------------

# Muster sizing: a base levy plus a slice of the faction's territory-derived
# military strength. Pure and RNG-free, so the same faction always raises the
# same host (the ticket's "muster sizing deterministic"). Tuned up for issue #13
# so each host that *is* raised (rarely, and often as a coalition summing several
# of these) is a heavy, several-fold-larger war-effort, not a small annual levy.
MUSTER_BASE = 2000
MUSTER_PER_STRENGTH = 120
# Sauron's rise scales the dark realm's musters (issue #5): each point of the
# phase-7 ``sauron_strength`` scalar (zero on every other faction) adds this many
# to the host it raises — a strong Shadow fields hosts no free realm can match.
SAURON_MUSTER_PER_STRENGTH = 60

# Muster cadence (issue #13). A faction that fields a host cannot raise or lend to
# another until this many years pass *after that host leaves play* — a base rest
# plus a slice that grows with the size of the host, so a great hosting depletes
# the realm's manpower for longer (ADR-0009). All integer; keeps hosts episodic.
MUSTER_COOLDOWN_BASE = 4
MUSTER_COOLDOWN_PER_SIZE = 2500  # +1 year of rest per this much mustered size
MUSTER_COOLDOWN_CAP = 15

# Concurrent hosts (issue #33, ADR-0013; revisiting issue #13's one-host cadence).
# A realm may keep
# several hosts afield at once — one always, plus one per this much derived
# military strength, plus (dark realm only) one per this much of Sauron's scalar.
# So a great power wages a multi-front war while a small realm still fields a
# single host, and — because muster size scales with the *same* strength — more
# hosts never means a swarm of small levies (the tiny-army problem #13 fixed).
# The muster cooldown still paces *re-raising* a host once one leaves play.
HOSTS_PER_STRENGTH = 40  # +1 concurrent host per this much military_strength
HOSTS_PER_SAURON_STRENGTH = 40  # dark realm only: +1 more per this much sauron_strength
# Hard ceiling on concurrent hosts. Held at 4 (not 5) deliberately: a fifth
# roaming host let even a *concentrating* Mordor intercept the whole coalition
# that must storm Barad-dûr, and the Black Land never fell (ADR-0012). At 4, peak
# Mordor still wages a two-front war yet leaves the West enough clear approaches
# to take the seat late — durable, not invincible.
MAX_CONCURRENT_HOSTS = 4

# Concentrate-then-spread (issue #33, ADR-0013). A realm masses on its **strongest** enemy
# before opening a second front: the primary threat carries this many hosts of
# head-start, so a great host stays concentrated and only *surplus* hosts fan out
# to weaker foes. Tuned with MAX_CONCURRENT_HOSTS so Mordor still splits across
# fronts (peak: three hosts on its main foe, one peeled off) without its spread
# breaking up every coalition that marches on it — the ADR-0012 fall stays reachable.
PRIMARY_FRONT_HEAD_START = 2

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
    mustered_size: int = 0  # strength at muster; battle destruction is proportional to it
    target_faction_id: Optional[int] = None
    dest_site_id: Optional[int] = None
    path: List[List[int]] = field(default_factory=list)
    move_points: int = 0
    miles_per_year: int = DEFAULT_MILES_PER_YEAR
    # A coalition's contributing factions (lead first). Each rests under a muster
    # cooldown when this host leaves play; ``cooldown_years`` is that rest, scaled
    # at muster time from the host's size (ADR-0009). Empty on a bare test host —
    # :func:`end_host` then falls back to the lead ``faction_id`` alone.
    contributor_ids: List[int] = field(default_factory=list)
    cooldown_years: int = 0
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
    fields the same number. ``sauron_strength`` (non-zero only on the dark realm)
    scales its musters on top of ordinary strength — the issue-#5 consumption of
    the phase-7 scalar, one tick after it was computed.
    """
    return (
        MUSTER_BASE
        + max(0, faction.military_strength) * MUSTER_PER_STRENGTH
        + max(0, faction.sauron_strength) * SAURON_MUSTER_PER_STRENGTH
    )


def max_concurrent_hosts(faction: Faction) -> int:
    """How many hosts ``faction`` may keep afield at once.

    One host always, plus one per ``HOSTS_PER_STRENGTH`` of derived military
    strength and (dark realm only) one per ``HOSTS_PER_SAURON_STRENGTH`` of
    Sauron's scalar — a great power fights on several fronts while a small realm
    fields a single host — capped at ``MAX_CONCURRENT_HOSTS``. Because
    :func:`muster_size` scales with the same strength, a realm that fields more
    hosts fields *bigger* ones, not a swarm of small levies.
    """
    extra = max(0, faction.military_strength) // HOSTS_PER_STRENGTH
    extra += max(0, faction.sauron_strength) // HOSTS_PER_SAURON_STRENGTH
    return min(MAX_CONCURRENT_HOSTS, 1 + extra)


def host_cooldown_years(size: int) -> int:
    """Years a contributor rests after a host of ``size`` leaves play (integer).

    A base rest plus a slice that grows with the host raised, capped — so a great
    coalition hosting keeps its realms out of the field far longer than a small levy.
    """
    return min(MUSTER_COOLDOWN_CAP, MUSTER_COOLDOWN_BASE + max(0, size) // MUSTER_COOLDOWN_PER_SIZE)


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
    events.extend(_stand_down_ended_wars(world))  # free capacity from hosts whose war is over
    events.extend(_muster(world, grid))
    for army in armies(world, alive_only=True):
        events.extend(_advance(world, grid, army))
    return events


def _stand_down_ended_wars(world: World) -> List[Event]:
    """Disband every host whose war has ended: the raising realm is no longer at
    war with the enemy it marched on (peace was made, or that enemy left play to a
    third party). A host outlives neither its war nor its objective — standing it
    down rests its contributors and frees the realm's muster capacity, instead of
    leaving a zombie garrison pinned on a former foe's seat forever (which would
    otherwise lock a multi-front realm at its host ceiling once its wars resolve).
    """
    events: List[Event] = []
    for army in armies(world, alive_only=True):
        target_id = army.target_faction_id
        if target_id is None:
            continue  # no objective (unreachable at muster) — it simply garrisons home
        lead = _faction(world, army.faction_id) if army.faction_id is not None else None
        if lead is not None and lead.is_at_war_with(target_id):
            continue  # the war it marches to prosecute is still on
        army.status = EntityStatus.DEAD.value
        end_host(world, army)  # its contributors now rest under a muster cooldown
        events.append(
            world.new_event(
                type=ARMY_DISBANDED_EVENT,
                subject_ids=_army_subjects(army),
                location_id=None,
                payload={"cause": "war_ended", "faction_id": army.faction_id},
            )
        )
    return events


# -- muster ---------------------------------------------------------------

def _muster(world: World, grid: TileGrid) -> List[Event]:
    """Raise a host for each faction that chose force and may lawfully take the field.

    A host is raised only while the faction is genuinely **at war** (not mere
    hostility), is **not within a muster cooldown**, and is not already committed to
    a standing host — the cadence gate that keeps hosts episodic (ADR-0009).
    """
    events: List[Event] = []
    for faction in deciding_factions(world):
        intent = faction.current_intent.get("intent")
        if intent not in (Intent.MUSTER.value, Intent.ATTACK.value):
            continue
        if not _can_muster(world, faction):
            continue
        seat = _seat_tile(grid, faction)
        if seat is None:  # no capital to raise a host at (most cultures)
            continue
        # Split a realm's several hosts across its enemies, but concentrate first:
        # the strongest threat draws the opening hosts, surplus hosts open weaker
        # fronts (see _march_target). Coverage counts this faction's standing hosts.
        target = _march_target(world, faction, _covered_target_counts(world, faction.id))
        contributors = _coalition(world, faction, target)
        events.append(_raise_army(world, grid, faction, seat, target, contributors))
    return events


def _coalition(world: World, lead: Faction, target: Faction) -> List[Faction]:
    """The factions that Gather into one host behind ``lead`` against ``target``.

    The lead plus each of its **treaty-allies, vassals, or overlord** that is *also*
    at war with the same enemy and itself free to muster (past its cooldown, not
    already committed). Sharing a war is what combines levies — an unbound third
    party at war with the same enemy fields its own host (ADR-0009). Lead first,
    then the rest in id order (deterministic).
    """
    members = [lead]
    for other in _bound_factions(world, lead):
        if other.id == lead.id or not other.alive or other.is_provider:
            continue
        if not other.is_at_war_with(target.id):
            continue
        if world.current_year < other.muster_cooldown_until:
            continue
        if _at_host_capacity(world, other):
            continue
        members.append(other)
    return members


def _bound_factions(world: World, lead: Faction) -> List[Faction]:
    """A faction's treaty-allies, vassals, and overlord (id order) — its co-belligerent
    pool for a Gathering."""
    ids = set(lead.treaties)
    if lead.overlord_faction_id is not None:
        ids.add(lead.overlord_faction_id)
    for other in factions(world, alive_only=True):
        if other.overlord_faction_id == lead.id:
            ids.add(other.id)
    return [f for i in sorted(ids) if (f := _faction(world, i)) is not None]


def _can_muster(world: World, faction: Faction) -> bool:
    """Whether ``faction`` may raise a host this tick: past its cooldown, still
    below its strength-scaled host ceiling, and holding a war enemy to march on."""
    if world.current_year < faction.muster_cooldown_until:
        return False
    if _at_host_capacity(world, faction):
        return False
    return _march_target(world, faction) is not None


def _committed_host_count(world: World, faction_id: int) -> int:
    """How many living hosts a faction currently leads *or* lends a levy to."""
    return sum(
        1
        for army in armies(world, alive_only=True)
        if army.faction_id == faction_id or faction_id in army.contributor_ids
    )


def _at_host_capacity(world: World, faction: Faction) -> bool:
    """Whether ``faction`` already fields (or lends to) as many hosts as its
    strength-scaled :func:`max_concurrent_hosts` ceiling allows."""
    return _committed_host_count(world, faction.id) >= max_concurrent_hosts(faction)


def end_host(world: World, army: Army) -> None:
    """Rest every faction that contributed to a host that has just left play.

    Sets each contributor's muster cooldown to the current year plus the host's
    size-scaled ``cooldown_years`` (never shortening an existing, longer rest). A
    bare host with no recorded contributors falls back to its lead faction alone.
    Call this wherever a host is disbanded or destroyed, so the cadence gate sees
    the recovery no matter which phase ended the host.
    """
    until = world.current_year + army.cooldown_years
    ids = army.contributor_ids or ([army.faction_id] if army.faction_id is not None else [])
    for fid in ids:
        faction = _faction(world, fid)
        if faction is not None:
            faction.muster_cooldown_until = max(faction.muster_cooldown_until, until)


def _raise_army(
    world: World,
    grid: TileGrid,
    faction: Faction,
    seat: Tuple[int, int],
    target: Faction,
    contributors: List[Faction],
) -> Event:
    """Gather one coalition host at ``seat``: sum its levies, lead it, set its march.

    ``faction`` is the lead (the host's owner and muster point); ``contributors`` is
    the coalition (lead first). Size is the sum of every contributor's levy; the
    general is the ablest leader across the *whole* coalition down the ladder; the
    host marches at the lead's pace and rests every contributor when it ends.
    """
    leader = _coalition_leader(world, contributors, faction)
    dest_site_id: Optional[int] = None
    path: List[List[int]] = []
    dest = _seat_tile(grid, target)
    if dest is not None:
        candidate = find_path(grid, seat, dest)
        if candidate:  # reachable — commit to the march
            dest_site_id = target.capital_location_id
            path = candidate
    size = sum(muster_size(c) for c in contributors)
    army = Army(
        id=world.next_id(),
        kind="army",
        name=f"Host of {faction.name}",
        created_year=world.current_year,
        faction_id=faction.id,
        leader_id=leader.id if leader is not None else None,
        col=seat[0],
        row=seat[1],
        size=size,
        mustered_size=size,
        target_faction_id=target.id if path else None,
        dest_site_id=dest_site_id,
        path=path,
        miles_per_year=faction_march_speed(faction),
        contributor_ids=[c.id for c in contributors],
        cooldown_years=host_cooldown_years(size),
        prominence=faction.prominence,
    )
    world.entities[army.id] = army
    if leader is not None and leader.role in (Role.NONE.value, Role.RANGER.value):
        leader.role = Role.GENERAL.value  # the ablest takes field command
    subjects = [army.id, faction.id]
    if leader is not None:
        subjects.append(leader.id)
    payload: Dict[str, object] = {
        "size": army.size,
        "faction_id": faction.id,
        "led": leader is not None,
        "contributors": [c.id for c in contributors],
    }
    if army.target_faction_id is not None:
        payload["target_faction_id"] = army.target_faction_id
    return world.new_event(
        type=ARMY_MUSTERED_EVENT,
        subject_ids=subjects,
        location_id=faction.capital_location_id,
        payload=payload,
    )


# The roles a host's general may be drawn from at the top rung: an idle member, a
# ranger, or a standing general. A ruler and an heir are excluded here (rulers stay
# home; heirs are the *second* rung), and are handled explicitly below.
_FIELD_ROLES = (Role.NONE.value, Role.RANGER.value, Role.GENERAL.value)


def _coalition_leader(
    world: World, contributors: List[Faction], lead: Faction
) -> Optional[Character]:
    """Walk the leader ladder across the whole coalition — hosts are always led.

    Rung 1: the ablest field-eligible **non-heir** (idle/ranger/general) of any
    contributor. Rung 2: failing that, the ablest **heir** across the coalition —
    who may then die in battle, seating the next heir at the next succession. Rung
    3: failing even that, a freshly **generated named captain** for the lead (a
    non-dynastic character outside succession/kinship). So a leaderless host never
    marches (ADR-0009). Ties break by lowest id; a character already leading a host
    or standing as a ruler is unavailable.
    """
    faction_ids = {c.id for c in contributors}
    excluded = {a.leader_id for a in armies(world, alive_only=True) if a.leader_id}
    excluded.update(c.leader_id for c in contributors if c.leader_id is not None)
    field_leader = _ablest(world, faction_ids, excluded, _FIELD_ROLES)
    if field_leader is not None:
        return field_leader
    heir = _ablest(world, faction_ids, excluded, (Role.HEIR.value,))
    if heir is not None:
        return heir
    return generate_captain(world, lead)


def _ablest(
    world: World, faction_ids: set, excluded: set, roles: Tuple[str, ...]
) -> Optional[Character]:
    """The ablest (highest martial+leadership) living, mature member of any of
    ``faction_ids`` in one of ``roles`` and not ``excluded``; lowest id breaks ties."""
    year = world.current_year
    best: Optional[Character] = None
    best_key: Optional[Tuple[int, int]] = None
    for char in characters(world, alive_only=True):
        if char.faction_id not in faction_ids or char.id in excluded:
            continue
        if char.role not in roles:
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


# Generated-captain traits: a competent-but-unexceptional field officer. Kept
# deterministic and RNG-free (movement draws no RNG — it must never perturb the
# shared stream), so the spread is derived from integer identity, not a draw.
_CAPTAIN_TRAIT_BASE = 45
_CAPTAIN_TRAIT_SPREAD = 30


def generate_captain(world: World, lead: Faction) -> Character:
    """Raise a generated named captain to lead ``lead``'s host — the ladder's floor.

    A non-dynastic character (no parents, outside the succession/kinship line) with
    modest generated ``martial``/``leadership``, seated as a :data:`Role.GENERAL`.
    Its traits are a deterministic function of the lead's id and the tick (no RNG),
    so a run stays byte-stable. This deliberately grows a new, generated
    sub-population of captains over a long history.
    """
    from .characters import add_character, characters
    from .naming import choose_sex, generate_name

    race = _people_race(lead.people)
    mature = RACE_CONFIG[race].maturity_age
    mix = (lead.id * 2_654_435_761 + world.tick * 40_503) & 0xFFFFFFFF
    martial = _CAPTAIN_TRAIT_BASE + mix % _CAPTAIN_TRAIT_SPREAD
    leadership = _CAPTAIN_TRAIT_BASE + (mix // _CAPTAIN_TRAIT_SPREAD) % _CAPTAIN_TRAIT_SPREAD

    # A culture-authentic personal name, chosen as a pure function of the same stable
    # identity that fixes the traits — RNG-free, so the movement phase stays
    # byte-stable (issue #34). A distinct integer mix decorrelates name from traits.
    # ``taken`` disambiguates against living namesakes in the same faction.
    culture = lead.naming_culture
    name_seed = (mix * 2_246_822_519 + lead.id) & 0xFFFFFFFF
    sex = choose_sex(culture, name_seed)
    taken = {c.name for c in characters(world, alive_only=True) if c.faction_id == lead.id}
    name = generate_name(culture, sex, name_seed, taken)

    captain = add_character(
        world,
        name=name,
        race=race,
        birth_year=world.current_year - (mature + 5),  # a seasoned adult of its race
        sex=sex,
        role=Role.GENERAL,
        location_id=lead.capital_location_id,  # birthplace: the realm's seat
        faction_id=lead.id,
        # A light authored origin (issue #34): the honorific marks a raised captain as
        # an authored officer, not a spawn, wherever a character label renders. The
        # year it was raised is its ``created_year`` and reads on the muster event.
        title="Captain",
        traits={"martial": martial, "leadership": leadership},
    )
    return captain


# People → the race a generated captain of that folk is (approximate: Gondor's
# captains read as Men, not Dúnedain — close enough for a levied officer).
_PEOPLE_RACE = {
    People.MEN.value: Race.MAN,
    People.ELVES.value: Race.ELF,
    People.DWARVES.value: Race.DWARF,
    People.ORCS.value: Race.ORC,
    People.HOBBITS.value: Race.HOBBIT,
}


def _people_race(people: str) -> Race:
    return _PEOPLE_RACE.get(people, Race.MAN)


def _threat(faction: Optional[Faction]) -> int:
    """How dangerous an enemy is to overcome — its ordinary strength plus (dark
    realm only) Sauron's scalar. Drives which front a realm concentrates on: the
    strongest threat draws its first hosts before any surplus opens a new front."""
    if faction is None:
        return 0
    return max(0, faction.military_strength) + max(0, faction.sauron_strength)


def _march_target(
    world: World, faction: Faction, coverage: Optional[Dict[int, int]] = None
) -> Optional[Faction]:
    """The war enemy a fresh host marches on, or ``None`` when there is none.

    Only an active, conquerable holder with a seat qualifies (providers hold no
    ground and are never a march objective). Mere hostility no longer raises a
    host — a faction musters only when genuinely **at war** (ADR-0009), which is
    exactly what this returning ``None`` gates on.

    A realm **concentrates before it spreads**: given ``coverage`` (how many of
    its standing hosts already march on each enemy), it fields against the front
    of least coverage, but the strongest threat carries a ``PRIMARY_FRONT_HEAD_START``
    head-start — so it draws the opening hosts before a second front opens, and
    only surplus hosts then fan out to weaker enemies (ADR-0012 keeps Mordor's
    fall reachable: the West still masses on the Shadow rather than scattering,
    and Mordor cannot spread thin enough to intercept the whole coalition). Ties
    break toward the greater threat, then the lower id. With no coverage the
    strongest objective wins — the ``_can_muster`` gate only needs a front to exist.
    """
    objectives: List[Faction] = []
    for enemy_id in faction.at_war_with:  # already sorted ascending
        enemy = _faction(world, enemy_id)
        if _is_march_objective(enemy):
            objectives.append(enemy)
    if not objectives:
        return None
    counts = coverage or {}
    primary = max(objectives, key=lambda e: (_threat(e), -e.id))

    def load(enemy: Faction) -> Tuple[int, int, int]:
        # Least-covered front wins; the primary threat gets a head-start so it
        # concentrates. Break ties toward the greater threat, then lower id.
        head_start = PRIMARY_FRONT_HEAD_START if enemy.id == primary.id else 0
        return (counts.get(enemy.id, 0) - head_start, -_threat(enemy), enemy.id)

    return min(objectives, key=load)


def _covered_target_counts(world: World, faction_id: int) -> Dict[int, int]:
    """How many of a faction's living hosts (led *or* lent to) already march on
    each war enemy — the per-front coverage that concentrates its next host
    (see :func:`_march_target`)."""
    counts: Dict[int, int] = {}
    for army in armies(world, alive_only=True):
        target_id = army.target_faction_id
        if target_id is None:
            continue
        if army.faction_id == faction_id or faction_id in army.contributor_ids:
            counts[target_id] = counts.get(target_id, 0) + 1
    return counts


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
        end_host(world, army)  # its contributors now rest under a muster cooldown
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


def step_along_path(
    grid: TileGrid,
    col: int,
    row: int,
    path: List[List[int]],
    move_points: int,
    miles_per_year: int,
) -> Tuple[int, int, List[List[int]], int]:
    """Walk a tile-mover one tick along ``path`` on a miles/year budget.

    Pure and reusable: given a position, its remaining path, its carried budget and
    its pace, it spends this tick's effort against tile enter-costs and returns the
    new ``(col, row, remaining_path, leftover_points)``. The remaining path is a
    fresh list (snapshot-safe). Shared by the marching host (:func:`_step_along_path`)
    and the One Ring's errand, so the two can never price a step differently.
    """
    points = move_points + tick_speed(miles_per_year, grid.miles_per_tile)
    remaining = [list(tile) for tile in path]
    while remaining:
        nc, nr = remaining[0]
        cost = _enter_cost(grid, nc, nr)
        if points < cost:
            break
        points -= cost
        col, row = nc, nr
        remaining.pop(0)
    return col, row, remaining, points


def _step_along_path(grid: TileGrid, army: Army) -> None:
    """Spend this tick's budget to walk the host as far along ``path`` as it reaches."""
    army.col, army.row, army.path, army.move_points = step_along_path(
        grid, army.col, army.row, army.path, army.move_points, army.miles_per_year
    )


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
