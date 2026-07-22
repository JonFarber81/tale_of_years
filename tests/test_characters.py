"""Characters & lifecycle (build ticket 05): the record, the race table, phase-1
births/deaths/departures under a fixed seed, and the canon TA 2965 roster.
"""

import pytest

from arda_sim import START_YEAR
from arda_sim.characters import (
    BP_SCALE,
    RACE_CONFIG,
    Character,
    MortalityKind,
    Race,
    Role,
    add_character,
    aging_births_deaths,
    annual_death_bp,
    character_timeline,
    characters,
    compute_prominence,
    is_immortal,
    new_seeded_run,
    seed_roster,
)
from arda_sim.entities import EntityStatus
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import run_years
from arda_sim.world import World


# -- the record & derived fields -----------------------------------------

def test_character_is_an_entity_with_lifecycle_fields():
    w = World.new_run("seed")
    c = add_character(
        w, "Aragorn", Race.DUNEDAIN, birth_year=2931, sex="M", role=Role.RANGER,
        location_id=7, title="Heir of Isildur", traits={"leadership": 92},
    )
    assert c.kind == "character"
    assert c.race == "dunedain" and c.birth_year == 2931 and c.sex == "M"
    assert c.role == "ranger" and c.location_id == 7 and c.title == "Heir of Isildur"
    assert c.age(START_YEAR) == START_YEAR - 2931
    assert c.alive and c.status == EntityStatus.ACTIVE.value
    # trait vector is filled to the full set; authored values are kept.
    assert c.traits["leadership"] == 92 and set(c.traits) >= {"martial", "loyalty"}


def test_prominence_is_derived_from_role_trait_and_title():
    w = World.new_run("seed")
    ruler = add_character(w, "R", Race.MAN, 2900, role=Role.RULER,
                          title="King", traits={"leadership": 80})
    nobody = add_character(w, "N", Race.MAN, 2940, role=Role.NONE)
    assert ruler.prominence == compute_prominence(ruler) > nobody.prominence


# -- the race config table -----------------------------------------------

def test_every_race_has_a_config():
    assert set(RACE_CONFIG) == set(Race)


def test_mortality_kinds_are_assigned_as_designed():
    kinds = {r: RACE_CONFIG[r].mortality_kind for r in Race}
    assert kinds[Race.MAN] is MortalityKind.MORTAL
    assert kinds[Race.DUNEDAIN] is MortalityKind.LONG_LIVED
    assert kinds[Race.DWARF] is MortalityKind.LONG_LIVED
    assert kinds[Race.ELF] is MortalityKind.IMMORTAL
    assert kinds[Race.MAIA] is MortalityKind.IMMORTAL


def test_death_curve_is_monotonic_and_integer():
    # Older is never safer; every probability is an int in basis points.
    for race in (Race.MAN, Race.HOBBIT, Race.DUNEDAIN, Race.DWARF, Race.ORC):
        last = -1
        for age in range(0, 320, 5):
            bp = annual_death_bp(race, age)
            assert isinstance(bp, int) and 0 <= bp <= BP_SCALE
            assert bp >= last
            last = bp


def test_immortals_have_no_death_probability_at_any_age():
    for race in (Race.ELF, Race.MAIA):
        assert is_immortal(race)
        assert all(annual_death_bp(race, age) == 0 for age in range(0, 10000, 250))


def test_longlived_outlive_mortals_at_the_same_age():
    # A Dúnadan at 80 is far likelier to survive than a Man at 80.
    assert annual_death_bp(Race.DUNEDAIN, 80) < annual_death_bp(Race.MAN, 80)


# -- phase 1: determinism -------------------------------------------------

def _couple_world(seed="hornburg"):
    """A tiny world with one fertile Man/woman couple, at the start year."""
    w = World.new_run(seed)
    husband = add_character(w, "Éomund", Race.MAN, 2930, sex="M")
    wife = add_character(w, "Théodwyn", Race.MAN, 2938, sex="F")
    wife.spouse_id = husband.id
    husband.spouse_id = wife.id
    return w


