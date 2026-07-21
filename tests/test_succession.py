"""Dynasties & succession (build ticket 08): the heir walk under each rule, a
failed line's fragmentation/absorption, and the dormant claim that outlives it —
each reproducing under a fixed seed and driven through the succession phase.
"""

import pytest

from arda_sim.characters import (
    Race,
    Role,
    add_character,
    bloodline,
    characters,
    new_seeded_run,
)
from arda_sim.entities import EntityStatus
from arda_sim.factions import (
    Faction,
    FactionKind,
    SuccessionRule,
    add_faction,
    factions,
    seed_world,
)
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import run_ticks
from arda_sim.succession import (
    ABSORPTION_EVENT,
    LINE_FAILED_EVENT,
    SUCCESSION_EVENT,
    _owned_tile_count,
    _strongest_bordering_faction,
    succession,
)
from arda_sim.tiles import UNOWNED, Region, Terrain, TileGrid
from arda_sim.world import World


# -- helpers -------------------------------------------------------------

def _faction(world: World, name: str) -> Faction:
    return next(f for f in factions(world) if f.name == name)


def _character(world: World, name: str):
    return next(c for c in characters(world) if c.name == name)


def _kill(world: World, name: str):
    char = _character(world, name)
    char.status = EntityStatus.DEAD.value
    return char


def _extinguish_line(world: World, faction: Faction) -> None:
    """Kill every kin of the seat-holder, so no heir can be walked to."""
    for kin in bloodline(world, faction.leader_id):
        kin.status = EntityStatus.DEAD.value


# -- normal succession, per canon rule -----------------------------------

@pytest.mark.parametrize(
    "realm,dead,heir,rule",
    [
        ("Gondor", "Ecthelion II", "Denethor II", "stewardship"),
        ("Rohan", "Thengel", "Théoden", "agnatic_primogeniture"),
        ("Durin's Folk", "Dáin II Ironfoot", "Thorin III Stonehelm", "dwarf_line_of_durin"),
    ],
)
def test_seat_passes_to_the_canon_heir(realm, dead, heir, rule):
    world, _grid, _ = seed_world("succ")
    faction = _faction(world, realm)
    assert faction.succession_rule == rule

    _kill(world, dead)
    events = succession(world, world.rng)

    assert any(e.type == SUCCESSION_EVENT for e in events)
    seated = world.entities[faction.leader_id]
    assert seated.name == heir
    assert seated.role == Role.RULER.value
    assert seated.faction_id == faction.id


def test_stewardship_office_title_passes_to_the_heir():
    world, _grid, _ = seed_world("title")
    gondor = _faction(world, "Gondor")
    _kill(world, "Ecthelion II")
    succession(world, world.rng)
    assert world.entities[gondor.leader_id].title == "Steward of Gondor"


def test_a_leaderless_faction_never_triggers_succession():
    # Dol Guldur is seeded with no leader and the cultures hold ground without one;
    # a vacant-by-design seat must not read as a failed line on the very first tick.
    world, _grid, _ = seed_world("noop")
    assert succession(world, world.rng) == []


def test_succession_fires_through_the_pipeline():
    world, _grid, _ = seed_world("pipeline")
    rohan = _faction(world, "Rohan")
    _kill(world, "Thengel")
    run_ticks(world, 1)
    assert world.entities[rohan.leader_id].name == "Théoden"
    assert any(e.type == SUCCESSION_EVENT for e in world.events)


# -- elective fallback ---------------------------------------------------

def test_elective_elects_the_worthiest_member():
    world = World.new_run("elect")
    king = add_character(world, "Old King", Race.MAN, 2900, role=Role.RULER)
    realm = add_faction(
        world, "Elective Realm", FactionKind.REALM,
        succession_rule=SuccessionRule.ELECTIVE, leader_id=king.id,
    )
    king.faction_id = realm.id
    # Two unrelated members; the higher-prominence one (a general) should win over
    # the councillor. No kinship exists, so only an election can resolve the seat.
    add_character(world, "Councillor", Race.MAN, 2930, role=Role.COUNCILLOR, faction_id=realm.id)
    strong = add_character(world, "Marshal", Race.MAN, 2930, role=Role.GENERAL, faction_id=realm.id)

    _kill(world, "Old King")
    events = succession(world, world.rng)

    assert any(e.type == SUCCESSION_EVENT for e in events)
    assert realm.leader_id == strong.id
    assert strong.role == Role.RULER.value


