"""Factions & territory — the powers of Middle-earth and their grip on the map
(build ticket 07).

A :class:`Faction` is an ordinary id-keyed :class:`~arda_sim.entities.Entity`
subtype, its behaviour switched by a ``kind`` tag:

* **realm** — owns regions, musters hosts, has a capital and a leader (Gondor,
  Rohan, Mordor, the Elf realms, …).
* **culture** — holds ground and identity but projects little force and has no
  seeded leader (the Shire, Bree-land, Dunland, the Grey Havens).
* **provider** — an abstract off-map people reached through a map-edge *gateway*
  (Haradrim, Easterlings, Variags, Corsairs). It never owns a region and is never
  a conquest target; it exposes only an allegiance and a commitment, and (once war
  lands, ticket 11) spawns a real allied host at its gateway.

One record type keeps ``owner_faction_id`` a single foreign key everywhere and
lets territory/war/diplomacy treat every holder uniformly (see the design in
``.scratch/arda-history-v1/issues/06-faction-territory-system.md``).

**Territory** is per-tile ``owner_faction_id`` on the :class:`~arda_sim.tiles.TileGrid`
— the only authoritative mutable tile state; borders and "contested" are *derived*
(:meth:`TileGrid.is_border`), never stored. A region is owned atomically: seeding
paints every tile of an owned region with its faction. Ownership only changes by
conquest, which is war's job (ticket 11); until then the political map is a pure
function of this seed, so it needs no separate persistence yet.

**Phase 2** (:func:`faction_decisions`) is the faction turn: each realm/culture
scores a fixed intent menu (muster / attack / fortify / seek-pact / build) by a
weighted-utility function plus seeded-RNG jitter, records the winning intent, and
emits a low-salience intent event for later phases to consume. It is a pure
``system(world, rng) -> events`` and deterministic under seed. Providers do not
decide here — they respond to diplomacy (ticket 08).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .characters import Race
from .characters import characters as _all_characters
from .entities import Entity, EntityStatus, Event, register_entity_type
from .scenarios import load_scenario
from .tiles import UNOWNED, TileGrid
from .world import World


class FactionKind(str, Enum):
    REALM = "realm"
    CULTURE = "culture"
    PROVIDER = "provider"

    def __str__(self) -> str:
        return self.value


class People(str, Enum):
    """The broad folk a faction belongs to (CONTEXT.md "People").

    World-truth about the faction itself, not its army's composition, and
    independent of ``faction_kind`` — Isengard in TA 2965 is ``men`` (Saruman's
    holding, no Uruk-hai yet). Authored at seed on every faction, providers
    included; the army-sprite renderer (map-visuals ticket 03) reads it.
    """

    MEN = "men"
    ELVES = "elves"
    DWARVES = "dwarves"
    ORCS = "orcs"
    HOBBITS = "hobbits"

    def __str__(self) -> str:
        return self.value


class NamingCulture(str, Enum):
    """The naming register a faction's generated characters draw names from.

    Finer-grained than :class:`People` on purpose: Gondor, Rohan, and the Dúnedain
    are all ``men`` but must name very differently (Númenórean-formal vs Old-English
    vs archaic Sindarin). The eight registers cover every seeded folk; ``MANNISH`` is
    the generic fallback for Men without a distinct register (Dale, Bree, Dunland,
    Isengard-men). See issue #34. String-backed so it round-trips through canonical
    JSON like the other faction enum fields.
    """

    ORCISH = "orcish"
    DWARVISH = "dwarvish"
    ELVISH = "elvish"
    DUNEDAIN = "dunedain"
    GONDORIAN = "gondorian"
    ROHIRRIC = "rohirric"
    HOBBIT = "hobbit"
    MANNISH = "mannish"

    def __str__(self) -> str:
        return self.value


# The register a faction falls back to when it authors no explicit ``culture`` —
# derived from its broad :class:`People`. Men default to the generic MANNISH; the
# distinct Men realms (Gondor, Rohan, the Dúnedain) override this at seed.
_DEFAULT_CULTURE: Dict[str, NamingCulture] = {
    People.ELVES.value: NamingCulture.ELVISH,
    People.DWARVES.value: NamingCulture.DWARVISH,
    People.ORCS.value: NamingCulture.ORCISH,
    People.HOBBITS.value: NamingCulture.HOBBIT,
    People.MEN.value: NamingCulture.MANNISH,
}


def default_culture_for_people(people: str) -> NamingCulture:
    """The naming register a folk uses when its faction authors no ``culture``."""
    return _DEFAULT_CULTURE.get(people, NamingCulture.MANNISH)


# Race is finer than People — the Dúnedain are their own race though ``men`` as a
# people — so a race carries its own culture default, used to name a generated child
# when neither parent holds a faction to read a register from (issue #34). Maiar/
# Wraiths never breed; their entries are only a total-map safeguard.
_RACE_CULTURE: Dict[str, NamingCulture] = {
    Race.MAN.value: NamingCulture.MANNISH,
    Race.DUNEDAIN.value: NamingCulture.DUNEDAIN,
    Race.HOBBIT.value: NamingCulture.HOBBIT,
    Race.ORC.value: NamingCulture.ORCISH,
    Race.DWARF.value: NamingCulture.DWARVISH,
    Race.ELF.value: NamingCulture.ELVISH,
    Race.MAIA.value: NamingCulture.ELVISH,
    Race.WRAITH.value: NamingCulture.MANNISH,
}


def default_culture_for_race(race: str) -> NamingCulture:
    """The naming register a race defaults to when no faction register is available."""
    return _RACE_CULTURE.get(race, NamingCulture.MANNISH)


class SuccessionRule(str, Enum):
    """How a realm chooses the next holder of its ``leader_id`` when the seat
    falls vacant (build ticket 08). The rule is resolved by the succession phase,
    not here — this enum is only the tag each faction carries.

    * ``agnatic_primogeniture`` — the eldest descendant, male-preferring, then
      collateral kin (Rohan, the Dúnedain Chieftains, most realms of Men).
    * ``stewardship`` — the same bloodline walk, but the office is a stewardship
      held "until the king returns" (Gondor's Ruling Stewards).
    * ``dwarf_line_of_durin`` — agnatic within the line of Durin (Durin's Folk).
    * ``elective`` — no direct heir required; the realm elects its worthiest
      member when the line has no kin to call on.
    """

    AGNATIC_PRIMOGENITURE = "agnatic_primogeniture"
    STEWARDSHIP = "stewardship"
    DWARF_LINE_OF_DURIN = "dwarf_line_of_durin"
    ELECTIVE = "elective"

    def __str__(self) -> str:
        return self.value


class Posture(str, Enum):
    """A faction's standing stance, seeded and canon-flavoured.

    ``withdrawing`` is the fading-Elves stance (per ticket 05): it biases a
    faction hard toward holding and building and away from attacking or mustering.
    """

    AGGRESSIVE = "aggressive"
    DEFENSIVE = "defensive"
    NEUTRAL = "neutral"
    WITHDRAWING = "withdrawing"

    def __str__(self) -> str:
        return self.value


# The fixed intent menu phase 2 scores. Order is fixed so the per-intent RNG
# jitter is drawn in a stable sequence (determinism under seed).
class Intent(str, Enum):
    MUSTER = "muster"
    ATTACK = "attack"
    FORTIFY = "fortify"
    SEEK_PACT = "seek_pact"
    BUILD = "build"
    # Loose the Nine upon the Ring (issue #5): scoreable only by the dark realm,
    # and only while Sauron's strength and the Ring's pull are both high.
    HUNT = "hunt_ring"

    def __str__(self) -> str:
        return self.value


INTENT_MENU: tuple = (
    Intent.MUSTER,
    Intent.ATTACK,
    Intent.FORTIFY,
    Intent.SEEK_PACT,
    Intent.BUILD,
    Intent.HUNT,
)

# Event type phase 2 emits — one per deciding faction per year. Kept deliberately
# low-salience (see chronicle.BASE_WEIGHT) so the annals aren't flooded; it is
# still visible under "show all" and on a faction's own inspection timeline.
FACTION_INTENT_EVENT = "faction_intent"


@dataclass
class Faction(Entity):
    """A power on the map. Extends the entity base with rule, territory, and stance.

    Every cross-reference is an id: ``leader_id`` is a character entity id,
    ``capital_location_id`` / ``gateway_location_id`` are config-space site ids
    (see :class:`~arda_sim.tiles.Site`), ``overlord_faction_id`` and the
    ``disposition`` keys are faction entity ids. ``disposition`` and ``output``
    use *string* keys so the whole record round-trips through canonical JSON
    without int-key coercion (mirroring ``Character.traits``).
    """

    faction_kind: str = FactionKind.REALM.value
    # The broad folk this faction is (CONTEXT.md "People"); string-backed like the
    # other enum fields so it round-trips through canonical JSON. World-truth, not
    # army composition — read by the army-sprite renderer (map-visuals ticket 03).
    people: str = People.MEN.value
    # The naming register generated characters (captains, later children) draw from
    # (issue #34). Empty string = unset, so it derives from ``people`` via
    # :meth:`naming_culture` — this keeps the field persistence-backward-compatible
    # (snapshots predating it load with the derived default). Authored explicitly at
    # seed only where ``people`` is too coarse (Gondor/Rohan/Dúnedain, all ``men``).
    culture: str = ""
    succession_rule: str = SuccessionRule.AGNATIC_PRIMOGENITURE.value
    leader_id: Optional[int] = None
    capital_location_id: Optional[int] = None
    overlord_faction_id: Optional[int] = None
    aggression: int = 40  # 0..100 seeded drive toward force
    posture: str = Posture.NEUTRAL.value
    # Sparse, asymmetric relation map: str(other_faction_id) -> scalar -100..100.
    disposition: Dict[str, int] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    # The intent (an :class:`Intent` value) canonicity leans this faction toward,
    # or None. Explicit so the canon nudge never hinges on how ``goals`` is ordered.
    canon_intent: Optional[str] = None
    treasury: int = 0
    # A dormant territorial claim held without ownership (the Rangers' "unclaimed
    # North"), as config-space region ids — never painted onto the map.
    claim_region_ids: List[int] = field(default_factory=list)
    # Provider-only fields (None/empty for realms and cultures).
    gateway_location_id: Optional[int] = None
    allegiance_faction_id: Optional[int] = None
    commitment: int = 0  # 0..100; rises with its patron's strength (ticket 14)
    output: Dict[str, int] = field(default_factory=dict)  # unit profile, str keys
    # Derived/cached scalars, recomputed when territory changes (war, ticket 11).
    military_strength: int = 0
    prominence: int = 0  # salience input, read by chronicle.subject_prominence
    # The winning intent from the most recent phase-2 turn (transient decision
    # state consumed by later phases), as {"intent": str, "target_faction_id": int,
    # "score": int}. Mixed value types, but JSON-clean (str keys, scalar values).
    current_intent: Dict[str, Any] = field(default_factory=dict)
    # Diplomacy (build ticket 09). ``disposition`` above *evolves*; it decays each
    # year toward this frozen authored ``baseline_disposition`` (same str keys),
    # so canon tempers are lasting attractors rather than a mere opening position
    # (ADR-0005). ``at_war_with`` / ``treaties`` are the *symmetric* pinned flags —
    # each faction id appears on both parties' lists, maintained by phase 3. The
    # *stance* (alliance/neutrality/hostility/vassalage) is derived from these plus
    # ``overlord_faction_id`` (see :func:`arda_sim.diplomacy.stance`), never stored.
    baseline_disposition: Dict[str, int] = field(default_factory=dict)
    at_war_with: List[int] = field(default_factory=list)
    treaties: List[int] = field(default_factory=list)
    # War-layer tuning state (issue #13). ``march_speed`` is an authored per-faction
    # miles/year pace (0 = derive from ``people`` via :func:`faction_march_speed`),
    # replacing the single global rate. ``muster_cooldown_until`` is the TA year
    # before which this faction may not (re-)muster or lend a levy — set when a host
    # it contributed to leaves play, scaled by that host's size, so a great hosting
    # depletes the realm's manpower for longer (ADR-0009).
    march_speed: int = 0
    muster_cooldown_until: int = 0
    # Sauron's rise (issue #5) — meaningful only on the dark realm (Mordor), zero
    # everywhere else. ``sauron_strength`` is the phase-7 scalar
    # (canon_baseline × canonicity + Σ emergent deltas), consumed by the *next*
    # tick's phases 2–4 (musters, provider commitment, the hunt). ``sauron_delta``
    # is the bounded accumulator of emergent checks and spurs (defeats, victories,
    # conquests); ``sauron_events_seen`` is the event-id watermark the phase-7
    # scan resumes from, so each battle counts exactly once.
    sauron_strength: int = 0
    sauron_delta: int = 0
    sauron_events_seen: int = 0

    @property
    def kind_tag(self) -> FactionKind:
        return FactionKind(self.faction_kind)

    @property
    def naming_culture(self) -> NamingCulture:
        """The naming register for this faction's generated characters: its authored
        ``culture`` if set, else the default for its :class:`People` (issue #34)."""
        if self.culture:
            return NamingCulture(self.culture)
        return default_culture_for_people(self.people)

    @property
    def is_provider(self) -> bool:
        return self.faction_kind == FactionKind.PROVIDER.value

    @property
    def alive(self) -> bool:
        """In play — not tombstoned by extinction (its last seat lost, ticket 11)."""
        return self.status == EntityStatus.ACTIVE.value

    def disposition_toward(self, faction_id: int) -> int:
        """Relation scalar toward another faction (0 = indifferent by default)."""
        return self.disposition.get(str(faction_id), 0)

    def baseline_toward(self, faction_id: int) -> int:
        """The frozen authored temper this pair decays back to (0 by default)."""
        return self.baseline_disposition.get(str(faction_id), 0)

    def is_at_war_with(self, faction_id: int) -> bool:
        return faction_id in self.at_war_with

    def has_treaty_with(self, faction_id: int) -> bool:
        return faction_id in self.treaties


register_entity_type("faction", Faction)


# -- march pace (issue #13) -----------------------------------------------

# Default miles/year by People, replacing the single global rate: cavalry-realms
# march fastest (Rohan carries an authored override above this), Elves are lithe,
# Men are the mid reference, Orc-hosts their own profile, Dwarves are slower, and
# Hobbits (who never muster) slowest. A faction's authored ``march_speed`` beats
# this when set (see :func:`faction_march_speed`).
_PEOPLE_MARCH_SPEED: Dict[str, int] = {
    People.MEN.value: 180,
    People.ELVES.value: 200,
    People.DWARVES.value: 140,
    People.ORCS.value: 170,
    People.HOBBITS.value: 120,
}
_DEFAULT_MARCH_SPEED = 180


def faction_march_speed(faction: Faction) -> int:
    """A faction's marching pace (miles/year): its authored ``march_speed`` if set,
    else the default for its ``people``. A coalition marches at its lead's pace."""
    if faction.march_speed > 0:
        return faction.march_speed
    return _PEOPLE_MARCH_SPEED.get(faction.people, _DEFAULT_MARCH_SPEED)


# -- derived fields -------------------------------------------------------

_KIND_PROMINENCE = {
    FactionKind.REALM.value: 40,
    FactionKind.CULTURE.value: 20,
    FactionKind.PROVIDER.value: 25,
}

# Per-kind base contribution to derived military strength (providers derive
# theirs from commitment instead; see compute_military_strength).
_KIND_STRENGTH_BASE = {
    FactionKind.REALM.value: 20,
    FactionKind.CULTURE.value: 5,
}


def compute_military_strength(faction: Faction, owned_tiles: int, leader: Optional[Entity]) -> int:
    """Derived host potential: territory + a leader's martial bearing + kind base.

    Cached on the record so phase 2 (which never sees the grid) reads a scalar.
    Recomputed when territory changes; providers derive theirs from commitment.
    """
    if faction.is_provider:
        return faction.commitment * 3
    base = _KIND_STRENGTH_BASE.get(faction.faction_kind, 0)
    martial = int(getattr(leader, "traits", {}).get("martial", 0)) if leader else 0
    # One point of strength per ~15 tiles held keeps the biggest realms from
    # dwarfing the rest purely on wilderness acreage.
    return base + owned_tiles // 15 + martial // 2


def compute_prominence(faction: Faction, owned_tiles: int, leader: Optional[Entity]) -> int:
    """Derived salience: kind base + a leader's stature + a territory bonus.

    The faction-side counterpart to :func:`arda_sim.characters.compute_prominence`,
    read unchanged by :func:`arda_sim.chronicle.subject_prominence`.
    """
    kind_base = _KIND_PROMINENCE.get(faction.faction_kind, 0)
    leader_prom = int(getattr(leader, "prominence", 0) or 0) if leader else 0
    territory_bonus = min(30, owned_tiles // 20)
    return kind_base + leader_prom // 2 + territory_bonus


# -- construction ---------------------------------------------------------

def add_faction(
    world: World,
    name: str,
    kind: FactionKind,
    *,
    people: People = People.MEN,
    culture: Optional[NamingCulture] = None,
    succession_rule: SuccessionRule = SuccessionRule.AGNATIC_PRIMOGENITURE,
    leader_id: Optional[int] = None,
    capital_location_id: Optional[int] = None,
    overlord_faction_id: Optional[int] = None,
    aggression: int = 40,
    posture: Posture = Posture.NEUTRAL,
    disposition: Optional[Dict[int, int]] = None,
    goals: Optional[List[str]] = None,
    canon_intent: Optional[Intent] = None,
    treasury: int = 0,
    claim_region_ids: Optional[List[int]] = None,
    gateway_location_id: Optional[int] = None,
    allegiance_faction_id: Optional[int] = None,
    commitment: int = 0,
    output: Optional[Dict[str, int]] = None,
    march_speed: int = 0,
    status: str = EntityStatus.ACTIVE.value,
) -> Faction:
    """Create and register a Faction with a fresh id at the current year.

    ``disposition`` is authored with int faction-id keys for convenience and
    stored with string keys (JSON-clean). Derived scalars are filled by the
    caller once territory is known (see :func:`seed_factions`).
    """
    faction = Faction(
        id=world.next_id(),
        kind="faction",
        name=name,
        created_year=world.current_year,
        status=status,
        faction_kind=kind.value if isinstance(kind, FactionKind) else kind,
        people=people.value if isinstance(people, People) else people,
        culture=(
            culture.value if isinstance(culture, NamingCulture)
            else (culture or "")
        ),
        succession_rule=(
            succession_rule.value
            if isinstance(succession_rule, SuccessionRule)
            else succession_rule
        ),
        leader_id=leader_id,
        capital_location_id=capital_location_id,
        overlord_faction_id=overlord_faction_id,
        aggression=aggression,
        posture=posture.value if isinstance(posture, Posture) else posture,
        disposition={str(k): int(v) for k, v in (disposition or {}).items()},
        goals=list(goals) if goals else [],
        canon_intent=canon_intent.value if isinstance(canon_intent, Intent) else canon_intent,
        treasury=treasury,
        claim_region_ids=list(claim_region_ids) if claim_region_ids else [],
        gateway_location_id=gateway_location_id,
        allegiance_faction_id=allegiance_faction_id,
        commitment=commitment,
        output=dict(output) if output else {},
        march_speed=march_speed,
    )
    world.entities[faction.id] = faction
    return faction


# -- queries --------------------------------------------------------------

def factions(world: World, *, alive_only: bool = False) -> List[Faction]:
    """All Faction records in id order (optionally only those still in play)."""
    result = [e for _id, e in sorted(world.entities.items()) if isinstance(e, Faction)]
    return [f for f in result if f.alive] if alive_only else result


def deciding_factions(world: World) -> List[Faction]:
    """The factions that take a phase-2 turn: active realms and cultures in id
    order. Providers are excluded — they respond to diplomacy, not decide.
    """
    return [f for f in factions(world, alive_only=True) if not f.is_provider]


def faction_timeline(world: World, faction_id: int) -> List[Event]:
    """Every event naming this faction, oldest first — the inspection timeline."""
    return sorted(
        (ev for ev in world.events if faction_id in ev.subject_ids),
        key=lambda ev: (ev.year, ev.id),
    )


def faction_of_owner(world: World) -> Dict[int, str]:
    """A ``faction id -> name`` map for every faction (UI territory labels)."""
    return {f.id: f.name for f in factions(world)}


# -- phase 2: the faction turn -------------------------------------------

# Utility tuning (all integer; scores are unitless and only compared to each
# other). Kept modest so aggression/posture and the disposition map, not the
# jitter, decide the ordinary case.
_JITTER = 15  # exclusive upper bound of the per-intent RNG add
_CANON_WEIGHT = 40  # how hard the canonicity scalar leans on a faction's canon move
_WITHDRAW_PENALTY = 60  # subtracted from attack/muster for a withdrawing faction

# The rousing of the withdrawn. A faction that has withdrawn from the world's
# quarrels does not stay hidden once the Shadow looms: when the greatest
# ``sauron_strength`` abroad (see :func:`_perceived_shadow`) crosses this, dread of
# the dark realm lifts its withdrawal outright and drives it to take the field —
# the late-Third-Age turn when the Elf realms marched at last. Pitched at the same
# point diplomacy first *perceives* Mordor (its ``_VISIBILITY_THRESHOLD``), so the
# elves stir in the same War-of-the-Ring window and never in 2965's long peace.
ROUSE_STRENGTH_MIN = 60  # perceived sauron_strength that ends a withdrawal
_ROUSE_URGENCY = 60  # flat attack weight a roused faction gains (grows as the Shadow does)

# The hunt (issue #5): gates on the phase-7 scalars computed *last* tick — the
# spec's deliberate one-tick lag. Blocked outright for every faction with no
# ``sauron_strength``, and for the dark realm itself until both thresholds hold.
HUNT_STRENGTH_MIN = 45  # sauron_strength needed before the Nine ride
HUNT_PULL_MIN = 35  # the Ring must have stirred (pull) this loudly
_HUNT_URGENCY = 60  # flat weight once unlocked: a stirring Ring outranks a war
_HUNT_BLOCKED = -10_000  # a score no jitter can rescue


def _hostility(faction: Faction) -> tuple:
    """The faction this one most dislikes and how strongly (0 if none disliked)."""
    worst_id = 0
    worst = 0
    for key, value in faction.disposition.items():
        if value < worst:
            worst = value
            worst_id = int(key)
    return worst_id, -worst  # (target id, positive hostility magnitude)


def _friendliness(faction: Faction) -> int:
    """The strongest positive disposition this faction holds (0 if none)."""
    return max([v for v in faction.disposition.values() if v > 0], default=0)


def _score_intents(
    faction: Faction,
    canonicity: float,
    hunt_drive: int = _HUNT_BLOCKED,
    shadow: int = 0,
) -> Dict[Intent, int]:
    """Weighted-utility score per menu intent, before RNG jitter.

    Reads only the faction's own cached scalars and disposition map — never the
    grid — so it is safe inside the ``system(world, rng)`` signature.
    ``hunt_drive`` is computed by the caller (it needs the Ring's ``pull``);
    blocked by default so a bare call scores the classic menu. ``shadow`` is the
    greatest ``sauron_strength`` abroad this tick (0 by default), which rouses a
    withdrawn faction once it crosses :data:`ROUSE_STRENGTH_MIN`.
    """
    _target, hostility = _hostility(faction)
    friendliness = _friendliness(faction)
    aggression = faction.aggression
    strength = faction.military_strength
    withdrawing = faction.posture == Posture.WITHDRAWING.value
    roused = withdrawing and shadow >= ROUSE_STRENGTH_MIN

    scores = {
        Intent.MUSTER: aggression + strength // 4,
        Intent.ATTACK: aggression + hostility,
        Intent.FORTIFY: (100 - aggression) + hostility // 2,
        Intent.SEEK_PACT: friendliness + max(0, 60 - strength),
        Intent.BUILD: (100 - aggression) // 2 + 20,
        Intent.HUNT: hunt_drive,
    }
    if roused:
        # The Shadow has risen past bearing: the withdrawal lifts and dread of the
        # dark realm drives an assault on the enemy this faction most hates — and
        # the dread grows as the Shadow does, so a stronger Mordor rouses harder.
        scores[Intent.ATTACK] += _ROUSE_URGENCY + (shadow - ROUSE_STRENGTH_MIN)
    elif withdrawing:
        scores[Intent.ATTACK] -= _WITHDRAW_PENALTY
        scores[Intent.MUSTER] -= _WITHDRAW_PENALTY
        scores[Intent.FORTIFY] += 20

    # Canonicity nudges the faction's authored canon move (goals[0], if it names
    # an intent) toward the top — a global weight, never a scripted timeline.
    canon = _canon_intent(faction)
    if canon is not None:
        scores[canon] += int(canonicity * _CANON_WEIGHT)
    return scores


def _canon_intent(faction: Faction) -> Optional[Intent]:
    """The intent canonicity leans this faction toward, if any."""
    if not faction.canon_intent:
        return None
    try:
        return Intent(faction.canon_intent)
    except ValueError:
        return None


def _hunt_drive(world: World, faction: Faction) -> int:
    """The hunt's phase-2 score for this faction, or blocked.

    Only the dark realm (the one faction carrying a ``sauron_strength``) may
    hunt, and only while last phase 7's strength and the Ring's ``pull`` are both
    over their thresholds — the spec's "high strength + high pull" trigger. The
    Ring is read duck-typed (pull + bearer only, never mutated); a Ring already
    in dark hands, destroyed, or absent blocks the hunt outright.
    """
    if faction.sauron_strength < HUNT_STRENGTH_MIN:
        return _HUNT_BLOCKED
    ring = None
    for _id, entity in sorted(world.entities.items()):
        if getattr(entity, "kind", None) == "ring":
            ring = entity
            break
    if ring is None or ring.status != EntityStatus.ACTIVE.value:
        return _HUNT_BLOCKED
    pull = int(getattr(ring, "pull", 0) or 0)
    if pull < HUNT_PULL_MIN:
        return _HUNT_BLOCKED
    bearer_id = getattr(ring, "bearer_id", None)
    if bearer_id is not None:
        bearer = world.entities.get(bearer_id)
        if getattr(bearer, "faction_id", None) == faction.id:
            return _HUNT_BLOCKED  # already in the Shadow's keeping
    return faction.sauron_strength + pull + _HUNT_URGENCY


def _perceived_shadow(world: World) -> int:
    """The greatest ``sauron_strength`` abroad this tick — how loudly the Shadow
    presses on the world (0 in a light world). Only the dark realm carries a
    non-zero value, so this is Mordor's strength; phase 2 reads it so a withdrawn
    faction can rouse when Mordor grows strong (see :data:`ROUSE_STRENGTH_MIN`)."""
    return max((f.sauron_strength for f in factions(world)), default=0)


def _decide(
    faction: Faction,
    rng: random.Random,
    canonicity: float,
    hunt_drive: int,
    shadow: int = 0,
) -> Intent:
    """Pick this faction's intent: top weighted-utility score + RNG jitter.

    Jitter is drawn once per menu intent in fixed :data:`INTENT_MENU` order, so
    the whole decision is reproducible under the run seed. Ties break by menu
    order (``max`` keeps the first seen).
    """
    base = _score_intents(faction, canonicity, hunt_drive, shadow)
    best: Optional[Intent] = None
    best_score = None
    for intent in INTENT_MENU:
        score = base[intent] + rng.randrange(_JITTER)
        if best_score is None or score > best_score:
            best_score = score
            best = intent
    faction.current_intent = {
        "intent": best.value,
        "score": int(best_score),
    }
    return best


def faction_decisions(world: World, rng: random.Random) -> List[Event]:
    """Phase 2: every deciding faction scores the intent menu and records its move.

    Deterministic given the RNG: factions are processed in id order and each
    draws its per-intent jitter in fixed menu order. The winning intent is cached
    on the faction (for later phases) and emitted as a low-salience event (for the
    chronicle and faction inspection). Returns the events; the pipeline appends.
    """
    events: List[Event] = []
    canonicity = world.config.canonicity
    shadow = _perceived_shadow(world)
    for faction in deciding_factions(world):
        intent = _decide(faction, rng, canonicity, _hunt_drive(world, faction), shadow)
        target_id = 0
        if intent is Intent.ATTACK:
            target_id, _ = _hostility(faction)
            faction.current_intent["target_faction_id"] = target_id
        payload = {"intent": intent.value}
        if target_id:
            payload["target_faction_id"] = target_id
        subject_ids = [faction.id]
        events.append(
            world.new_event(
                type=FACTION_INTENT_EVENT,
                subject_ids=subject_ids,
                location_id=faction.capital_location_id,
                payload=payload,
            )
        )
    return events


# =========================================================================
# Seeding — the TA 2965 roster and its territory
# =========================================================================

# The scenario whose regions and sites anchor faction territory and capitals.
_ROSTER_SCENARIO_FILE = "arda_ta2965"


@dataclass(frozen=True)
class _FactionSeed:
    """One authored roster entry. ``leader`` is a roster character name resolved
    to an id after characters exist; ``capital`` / ``gateway`` are site names;
    ``regions`` / ``claims`` are region *labels* resolved to ids at seed time.
    ``disposition`` is authored by faction *name* and resolved once ids exist.
    """

    name: str
    kind: FactionKind
    people: People = People.MEN
    # Naming register override (issue #34); None = derive from ``people`` at runtime.
    # Authored only where ``people`` is too coarse — the distinct Men realms.
    culture: Optional[NamingCulture] = None
    succession_rule: SuccessionRule = SuccessionRule.AGNATIC_PRIMOGENITURE
    leader: Optional[str] = None
    capital: Optional[str] = None
    gateway: Optional[str] = None
    overlord: Optional[str] = None
    aggression: int = 40
    posture: Posture = Posture.NEUTRAL
    regions: tuple = ()
    claims: tuple = ()
    goals: tuple = ()
    # The intent canonicity leans this faction toward. Defaults at seed time to
    # the faction's first goal when that names an intent (see _seed_canon_intent).
    canon_intent: Optional[Intent] = None
    disposition: tuple = ()  # ((other_name, value), ...)
    commitment: int = 0
    allegiance: Optional[str] = None
    output: tuple = ()  # ((unit, weight), ...)
    treasury: int = 0
    march_speed: int = 0  # authored miles/year override; 0 = derive from people


# The canon TA 2965 roster. Region labels are the substrate's own
# (arda_ta2965.json legend). Wilderness regions left unlisted stay unowned
# (owner_faction_id = None) — no sentinel faction inflates the map.
_ROSTER: tuple = (
    _FactionSeed(
        "Gondor", FactionKind.REALM, people=People.MEN,
        culture=NamingCulture.GONDORIAN,
        succession_rule=SuccessionRule.STEWARDSHIP,
        leader="Ecthelion II", capital="Minas Tirith",
        aggression=45, posture=Posture.DEFENSIVE,
        regions=("Gondor", "Anórien", "Ithilien", "Lebennin", "Belfalas",
                 "Lamedon", "Anfalas", "Emyn Arnen", "Pinnath Gelin", "Druadan Forest"),
        goals=("fortify", "hold_the_anduin"),
        disposition=(("Mordor", -100), ("Rohan", 80), ("Dol Guldur", -60)),
        treasury=60,
    ),
    _FactionSeed(
        "Rohan", FactionKind.REALM, people=People.MEN,
        culture=NamingCulture.ROHIRRIC,
        leader="Thengel", capital="Edoras",
        aggression=50, posture=Posture.DEFENSIVE,
        regions=("Rohan", "Westemnet", "Eastemnet", "The Wold"),
        goals=("muster", "guard_the_fords"),
        disposition=(("Gondor", 80), ("Mordor", -80), ("Isengard", 10), ("Dunland", -40)),
        treasury=30,
        march_speed=320,  # the Riddermark rides — a mounted host far outpaces foot
    ),
    _FactionSeed(
        "Dúnedain of the North", FactionKind.REALM, people=People.MEN,
        culture=NamingCulture.DUNEDAIN,
        leader="Aragorn",
        aggression=35, posture=Posture.NEUTRAL,
        claims=("North Downs", "Arthedain", "Cardolan", "Evendim"),
        goals=("muster", "restore_arnor"),
        disposition=(("Mordor", -90),),
    ),
    _FactionSeed(
        # people=men is deliberate: TA 2965, before the Uruk-hai — world-truth
        # beats villain styling. Do not "fix" this to orcs.
        "Isengard", FactionKind.REALM, people=People.MEN,
        leader="Saruman", capital="Isengard",
        aggression=55, posture=Posture.NEUTRAL,
        regions=("Nan Curunír",),  # Saruman's vale — his own holding, not Rohan's
        goals=("build", "study_the_enemy"),
        disposition=(("Rohan", 10), ("Mordor", -20)),
        treasury=40,
    ),
    _FactionSeed(
        "Mordor", FactionKind.REALM, people=People.ORCS,
        leader="Sauron", capital="Barad-dûr",
        aggression=95, posture=Posture.AGGRESSIVE,
        regions=("Mordor", "Gorgoroth", "Nurn", "Udûn", "Dagorlad", "Lithlad"),
        goals=("attack", "dominate_middle_earth"),
        disposition=(("Gondor", -100), ("Rohan", -80), ("Lothlórien", -70),
                     ("Dúnedain of the North", -90)),
        treasury=80,
    ),
    _FactionSeed(
        "Dol Guldur", FactionKind.REALM, people=People.ORCS,
        leader=None, capital="Dol Guldur",
        overlord="Mordor", aggression=80, posture=Posture.AGGRESSIVE,
        regions=("Mirkwood", "Brown Lands"),
        goals=("attack", "break_lorien"),
        disposition=(("Lothlórien", -90), ("Woodland Realm", -80)),
    ),
    _FactionSeed(
        "Durin's Folk", FactionKind.REALM, people=People.DWARVES,
        succession_rule=SuccessionRule.DWARF_LINE_OF_DURIN,
        leader="Dáin II Ironfoot", capital="Erebor",
        aggression=45, posture=Posture.DEFENSIVE,
        regions=("Erebor", "Iron Hills"),
        goals=("build", "guard_the_mountain"),
        disposition=(("Dale", 80), ("Mordor", -60)),
        treasury=90,
    ),
    _FactionSeed(
        "Dale", FactionKind.REALM, people=People.MEN,
        leader="Bard I", capital="Dale",
        aggression=35, posture=Posture.DEFENSIVE,
        regions=("Dale",),
        goals=("build", "trade_with_erebor"),
        disposition=(("Durin's Folk", 80), ("Mordor", -60)),
        treasury=40,
    ),
    _FactionSeed(
        "Rivendell", FactionKind.REALM, people=People.ELVES,
        leader="Elrond", capital="Rivendell",
        aggression=20, posture=Posture.WITHDRAWING,
        regions=("Trollshaws",),
        goals=("fortify", "keep_the_hidden_valley"),
        disposition=(("Mordor", -70), ("Dúnedain of the North", 70)),
    ),
    _FactionSeed(
        "Lothlórien", FactionKind.REALM, people=People.ELVES,
        leader="Galadriel", capital="Caras Galadhon",
        aggression=25, posture=Posture.WITHDRAWING,
        regions=("Lórien",),
        goals=("fortify", "guard_the_golden_wood"),
        disposition=(("Dol Guldur", -90), ("Mordor", -70)),
    ),
    _FactionSeed(
        "Woodland Realm", FactionKind.REALM, people=People.ELVES,
        leader="Thranduil",
        capital="Thranduil's Halls", aggression=35, posture=Posture.WITHDRAWING,
        regions=("Woodland Realm",),
        goals=("fortify", "cleanse_the_forest"),
        disposition=(("Dol Guldur", -80),),
    ),
    _FactionSeed(
        "Grey Havens", FactionKind.CULTURE, people=People.ELVES,
        leader="Círdan", capital="Grey Havens",
        aggression=10, posture=Posture.WITHDRAWING,
        regions=("Lindon", "Forlindon", "Harlindon"),
        goals=("build", "make_ready_the_ships"),
    ),
    _FactionSeed(
        "The Shire", FactionKind.CULTURE, people=People.HOBBITS,
        leader=None, capital="Michel Delving",
        aggression=5, posture=Posture.NEUTRAL,
        regions=("The Shire",),
        goals=("build", "keep_the_peace"),
    ),
    _FactionSeed(
        "Bree-land", FactionKind.CULTURE, people=People.MEN,
        leader=None, capital="Bree",
        aggression=8, posture=Posture.NEUTRAL,
        regions=("Bree-land",),  # Bree and its villages — its own ground, not the Shire's
        goals=("build",),
    ),
    _FactionSeed(
        "Dunland", FactionKind.CULTURE, people=People.MEN,
        leader=None, aggression=45, posture=Posture.NEUTRAL,
        regions=("Dunland",),
        goals=("muster", "raid_the_horse_lords"),
        disposition=(("Rohan", -60),),
    ),
    # Off-map providers — gateway peoples, chiefly leaning to Mordor under canon
    # pressure. They own no ground and take no phase-2 turn.
    _FactionSeed(
        "Haradrim", FactionKind.PROVIDER, people=People.MEN,
        gateway="Harad Road (Poros)",
        allegiance="Mordor", commitment=30,
        output=(("heavy_infantry", 60), ("mumakil", 10)),
    ),
    _FactionSeed(
        "Easterlings of Rhûn", FactionKind.PROVIDER, people=People.MEN,
        gateway="East Rhûn",
        allegiance="Mordor", commitment=25,
        output=(("infantry", 50), ("cavalry", 30)),
    ),
    _FactionSeed(
        "Variags of Khand", FactionKind.PROVIDER, people=People.MEN,
        gateway="SE Khand",
        allegiance="Mordor", commitment=20,
        output=(("auxiliaries", 40),),
    ),
    _FactionSeed(
        "Corsairs of Umbar", FactionKind.PROVIDER, people=People.MEN,
        gateway="Umbar Sea",
        allegiance="Mordor", commitment=25,
        output=(("raiders", 40), ("ships", 20)),
    ),
)


def seed_factions(
    world: World, grid: TileGrid, scenario_file: Optional[str] = None
) -> Dict[int, str]:
    """Seed the canon TA 2965 faction roster into ``world`` and paint ``grid``.

    Characters must already be seeded (:func:`arda_sim.characters.seed_roster`) so
    leaders resolve. Region labels become atomic tile ownership on the grid; the
    derived ``military_strength``/``prominence`` scalars are computed from the
    tiles held. Returns a ``faction id -> name`` map for the UI's territory labels.
    Emits no events — the roster predates play, like the character roster.
    """
    grid_for_ids = load_scenario(scenario_file or _ROSTER_SCENARIO_FILE)
    region_id_of = {r.name: r.id for r in grid_for_ids.regions.values()}
    site_id_of = grid_for_ids.site_id_of
    chars_by_name = {c.name: c for c in _all_characters(world)}

    by_name: Dict[str, Faction] = {}
    region_owner: Dict[int, int] = {}  # region id -> faction id, for painting

    # Pass 1 — create every faction (ids exist before we resolve cross-links).
    for s in _ROSTER:
        leader = chars_by_name.get(s.leader) if s.leader else None
        if s.leader and leader is None:
            raise ValueError(f"faction {s.name!r} leader {s.leader!r} not in roster")
        capital_id = _resolve_site(site_id_of, s.capital, s.name, "capital")
        gateway_id = _resolve_site(site_id_of, s.gateway, s.name, "gateway")
        region_ids = [_resolve_region(region_id_of, name, s.name) for name in s.regions]
        claim_ids = [_resolve_region(region_id_of, name, s.name) for name in s.claims]

        faction = add_faction(
            world,
            name=s.name,
            kind=s.kind,
            people=s.people,
            culture=s.culture,
            succession_rule=s.succession_rule,
            leader_id=leader.id if leader else None,
            capital_location_id=capital_id,
            aggression=s.aggression,
            posture=s.posture,
            goals=list(s.goals),
            canon_intent=_seed_canon_intent(s),
            treasury=s.treasury,
            claim_region_ids=claim_ids,
            gateway_location_id=gateway_id,
            commitment=s.commitment,
            output={unit: weight for unit, weight in s.output},
            march_speed=s.march_speed,
        )
        by_name[s.name] = faction
        if leader is not None:
            leader.faction_id = faction.id
        for rid in region_ids:
            if rid in region_owner:
                other = world.entities[region_owner[rid]].name
                raise ValueError(f"region id {rid} claimed by both {other!r} and {s.name!r}")
            region_owner[rid] = faction.id

    # Pass 2 — resolve faction-to-faction links now that every id exists.
    for s in _ROSTER:
        faction = by_name[s.name]
        if s.overlord:
            faction.overlord_faction_id = by_name[s.overlord].id
        if s.allegiance:
            faction.allegiance_faction_id = by_name[s.allegiance].id
        faction.disposition = {
            str(by_name[other].id): value for other, value in s.disposition
        }
        # Freeze the authored temper as the decay attractor (ADR-0005): the live
        # disposition above evolves under events, but always pulls back to this.
        faction.baseline_disposition = dict(faction.disposition)

    # Pass 3 — paint atomic region ownership onto the grid.
    _paint_territory(grid, region_owner)

    # Pass 4 — fill the derived scalars from the territory just painted.
    owned_tiles = _owned_tile_counts(grid)
    for faction in by_name.values():
        leader = world.entities.get(faction.leader_id) if faction.leader_id else None
        tiles = owned_tiles.get(faction.id, 0)
        faction.military_strength = compute_military_strength(faction, tiles, leader)
        faction.prominence = compute_prominence(faction, tiles, leader)

    return {f.id: f.name for f in by_name.values()}


def _seed_canon_intent(seed: "_FactionSeed") -> Optional[Intent]:
    """The seed's explicit canon intent, or its first goal when that names one.

    Confines the "first goal is usually the canon move" convention to seed
    authoring; the runtime scorer reads only the resolved ``Faction.canon_intent``.
    """
    if seed.canon_intent is not None:
        return seed.canon_intent
    for goal in seed.goals:
        try:
            return Intent(goal)
        except ValueError:
            continue
    return None


def _resolve_site(
    site_id_of, name: Optional[str], faction_name: str, what: str
) -> Optional[int]:
    if name is None:
        return None
    site_id = site_id_of(name)
    if site_id is None:
        raise ValueError(f"faction {faction_name!r} {what} site {name!r} not in scenario")
    return site_id


def _resolve_region(region_id_of: Dict[str, int], name: str, faction_name: str) -> int:
    rid = region_id_of.get(name)
    if rid is None:
        raise ValueError(f"faction {faction_name!r} region {name!r} not in scenario")
    return rid


def _paint_territory(grid: TileGrid, region_owner: Dict[int, int]) -> None:
    """Set every tile's owner from its region's faction (atomic region ownership)."""
    for row in range(grid.height):
        for col in range(grid.width):
            rid = grid.region_of[grid.index(col, row)]
            owner = region_owner.get(rid)
            if owner:
                grid.set_owner(col, row, owner)


def _owned_tile_counts(grid: TileGrid) -> Dict[int, int]:
    """Count owned tiles per faction id from the painted grid."""
    counts: Dict[int, int] = {}
    for value in grid.owner:
        if value != UNOWNED:
            counts[value] = counts.get(value, 0) + 1
    return counts


def seed_world(seed_str: str, canonicity: float = 1.0):
    """A fresh run with the canon roster *and* factions seeded, plus its grid.

    The headless entry point for exercising factions end to end: returns
    ``(world, grid, faction_names)``. The UI and faction tests both build on this
    so the political map and the phase-2 turn are set up identically everywhere.
    """
    from .characters import new_seeded_run
    from .ring import seed_ring
    from .sauron import seed_nazgul

    world = new_seeded_run(seed_str, canonicity=canonicity)
    grid = load_scenario(_ROSTER_SCENARIO_FILE)
    faction_names = seed_factions(world, grid)
    world.grid = grid  # live handle: lets the succession phase reach territory (ADR-0004)
    seed_ring(world, grid)  # the One Ring, borne by Bilbo (ticket 13)
    seed_nazgul(world)  # the Nine, seated at Minas Morgul and Dol Guldur (issue #5)
    return world, grid, faction_names
