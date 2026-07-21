"""War & battles — tick phase 5 (build ticket 11).

Armed conflict that changes the world. By the time this phase runs, phase 4 has
already marched every host to where it stands this tick; war reads those
positions and resolves the fighting:

* **Field battles** — two hosts of factions *formally at war* (ticket 09's
  ``at_war_with`` flag) that share a tile, or stand on adjacent tiles, clash.
  Each side's **effective strength** = ``size × leader × terrain/posture ×
  provider-unit`` modifiers; **one bounded seeded roll** perturbs the ratio, so a
  weaker host can still snatch an upset. The loser takes the heavier casualties
  and either retreats toward home or is destroyed outright.
* **Sieges** — a host standing on an at-war enemy's fortified **capital seat**
  invests it. A siege is a *multi-tick* state: ``Army.siege_progress`` accumulates
  each tick against the seat's **fortification**, so a great city holds out for
  months. When it falls the besieger **conquers** the realm — the seat's owner
  loses *all* its territory (a v1 decapitation; per-region seats are content-fog)
  — and, if the attacker is ruthless, **razes** the land to waste rather than
  annexing it. A realm whose last ground is taken is **extinguished** (tombstoned
  with a dormant claim, exactly as a failed line is), and its wars end.
* **Named death** — after a battle or a storming, each named leader present rolls
  a rare death check, far likelier on the broken side and blunted by the
  character's ``martial``. A ruler who falls this way vacates ``leader_id`` — and
  next tick's succession phase (phase 2) seats the heir.
* **Providers at war** — a committed off-map people whose patron is at war sends
  a real host to the front (fighting with unit-type modifiers — mûmakil, cavalry,
  auxiliaries), except the **Corsairs**, who never march overland: they strike
  **coastal raids** at an enemy's shore, pillaging without seizing any seat.

Every outcome-deciding comparison is **integer/fixed-point** (the float-determinism
policy): effective strengths are permille-scaled integers, the battle swing and
the death checks are integer ``randrange`` draws, and siege progress is integer
addition. **Canonicity never touches the dice** — it weights only phase-2 intents
(who musters, who attacks); battles are honest. Like every territory-touching
phase, war reaches the map through the live ``world.grid`` handle (ADR-0004) and
is a no-op when no grid is attached.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from .armies import (
    ARMY_DISBANDED_EVENT,
    ARMY_MUSTERED_EVENT,
    Army,
    armies,
    end_host,
    find_path,
    host_cooldown_years,
)
from .characters import Character, DEATH_EVENT
from .diplomacy import make_peace
from .entities import EntityStatus, Event
from .factions import Faction, Posture, compute_military_strength, factions
from .tiles import Site, Terrain, TileGrid, UNOWNED
from .world import World

# Event types this phase emits.
BATTLE_EVENT = "battle"  # two hosts met in the field
EVASION_EVENT = "evasion"  # an outmatched host refused battle and slipped away
SIEGE_EVENT = "siege"  # a host invests / storms a fortified seat
CONQUEST_EVENT = "conquest"  # a seat fell and a realm's land changed hands
RAZING_EVENT = "razing"  # a captured land was laid waste rather than held
COASTAL_RAID_EVENT = "coastal_raid"  # corsairs pillaged an enemy shore

# -- effective-strength tuning (permille; 1000 = ×1.0) --------------------
#
# Effective strength is ``size`` scaled by a chain of permille multipliers. Size
# dominates — the modifiers only tilt an even fight — so the bigger host usually
# wins, but never certainly (see the battle swing below).

_UNIT = 1000

# Leadership: a good general is worth a fraction more than his numbers; a
# leaderless host fights at a discount. martial+leadership runs ~0..200.
_LEADER_BASE = 800
_LEADER_SLOPE = 2  # permille per point of (martial + leadership)
_LEADERLESS = 750

# Terrain favours a *defender* dug into rough ground (open plains are neutral).
_TERRAIN_DEFENCE: Dict[Terrain, int] = {
    Terrain.MOUNTAIN: 1300,
    Terrain.HILLS: 1200,
    Terrain.FOREST: 1150,
    Terrain.MARSH: 1100,
    Terrain.RIVER: 1100,
}

# Posture: an aggressive host presses the attack; a defensive one holds ground.
_POSTURE_ATTACK = {Posture.AGGRESSIVE.value: 1100}
_POSTURE_DEFENCE = {Posture.DEFENSIVE.value: 1150}

# Provider unit profiles → an effective-strength bonus. mûmakil are shock troops,
# Easterling cavalry hit hard in the open, Variag auxiliaries add flat weight.
_PROVIDER_UNIT_BONUS: Dict[str, int] = {
    "mumakil": 6,  # permille per point of output weight
    "cavalry": 3,
    "heavy_infantry": 2,
    "infantry": 1,
    "auxiliaries": 1,
    "raiders": 2,
}

# -- battle-resolution tuning (integer) -----------------------------------

# One bounded roll swings the field by ±this percent. The single draw tilts the
# *ratio* both ways at once — it lifts one side while it drops the other — so the
# stronger host usually prevails, an even fight is a true coin toss, and a moderate
# edge can still be overturned by a bold stroke. The ratio decides, not a flip.
_BATTLE_SWING = 35

# Outcome tiers by the winner-to-loser effective-strength ratio (×100).
_DECISIVE_RATIO = 200  # winner ≥ 2× loser → a rout

# Casualties as a percent of each side's *size*, by tier. The loser always bleeds
# harder; even a decisive victor loses some men. Tuned up for issue #13 so a
# decisive clash *shatters* the broken host in one stroke — a real turning point,
# not an indecisive bleed that limps home to re-fight.
_CASUALTY_WINNER = {"decisive": 8, "marginal": 15}
_CASUALTY_LOSER = {"decisive": 75, "marginal": 35}

# Destruction is **proportional** to a host's own mustered strength (issue #13): a
# host cut below this percent of the strength it took the field with is wiped out,
# not merely beaten — so one key battle can end a war. A small absolute floor keeps
# the rule sensible for tiny/bare hosts whose mustered strength wasn't recorded.
_DESTROY_FRACTION = 25
_DESTROY_FLOOR = 100

# -- evasion tuning (giving vs. refusing battle, issue #13) ----------------
#
# Before a shared-tile clash, a *defender* whose pursuer's effective strength
# exceeds its own by more than this ratio (×100 → 150 = 1.5×) tries to slip away
# rather than give battle. An aggressor pressing its objective never evades, nor
# does a host defending its own seat or with nowhere to run. Escape is a seeded,
# can-fail contest: succeed → withdraw a tile toward home, no battle; fail → be
# caught and fight at a disorder penalty. Traits bite here — the evader's general
# lends leadership+guile, and a faster host outruns a slower pursuer.
_EVASION_THRESHOLD = 150  # pursuer must be >1.5× the evader's strength to prompt flight
_EVASION_BASE = 40  # base escape odds (percent)
_EVASION_PACE_DIV = 8  # +1 odds per this much miles/year the evader is faster
_EVASION_LEADER_DIV = 8  # +1 odds per this much (leadership + guile) of the evader's general
_EVASION_EDGE_DIV = 6  # -1 odds per this much percent the pursuer outmatches the evader
_EVASION_ODDS_MIN = 5
_EVASION_ODDS_MAX = 90
_DISORDER_PENALTY = 850  # permille strength of a host caught after a failed evasion

# -- siege tuning (integer) -----------------------------------------------

# Fortification each seat kind resists a siege with (progress needed to take it).
_FORTIFICATION: Dict[str, int] = {
    "city": 800,
    "gate": 700,
    "volcano": 900,
    "fort": 500,
    "town": 250,
    "pass": 200,
    "ruin": 100,
    "gateway": 100,
}
_FORT_DEFAULT = 300

# Per-tick siege progress: a base effort, plus a slice of the besieger's size,
# plus a bounded seeded roll — so a strong host storms a seat in a few months and
# a weak one grinds, and a siege always spans multiple ticks.
_SIEGE_BASE = 60
_SIEGE_SIZE_DIV = 50
_SIEGE_JITTER = 60

# -- named-death tuning (basis points, /10000) ----------------------------

# Base per-battle death chance for a named leader, by which side they were on.
_DEATH_BP_WINNER = 150
_DEATH_BP_LOSER = 900
_DEATH_BP_STORMED = 1500  # a ruler whose city is stormed
# Each point of martial shaves this many bp off the chance (a hardened warrior is
# harder to kill); floored so a death is never impossible.
_DEATH_MARTIAL_SLOPE = 6
_DEATH_BP_FLOOR = 20

# -- provider-war tuning --------------------------------------------------

_PROVIDER_MUSTER_MIN = 20  # commitment a provider needs before it sends a host
_RAID_DAMAGE = 4  # military-strength a coastal raid pillages from its target
_RAID_BASE_ODDS = 25  # base per-year chance a committed corsair puts to sea
_RAID_ODDS_PER_COMMIT = 1  # ...rising this much per point of commitment (capped)
_RAID_ODDS_CAP = 75


# =========================================================================
# The phase
# =========================================================================

def war(world: World, rng: random.Random) -> List[Event]:
    """Phase 5: resolve field battles, press sieges, and loose the providers.

    Deterministic given the world and RNG: hosts, sieges, and providers are each
    processed in a fixed id/tile order, and every draw is an integer. A no-op
    (drawing no RNG) on a tick with no fighting anywhere, and inert without a grid.
    """
    grid = world.grid
    if grid is None:
        return []
    events: List[Event] = []
    events.extend(_muster_providers(world, grid))
    events.extend(_field_battles(world, grid, rng))
    events.extend(_sieges(world, grid, rng))
    events.extend(_coastal_raids(world, grid, rng))
    return events


# =========================================================================
# Field battles — enemy hosts meeting on or beside a tile
# =========================================================================

def _field_battles(world: World, grid: TileGrid, rng: random.Random) -> List[Event]:
    """Resolve every clash between at-war hosts that share or border a tile.

    Pairs are found in a fixed order (by the lower army's tile then id) and each
    host fights at most once a tick; a host destroyed or routed early is spent.
    """
    events: List[Event] = []
    spent: set = set()
    live = armies(world, alive_only=True)
    for i, a in enumerate(live):
        if a.id in spent:
            continue
        for b in live[i + 1 :]:
            if b.id in spent or a.id in spent:
                continue
            if not _hosts_engage(world, grid, a, b):
                continue
            attacker, defender = _sides(world, grid, a, b)
            events.extend(_resolve_engagement(world, grid, rng, attacker, defender))
            spent.add(a.id)
            spent.add(b.id)
            break
    return events


def _resolve_engagement(
    world: World, grid: TileGrid, rng: random.Random, attacker: Army, defender: Army
) -> List[Event]:
    """Give or refuse battle: an outmatched defender may slip away before it clashes.

    A defender the attacker outmatches by more than :data:`_EVASION_THRESHOLD`
    attempts a seeded evasion (unless it is defending its own seat or has nowhere to
    run — an aggressor never evades). Success → it withdraws a tile toward home and
    no battle is fought; failure → it is caught and fights at a disorder penalty.
    """
    outcome = _attempt_evasion(world, grid, rng, attacker, defender)
    if outcome == "escaped":
        return [_evasion_event(world, attacker, defender)]
    disordered = defender if outcome == "caught" else None
    return _resolve_battle(world, grid, rng, attacker, defender, seat_site=None, disordered=disordered)


def _attempt_evasion(
    world: World, grid: TileGrid, rng: random.Random, attacker: Army, defender: Army
) -> str:
    """Decide the defender's evasion: ``"escaped"``, ``"caught"``, or ``"stand"``.

    Draws the seeded escape roll only when the defender is genuinely outmatched and
    *able* to run, so a battle that was always going to be fought perturbs no RNG
    beyond the clash itself. On ``"escaped"`` the defender is stepped one tile home.
    """
    a_eff = _effective_strength(world, grid, attacker, defending=False)
    d_eff = _effective_strength(world, grid, defender, defending=True)
    if a_eff * 100 <= d_eff * _EVASION_THRESHOLD:  # not outmatched enough to flee
        return "stand"
    retreat = _retreat_step(world, grid, defender)
    if retreat is None:  # defending its seat, or nowhere to run — it must give battle
        return "stand"
    if rng.randrange(100) < _evasion_odds(world, attacker, defender, a_eff, d_eff):
        _withdraw_to(world, defender, retreat)
        return "escaped"
    return "caught"


def _evasion_odds(
    world: World, attacker: Army, defender: Army, a_eff: int, d_eff: int
) -> int:
    """Integer percent chance an outmatched defender slips away (bounded).

    Raised by the evader's pace edge over the pursuer and by its general's
    leadership+guile (traits with bite); lowered by how badly the pursuer outmatches
    it. All integer — no float reaches the roll.
    """
    odds = _EVASION_BASE
    odds += (defender.miles_per_year - attacker.miles_per_year) // _EVASION_PACE_DIV
    general = world.entities.get(defender.leader_id) if defender.leader_id else None
    if isinstance(general, Character) and general.alive:
        rally = int(general.traits.get("leadership", 0)) + int(general.traits.get("guile", 0))
        odds += rally // _EVASION_LEADER_DIV
    edge_percent = a_eff * 100 // max(1, d_eff) - 100  # how far over the evader the pursuer is
    odds -= edge_percent // _EVASION_EDGE_DIV
    return max(_EVASION_ODDS_MIN, min(_EVASION_ODDS_MAX, odds))


def _retreat_step(world: World, grid: TileGrid, army: Army) -> Optional[Tuple[int, int]]:
    """The first tile of the path home for a host that would flee, or ``None`` when
    it cannot evade — it stands on its own capital seat (besieged) or has no path home."""
    faction = _faction(world, army.faction_id)
    if faction is None:
        return None
    home = _site_tile(grid, faction.capital_location_id)
    if home is None or (army.col, army.row) == home:  # no seat, or defending it
        return None
    path = find_path(grid, (army.col, army.row), home)
    if not path:
        return None
    return (path[0][0], path[0][1])


def _withdraw_to(world: World, army: Army, tile: Tuple[int, int]) -> None:
    """Step a fleeing host one tile toward home and set it marching the rest of the
    way (path reassigned fresh — snapshot-safe), abandoning any objective/siege."""
    grid = world.grid
    army.col, army.row = tile
    army.target_faction_id = None
    army.dest_site_id = None
    army.siege_progress = 0
    faction = _faction(world, army.faction_id)
    home = _site_tile(grid, faction.capital_location_id) if faction is not None else None
    army.path = find_path(grid, (army.col, army.row), home) if (grid is not None and home) else []


def _evasion_event(world: World, attacker: Army, defender: Army) -> Event:
    """The annal of a host refusing battle and slipping away before the clash."""
    return world.new_event(
        type=EVASION_EVENT,
        subject_ids=_army_and_factions(
            defender, _faction(world, defender.faction_id), _faction(world, attacker.faction_id)
        ),
        location_id=None,
        payload={
            "evader_faction_id": defender.faction_id,
            "pursuer_faction_id": attacker.faction_id,
        },
    )


def _hosts_engage(world: World, grid: TileGrid, a: Army, b: Army) -> bool:
    """Whether two hosts fight this tick: at-war factions sharing the **same tile**.

    Adjacency no longer triggers a clash (issue #13) — battles concentrate where
    hosts actually *meet*, so incidental border skirmishes vanish and the few
    battles that do fire are the decisive ones. (Providers fight their patron's wars.)
    """
    fa, fb = _faction(world, a.faction_id), _faction(world, b.faction_id)
    if fa is None or fb is None or fa.id == fb.id:
        return False
    if not _factions_at_war(world, fa, fb):
        return False
    return a.col == b.col and a.row == b.row


def _sides(world: World, grid: TileGrid, a: Army, b: Army) -> Tuple[Army, Army]:
    """(attacker, defender): the host on friendly soil defends (and earns the
    terrain bonus); failing that, the lower id defends — a deterministic choice."""
    a_home = grid.owner_at(a.col, a.row) == a.faction_id
    b_home = grid.owner_at(b.col, b.row) == b.faction_id
    if b_home and not a_home:
        return a, b
    if a_home and not b_home:
        return b, a
    return (a, b) if a.id > b.id else (b, a)  # lower id defends


# =========================================================================
# Battle resolution (shared by field battles and the storming of a seat)
# =========================================================================

def _resolve_battle(
    world: World,
    grid: TileGrid,
    rng: random.Random,
    attacker: Army,
    defender: Army,
    seat_site: Optional[Site],
    disordered: Optional[Army] = None,
) -> List[Event]:
    """Fight one battle to a decision and emit its ``battle`` event plus any deaths.

    ``seat_site`` (a :class:`~arda_sim.tiles.Site` or ``None``) adds a
    fortification bonus to the defender when the clash is at a defended seat.
    ``disordered`` (a host caught after a failed evasion) fights at a strength
    penalty.
    """
    a_eff = _effective_strength(world, grid, attacker, defending=False)
    d_eff = _effective_strength(world, grid, defender, defending=True)
    if seat_site is not None:
        d_eff += d_eff * fortification(seat_site) // _FORT_DEFAULT
    if disordered is attacker:
        a_eff = a_eff * _DISORDER_PENALTY // _UNIT
    elif disordered is defender:
        d_eff = d_eff * _DISORDER_PENALTY // _UNIT

    swing = rng.randrange(-_BATTLE_SWING, _BATTLE_SWING + 1)
    a_roll = a_eff * (100 + swing) // 100  # the roll lifts one side...
    d_roll = d_eff * (100 - swing) // 100  # ...and drops the other, from one draw
    if a_roll >= d_roll:
        winner, loser, w_eff, l_eff = attacker, defender, a_roll, d_roll
    else:
        winner, loser, w_eff, l_eff = defender, attacker, d_roll, a_roll

    tier = "decisive" if l_eff <= 0 or w_eff * 100 >= l_eff * _DECISIVE_RATIO else "marginal"
    w_cas = winner.size * _CASUALTY_WINNER[tier] // 100
    l_cas = loser.size * _CASUALTY_LOSER[tier] // 100
    winner.size = max(0, winner.size - w_cas)
    loser.size = max(0, loser.size - l_cas)

    events: List[Event] = [
        world.new_event(
            type=BATTLE_EVENT,
            subject_ids=_battle_subjects(winner, loser),
            location_id=(seat_site.id if seat_site is not None else None),
            payload={
                "winner_faction_id": winner.faction_id,
                "loser_faction_id": loser.faction_id,
                "winner_army_id": winner.id,
                "loser_army_id": loser.id,
                "tier": tier,
                "winner_casualties": w_cas,
                "loser_casualties": l_cas,
            },
        )
    ]
    # The broken host retreats toward home, or is destroyed if it is shattered —
    # cut below a fraction of the strength it mustered with (issue #13).
    destroy_floor = max(_DESTROY_FLOOR, loser.mustered_size * _DESTROY_FRACTION // 100)
    if loser.size <= destroy_floor:
        events.append(_destroy_host(world, loser))
    else:
        _retreat(world, grid, loser)
    # Named leaders may fall — far likelier on the losing side.
    events.extend(_roll_battle_deaths(world, rng, winner, loser, tier))
    return events


def _effective_strength(
    world: World, grid: TileGrid, army: Army, *, defending: bool
) -> int:
    """A host's fighting weight: ``size`` scaled by leader, provider, and (for the
    defender) terrain/posture multipliers — all integer permille."""
    eff = army.size * _UNIT
    leader = world.entities.get(army.leader_id) if army.leader_id else None
    eff = eff * _leader_factor(leader) // _UNIT
    faction = _faction(world, army.faction_id)
    if faction is not None and faction.is_provider:
        eff = eff * _provider_factor(faction) // _UNIT
    if faction is not None:
        posture_map = _POSTURE_DEFENCE if defending else _POSTURE_ATTACK
        eff = eff * posture_map.get(faction.posture, _UNIT) // _UNIT
    if defending:
        terrain = grid.terrain_at(army.col, army.row)
        eff = eff * _TERRAIN_DEFENCE.get(terrain, _UNIT) // _UNIT
    return eff


def _leader_factor(leader: Optional[object]) -> int:
    """Permille strength multiplier a general lends (a leaderless host is docked)."""
    if not isinstance(leader, Character) or not leader.alive:
        return _LEADERLESS
    martial = int(leader.traits.get("martial", 0))
    leadership = int(leader.traits.get("leadership", 0))
    return _LEADER_BASE + (martial + leadership) * _LEADER_SLOPE


def _provider_factor(faction: Faction) -> int:
    """Permille multiplier from a provider's unit-type ``output`` profile."""
    bonus = 0
    for unit, weight in faction.output.items():
        bonus += _PROVIDER_UNIT_BONUS.get(unit, 0) * int(weight)
    return _UNIT + bonus


def fortification(site: Site) -> int:
    """The siege resistance of a seat, by its kind (unknown kinds get a modest wall)."""
    return _FORTIFICATION.get(site.kind, _FORT_DEFAULT)


# =========================================================================
# Sieges — investing and storming a fortified enemy seat
# =========================================================================

def _sieges(world: World, grid: TileGrid, rng: random.Random) -> List[Event]:
    """Advance every siege: a host standing on an at-war enemy's capital seat.

    Progress accumulates on the besieging host across ticks; when it tops the
    seat's fortification the realm is conquered. Processed in host id order.
    """
    events: List[Event] = []
    seat_index = _capital_seats(world)  # (col,row) -> (faction, site)
    for army in armies(world, alive_only=True):
        if not army.alive:  # a host disbanded earlier this phase is skipped
            continue
        target = seat_index.get((army.col, army.row))
        if target is None:
            army.siege_progress = 0  # not besieging anything
            continue
        besieged, seat = target
        attacker = _faction(world, army.faction_id)
        if attacker is None or not _factions_at_war(world, attacker, besieged):
            army.siege_progress = 0
            continue
        events.extend(_press_siege(world, grid, rng, army, attacker, besieged, seat))
    return events


def _press_siege(
    world: World,
    grid: TileGrid,
    rng: random.Random,
    army: Army,
    attacker: Faction,
    besieged: Faction,
    seat: Site,
) -> List[Event]:
    """Add this tick's progress; when the wall breaks, storm and conquer the seat."""
    inc = _SIEGE_BASE + army.size // _SIEGE_SIZE_DIV + rng.randrange(_SIEGE_JITTER)
    army.siege_progress += inc
    if army.siege_progress < fortification(seat):
        return [
            world.new_event(
                type=SIEGE_EVENT,
                subject_ids=_army_and_factions(army, attacker, besieged),
                location_id=seat.id,
                payload={
                    "besieger_faction_id": attacker.id,
                    "besieged_faction_id": besieged.id,
                    "progress": army.siege_progress,
                    "required": fortification(seat),
                },
            )
        ]
    # The seat falls: conquer the realm, maybe raze it, and slay a ruler at bay.
    army.siege_progress = 0
    return _conquer(world, grid, rng, army, attacker, besieged, seat)


def _conquer(
    world: World,
    grid: TileGrid,
    rng: random.Random,
    army: Army,
    attacker: Faction,
    besieged: Faction,
    seat: Site,
) -> List[Event]:
    """Flip the fallen realm's land to the victor (or lay it waste) and end its wars."""
    events: List[Event] = []
    raze = _will_raze(attacker)
    region_ids = _owned_region_ids(grid, besieged.id)
    new_owner = UNOWNED if raze else attacker.id
    _transfer_faction_tiles(grid, besieged.id, new_owner)
    if raze:
        # The stormed seat is thrown down — it drops to a ruin that peacetime
        # construction (ticket 12) can raise again once someone holds the land.
        grid.set_site(seat.id, "ruin", 0)

    events.append(
        world.new_event(
            type=CONQUEST_EVENT,
            subject_ids=[besieged.id, attacker.id],
            location_id=seat.id,
            payload={
                "conqueror_faction_id": attacker.id,
                "razed": raze,
                "regions": region_ids,
            },
        )
    )
    if raze:
        events.append(
            world.new_event(
                type=RAZING_EVENT,
                subject_ids=[besieged.id, attacker.id],
                location_id=seat.id,
                payload={"razer_faction_id": attacker.id, "regions": region_ids},
            )
        )
    # A ruler present at the storming may be cut down (→ succession next tick).
    ruler = world.entities.get(besieged.leader_id) if besieged.leader_id else None
    if isinstance(ruler, Character) and ruler.alive:
        death = _maybe_slay(world, rng, ruler, _DEATH_BP_STORMED)
        if death is not None:
            events.append(death)
    # The realm has no ground left: extinguish it (dormant claim kept) and end its wars.
    if _owned_tile_count(grid, besieged.id) == 0:
        events.extend(_extinguish(world, besieged, region_ids))
    # The victor annexes the seat as friendly soil, so it refreshes its strength.
    _refresh_strength(world, attacker, grid)
    return events


def _will_raze(attacker: Faction) -> bool:
    """Whether a conqueror lays the land waste rather than holding it.

    Ruthless powers (aggressive posture or a high war-drive) raze; realms that
    mean to *rule* what they take hold the seat intact — the seam that lets an
    Isengard seize the Shire whole and an Orc-host leave only ruin behind.
    """
    return attacker.posture == Posture.AGGRESSIVE.value or attacker.aggression >= 80


def _extinguish(world: World, faction: Faction, region_ids: List[int]) -> List[Event]:
    """Tombstone a realm that has lost all its land, keeping a dormant claim and
    ending every war it was party to (mirrors a failed line's extinction)."""
    events: List[Event] = []
    for enemy_id in list(faction.at_war_with):
        enemy = _faction(world, enemy_id)
        if enemy is not None:
            peace = make_peace(world, faction, enemy)
            if peace is not None:
                events.append(peace)
    faction.status = EntityStatus.DEAD.value
    faction.military_strength = 0
    faction.claim_region_ids = sorted(set(faction.claim_region_ids) | set(region_ids))
    # Its hosts, now homeless, disband.
    for host in armies(world, alive_only=True):
        if host.faction_id == faction.id:
            events.append(_destroy_host(world, host))
    return events


# =========================================================================
# Providers at war — hosts to the front, corsairs to the shore
# =========================================================================

def _muster_providers(world: World, grid: TileGrid) -> List[Event]:
    """Send a host from each committed land-provider whose patron is at war.

    A no-op for a provider already fielding a host, one below the commitment
    floor, or a naval people (the Corsairs, who raid instead — see below).
    """
    events: List[Event] = []
    for provider in factions(world, alive_only=True):
        if not provider.is_provider or _is_naval(provider):
            continue
        if provider.commitment < _PROVIDER_MUSTER_MIN:
            continue
        patron = _faction(world, provider.allegiance_faction_id)
        if patron is None or not patron.at_war_with:
            continue
        if _has_host(world, provider.id):
            continue
        if world.current_year < provider.muster_cooldown_until:
            continue  # a spent host still resting — the same cadence gate realms use
        host = _spawn_provider_host(world, grid, provider, patron)
        if host is not None:
            events.append(host)
    return events


def _spawn_provider_host(
    world: World, grid: TileGrid, provider: Faction, patron: Faction
) -> Optional[Event]:
    """Raise a provider-flagged host at the gateway, marching on the patron's foe."""
    gateway = _site_tile(grid, provider.gateway_location_id)
    if gateway is None:
        return None
    enemy = _patron_enemy(world, patron)
    dest_site_id: Optional[int] = None
    path: List[List[int]] = []
    if enemy is not None and enemy.capital_location_id is not None:
        dest = _site_tile(grid, enemy.capital_location_id)
        if dest is not None:
            candidate = find_path(grid, gateway, dest)
            if candidate:
                dest_site_id = enemy.capital_location_id
                path = candidate
    size = max(1, provider.commitment) * 20
    army = Army(
        id=world.next_id(),
        kind="army",
        name=f"Host of the {provider.name}",
        created_year=world.current_year,
        faction_id=provider.id,
        col=gateway[0],
        row=gateway[1],
        size=size,
        target_faction_id=enemy.id if (enemy is not None and path) else None,
        dest_site_id=dest_site_id,
        path=path,
        contributor_ids=[provider.id],
        cooldown_years=host_cooldown_years(size),
        prominence=provider.prominence,
    )
    world.entities[army.id] = army
    payload: Dict[str, object] = {"size": size, "faction_id": provider.id, "led": False}
    if army.target_faction_id is not None:
        payload["target_faction_id"] = army.target_faction_id
    return world.new_event(
        type=ARMY_MUSTERED_EVENT,
        subject_ids=[army.id, provider.id],
        location_id=provider.gateway_location_id,
        payload=payload,
    )


def _coastal_raids(world: World, grid: TileGrid, rng: random.Random) -> List[Event]:
    """Loose each naval provider whose patron is at war against an enemy shore.

    A raid pillages — it dents the target's strength and reads in the annals — but
    seizes no seat: providers hold no territory (the Corsairs-of-Umbar path). A
    raiding season is *occasional*, not perpetual: each committed corsair puts to
    sea on at most one seeded roll a year (odds rising with commitment), so the
    shores are harried in bursts rather than every single month.
    """
    events: List[Event] = []
    if world.month != 1:  # a once-a-year raiding season (the clock is monthly)
        return events
    coast = _coastal_owners(grid)  # faction id -> a representative coast site id
    for provider in factions(world, alive_only=True):
        if not provider.is_provider or not _is_naval(provider):
            continue
        if provider.commitment < _PROVIDER_MUSTER_MIN:
            continue
        patron = _faction(world, provider.allegiance_faction_id)
        if patron is None:
            continue
        target = _coastal_enemy(world, patron, coast)
        if target is None:
            continue
        odds = min(_RAID_ODDS_CAP, _RAID_BASE_ODDS + provider.commitment * _RAID_ODDS_PER_COMMIT)
        if rng.randrange(100) >= odds:  # the season passed without a raid
            continue
        target.military_strength = max(0, target.military_strength - _RAID_DAMAGE)
        events.append(
            world.new_event(
                type=COASTAL_RAID_EVENT,
                subject_ids=[provider.id, target.id],
                location_id=coast.get(target.id),
                payload={
                    "raider_faction_id": provider.id,
                    "target_faction_id": target.id,
                    "damage": _RAID_DAMAGE,
                },
            )
        )
    return events


# =========================================================================
# Named death
# =========================================================================

def _roll_battle_deaths(
    world: World, rng: random.Random, winner: Army, loser: Army, tier: str
) -> List[Event]:
    """Roll the field death of each host's general — heavier on the broken side."""
    events: List[Event] = []
    for army, base in ((loser, _DEATH_BP_LOSER), (winner, _DEATH_BP_WINNER)):
        leader = world.entities.get(army.leader_id) if army.leader_id else None
        if isinstance(leader, Character) and leader.alive:
            death = _maybe_slay(world, rng, leader, base)
            if death is not None:
                events.append(death)
    return events


def _maybe_slay(
    world: World, rng: random.Random, char: Character, base_bp: int
) -> Optional[Event]:
    """Roll one integer death check; on a hit, tombstone the character in battle.

    The chance is ``base_bp`` blunted by the character's ``martial`` and floored,
    so even the mightiest is never wholly safe. A ruler slain here vacates
    ``leader_id``; the succession phase seats the heir on the next tick.
    """
    martial = int(char.traits.get("martial", 0))
    bp = max(_DEATH_BP_FLOOR, base_bp - martial * _DEATH_MARTIAL_SLOPE)
    if rng.randrange(10_000) >= bp:
        return None
    char.status = EntityStatus.DEAD.value
    return world.new_event(
        type=DEATH_EVENT,
        subject_ids=[char.id],
        location_id=char.location_id,
        payload={
            "cause": "killed_in_battle",
            "age": char.age(world.current_year),
            "race": char.race,
        },
    )


# =========================================================================
# Territory & host helpers (read/write world.grid)
# =========================================================================

def _capital_seats(world: World) -> Dict[Tuple[int, int], Tuple[Faction, Site]]:
    """``(col,row) -> (faction, seat site)`` for every active realm with a capital."""
    grid = world.grid
    index: Dict[Tuple[int, int], Tuple[Faction, Site]] = {}
    if grid is None:
        return index
    for faction in factions(world, alive_only=True):
        if faction.capital_location_id is None:
            continue
        site = grid.site_by_id(faction.capital_location_id)
        if site is not None:
            index[(site.col, site.row)] = (faction, site)
    return index


def _owned_region_ids(grid: TileGrid, faction_id: int) -> List[int]:
    """The config-space region ids the faction holds any tile of (sorted)."""
    ids = set()
    for i, owner in enumerate(grid.owner):
        if owner == faction_id:
            rid = grid.region_of[i]
            if rid:
                ids.add(rid)
    return sorted(ids)


def _owned_tile_count(grid: TileGrid, faction_id: int) -> int:
    return sum(1 for owner in grid.owner if owner == faction_id)


def _transfer_faction_tiles(grid: TileGrid, from_id: int, to_id: int) -> None:
    """Flip every tile owned by ``from_id`` to ``to_id`` (conquest / laying waste)."""
    grid.owner = [to_id if owner == from_id else owner for owner in grid.owner]


def _refresh_strength(world: World, faction: Faction, grid: TileGrid) -> None:
    """Recompute a faction's cached military strength after a territory change."""
    leader = world.entities.get(faction.leader_id) if faction.leader_id else None
    tiles = _owned_tile_count(grid, faction.id)
    faction.military_strength = compute_military_strength(faction, tiles, leader)


def _retreat(world: World, grid: TileGrid, army: Army) -> None:
    """Send a beaten host fleeing toward its own capital (path reassigned fresh)."""
    army.siege_progress = 0
    army.target_faction_id = None
    army.dest_site_id = None
    faction = _faction(world, army.faction_id)
    home = _site_tile(grid, faction.capital_location_id) if faction is not None else None
    army.path = find_path(grid, (army.col, army.row), home) if home is not None else []


def _destroy_host(world: World, army: Army) -> Event:
    """Tombstone a host wiped out in battle, emitting its disband event."""
    army.status = EntityStatus.DEAD.value
    army.siege_progress = 0
    end_host(world, army)  # its contributors now rest under a muster cooldown
    return world.new_event(
        type=ARMY_DISBANDED_EVENT,
        subject_ids=_army_and_factions(army, _faction(world, army.faction_id), None),
        location_id=None,
        payload={"cause": "destroyed_in_battle", "faction_id": army.faction_id},
    )


def _coastal_owners(grid: TileGrid) -> Dict[int, int]:
    """``faction id -> a coast site id`` for every faction owning a tile by the Sea.

    A cheap single scan: a tile is coastal if it borders a Sea tile. The site id
    is only for the raid event's ``location_id`` (its shore), so any owned coastal
    site of that faction will do — the lowest keeps it deterministic.
    """
    coastal_factions: set = set()
    for row in range(grid.height):
        for col in range(grid.width):
            owner = grid.owner_at(col, row)
            if owner == UNOWNED:
                continue
            if any(grid.terrain_at(nc, nr) == Terrain.SEA for nc, nr in grid.neighbors(col, row)):
                coastal_factions.add(owner)
    result: Dict[int, int] = {}
    for site in grid.sites:
        owner = grid.owner_at(site.col, site.row)
        if owner in coastal_factions and owner not in result:
            result[owner] = site.id
    # Factions with coast but no site on it still count (location_id falls back to None).
    for fid in coastal_factions:
        result.setdefault(fid, None)  # type: ignore[arg-type]
    return result


# =========================================================================
# Faction / war lookups
# =========================================================================

def _factions_at_war(world: World, a: Faction, b: Faction) -> bool:
    """Whether two factions fight — either directly, or one as a provider's patron.

    A provider has no ``at_war_with`` of its own; it fights the wars of the patron
    it is pledged to, so a Haradrim host counts as at war with Gondor when Mordor is.
    """
    if a.is_at_war_with(b.id):
        return True
    pa = _patron(world, a)
    pb = _patron(world, b)
    if pa is not None and pa.is_at_war_with(b.id):
        return True
    if pb is not None and pb.is_at_war_with(a.id):
        return True
    if pa is not None and pb is not None and pa.is_at_war_with(pb.id):
        return True
    return False


def _patron(world: World, faction: Faction) -> Optional[Faction]:
    """The realm a provider fights for (``None`` for a non-provider)."""
    if not faction.is_provider:
        return None
    return _faction(world, faction.allegiance_faction_id)


def _patron_enemy(world: World, patron: Faction) -> Optional[Faction]:
    """A seated realm the patron is at war with (lowest id), for a provider to march on."""
    for enemy_id in patron.at_war_with:  # sorted ascending
        enemy = _faction(world, enemy_id)
        if enemy is not None and enemy.alive and not enemy.is_provider and enemy.capital_location_id is not None:
            return enemy
    return None


def _coastal_enemy(
    world: World, patron: Faction, coast: Dict[int, int]
) -> Optional[Faction]:
    """The strongest coast-holding realm the patron is at war with (id breaks ties)."""
    best: Optional[Faction] = None
    for enemy_id in patron.at_war_with:
        enemy = _faction(world, enemy_id)
        if enemy is None or not enemy.alive or enemy.is_provider:
            continue
        if enemy.id not in coast:
            continue
        if best is None or (enemy.military_strength, -enemy.id) > (best.military_strength, -best.id):
            best = enemy
    return best


def _is_naval(faction: Faction) -> bool:
    """Whether a provider fights from the sea (corsairs) rather than marching.

    Keyed on ``ships`` alone — ``raiders`` is also a *land* unit-modifier key
    (:data:`_PROVIDER_UNIT_BONUS`), so it can't stand in for "naval" too.
    """
    return "ships" in faction.output


def _has_host(world: World, faction_id: int) -> bool:
    return any(a.faction_id == faction_id for a in armies(world, alive_only=True))


def _site_tile(grid: TileGrid, site_id: Optional[int]) -> Optional[Tuple[int, int]]:
    if site_id is None:
        return None
    site = grid.site_by_id(site_id)
    return (site.col, site.row) if site is not None else None


def _faction(world: World, faction_id: Optional[int]) -> Optional[Faction]:
    if faction_id is None:
        return None
    entity = world.entities.get(faction_id)
    return entity if isinstance(entity, Faction) else None


# =========================================================================
# Event subject helpers
# =========================================================================

def _battle_subjects(winner: Army, loser: Army) -> List[int]:
    """Both hosts and both factions name a battle (so it reads on every timeline)."""
    subjects = [winner.id, loser.id]
    for fid in (winner.faction_id, loser.faction_id):
        if fid is not None:
            subjects.append(fid)
    return subjects


def _army_and_factions(
    army: Army, a: Optional[Faction], b: Optional[Faction]
) -> List[int]:
    """A host followed by the factions naming its event, de-duplicated in order."""
    subjects = [army.id]
    for f in (a, b):
        if f is not None and f.id not in subjects:
            subjects.append(f.id)
    return subjects
