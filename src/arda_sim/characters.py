"""Characters & lifecycle — tick phase 1 (build ticket 05).

Named people who live and die over the years. A :class:`Character` is an ordinary
id-keyed :class:`~arda_sim.entities.Entity` subtype; there is no Dynasty record —
a bloodline is just a query over the kinship id-fields (``parent_ids``,
``spouse_id``).

Phase 1 (:func:`aging_births_deaths`) ages everyone, rolls natural/disease deaths
against a per-race age→annual-death curve, and produces births on established
couples — all off the single seeded RNG, using integer (basis-point) comparisons
so outcomes never hinge on float rounding. Immortals (Elves, Maiar) skip the
death roll entirely; Elves instead accrue a weariness drive and eventually
**depart** over the Sea (status ``departed``). Violent death is *not* rolled here
— that is war's job (ticket 11).

The TA 2965 canon roster is seeded by :func:`seed_roster`; characters born after
the start year are deliberately absent until the sim produces them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from . import START_YEAR
from .entities import Entity, EntityStatus, Event, register_entity_type
from .scenarios import load_scenario
from .world import World

# Basis points: probabilities are integers out of this, so every life-or-death
# comparison is ``rng.randrange(BP_SCALE) < probability_bp`` — pure integer math.
BP_SCALE = 10_000

# Elf weariness: each year an Elf accrues a small increment; once accrued
# weariness crosses the threshold they sail West. Tuned so departures unfold over
# centuries, not decades — the fading Third Age, not an exodus.
_WEARINESS_THRESHOLD = 6_000
_WEARINESS_BASE = 8
_WEARINESS_JITTER = 25  # exclusive upper bound of the per-year random add

_TRAIT_KEYS = ("leadership", "martial", "ambition", "loyalty", "wisdom", "guile")
_DEFAULT_TRAIT = 50
_HERITABILITY_JITTER = 12  # +/- spread of a child's trait around the parent mean


class Race(str, Enum):
    MAN = "man"
    HOBBIT = "hobbit"
    ORC = "orc"
    DUNEDAIN = "dunedain"
    DWARF = "dwarf"
    ELF = "elf"
    MAIA = "maia"

    def __str__(self) -> str:
        return self.value


class MortalityKind(str, Enum):
    MORTAL = "mortal"
    LONG_LIVED = "long_lived"
    IMMORTAL = "immortal"

    def __str__(self) -> str:
        return self.value


class Role(str, Enum):
    RULER = "ruler"
    HEIR = "heir"
    GENERAL = "general"
    RING_BEARER = "ring_bearer"
    RANGER = "ranger"
    COUNCILLOR = "councillor"
    NONE = "none"

    def __str__(self) -> str:
        return self.value


# Event types this phase emits.
BIRTH_EVENT = "birth"
DEATH_EVENT = "death"
DEPARTED_EVENT = "departed"


@dataclass
class RaceConfig:
    """Per-race lifecycle data. ``death_curve`` is ascending ``(min_age, bp)``
    breakpoints: the annual natural-death probability is the ``bp`` of the highest
    ``min_age`` at or below the character's age (0 below the first breakpoint).
    ``fertility_window`` is the inclusive mother-age range for births.
    """

    mortality_kind: MortalityKind
    maturity_age: int
    fertility_window: tuple  # (min_age, max_age), inclusive
    fertility_bp: int  # annual per-couple birth probability, basis points
    death_curve: tuple  # ((min_age, bp), ...) ascending; empty for immortals


# The race table. Immortals carry an empty death curve and never roll to die.
RACE_CONFIG: Dict[Race, RaceConfig] = {
    Race.MAN: RaceConfig(
        MortalityKind.MORTAL, 18, (18, 45), 1400,
        ((0, 10), (40, 80), (55, 300), (70, 1200), (85, 4000), (100, 8000)),
    ),
    Race.HOBBIT: RaceConfig(
        MortalityKind.MORTAL, 22, (24, 50), 1300,
        ((0, 8), (50, 60), (70, 250), (90, 1200), (105, 4000), (120, 8000)),
    ),
    Race.ORC: RaceConfig(
        MortalityKind.MORTAL, 12, (12, 40), 1600,
        ((0, 50), (30, 300), (45, 1500), (60, 5000)),
    ),
    Race.DUNEDAIN: RaceConfig(
        MortalityKind.LONG_LIVED, 25, (25, 90), 1000,
        ((0, 5), (90, 50), (140, 300), (180, 1500), (210, 5000)),
    ),
    Race.DWARF: RaceConfig(
        MortalityKind.LONG_LIVED, 30, (40, 150), 700,
        ((0, 4), (150, 60), (220, 400), (260, 2000), (300, 6000)),
    ),
    Race.ELF: RaceConfig(MortalityKind.IMMORTAL, 50, (50, 3000), 200, ()),
    Race.MAIA: RaceConfig(MortalityKind.IMMORTAL, 0, (0, 0), 0, ()),
}


@dataclass
class Character(Entity):
    """A named person. Extends the entity base with lifecycle, kinship, traits.

    ``created_year`` (base) is when the record entered the world; ``birth_year``
    is the canonical birth year, which for a seeded character predates the sim.
    All cross-references are ids: ``parent_ids``/``spouse_id`` are entity ids,
    ``location_id`` is a config-space site id (see :class:`~arda_sim.tiles.Site`),
    ``faction_id`` an entity id (factions arrive in ticket 07).
    """

    race: str = Race.MAN.value
    birth_year: int = START_YEAR
    sex: str = "M"  # "M" | "F"; the mother (F) drives the fertility roll
    location_id: Optional[int] = None
    faction_id: Optional[int] = None
    role: str = Role.NONE.value
    title: Optional[str] = None
    traits: Dict[str, int] = field(default_factory=dict)
    parent_ids: List[int] = field(default_factory=list)
    spouse_id: Optional[int] = None
    weariness: int = 0  # Elves only; accrues toward departure over the Sea
    prominence: int = 0  # derived salience (role + trait magnitude + title)

    def age(self, year: int) -> int:
        return year - self.birth_year

    @property
    def alive(self) -> bool:
        """In play — neither dead nor departed. Kinship still resolves either way."""
        return self.status == EntityStatus.ACTIVE.value


register_entity_type("character", Character)


# -- derived fields -------------------------------------------------------

_ROLE_WEIGHT = {
    Role.RULER.value: 100,
    Role.RING_BEARER.value: 90,
    Role.HEIR.value: 70,
    Role.GENERAL.value: 60,
    Role.COUNCILLOR.value: 40,
    Role.RANGER.value: 30,
    Role.NONE.value: 0,
}


def compute_prominence(char: Character) -> int:
    """Derived salience: role weight + strongest trait + a title bonus.

    Owned here so the chronicle (ticket 06) reads a field rather than reinventing
    a scoring rule.
    """
    top_trait = max(char.traits.values(), default=0)
    title_bonus = 20 if char.title else 0
    return _ROLE_WEIGHT.get(char.role, 0) + top_trait + title_bonus


def _filled_traits(partial: Optional[Dict[str, int]]) -> Dict[str, int]:
    """A full trait vector: authored values over the neutral default."""
    traits = {k: _DEFAULT_TRAIT for k in _TRAIT_KEYS}
    if partial:
        traits.update({k: int(v) for k, v in partial.items() if k in _TRAIT_KEYS})
    return traits


# -- construction ---------------------------------------------------------

def add_character(
    world: World,
    name: str,
    race: Race,
    birth_year: int,
    sex: str = "M",
    role: Role = Role.NONE,
    location_id: Optional[int] = None,
    faction_id: Optional[int] = None,
    title: Optional[str] = None,
    traits: Optional[Dict[str, int]] = None,
    parent_ids: Optional[List[int]] = None,
    spouse_id: Optional[int] = None,
    status: str = EntityStatus.ACTIVE.value,
) -> Character:
    """Create and register a Character with a fresh id at the current year."""
    char = Character(
        id=world.next_id(),
        kind="character",
        name=name,
        created_year=world.current_year,
        status=status,
        race=race.value if isinstance(race, Race) else race,
        birth_year=birth_year,
        sex=sex,
        location_id=location_id,
        faction_id=faction_id,
        role=role.value if isinstance(role, Role) else role,
        title=title,
        traits=_filled_traits(traits),
        parent_ids=list(parent_ids) if parent_ids else [],
        spouse_id=spouse_id,
    )
    char.prominence = compute_prominence(char)
    world.entities[char.id] = char
    return char


# -- lifecycle math -------------------------------------------------------

def annual_death_bp(race: Race, age: int) -> int:
    """Natural/disease annual death probability (basis points) for a race & age.

    Immortals (empty curve) return 0 — they never roll to die.
    """
    curve = RACE_CONFIG[race].death_curve
    bp = 0
    for min_age, value in curve:
        if age >= min_age:
            bp = value
        else:
            break
    return bp


def is_immortal(race: Race) -> bool:
    return RACE_CONFIG[race].mortality_kind is MortalityKind.IMMORTAL


def _living_characters(world: World) -> List[Character]:
    """Active characters in ascending id order (deterministic iteration)."""
    return [
        e
        for _id, e in sorted(world.entities.items())
        if isinstance(e, Character) and e.alive
    ]


# -- phase 1 --------------------------------------------------------------

def aging_births_deaths(world: World, rng: random.Random) -> List[Event]:
    """Phase 1: age everyone, roll natural deaths and Elf departures, then births.

    Deterministic given the RNG: characters are processed in id order, and each
    sub-phase (deaths, then births) runs as its own pass so ordering is stable.
    Returns the events emitted; the pipeline appends them.
    """
    year = world.current_year
    events: List[Event] = []

    # Pass 1 — deaths and departures. Snapshot the living set first so a death
    # this year cannot cascade within the same pass.
    for char in _living_characters(world):
        race = Race(char.race)
        if is_immortal(race):
            events.extend(_maybe_depart(world, rng, char))
            continue
        bp = annual_death_bp(race, char.age(year))
        if bp > 0 and rng.randrange(BP_SCALE) < bp:
            events.append(_kill(world, char, cause="natural"))

    # Pass 2 — births on established couples (both partners still alive after the
    # death pass). Iterate the mothers so each couple rolls exactly once.
    for mother in _living_characters(world):
        if mother.sex != "F" or mother.spouse_id is None:
            continue
        father = world.entities.get(mother.spouse_id)
        if not isinstance(father, Character) or not father.alive:
            continue
        birth = _maybe_birth(world, rng, mother, father)
        if birth is not None:
            events.append(birth)

    return events


def _kill(world: World, char: Character, cause: str) -> Event:
    """Tombstone a character as dead (record kept; kinship still resolves)."""
    char.status = EntityStatus.DEAD.value
    return world.new_event(
        type=DEATH_EVENT,
        subject_ids=[char.id],
        location_id=char.location_id,
        importance=char.prominence,
        payload={"cause": cause, "age": char.age(world.current_year), "race": char.race},
        text=f"{char.name} died.",
    )


def _maybe_depart(world: World, rng: random.Random, char: Character) -> List[Event]:
    """Accrue Elf weariness; once it crosses the threshold, sail West.

    Only Elves depart — Maiar are immortal but stay (their fates are the Ring's
    and Sauron's, tickets 13/14), so they accrue nothing.
    """
    if char.race != Race.ELF.value:
        return []
    char.weariness += _WEARINESS_BASE + rng.randrange(_WEARINESS_JITTER)
    if char.weariness < _WEARINESS_THRESHOLD:
        return []
    char.status = EntityStatus.DEPARTED.value
    return [
        world.new_event(
            type=DEPARTED_EVENT,
            subject_ids=[char.id],
            location_id=char.location_id,
            importance=char.prominence,
            payload={"race": char.race, "age": char.age(world.current_year)},
            text=f"{char.name} sailed West over the Sea.",
        )
    ]


def _maybe_birth(
    world: World, rng: random.Random, mother: Character, father: Character
) -> Optional[Event]:
    """Roll a birth for an established couple; on success create the child."""
    race = Race(mother.race)
    cfg = RACE_CONFIG[race]
    lo, hi = cfg.fertility_window
    mother_age = mother.age(world.current_year)
    if not (lo <= mother_age <= hi):
        return None
    if father.age(world.current_year) < RACE_CONFIG[Race(father.race)].maturity_age:
        return None
    if cfg.fertility_bp <= 0 or rng.randrange(BP_SCALE) >= cfg.fertility_bp:
        return None

    child = _bear_child(world, rng, mother, father)
    return world.new_event(
        type=BIRTH_EVENT,
        subject_ids=[child.id, mother.id, father.id],
        location_id=child.location_id,
        importance=child.prominence,
        payload={"race": child.race, "sex": child.sex},
        text=f"{child.name} was born.",
    )


# Neutral generated names — real names arrive with the naming system; until then
# a child is legible as "<race>-child of <mother>" via the parent link.
def _child_name(mother: Character) -> str:
    return f"Child of {mother.name}"


def _bear_child(
    world: World, rng: random.Random, mother: Character, father: Character
) -> Character:
    """Create a child of this couple: race from mother, traits mildly heritable."""
    sex = "F" if rng.randrange(2) == 0 else "M"
    traits = {
        k: _clamp(
            (mother.traits.get(k, _DEFAULT_TRAIT) + father.traits.get(k, _DEFAULT_TRAIT)) // 2
            + rng.randrange(-_HERITABILITY_JITTER, _HERITABILITY_JITTER + 1)
        )
        for k in _TRAIT_KEYS
    }
    return add_character(
        world,
        name=_child_name(mother),
        race=Race(mother.race),
        birth_year=world.current_year,
        sex=sex,
        role=Role.NONE,
        location_id=mother.location_id,
        faction_id=mother.faction_id,
        traits=traits,
        parent_ids=[mother.id, father.id],
    )


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


# -- queries --------------------------------------------------------------

def character_timeline(world: World, char_id: int) -> List[Event]:
    """Every event naming this character, oldest first — the inspection timeline.

    Works for tombstoned (dead/departed) characters too; their records are never
    deleted, so the whole life reads back.
    """
    return sorted(
        (ev for ev in world.events if char_id in ev.subject_ids),
        key=lambda ev: (ev.year, ev.id),
    )


def characters(world: World, *, alive_only: bool = False) -> List[Character]:
    """All Character records in id order (optionally only those still in play)."""
    result = [e for _id, e in sorted(world.entities.items()) if isinstance(e, Character)]
    return [c for c in result if c.alive] if alive_only else result


# -- seeding --------------------------------------------------------------

# The scenario whose sites anchor the canon roster's home locations. The run
# config's scenario_id is the abstract identity; this is the bundled data file.
_ROSTER_SCENARIO_FILE = "arda_ta2965"


@dataclass(frozen=True)
class _Seed:
    """One authored roster entry. ``home`` is a site name resolved to an id at
    seed time; ``spouse`` / ``parents`` are names resolved after all are created.
    """

    name: str
    race: Race
    birth_year: int
    sex: str = "M"
    role: Role = Role.NONE
    home: Optional[str] = None
    title: Optional[str] = None
    traits: Optional[Dict[str, int]] = None
    spouse: Optional[str] = None
    parents: tuple = ()


# An "ancient" birth year for beings older than reliable dating (Ainur, elder
# Eldar) — safely before the First Age, so their computed age is merely "vast".
_ANCIENT = -3000

# The canon roster living in TA 2965 (north-west Middle-earth theatre). Characters
# born after the start year (Frodo 2968, Boromir 2978, Éomer 2991, ...) are
# deliberately omitted — the sim must produce them, not seed them.
_ROSTER: tuple = (
    # Gondor — ruling Stewards (Dúnedain of Gondor, long-lived).
    _Seed("Ecthelion II", Race.DUNEDAIN, 2886, "M", Role.RULER, "Minas Tirith",
          "Steward of Gondor", {"leadership": 80, "wisdom": 75}),
    _Seed("Denethor II", Race.DUNEDAIN, 2930, "M", Role.HEIR, "Minas Tirith",
          None, {"leadership": 78, "ambition": 80, "wisdom": 72}, parents=("Ecthelion II",)),
    _Seed("Adrahil II", Race.DUNEDAIN, 2917, "M", Role.RULER, "Dol Amroth",
          "Prince of Dol Amroth", {"leadership": 70}),
    _Seed("Imrahil", Race.DUNEDAIN, 2955, "M", Role.HEIR, "Dol Amroth",
          None, {"leadership": 74, "martial": 76}, parents=("Adrahil II",)),
    # Rohan — House of Eorl (Men).
    _Seed("Thengel", Race.MAN, 2905, "M", Role.RULER, "Edoras",
          "King of Rohan", {"leadership": 76, "martial": 78}),
    _Seed("Morwen", Race.MAN, 2922, "F", Role.NONE, "Edoras",
          None, {"wisdom": 70}, spouse="Thengel"),
    _Seed("Théoden", Race.MAN, 2948, "M", Role.HEIR, "Edoras",
          None, {"leadership": 72, "martial": 70}, parents=("Thengel", "Morwen")),
    # The Dúnedain of the North — the Heir of Isildur, in Rivendell's keeping.
    _Seed("Gilraen", Race.DUNEDAIN, 2907, "F", Role.NONE, "Rivendell"),
    _Seed("Aragorn", Race.DUNEDAIN, 2931, "M", Role.RANGER, "Rivendell",
          "Heir of Isildur", {"leadership": 92, "martial": 88, "wisdom": 80, "loyalty": 85},
          parents=("Gilraen",)),
    # Imladris — the House of Elrond (Elves; Half-elven kept as Elf-kind here).
    _Seed("Elrond", Race.ELF, _ANCIENT, "M", Role.RULER, "Rivendell",
          "Lord of Rivendell", {"wisdom": 95, "leadership": 85}),
    _Seed("Arwen", Race.ELF, 241, "F", Role.NONE, "Rivendell",
          None, {"wisdom": 80}, parents=("Elrond",)),
    _Seed("Elladan", Race.ELF, 130, "M", Role.NONE, "Rivendell",
          None, {"martial": 82}, parents=("Elrond",)),
    _Seed("Elrohir", Race.ELF, 130, "M", Role.NONE, "Rivendell",
          None, {"martial": 82}, parents=("Elrond",)),
    # Lothlórien.
    _Seed("Galadriel", Race.ELF, _ANCIENT, "F", Role.RULER, "Caras Galadhon",
          "Lady of Lórien", {"wisdom": 98, "leadership": 90}),
    _Seed("Celeborn", Race.ELF, _ANCIENT, "M", Role.RULER, "Caras Galadhon",
          "Lord of Lórien", {"wisdom": 85, "leadership": 82}, spouse="Galadriel"),
    # The Woodland Realm.
    _Seed("Thranduil", Race.ELF, _ANCIENT, "M", Role.RULER, "Thranduil's Halls",
          "Elvenking", {"leadership": 80, "martial": 78}),
    _Seed("Legolas", Race.ELF, 1200, "M", Role.NONE, "Thranduil's Halls",
          None, {"martial": 85}, parents=("Thranduil",)),
    # The Grey Havens.
    _Seed("Círdan", Race.ELF, _ANCIENT, "M", Role.RULER, "Grey Havens",
          "Shipwright", {"wisdom": 90}),
    # The Istari and the Enemy (Maiar — immortal, never depart).
    _Seed("Gandalf", Race.MAIA, _ANCIENT, "M", Role.COUNCILLOR, None,
          "Mithrandir", {"wisdom": 96, "leadership": 80}),
    _Seed("Saruman", Race.MAIA, _ANCIENT, "M", Role.RULER, "Isengard",
          "the White", {"wisdom": 92, "ambition": 85, "guile": 88}),
    _Seed("Sauron", Race.MAIA, _ANCIENT, "M", Role.RULER, "Barad-dûr",
          "the Dark Lord", {"ambition": 100, "guile": 98, "leadership": 95, "martial": 90}),
    # Erebor & the Iron Hills (Dwarves — Durin's Folk).
    _Seed("Dáin II Ironfoot", Race.DWARF, 2767, "M", Role.RULER, "Erebor",
          "King under the Mountain", {"leadership": 82, "martial": 84}),
    _Seed("Thorin III Stonehelm", Race.DWARF, 2866, "M", Role.HEIR, "Erebor",
          None, {"martial": 76}, parents=("Dáin II Ironfoot",)),
    _Seed("Glóin", Race.DWARF, 2783, "M", Role.NONE, "Erebor",
          None, {"martial": 70}),
    _Seed("Gimli", Race.DWARF, 2879, "M", Role.NONE, "Erebor",
          None, {"martial": 78, "loyalty": 88}, parents=("Glóin",)),
    # Dale — the restored kingdom of Men by the Mountain.
    _Seed("Bard I", Race.MAN, 2896, "M", Role.RULER, "Dale",
          "King of Dale", {"leadership": 78, "martial": 82}),
    _Seed("Bain", Race.MAN, 2924, "M", Role.HEIR, "Dale",
          None, {"leadership": 70}, parents=("Bard I",)),
    # The Shire.
    _Seed("Bilbo Baggins", Race.HOBBIT, 2890, "M", Role.RING_BEARER, "Michel Delving",
          "Ring-bearer", {"wisdom": 72, "loyalty": 80}),
)


def seed_roster(world: World, scenario_file: Optional[str] = None) -> List[Character]:
    """Seed the canon TA 2965 roster into ``world`` (no events — they predate play).

    Home site names are resolved to config-space ids via the scenario grid;
    spouse and parent links are resolved by name after every record exists. The
    world must be at its start year (seeding stamps ``created_year`` accordingly).
    """
    grid = load_scenario(scenario_file or _ROSTER_SCENARIO_FILE)
    by_name: Dict[str, Character] = {}

    for s in _ROSTER:
        location_id = grid.site_id_of(s.home) if s.home else None
        if s.home is not None and location_id is None:
            raise ValueError(f"roster home site {s.home!r} not found in scenario")
        char = add_character(
            world,
            name=s.name,
            race=s.race,
            birth_year=s.birth_year,
            sex=s.sex,
            role=s.role,
            location_id=location_id,
            title=s.title,
            traits=s.traits,
        )
        by_name[s.name] = char

    # Resolve kinship now that every id exists.
    for s in _ROSTER:
        char = by_name[s.name]
        if s.spouse:
            partner = by_name[s.spouse]
            char.spouse_id = partner.id
            partner.spouse_id = char.id  # spouse links are symmetric
        if s.parents:
            char.parent_ids = [by_name[p].id for p in s.parents]

    return list(by_name.values())


def new_seeded_run(seed_str: str, canonicity: float = 1.0) -> World:
    """A fresh run with the canon TA 2965 roster already seeded — the entry point
    the scenario/UI uses when it wants people in the world from year one.
    """
    world = World.new_run(seed_str, canonicity=canonicity)
    seed_roster(world)
    return world