def test_bloodline_rule_falls_back_to_election_when_kin_are_gone():
    world = World.new_run("fallback")
    king = add_character(world, "Last King", Race.MAN, 2900, role=Role.RULER)
    realm = add_faction(
        world, "Agnatic Realm", FactionKind.REALM,
        succession_rule=SuccessionRule.AGNATIC_PRIMOGENITURE, leader_id=king.id,
    )
    king.faction_id = realm.id
    steward = add_character(world, "Regent", Race.MAN, 2935, role=Role.COUNCILLOR, faction_id=realm.id)

    _kill(world, "Last King")  # no descendants, no collateral kin
    succession(world, world.rng)

    assert realm.leader_id == steward.id  # kin exhausted -> the realm elected


# -- failed line: fragmentation & absorption -----------------------------

def test_failed_line_is_absorbed_by_the_strongest_neighbour():
    world, grid, _ = seed_world("absorb")
    dale = _faction(world, "Dale")
    held = _owned_tile_count(grid, dale.id)
    assert held > 0
    expected = _strongest_bordering_faction(world, dale, grid)
    assert expected is not None

    _extinguish_line(world, dale)
    events = succession(world, world.rng)

    assert any(e.type == LINE_FAILED_EVENT for e in events)
    absorption = next(e for e in events if e.type == ABSORPTION_EVENT)
    assert absorption.payload["absorber_faction_id"] == expected.id
    assert _owned_tile_count(grid, dale.id) == 0  # every tile changed hands
    assert _owned_tile_count(grid, expected.id) >= held
    assert not dale.alive


def test_failed_line_with_no_neighbour_fragments_to_unowned_land():
    world = World.new_run("fragment")
    king = add_character(world, "Hermit King", Race.MAN, 2900, role=Role.RULER)
    realm = add_faction(
        world, "Hidden Realm", FactionKind.REALM, leader_id=king.id,
    )
    king.faction_id = realm.id
    # A tiny island of ownership: one owned tile ringed by unowned land.
    grid = TileGrid(
        width=3, height=3,
        terrain=[Terrain.PLAINS] * 9,
        region_of=[0, 0, 0, 0, 1, 0, 0, 0, 0],
        regions={1: Region(1, "Heartland")},
    )
    grid.set_owner(1, 1, realm.id)
    world.grid = grid

    _kill(world, "Hermit King")
    events = succession(world, world.rng)

    assert any(e.type == LINE_FAILED_EVENT for e in events)
    assert not any(e.type == ABSORPTION_EVENT for e in events)  # no one to absorb it
    assert grid.owner_at(1, 1) == UNOWNED  # land went wild
    assert realm.claim_region_ids == [1]  # the dormant claim was recorded
    assert not realm.alive


# -- dormant claim persistence -------------------------------------------

def test_dormant_claim_survives_save_and_load():
    world, grid, _ = seed_world("dormant")
    dale = _faction(world, "Dale")
    _extinguish_line(world, dale)
    succession(world, world.rng)
    assert dale.claim_region_ids  # a claim was left behind

    reloaded = loads(dumps(world))
    restored = next(f for f in factions(reloaded) if f.name == "Dale")
    assert not restored.alive  # still tombstoned after the round trip
    assert restored.claim_region_ids == dale.claim_region_ids  # claim persisted intact


# -- determinism ---------------------------------------------------------

def _succession_fingerprint(seed: str):
    world, _grid, _ = seed_world(seed)
    _extinguish_line(world, _faction(world, "Dale"))
    _kill(world, "Ecthelion II")
    events = succession(world, world.rng)
    return [
        (e.type, tuple(e.subject_ids), tuple(sorted((e.payload or {}).items())))
        for e in events
    ]


def test_succession_is_deterministic_under_seed():
    assert _succession_fingerprint("same") == _succession_fingerprint("same")


def test_new_seeded_run_without_a_grid_still_resolves_heirs():
    # A world seeded with people but no factions/grid (the characters entry point)
    # must degrade gracefully: heir walks still run, the absorption branch is simply
    # unreachable (guarded on world.grid, per ADR-0004).
    world = new_seeded_run("no-grid")
    king = add_character(world, "Petty King", Race.MAN, 2900, role=Role.RULER)
    heir = add_character(world, "Young Prince", Race.MAN, 2940, role=Role.HEIR, parent_ids=[king.id])
    realm = add_faction(world, "Landless Realm", FactionKind.REALM, leader_id=king.id)
    king.faction_id = realm.id
    assert world.grid is None

    _kill(world, "Petty King")
    succession(world, world.rng)
    assert realm.leader_id == heir.id  # kinship alone resolved it, no grid needed