def test_births_and_deaths_are_deterministic_under_a_fixed_seed():
    a = _couple_world()
    b = _couple_world()
    run_years(a, 60)
    run_years(b, 60)
    # Same seed, same construction -> byte-identical runs.
    assert dumps(a) == dumps(b)


def test_established_couples_produce_births():
    w = _couple_world()
    run_years(w, 60)
    births = [e for e in w.events if e.type == "birth"]
    assert births, "a fertile couple over 60 years should produce at least one birth"
    child_id = births[0].subject_ids[0]
    child = w.entities[child_id]
    assert isinstance(child, Character)
    assert child.race == Race.MAN.value
    # kinship points back at both parents.
    assert len(child.parent_ids) == 2


def test_a_generated_child_takes_a_culture_authentic_name(): # issue #34
    from arda_sim.characters import _bear_child
    from arda_sim.factions import NamingCulture, add_faction, FactionKind
    from arda_sim.naming import load_name_pools
    import random

    w = World.new_run("brood")
    rohan = add_faction(w, "Rohan", FactionKind.REALM, culture=NamingCulture.ROHIRRIC)
    mother = add_character(w, "Théodwyn", Race.MAN, 2938, sex="F", faction_id=rohan.id)
    father = add_character(w, "Éomund", Race.MAN, 2930, sex="M", faction_id=rohan.id)
    pool = load_name_pools()[NamingCulture.ROHIRRIC.value]["given"]
    rng = random.Random(1)
    for _ in range(20):
        child = _bear_child(w, rng, mother, father)
        assert not child.name.startswith("Child of")  # the placeholder is retired
        # a daughter draws a woman's name, a son a man's — pools are gendered
        canon = pool["female"] if child.sex == "F" else pool["male"]
        assert child.name.split()[0] in canon  # from Rohan's own gendered register


def test_a_child_names_from_the_factioned_parent_when_the_other_is_factionless():
    from arda_sim.characters import _bear_child
    from arda_sim.factions import NamingCulture, add_faction, FactionKind
    from arda_sim.naming import load_name_pools
    import random

    w = World.new_run("lineage")
    shire = add_faction(w, "The Shire", FactionKind.CULTURE, culture=NamingCulture.HOBBIT)
    mother = add_character(w, "Primula", Race.HOBBIT, 2920, sex="F")  # no faction
    father = add_character(w, "Drogo", Race.HOBBIT, 2908, sex="M", faction_id=shire.id)
    hobbit = load_name_pools()[NamingCulture.HOBBIT.value]
    child = _bear_child(w, random.Random(3), mother, father)
    # Read the register off the father's Shire faction, not the race default.
    assert child.name.split()[0] in hobbit["given"]["male"] + hobbit["given"]["female"]
    assert len(child.name.split()) >= 2  # Hobbits carry a surname


def test_a_lone_character_never_gives_birth():
    w = World.new_run("solo")
    add_character(w, "Gilraen", Race.MAN, 2907, sex="F")  # no spouse
    run_years(w, 40)
    assert not [e for e in w.events if e.type == "birth"]


def test_births_and_deaths_survive_a_save_load_round_trip():
    w = _couple_world()
    run_years(w, 30)
    restored = loads(dumps(w))
    # Characters rehydrate as Characters (not the base Entity), with their fields.
    people = characters(restored)
    assert people and all(isinstance(c, Character) for c in people)
    run_years(w, 20)
    run_years(restored, 20)
    assert dumps(restored) == dumps(w)


# -- phase 1: immortality, departure --------------------------------------

def test_immortals_never_die_naturally_but_elves_depart():
    w = World.new_run("valinor")
    elf = add_character(w, "Gil-galad", Race.ELF, -3000)
    maia = add_character(w, "Olórin", Race.MAIA, -3000)
    run_years(w, 600)
    assert elf.status != EntityStatus.DEAD.value
    assert maia.status != EntityStatus.DEAD.value
    # Over centuries the Elf wearies and sails West; the Maia never departs.
    assert elf.status == EntityStatus.DEPARTED.value
    assert maia.status == EntityStatus.ACTIVE.value
    assert [e for e in w.events if e.type == "departed"]


