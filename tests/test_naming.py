"""Culture-authentic naming for generated characters (issue #34).

The selector is a pure function of (culture, sex, seed, taken) — no RNG — so a run
stays byte-stable. These tests pin that determinism, the per-register flavour, the
bounded female rate, and the layered collision policy.
"""

import pytest

from arda_sim.factions import NamingCulture
from arda_sim.naming import choose_sex, generate_name, load_name_pools


ALL_CULTURES = list(NamingCulture)
FEMALE_CULTURES = {
    NamingCulture.ROHIRRIC,
    NamingCulture.DUNEDAIN,
    NamingCulture.ELVISH,
    NamingCulture.GONDORIAN,
}


def test_every_culture_has_a_nonempty_male_pool():
    pools = load_name_pools()
    for culture in ALL_CULTURES:
        assert pools[culture.value]["given"]["male"], culture


def test_generate_name_is_deterministic():
    for culture in ALL_CULTURES:
        a = generate_name(culture, "M", 12345, frozenset())
        b = generate_name(culture, "M", 12345, frozenset())
        assert a == b


def test_names_are_drawn_from_the_registers_pool():
    # A Rohan captain never gets an Elvish name: the base given name is from the pool.
    pools = load_name_pools()
    for culture in ALL_CULTURES:
        given = pools[culture.value]["given"]["male"]
        for seed in range(len(given) * 2):
            name = generate_name(culture, "M", seed, frozenset())
            assert name.split()[0] in given or name.split()[0] in _surnames(pools, culture)


def _surnames(pools, culture):
    return pools[culture.value].get("surnames", [])


def test_hobbits_carry_a_surname():
    name = generate_name(NamingCulture.HOBBIT, "M", 7, frozenset())
    assert len(name.split()) >= 2


def test_female_only_for_martial_women_cultures():
    for culture in ALL_CULTURES:
        seen_female = any(choose_sex(culture, seed) == "F" for seed in range(200))
        if culture in FEMALE_CULTURES:
            assert seen_female, f"{culture} should sometimes field a woman"
        else:
            assert not seen_female, f"{culture} should stay male for now"


def test_female_rate_is_low_but_present():
    females = sum(1 for seed in range(1000) if choose_sex(NamingCulture.ROHIRRIC, seed) == "F")
    assert 0 < females < 300  # rare, not half


def test_female_names_come_from_the_female_pool():
    pools = load_name_pools()
    female = pools[NamingCulture.ROHIRRIC.value]["given"]["female"]
    seed = next(s for s in range(200) if choose_sex(NamingCulture.ROHIRRIC, s) == "F")
    name = generate_name(NamingCulture.ROHIRRIC, "F", seed, frozenset())
    assert name.split()[0] in female


def test_collision_widens_then_ordinalizes():
    # First hit is the bare given name; feeding it back as taken forces a distinct
    # widened form, and feeding that back too forces a further-distinct name.
    culture = NamingCulture.GONDORIAN
    taken = set()
    names = []
    for _ in range(4):
        name = generate_name(culture, "M", 42, taken)
        assert name not in taken  # always resolves to something unused
        names.append(name)
        taken.add(name)
    assert len(set(names)) == 4  # every captain distinct within the living faction


def test_patronymic_widening_for_rohirric():
    # A Rohirric collision widens with a patronymic ("son of ...").
    taken = {generate_name(NamingCulture.ROHIRRIC, "M", 3, frozenset())}
    widened = generate_name(NamingCulture.ROHIRRIC, "M", 3, taken)
    assert "son of" in widened
