"""Diplomacy & vassalage — how powers relate in peace and bind together (ticket 09).

Phase 3 of the tick. It **evolves** the per-pair :attr:`Faction.disposition`
scalar and derives a discrete :func:`stance` from it, forms the peaceful bonds
between realms — treaties, dynastic marriages, vassalage, provider-pacts — and
owns the formal *state* of war: it sets and clears the symmetric at-war flag
(ticket 11's war phase produces the fighting; peace is deferred there too — this
ticket only builds :func:`make_peace` as the seam 11 will call).

Two forces move disposition:

* **Background drift**, once a year (gated on the year boundary, since the clock
  is monthly — ADR-0003): every live entry decays a small integer step toward its
  frozen authored **baseline** (ADR-0005), and every pair of factions whose land
  touches and who are *not* bound by treaty or vassalage suffers a little
  **border friction**.
* **Event jumps**, whenever a bond forms or breaks: a marriage, treaty, or
  vassalage warms a pair; a declaration of war — or, worse, a *betrayal* of a
  standing pact — sours it hard.

The active moves are driven by phase 2's ``current_intent``: a faction that chose
``SEEK_PACT`` courts its warmest eligible neighbour down a fixed ladder
(provider-pact → vassalage offer → marriage → treaty), each attempt a seeded
integer roll so bonds form organically rather than the instant a threshold is
crossed; a faction that chose ``ATTACK`` declares war on its target. The phase is
a pure ``system(world, rng) -> events`` and deterministic under seed.

Disposition and the flag lists are mutated by **reassigning** fresh containers
(never in-place), so a per-tick snapshot taken by the UI keeps the values as they
stood *that* tick rather than aliasing the live, still-evolving maps.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from .characters import RACE_CONFIG, Character, Race, characters, wed
from .entities import Entity, EntityStatus, Event
from .factions import (
    Faction,
    Intent,
    deciding_factions,
    factions,
)
from .tiles import UNOWNED, TileGrid
from .world import World

# Event types this phase emits.
TREATY_EVENT = "treaty"  # a signed pact of alliance between two realms
MARRIAGE_EVENT = "marriage"  # a dynastic union of two houses
VASSALAGE_EVENT = "vassalage"  # a fealty bond formed or thrown off
PROVIDER_PACT_EVENT = "provider_pact"  # a realm deepens/wins an off-map people
WAR_DECLARED_EVENT = "war_declared"  # the at-war flag raised
WAR_ENDED_EVENT = "war_ended"  # the at-war flag cleared (11 wires the trigger)

# Derived stance labels (see :func:`stance`).
ALLIANCE = "alliance"
NEUTRALITY = "neutrality"
HOSTILITY = "hostility"
VASSALAGE = "vassalage"

# -- tuning (all integer; see the ticket-09 grilling for the rationale) ----
_DISP_MIN, _DISP_MAX = -100, 100

# Stance thresholds on the disposition scalar (flags override these).
_ALLIANCE_MIN = 40
_HOSTILITY_MAX = -40

# Background drift, applied once a year.
_DECAY_STEP = 3  # integer step toward baseline per year
_FRICTION = 2  # yearly souring between adjacent, unbound factions

# Event-driven disposition jumps.
_JUMP_MARRIAGE = 30
_JUMP_TREATY = 20
_JUMP_VASSALAGE = 25
_JUMP_WAR = -40
_JUMP_BETRAYAL = -70
_JUMP_SECESSION = -20

# Pact ladder thresholds / gates.
_TREATY_MIN = 40  # disposition needed to court a treaty
_MARRIAGE_MIN = 55  # ...and (higher) for a marriage
_VASSAL_HI = 70  # a would-be vassal must adore its offered overlord this much
_VASSAL_RATIO_DIV = 2  # ...and be under strength(overlord)//this to accept
_BREAK_LO = -30  # a vassal this sour toward its overlord throws off the bond
_PROVIDER_STEP = 10  # commitment gained when a patron deepens a provider-pact
_PROVIDER_MAX = 100

# Canon pressure (issue #5): the canonicity knob softly weights *Free-Peoples*
# alliance formation — a bonus on the treaty/marriage odds when both parties are
# of the free folk — never a forced bond, never a touched die elsewhere.
_CANON_PACT_BONUS = 15  # added to the odds at full canonicity, scaled below it


# =========================================================================
# Derived stance
# =========================================================================

def stance(a: Faction, b: Faction) -> str:
    """The discrete relation *from* ``a`` *toward* ``b`` — a pure function of the
    disposition scalar and the pinned flags (never stored).

    A raised flag beats the scalar: war means hostility, a fealty bond either way
    means vassalage, a signed treaty means alliance. Absent a flag, the scalar
    decides against the alliance/hostility thresholds.
    """
    if a.is_at_war_with(b.id):
        return HOSTILITY
    if a.overlord_faction_id == b.id or b.overlord_faction_id == a.id:
        return VASSALAGE
    disp = a.disposition_toward(b.id)
    if a.has_treaty_with(b.id) or disp >= _ALLIANCE_MIN:
        return ALLIANCE
    if disp <= _HOSTILITY_MAX:
        return HOSTILITY
    return NEUTRALITY


# =========================================================================
# The phase
# =========================================================================

def diplomacy(world: World, rng: random.Random) -> List[Event]:
    """Phase 3: drift dispositions, dissolve stale vassalage, then act on intents.

    Deterministic given the RNG: factions are processed in id order, and each
    draws its per-attempt roll in a fixed sequence. Background drift is gated to
    the year boundary so an integer step is meaningful on the monthly clock.
    """
    events: List[Event] = []
    grid = world.grid

    # Faction adjacency is a full-grid scan; compute it at most once per tick and
    # only when a step actually needs it (border friction, or a vassalage offer).
    _adjacency_cache: Dict[str, Dict[int, set]] = {}

    def adjacency() -> Dict[int, set]:
        if "v" not in _adjacency_cache:
            _adjacency_cache["v"] = _faction_adjacencies(grid)
        return _adjacency_cache["v"]

    if world.month == 1:  # year boundary — background drift
        _decay_toward_baseline(world)
        if grid is not None:
            _apply_border_friction(world, adjacency())

    # A fallen or extinguished overlord, or a soured vassal, ends the bond.
    events.extend(_dissolve_stale_vassalage(world))

    for faction in deciding_factions(world):
        intent = faction.current_intent.get("intent")
        if intent == Intent.ATTACK.value:
            events.extend(_maybe_declare_war(world, faction))
        elif intent == Intent.SEEK_PACT.value:
            events.extend(_pursue_pact(world, rng, faction, adjacency()))
    return events


# =========================================================================
# Background drift
# =========================================================================

def _decay_toward_baseline(world: World) -> None:
    """Step every live disposition entry one increment toward its frozen baseline."""
    for faction in factions(world, alive_only=True):
        if not faction.disposition:
            continue
        moved: Dict[str, int] = {}
        for key, value in faction.disposition.items():
            target = faction.baseline_disposition.get(key, 0)
            moved[key] = _step(value, target, _DECAY_STEP)
        faction.disposition = moved  # reassign (snapshot-safe)


def _apply_border_friction(world: World, adjacency: Dict[int, set]) -> None:
    """Sour each adjacent, unbound faction pair a little (rubbing borders)."""
    for a_id, neighbours in adjacency.items():
        a = _faction(world, a_id)
        if a is None or not a.alive:
            continue
        for b_id in neighbours:
            if b_id <= a_id:  # each unordered pair once; then apply to both
                continue
            b = _faction(world, b_id)
            if b is None or not b.alive:
                continue
            if _bound(a, b):  # allies and lieges don't chafe
                continue
            _adjust(a, b_id, -_FRICTION)
            _adjust(b, a_id, -_FRICTION)


def _bound(a: Faction, b: Faction) -> bool:
    """Whether a treaty or vassalage bond exempts this pair from border friction."""
    return (
        a.has_treaty_with(b.id)
        or a.overlord_faction_id == b.id
        or b.overlord_faction_id == a.id
    )


# =========================================================================
# Vassalage dissolution
# =========================================================================

def _dissolve_stale_vassalage(world: World) -> List[Event]:
    """Break any bond whose overlord has fallen or whom the vassal now resents."""
    events: List[Event] = []
    for vassal in factions(world, alive_only=True):
        overlord_id = vassal.overlord_faction_id
        if overlord_id is None:
            continue
        overlord = _faction(world, overlord_id)
        fallen = overlord is None or not overlord.alive
        resentful = vassal.disposition_toward(overlord_id) <= _BREAK_LO
        if not (fallen or resentful):
            continue
        vassal.overlord_faction_id = None
        if overlord is not None:
            _adjust(vassal, overlord_id, _JUMP_SECESSION)
            if overlord.alive:
                _adjust(overlord, vassal.id, _JUMP_SECESSION)
        events.append(
            world.new_event(
                type=VASSALAGE_EVENT,
                subject_ids=[vassal.id, overlord_id],
                location_id=vassal.capital_location_id,
                payload={"bond": "broken", "overlord_faction_id": overlord_id},
            )
        )
    return events


# =========================================================================
# War declaration (deterministic — phase 2 already made the stochastic choice)
# =========================================================================

def _maybe_declare_war(world: World, faction: Faction) -> List[Event]:
    """Raise the symmetric at-war flag on this faction's ATTACK target.

    A no-op if already at war, or if the target is missing, inactive, a provider
    (providers are never conquest targets), or itself. Declaring on a faction one
    holds a treaty or fealty bond with is a **betrayal**: the pact is torn up and
    disposition sours far harder.
    """
    target_id = faction.current_intent.get("target_faction_id")
    if not target_id or target_id == faction.id:
        return []
    target = _faction(world, target_id)
    if target is None or not target.alive or target.is_provider:
        return []
    if faction.is_at_war_with(target_id):
        return []

    betrayal = _bound(faction, target)
    if betrayal:
        _break_treaty(faction, target)
        _break_vassalage(faction, target)
    _set_at_war(faction, target)
    jump = _JUMP_BETRAYAL if betrayal else _JUMP_WAR
    _adjust(faction, target_id, jump)
    _adjust(target, faction.id, jump)
    return [
        world.new_event(
            type=WAR_DECLARED_EVENT,
            subject_ids=[faction.id, target_id],
            location_id=faction.capital_location_id,
            payload={"target_faction_id": target_id, "betrayal": betrayal},
        )
    ]


def make_peace(world: World, a: Faction, b: Faction) -> Optional[Event]:
    """Clear the symmetric at-war flag between two factions and announce the peace.

    The public seam ticket 11 will call once it owns *when* wars end (exhaustion,
    tribute, subjugation). Nothing in phase 3 invokes it autonomously this ticket:
    a war, once declared, runs until 11 provides an ending. Returns the event, or
    ``None`` if the two were not actually at war.
    """
    if not a.is_at_war_with(b.id):
        return None
    _clear_at_war(a, b)
    return world.new_event(
        type=WAR_ENDED_EVENT,
        subject_ids=[a.id, b.id],
        location_id=a.capital_location_id,
        payload={},
    )


# =========================================================================
# The pact ladder (SEEK_PACT)
# =========================================================================

def _pursue_pact(
    world: World, rng: random.Random, faction: Faction, adjacency: Dict[int, set]
) -> List[Event]:
    """A faction seeking a pact tries, in order: deepen an aligned provider, offer
    overlordship to a weak adoring neighbour, marry a warm peer, sign a treaty.

    The first rung whose candidate exists *and* whose seeded roll succeeds fires,
    and the faction takes at most one diplomatic action this tick.
    """
    provider = _aligned_provider(world, faction)
    if provider is not None and _roll(rng, 60):
        return [_deepen_provider(world, faction, provider)]

    vassal = _weak_adoring_neighbour(world, faction, adjacency)
    if vassal is not None and _roll(rng, _vassal_odds(vassal.disposition_toward(faction.id))):
        return [_form_vassalage(world, overlord=faction, vassal=vassal)]

    peer = _warmest_peer(world, faction, _TREATY_MIN)
    if peer is None:
        return []
    disp = faction.disposition_toward(peer.id)
    canon_bonus = _canon_pact_bonus(world, faction, peer)
    if (
        disp >= _MARRIAGE_MIN
        and _roll(rng, _marriage_odds(disp) + canon_bonus)
    ):
        married = _make_marriage(world, faction, peer)
        if married:
            return married
    if not faction.has_treaty_with(peer.id) and _roll(
        rng, _treaty_odds(disp) + canon_bonus
    ):
        return [_sign_treaty(world, faction, peer)]
    return []


def _canon_pact_bonus(world: World, a: Faction, b: Faction) -> int:
    """The canonicity soft-weight on a Free-Peoples pact's odds (issue #5).

    Non-zero only when *both* parties are of the free folk (not orc-kind), scaled
    by the run's canonicity — a canon-leaning world knits its alliances a little
    faster; a chaotic one leaves them to disposition alone. Integer, and applied
    to the odds *before* the one seeded roll — the dice stay honest.
    """
    from .factions import People

    if a.people == People.ORCS.value or b.people == People.ORCS.value:
        return 0
    canonicity = max(0.0, min(1.0, world.config.canonicity))
    return _CANON_PACT_BONUS * int(canonicity * 1000) // 1000


def _sign_treaty(world: World, a: Faction, b: Faction) -> Event:
    """Sign a symmetric treaty of alliance and warm both parties."""
    _add_treaty(a, b)
    _adjust(a, b.id, _JUMP_TREATY)
    _adjust(b, a.id, _JUMP_TREATY)
    return world.new_event(
        type=TREATY_EVENT,
        subject_ids=[a.id, b.id],
        location_id=a.capital_location_id,
        payload={},
    )


def _form_vassalage(world: World, overlord: Faction, vassal: Faction) -> Event:
    """Bind ``vassal`` under ``overlord`` (a bond, never a merge) and warm both."""
    vassal.overlord_faction_id = overlord.id
    _adjust(overlord, vassal.id, _JUMP_VASSALAGE)
    _adjust(vassal, overlord.id, _JUMP_VASSALAGE)
    return world.new_event(
        type=VASSALAGE_EVENT,
        subject_ids=[vassal.id, overlord.id],
        location_id=vassal.capital_location_id,
        payload={"bond": "formed", "overlord_faction_id": overlord.id},
    )


def _deepen_provider(world: World, patron: Faction, provider: Faction) -> Event:
    """Raise an already-aligned provider's commitment toward its patron.

    The v1 provider-pact: a patron courting its own gateway-people strengthens
    their pledge. (Winning a *rival's* provider over is the same seam but needs a
    disposition toward the provider that no seeded realm holds yet; ticket 14 will
    also drive commitment from Sauron's pull.)
    """
    provider.commitment = min(_PROVIDER_MAX, provider.commitment + _PROVIDER_STEP)
    return world.new_event(
        type=PROVIDER_PACT_EVENT,
        subject_ids=[patron.id, provider.id],
        location_id=provider.gateway_location_id,
        payload={"commitment": provider.commitment},
    )


def _make_marriage(world: World, a: Faction, b: Faction) -> Optional[List[Event]]:
    """Wed the best eligible cross-house couple; the junior spouse joins the senior
    house, and the two realms warm to one another.

    Returns ``None`` (so the caller can fall through to a treaty) when no
    opposite-sex, unwed, adult pair exists across the two factions.
    """
    match = _best_couple(world, a, b)
    if match is None:
        return None
    spouse_a, spouse_b = match
    if not wed(world, spouse_a.id, spouse_b.id):
        return None
    # The junior partner weds into the senior house (higher faction prominence,
    # lower id breaking ties): whichever spouse sits in the junior faction adopts
    # the senior faction, so the couple's children belong to one realm.
    senior, junior = _rank_houses(a, b)
    junior_spouse = spouse_a if spouse_a.faction_id == junior.id else spouse_b
    junior_spouse.faction_id = senior.id
    _adjust(a, b.id, _JUMP_MARRIAGE)
    _adjust(b, a.id, _JUMP_MARRIAGE)
    return [
        world.new_event(
            type=MARRIAGE_EVENT,
            subject_ids=[spouse_a.id, spouse_b.id, a.id, b.id],
            location_id=senior.capital_location_id,
            payload={"realm_a": a.id, "realm_b": b.id, "senior_faction_id": senior.id},
        )
    ]


# =========================================================================
# Candidate selection
# =========================================================================

def _warmest_peer(world: World, faction: Faction, min_disp: int) -> Optional[Faction]:
    """The realm/culture this faction likes most (>= ``min_disp``), not at war with,
    excluding providers and itself. Ties break by lowest id (via id-order scan)."""
    best: Optional[Faction] = None
    best_disp = min_disp - 1
    for other in factions(world, alive_only=True):
        if other.id == faction.id or other.is_provider:
            continue
        if faction.is_at_war_with(other.id):
            continue
        disp = faction.disposition_toward(other.id)
        if disp > best_disp:
            best_disp = disp
            best = other
    return best


def _weak_adoring_neighbour(
    world: World, overlord: Faction, adjacency: Dict[int, set]
) -> Optional[Faction]:
    """A bordering, currently-unbound faction that adores ``overlord`` and is far
    weaker than it — a candidate to be offered overlordship. Most-adoring wins."""
    threshold = overlord.military_strength // _VASSAL_RATIO_DIV
    best: Optional[Faction] = None
    best_disp = _VASSAL_HI - 1
    for other_id in sorted(adjacency.get(overlord.id, ())):
        other = _faction(world, other_id)
        if other is None or not other.alive or other.is_provider:
            continue
        if other.overlord_faction_id is not None:  # already sworn
            continue
        if other.military_strength >= threshold:  # not weak enough
            continue
        disp = other.disposition_toward(overlord.id)
        if disp > best_disp:
            best_disp = disp
            best = other
    return best


def _aligned_provider(world: World, patron: Faction) -> Optional[Faction]:
    """The lowest-id provider already pledged to ``patron`` with room to deepen."""
    for other in factions(world, alive_only=True):
        if (
            other.is_provider
            and other.allegiance_faction_id == patron.id
            and other.commitment < _PROVIDER_MAX
        ):
            return other
    return None


def _best_couple(
    world: World, a: Faction, b: Faction
) -> Optional[Tuple[Character, Character]]:
    """The highest-prominence opposite-sex, unwed, adult pair with one spouse from
    each faction (or ``None`` if no such pair exists)."""
    a_m, a_f = _eligible_spouse(world, a.id, "M"), _eligible_spouse(world, a.id, "F")
    b_m, b_f = _eligible_spouse(world, b.id, "M"), _eligible_spouse(world, b.id, "F")
    options: List[Tuple[Character, Character]] = []
    if a_m and b_f:
        options.append((a_m, b_f))
    if a_f and b_m:
        options.append((a_f, b_m))
    if not options:
        return None
    return max(options, key=lambda p: (p[0].prominence + p[1].prominence, -p[0].id, -p[1].id))


def _eligible_spouse(world: World, faction_id: int, sex: str) -> Optional[Character]:
    """The most prominent living, unwed, adult member of a faction of this sex."""
    year = world.current_year
    best: Optional[Character] = None
    for char in characters(world, alive_only=True):
        if char.faction_id != faction_id or char.sex != sex or char.spouse_id is not None:
            continue
        if char.age(year) < RACE_CONFIG[Race(char.race)].maturity_age:
            continue
        if best is None or char.prominence > best.prominence:
            best = char
    return best


def _rank_houses(a: Faction, b: Faction) -> Tuple[Faction, Faction]:
    """(senior, junior) by faction prominence, lower id breaking ties."""
    if (a.prominence, -a.id) >= (b.prominence, -b.id):
        return a, b
    return b, a


# =========================================================================
# Odds (integer, drawn against rng.randrange(100) — mirrors phase-2 style)
# =========================================================================

def _roll(rng: random.Random, odds: int) -> bool:
    return rng.randrange(100) < odds


def _treaty_odds(disp: int) -> int:
    return min(90, 30 + (disp - _TREATY_MIN) // 2)


def _marriage_odds(disp: int) -> int:
    return min(70, 20 + (disp - _MARRIAGE_MIN) // 3)


def _vassal_odds(disp: int) -> int:
    return min(80, 30 + (disp - _VASSAL_HI) // 3)


# =========================================================================
# Container mutation — always reassign (never mutate in place) so a per-tick
# snapshot keeps the values as they stood that tick (see module docstring).
# =========================================================================

def _step(value: int, target: int, size: int) -> int:
    """One clamped integer step of at most ``size`` from ``value`` toward ``target``."""
    if value < target:
        return min(target, value + size)
    if value > target:
        return max(target, value - size)
    return value


def _adjust(faction: Faction, other_id: int, delta: int) -> None:
    """Add ``delta`` to a disposition entry, clamped, via a fresh dict."""
    key = str(other_id)
    updated = dict(faction.disposition)
    updated[key] = max(_DISP_MIN, min(_DISP_MAX, updated.get(key, 0) + delta))
    faction.disposition = updated


def _set_at_war(a: Faction, b: Faction) -> None:
    a.at_war_with = sorted(set(a.at_war_with) | {b.id})
    b.at_war_with = sorted(set(b.at_war_with) | {a.id})


def _clear_at_war(a: Faction, b: Faction) -> None:
    a.at_war_with = [x for x in a.at_war_with if x != b.id]
    b.at_war_with = [x for x in b.at_war_with if x != a.id]


def _add_treaty(a: Faction, b: Faction) -> None:
    a.treaties = sorted(set(a.treaties) | {b.id})
    b.treaties = sorted(set(b.treaties) | {a.id})


def _break_treaty(a: Faction, b: Faction) -> None:
    a.treaties = [x for x in a.treaties if x != b.id]
    b.treaties = [x for x in b.treaties if x != a.id]


def _break_vassalage(a: Faction, b: Faction) -> None:
    """Sever a fealty bond in either direction between two factions."""
    if a.overlord_faction_id == b.id:
        a.overlord_faction_id = None
    if b.overlord_faction_id == a.id:
        b.overlord_faction_id = None


# =========================================================================
# Territory / lookup helpers
# =========================================================================

def _faction_adjacencies(grid: Optional[TileGrid]) -> Dict[int, set]:
    """``faction id -> set of faction ids`` whose land touches it (derived, not
    stored). One O(tiles) scan; borders come from the grid like everywhere else."""
    adjacency: Dict[int, set] = {}
    if grid is None:
        return adjacency
    for row in range(grid.height):
        for col in range(grid.width):
            owner = grid.owner_at(col, row)
            if owner == UNOWNED:
                continue
            for nc, nr in grid.neighbors(col, row):
                other = grid.owner_at(nc, nr)
                if other != UNOWNED and other != owner:
                    adjacency.setdefault(owner, set()).add(other)
    return adjacency


def _faction(world: World, faction_id: Optional[int]) -> Optional[Faction]:
    if faction_id is None:
        return None
    entity = world.entities.get(faction_id)
    return entity if isinstance(entity, Faction) else None


# -- inspection ------------------------------------------------------------

def vassals_of(world: World, overlord_id: int) -> List[Faction]:
    """The factions sworn to an overlord (id order) — the inspection read-side."""
    return [f for f in factions(world) if f.overlord_faction_id == overlord_id]