def test_departed_elf_is_tombstoned_not_deleted():
    w = World.new_run("mithlond")
    elf = add_character(w, "Círdan", Race.ELF, -3000)
    run_years(w, 600)
    assert elf.id in w.entities  # record survives departure
    assert not elf.alive


# -- inspection -----------------------------------------------------------

def test_timeline_reads_back_a_full_life_including_the_tombstone():
    w = _couple_world()
    run_years(w, 80)
    # Find someone who both was born and died within the run.
    deaths = {e.subject_ids[0] for e in w.events if e.type == "death"}
    births = {e.subject_ids[0] for e in w.events if e.type == "birth"}
    lived_and_died = births & deaths
    if not lived_and_died:
        pytest.skip("no born-and-died character in this run horizon")
    cid = sorted(lived_and_died)[0]
    timeline = character_timeline(w, cid)
    types = [e.type for e in timeline]
    assert types[0] == "birth" and types[-1] == "death"
    assert w.entities[cid].status == EntityStatus.DEAD.value  # inspectable while dead


# -- the canon TA 2965 roster --------------------------------------------

@pytest.fixture(scope="module")
def seeded():
    w = World.new_run("canon")
    seed_roster(w)
    return w


def test_roster_seeds_the_expected_rulers_at_the_right_places(seeded):
    from arda_sim.scenarios import load_scenario
    grid = load_scenario("arda_ta2965")
    by_name = {c.name: c for c in characters(seeded)}

    def home(name):
        return grid.site_by_id(by_name[name].location_id).name

    assert by_name["Ecthelion II"].role == Role.RULER.value
    assert home("Ecthelion II") == "Minas Tirith"
    assert by_name["Thengel"].role == Role.RULER.value and home("Thengel") == "Edoras"
    assert by_name["Dáin II Ironfoot"].role == Role.RULER.value
    assert home("Dáin II Ironfoot") == "Erebor"
    assert home("Aragorn") == "Rivendell"


def test_roster_birth_years_and_races_match_canon(seeded):
    by_name = {c.name: c for c in characters(seeded)}
    assert by_name["Aragorn"].birth_year == 2931
    assert by_name["Aragorn"].race == Race.DUNEDAIN.value
    assert by_name["Théoden"].birth_year == 2948
    assert by_name["Bilbo Baggins"].race == Race.HOBBIT.value
    assert by_name["Gandalf"].race == Race.MAIA.value
    assert by_name["Legolas"].race == Race.ELF.value


def test_roster_excludes_characters_not_yet_born_in_2965(seeded):
    names = {c.name for c in characters(seeded)}
    # Frodo (2968), Boromir (2978), Faramir (2983), Éomer (2991) are all future.
    assert not (names & {"Frodo", "Boromir", "Faramir", "Éomer", "Éowyn", "Samwise"})
    # And no seeded character is born after the scenario's start year.
    assert all(c.birth_year <= START_YEAR for c in characters(seeded))


def test_roster_kinship_links_resolve(seeded):
    by_name = {c.name: c for c in characters(seeded)}
    # A spouse link is symmetric.
    assert by_name["Thengel"].spouse_id == by_name["Morwen"].id
    assert by_name["Morwen"].spouse_id == by_name["Thengel"].id
    # Théoden's parents are Thengel and Morwen.
    assert set(by_name["Théoden"].parent_ids) == {
        by_name["Thengel"].id, by_name["Morwen"].id
    }


def test_new_seeded_run_is_deterministic_and_populated():
    a, b = new_seeded_run("shire"), new_seeded_run("shire")
    assert dumps(a) == dumps(b)
    assert len(characters(a)) > 20
