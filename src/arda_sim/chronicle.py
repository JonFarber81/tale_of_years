"""The chronicle framework: turn the raw event stream into a readable history.

This is build ticket 06's framework — the plumbing every later system ticket
plugs into. It owns three things, all headless and deterministic (no Qt, no RNG):

* **Salience** — every event gets an absolute ``importance`` (0–100) at emission,
  ``type base-weight × subject prominence × scale × canon-bump``, computed with
  integer math and immutable once written (see :func:`score_importance`).
* **Prose** — :func:`render_text` fills ``Event.text`` from the event's
  ``subject_ids`` / ``location_id`` / ``payload`` via per-type templates and a
  seeded phrase-grammar. ``Event.text`` is the swappable seam: a future LLM
  backend can replace this renderer without touching a line of sim code.
* **The feed** — :class:`AnnalsFilter` filters events on the four query indices
  (subject, faction, year, type) plus an importance threshold, and
  :func:`pulse_events` selects the events that warrant a transient on-map pulse.

:func:`finalize_event` is the single call the pipeline makes as each event enters
the log: it stamps ``importance`` and ``text``. Systems emit *structured* events
(type, subjects, location, payload) and never score or phrase themselves — they
contribute their base-weights and templates *here*, so the whole chronicle voice
lives in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence

from .armies import (
    ARMY_ARRIVED_EVENT,
    ARMY_DISBANDED_EVENT,
    ARMY_MUSTERED_EVENT,
)
from .characters import BIRTH_EVENT, DEATH_EVENT, DEPARTED_EVENT
from .diplomacy import (
    MARRIAGE_EVENT,
    PROVIDER_PACT_EVENT,
    TREATY_EVENT,
    VASSALAGE_EVENT,
    WAR_DECLARED_EVENT,
    WAR_ENDED_EVENT,
)
from .economy import (
    FOUNDING_EVENT,
    ROAD_OPENED_EVENT,
    SETTLEMENT_GREW_EVENT,
)
from .entities import Event
from .factions import FACTION_INTENT_EVENT
from .succession import ABSORPTION_EVENT, LINE_FAILED_EVENT, SUCCESSION_EVENT
from .war import (
    BATTLE_EVENT,
    COASTAL_RAID_EVENT,
    CONQUEST_EVENT,
    RAZING_EVENT,
    SIEGE_EVENT,
)
from .world import World

# The heartbeat's type string (mirrors ``pipeline.HEARTBEAT_EVENT_TYPE``, kept
# local so this module doesn't import the pipeline that imports it).
_HEARTBEAT_EVENT = "tick"

# The feed's default "important-only" cutoff: events scoring below this are
# hidden until the viewer asks to see everything. Also the pulse threshold.
IMPORTANT_THRESHOLD = 30

MIN_IMPORTANCE = 0
MAX_IMPORTANCE = 100


# =========================================================================
# Salience
# =========================================================================

# Per-type salience base weight: the intrinsic importance of an event *kind*,
# before it is modulated by who it happened to and how big it was. This is the
# registry the spec means by "each system contributes its salience base-weight"
# — later tickets add their types (battle, conquest, succession, ...) here.
BASE_WEIGHT: Dict[str, int] = {
    BIRTH_EVENT: 20,
    DEATH_EVENT: 40,
    DEPARTED_EVENT: 55,
    # Dynastic events (ticket 08) are era-shaping: a crown changing hands, and —
    # rarer and heavier still — a ruling line failing and a realm swallowed whole.
    SUCCESSION_EVENT: 55,
    LINE_FAILED_EVENT: 70,
    ABSORPTION_EVENT: 75,
    # A faction's yearly intent is deliberately low: one fires for every power
    # every year, so it stays below the important-only cutoff and out of the
    # default feed, surfacing only under "show all" and on faction inspection.
    FACTION_INTENT_EVENT: 6,
    # Diplomacy (ticket 09): war is the era-shaping extreme; the peaceful bonds
    # descend from a fealty sworn, through a dynastic marriage, to an ordinary
    # treaty and the quiet deepening of an off-map pact.
    WAR_DECLARED_EVENT: 70,
    WAR_ENDED_EVENT: 65,
    VASSALAGE_EVENT: 55,
    MARRIAGE_EVENT: 45,
    TREATY_EVENT: 40,
    PROVIDER_PACT_EVENT: 35,
    # Armies & movement (ticket 10): a host taking the field and reaching its
    # objective are campaign-shaping; a host melting away on the march is graver
    # still. All sit above the important-only cutoff so campaigns read in the feed.
    ARMY_MUSTERED_EVENT: 35,
    ARMY_ARRIVED_EVENT: 40,
    ARMY_DISBANDED_EVENT: 45,
    # War & battles (ticket 11): a realm conquered or a land razed is history's
    # loudest event; a pitched battle rings just below; a siege in progress and a
    # coastal raid are steady campaign noise that still clears the important cut.
    CONQUEST_EVENT: 85,
    RAZING_EVENT: 80,
    BATTLE_EVENT: 60,
    SIEGE_EVENT: 45,
    COASTAL_RAID_EVENT: 40,
    # Construction & economy (ticket 12): a new-founded or rebuilt settlement is a
    # mark on the map that clears the important-only cut; a settlement growing and
    # a road opening are quieter civic works that read only under "show all".
    FOUNDING_EVENT: 40,
    SETTLEMENT_GREW_EVENT: 28,
    ROAD_OPENED_EVENT: 22,
    _HEARTBEAT_EVENT: 0,  # the placeholder tick is never important
}

# The base weight for a type with no registered entry — legible but modest, so a
# newly-introduced event type is never silently invisible.
_DEFAULT_BASE_WEIGHT = 30

# Prominence → multiplier, in permille (1000 = ×1.0). A subject with no
# prominence still lets the type's base weight through at half strength; an
# ordinary named person (~50) is ~neutral; a king or Ring-bearer maxes the cap.
# All integer, so scoring never hinges on float rounding (float-determinism).
_UNIT = 1000
_PROM_FLOOR = 500
_PROM_SLOPE = 10
_PROM_CAP = 2500


def subject_prominence(world: World, event: Event) -> int:
    """The prominence of the event's most prominent subject (0 if none resolve).

    Reads the ``prominence`` field off each subject entity, so it honours a
    character's prominence today and a faction's prominence unchanged once
    factions carry one (ticket 07) — same field, same query.
    """
    best = 0
    for sid in event.subject_ids:
        entity = world.entities.get(sid)
        if entity is None:
            continue
        best = max(best, int(getattr(entity, "prominence", 0) or 0))
    return best


def _prominence_factor(prominence: int) -> int:
    """Permille multiplier for a subject prominence, floored and capped."""
    return min(_PROM_CAP, _PROM_FLOOR + max(0, prominence) * _PROM_SLOPE)


def _scale_factor(event: Event) -> int:
    """Permille multiplier for an event's *magnitude* beyond its subject.

    Neutral (×1.0) for the framework's current types; the seam later tickets
    use to scale a battle by its casualties, a conquest by the territory taken,
    and so on, by reading ``event.payload``.
    """
    return _UNIT


def _canon_factor(event: Event, canonicity: float) -> int:
    """Permille multiplier bumping canon-aligned events toward ``canonicity``.

    Neutral (×1.0) here: none of the current types are canon-aligned. Later
    tickets flag the canon-weighty types (the Ring moving, Sauron's rise) and
    this becomes ``1000 + int(canonicity × bump)`` for them — still integer.
    """
    return _UNIT


def score_importance(event: Event, prominence: int, canonicity: float) -> int:
    """The absolute salience (0–100) of an event at emission.

    ``base-weight × prominence-factor × scale × canon-bump``, all integer, then
    clamped. Deterministic and RNG-free, so the same run scores every event
    identically across processes.
    """
    base = BASE_WEIGHT.get(event.type, _DEFAULT_BASE_WEIGHT)
    if base <= 0:
        return MIN_IMPORTANCE
    raw = base * _prominence_factor(prominence) * _scale_factor(event) * _canon_factor(event, canonicity)
    importance = raw // (_UNIT * _UNIT * _UNIT)
    return max(MIN_IMPORTANCE, min(MAX_IMPORTANCE, importance))


# =========================================================================
# Prose — per-type templates over a seeded phrase-grammar
# =========================================================================

class _RenderContext:
    """Resolves the ids in an event to the words a template needs.

    Subject names come from the world; place names from an optional site-name
    map (``site id -> name``) so location prose works once a caller threads the
    grid, and degrades gracefully to no place-name until then.
    """

    def __init__(self, world: World, site_names: Mapping[int, str]) -> None:
        self._entities = world.entities
        self._site_names = site_names

    def name(self, entity_id: int) -> str:
        entity = self._entities.get(entity_id)
        return entity.name if entity is not None else f"someone (#{entity_id})"

    def place(self, location_id: Optional[int]) -> Optional[str]:
        if location_id is None:
            return None
        return self._site_names.get(location_id)


def _pick(options: Sequence[str], event: Event, salt: int = 0) -> str:
    """Deterministically choose one phrasing, seeded by the event's id.

    A pure function of ``(event.id, salt)``: the same event always renders the
    same way (chronicle determinism), while distinct choice points vary through
    ``salt``. No RNG and no ``hash()`` — both are barred here.
    """
    return options[(event.id + salt) % len(options)]


def _render_birth(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    child = ctx.name(subjects[0]) if subjects else "a child"
    if len(subjects) >= 3:
        mother, father = ctx.name(subjects[1]), ctx.name(subjects[2])
        template = _pick(
            (
                "{child} was born to {mother} and {father}.",
                "To {mother} and {father} was born {child}.",
                "A child, {child}, came to {mother} and {father}.",
            ),
            event,
        )
        return template.format(child=child, mother=mother, father=father)
    template = _pick(("{child} was born.", "{child} came into the world."), event)
    return template.format(child=child)


def _render_death(ctx: _RenderContext, event: Event) -> str:
    name = ctx.name(event.subject_ids[0]) if event.subject_ids else "someone"
    cause = (event.payload or {}).get("cause")
    if cause and cause != "natural":
        template = _pick(
            ("{name} was slain.", "{name} fell.", "{name} met their end in violence."),
            event,
            salt=1,
        )
    else:
        template = _pick(
            (
                "{name} died.",
                "{name} passed away.",
                "{name} came to the end of their days.",
            ),
            event,
            salt=2,
        )
    return template.format(name=name)


def _render_departed(ctx: _RenderContext, event: Event) -> str:
    name = ctx.name(event.subject_ids[0]) if event.subject_ids else "an Elf"
    template = _pick(
        (
            "{name} sailed West over the Sea.",
            "{name} took ship into the West.",
            "{name} passed over the Sea, leaving Middle-earth behind.",
        ),
        event,
        salt=3,
    )
    return template.format(name=name)


# Phase-2 intent verbs → a chronicle phrasing. Keeps the low-salience faction
# turn readable under "show all" without leaking the internal enum name.
_INTENT_PHRASING: Dict[str, str] = {
    "muster": "called up its levies",
    "attack": "made ready for war",
    "fortify": "looked to its defences",
    "seek_pact": "sought new alliances",
    "build": "turned to building and husbandry",
}


def _render_faction_intent(ctx: _RenderContext, event: Event) -> str:
    name = ctx.name(event.subject_ids[0]) if event.subject_ids else "a power"
    payload = event.payload or {}
    verb = _INTENT_PHRASING.get(payload.get("intent"), "took counsel")
    target_id = payload.get("target_faction_id")
    if target_id:
        return f"{name} made ready for war against {ctx.name(target_id)}."
    return f"{name} {verb}."


def _render_succession(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    heir = ctx.name(subjects[0]) if subjects else "an heir"
    payload = event.payload or {}
    title = payload.get("title")
    as_title = f" as {title}" if title else ""
    former_id = payload.get("former_leader_id")
    if former_id is not None:
        return f"{heir} succeeded {ctx.name(former_id)}{as_title}."
    realm = ctx.name(subjects[1]) if len(subjects) >= 2 else "the realm"
    return f"{heir} took up the rule of {realm}{as_title}."


def _render_line_failed(ctx: _RenderContext, event: Event) -> str:
    realm = ctx.name(event.subject_ids[0]) if event.subject_ids else "a realm"
    template = _pick(
        (
            "The ruling line of {realm} failed, and no heir remained.",
            "The line of {realm} came to an end, leaving no heir.",
            "With none left to rule, the line of {realm} was extinguished.",
        ),
        event,
        salt=4,
    )
    return template.format(realm=realm)


def _render_absorption(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    fallen = ctx.name(subjects[0]) if subjects else "a realm"
    absorber = ctx.name(subjects[1]) if len(subjects) >= 2 else "a neighbour"
    template = _pick(
        (
            "{fallen} was absorbed into {absorber}.",
            "The lands of {fallen} passed to {absorber}.",
            "{absorber} took the leaderless lands of {fallen}.",
        ),
        event,
        salt=5,
    )
    return template.format(fallen=fallen, absorber=absorber)


def _render_treaty(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    a = ctx.name(subjects[0]) if subjects else "a realm"
    b = ctx.name(subjects[1]) if len(subjects) >= 2 else "another"
    template = _pick(
        (
            "{a} and {b} bound themselves in a treaty of alliance.",
            "A treaty of friendship was sealed between {a} and {b}.",
            "{a} and {b} swore alliance.",
        ),
        event,
        salt=6,
    )
    return template.format(a=a, b=b)


def _render_marriage(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    bride_a = ctx.name(subjects[0]) if subjects else "one"
    bride_b = ctx.name(subjects[1]) if len(subjects) >= 2 else "another"
    payload = event.payload or {}
    realm_a = ctx.name(payload.get("realm_a")) if payload.get("realm_a") else None
    realm_b = ctx.name(payload.get("realm_b")) if payload.get("realm_b") else None
    if realm_a and realm_b:
        return f"{bride_a} of {realm_a} wed {bride_b} of {realm_b}, joining their houses."
    return f"{bride_a} and {bride_b} were wed, joining their houses."


def _render_vassalage(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    vassal = ctx.name(subjects[0]) if subjects else "a realm"
    overlord = ctx.name(subjects[1]) if len(subjects) >= 2 else "a high king"
    if (event.payload or {}).get("bond") == "broken":
        template = _pick(
            (
                "{vassal} cast off the overlordship of {overlord}.",
                "{vassal} broke free of {overlord} and stood alone again.",
            ),
            event,
            salt=7,
        )
    else:
        template = _pick(
            (
                "{vassal} swore fealty to {overlord}.",
                "{vassal} bent the knee and took {overlord} for its overlord.",
            ),
            event,
            salt=8,
        )
    return template.format(vassal=vassal, overlord=overlord)


def _render_provider_pact(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    patron = ctx.name(subjects[0]) if subjects else "a power"
    provider = ctx.name(subjects[1]) if len(subjects) >= 2 else "an outland people"
    template = _pick(
        (
            "{patron} deepened its pact with the {provider}.",
            "The {provider} pledged themselves more firmly to {patron}.",
        ),
        event,
        salt=9,
    )
    return template.format(patron=patron, provider=provider)


def _render_war_declared(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    a = ctx.name(subjects[0]) if subjects else "a realm"
    b = ctx.name(subjects[1]) if len(subjects) >= 2 else "another"
    if (event.payload or {}).get("betrayal"):
        template = _pick(
            (
                "{a} broke faith and fell upon {b}.",
                "In betrayal of their pact, {a} declared war upon {b}.",
            ),
            event,
            salt=10,
        )
    else:
        template = _pick(
            (
                "{a} declared war upon {b}.",
                "War was proclaimed by {a} against {b}.",
            ),
            event,
            salt=11,
        )
    return template.format(a=a, b=b)


def _render_army_mustered(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    faction = ctx.name(subjects[1]) if len(subjects) >= 2 else "a power"
    payload = event.payload or {}
    place = ctx.place(event.location_id)
    at = f" at {place}" if place else ""
    leader = ctx.name(subjects[2]) if len(subjects) >= 3 else None
    under = f" under {leader}" if leader else ""
    target_id = payload.get("target_faction_id")
    if target_id:
        return f"{faction} mustered a host{at}{under} and marched against {ctx.name(target_id)}."
    return f"{faction} mustered a host{at}{under}."


def _render_army_arrived(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    faction = ctx.name(subjects[1]) if len(subjects) >= 2 else "a host"
    place = ctx.place(event.location_id)
    at = f" before {place}" if place else ""
    return f"The host of {faction} came{at}."


def _render_army_disbanded(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    faction = ctx.name(subjects[1]) if len(subjects) >= 2 else "a host"
    template = _pick(
        (
            "The host of {faction} melted away on the march, its strength spent.",
            "Worn down by the long road, the host of {faction} broke up and was no more.",
        ),
        event,
        salt=13,
    )
    return template.format(faction=faction)


def _render_battle(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    winner = ctx.name(subjects[0]) if subjects else "a host"
    loser = ctx.name(subjects[1]) if len(subjects) >= 2 else "another"
    place = ctx.place(event.location_id)
    at = f" before {place}" if place else ""
    if (event.payload or {}).get("tier") == "decisive":
        template = _pick(
            (
                "{winner} broke {loser} in the field{at}.",
                "{winner} routed {loser}{at}, and the day was theirs.",
            ),
            event,
            salt=14,
        )
    else:
        template = _pick(
            (
                "{winner} bested {loser} in a hard-fought battle{at}.",
                "{winner} and {loser} met in battle{at}, and {winner} held the field.",
            ),
            event,
            salt=15,
        )
    return template.format(winner=winner, loser=loser, at=at)


def _render_siege(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    besieger = ctx.name(subjects[1]) if len(subjects) >= 2 else "a host"
    place = ctx.place(event.location_id)
    at = f" {place}" if place else " the seat"
    template = _pick(
        (
            "{besieger} pressed the siege of{at}.",
            "The host of {besieger} lay before{at}, and its walls yet held.",
        ),
        event,
        salt=16,
    )
    return template.format(besieger=besieger, at=at)


def _render_conquest(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    fallen = ctx.name(subjects[0]) if subjects else "a realm"
    conqueror = ctx.name(subjects[1]) if len(subjects) >= 2 else "a conqueror"
    place = ctx.place(event.location_id)
    if place:
        template = _pick(
            (
                "{place} fell, and {conqueror} took the lands of {fallen}.",
                "{place} was stormed, and {fallen} was conquered by {conqueror}.",
            ),
            event,
            salt=17,
        )
    else:
        template = _pick(
            (
                "{conqueror} took the lands of {fallen}.",
                "{fallen} was conquered by {conqueror}.",
            ),
            event,
            salt=17,
        )
    return template.format(place=place, conqueror=conqueror, fallen=fallen)


def _render_razing(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    fallen = ctx.name(subjects[0]) if subjects else "a realm"
    razer = ctx.name(subjects[1]) if len(subjects) >= 2 else "the enemy"
    place = ctx.place(event.location_id)
    at = f" {place}" if place else " the seat"
    template = _pick(
        (
            "{razer} put{at} to the torch and left only ruin.",
            "The lands of {fallen} were laid waste by {razer}.",
        ),
        event,
        salt=18,
    )
    return template.format(razer=razer, fallen=fallen, at=at)


def _render_coastal_raid(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    raider = ctx.name(subjects[0]) if subjects else "raiders"
    target = ctx.name(subjects[1]) if len(subjects) >= 2 else "the coast"
    place = ctx.place(event.location_id)
    at = f" {place}" if place else " the coast"
    template = _pick(
        (
            "The {raider} fell upon{at} and harried the shores of {target}.",
            "{raider} raiders pillaged{at}, coast of {target}.",
        ),
        event,
        salt=19,
    )
    return template.format(raider=raider, target=target, at=at)


def _render_founding(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    builder = ctx.name(subjects[0]) if subjects else "a realm"
    payload = event.payload or {}
    place = ctx.place(event.location_id)
    at = f" {place}" if place else ""
    if payload.get("kind") == "fort":
        template = _pick(
            (
                "{builder} raised a fortress{at} to guard its marches.",
                "A stronghold was built{at} at the bidding of {builder}.",
            ),
            event,
            salt=20,
        )
    elif payload.get("rebuilt"):
        template = _pick(
            (
                "{builder} raised{at} anew from its ruins.",
                "The ruins{at} were rebuilt under {builder}.",
            ),
            event,
            salt=21,
        )
    else:
        template = _pick(
            (
                "{builder} founded a new town{at}.",
                "A settlement was founded{at} by {builder}.",
            ),
            event,
            salt=22,
        )
    return template.format(builder=builder, at=at)


def _render_settlement_grew(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    builder = ctx.name(subjects[0]) if subjects else "a realm"
    place = ctx.place(event.location_id)
    at = f" {place}" if place else " one of its towns"
    template = _pick(
        (
            "Under {builder},{at} grew into a city.",
            "{builder} saw{at} rise to a city.",
        ),
        event,
        salt=23,
    )
    return template.format(builder=builder, at=at)


def _render_road_opened(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    builder = ctx.name(subjects[0]) if subjects else "a realm"
    place = ctx.place(event.location_id)
    at = f" from {place}" if place else ""
    template = _pick(
        (
            "{builder} opened a new road{at} across its lands.",
            "A road was laid{at} at the labour of {builder}.",
        ),
        event,
        salt=24,
    )
    return template.format(builder=builder, at=at)


def _render_war_ended(ctx: _RenderContext, event: Event) -> str:
    subjects = event.subject_ids
    a = ctx.name(subjects[0]) if subjects else "a realm"
    b = ctx.name(subjects[1]) if len(subjects) >= 2 else "another"
    template = _pick(
        (
            "{a} and {b} laid down their arms and made peace.",
            "Peace was made between {a} and {b}.",
        ),
        event,
        salt=12,
    )
    return template.format(a=a, b=b)


# The per-type renderer registry. A type with no renderer yields no prose (the
# feed shows a structured placeholder for it) — this is where later tickets
# register their templates.
_RENDERERS: Dict[str, Callable[[_RenderContext, Event], str]] = {
    BIRTH_EVENT: _render_birth,
    DEATH_EVENT: _render_death,
    DEPARTED_EVENT: _render_departed,
    FACTION_INTENT_EVENT: _render_faction_intent,
    SUCCESSION_EVENT: _render_succession,
    LINE_FAILED_EVENT: _render_line_failed,
    ABSORPTION_EVENT: _render_absorption,
    TREATY_EVENT: _render_treaty,
    MARRIAGE_EVENT: _render_marriage,
    VASSALAGE_EVENT: _render_vassalage,
    PROVIDER_PACT_EVENT: _render_provider_pact,
    WAR_DECLARED_EVENT: _render_war_declared,
    WAR_ENDED_EVENT: _render_war_ended,
    ARMY_MUSTERED_EVENT: _render_army_mustered,
    ARMY_ARRIVED_EVENT: _render_army_arrived,
    ARMY_DISBANDED_EVENT: _render_army_disbanded,
    BATTLE_EVENT: _render_battle,
    SIEGE_EVENT: _render_siege,
    CONQUEST_EVENT: _render_conquest,
    RAZING_EVENT: _render_razing,
    COASTAL_RAID_EVENT: _render_coastal_raid,
    FOUNDING_EVENT: _render_founding,
    SETTLEMENT_GREW_EVENT: _render_settlement_grew,
    ROAD_OPENED_EVENT: _render_road_opened,
}


def render_text(
    world: World, event: Event, site_names: Optional[Mapping[int, str]] = None
) -> Optional[str]:
    """Render an event's prose, or ``None`` if its type has no template yet.

    Deterministic and offline. This whole function is the swappable seam: a
    future LLM backend replaces it and nothing upstream changes.
    """
    renderer = _RENDERERS.get(event.type)
    if renderer is None:
        return None
    return renderer(_RenderContext(world, site_names or {}), event)


# =========================================================================
# The emission seam
# =========================================================================

def finalize_event(
    world: World, event: Event, site_names: Optional[Mapping[int, str]] = None
) -> Event:
    """Stamp ``importance`` and ``text`` on a freshly-built event, in place.

    The single call the pipeline makes as each event enters the log, so scoring
    and phrasing happen exactly once, at emission, and are immutable thereafter.
    """
    prominence = subject_prominence(world, event)
    event.importance = score_importance(event, prominence, world.config.canonicity)
    event.text = render_text(world, event, site_names)
    return event


# =========================================================================
# The feed — filtering and pulses
# =========================================================================

# An empty subject→faction index: the default until factions exist (ticket 07).
_NO_FACTIONS: Mapping[int, int] = {}


@dataclass(frozen=True)
class AnnalsFilter:
    """Which events the annals feed shows.

    The four query indices (subject, faction, year, type) — any left ``None`` is
    unconstrained — plus an absolute importance threshold. Defaults to the feed's
    important-only view; :func:`show_all_filter` widens it to everything.
    """

    min_importance: int = IMPORTANT_THRESHOLD
    type: Optional[str] = None
    year: Optional[int] = None
    subject_id: Optional[int] = None
    faction_id: Optional[int] = None
    # Types hidden outright (the UI's category chips exclude whole buckets by
    # naming their member types); None/empty excludes nothing. ANDs with the
    # other constraints like every index does.
    excluded_types: Optional[FrozenSet[str]] = None

    def matches(self, event: Event, faction_of: Mapping[int, int] = _NO_FACTIONS) -> bool:
        """Whether ``event`` passes this filter.

        Faction membership is resolved through ``faction_of`` (a subject id →
        faction id map): an event matches a faction if any of its subjects
        belong to it. With no such index yet, a faction filter matches nothing.
        """
        if event.importance < self.min_importance:
            return False
        if self.type is not None and event.type != self.type:
            return False
        if self.excluded_types and event.type in self.excluded_types:
            return False
        if self.year is not None and event.year != self.year:
            return False
        if self.subject_id is not None and self.subject_id not in event.subject_ids:
            return False
        if self.faction_id is not None:
            factions = {faction_of.get(sid) for sid in event.subject_ids}
            if self.faction_id not in factions:
                return False
        return True


def show_all_filter() -> AnnalsFilter:
    """The one-click "show all" filter: no threshold, no index constraints."""
    return AnnalsFilter(min_importance=MIN_IMPORTANCE)


def pulse_events(events: Sequence[Event], threshold: int = IMPORTANT_THRESHOLD) -> List[Event]:
    """The events that should fire a transient on-map pulse.

    Above the importance ``threshold`` and anchored to a place (they have a
    ``location_id`` to pulse at). Order is preserved.
    """
    return [e for e in events if e.importance >= threshold and e.location_id is not None]
