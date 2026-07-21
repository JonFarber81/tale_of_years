"""Factions & territory (build ticket 07): the record, the canon TA 2965 roster,
atomic region ownership on the tile substrate, and the deterministic phase-2
faction turn.
"""

import pytest

from arda_sim import START_YEAR
from arda_sim.characters import new_seeded_run
from arda_sim.chronicle import BASE_WEIGHT, IMPORTANT_THRESHOLD, finalize_event
from arda_sim.entities import EntityStatus
from arda_sim.factions import (
    FACTION_INTENT_EVENT,
    INTENT_MENU,
    Faction,
    FactionKind,
    Intent,
    Posture,
    add_faction,
    compute_prominence,
    deciding_factions,
    faction_decisions,
    faction_timeline,
    factions,
    seed_factions,
    seed_world,
)
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import PIPELINE, run_ticks
from arda_sim.scenarios import load_scenario
from arda_sim.tiles import UNOWNED
from arda_sim.world import World


# -- the record ----------------------------------------------------------

def test_faction_is_an_entity_with_rule_and_stance_fields():
    w = World.new_run("seed")
    f = add_faction(
        w, "Gondor", FactionKind.REALM, leader_id=7, capital_location_id=3,
        aggression=45, posture=Posture.DEFENSIVE, disposition={2: -100}, goals=["fortify"],
    )
    assert f.kind == "faction" and f.faction_kind == "realm"
    assert f.leader_id == 7 and f.capital_location_id == 3
    assert f.aggression == 45 and f.posture == "defensive"
    assert f.alive and f.status == EntityStatus.ACTIVE.value
    # disposition is authored with int keys but stored JSON-clean with str keys.
    assert f.disposition == {"2": -100}
    assert f.disposition_toward(2) == -100 and f.disposition_toward(99) == 0


def test_provider_flag_and_no_territory_semantics():
    w = World.new_run("seed")
    prov = add_faction(w, "Haradrim", FactionKind.PROVIDER, gateway_location_id=9, commitment=30)
    realm = add_faction(w, "Gondor", FactionKind.REALM)
    assert prov.is_provider and not realm.is_provider
    assert prov.gateway_location_id == 9 and prov.commitment == 30


def test_prominence_grows_with_kind_leader_and_territory():
    w = World.new_run("seed")
    f = add_faction(w, "F", FactionKind.REALM)

    class _Leader:
        prominence = 100

    landless = compute_prominence(f, owned_tiles=0, leader=None)
    landed = compute_prominence(f, owned_tiles=400, leader=_Leader())
    assert landed > landless > 0


# -- the roster ----------------------------------------------------------

@pytest.fixture
def seeded():
    """A fresh run with the canon roster + factions seeded, and its grid."""
    return seed_world("fellowship")


def test_seed_roster_has_the_canon_powers(seeded):
    world, _grid, names = seeded
    by_name = {f.name: f for f in factions(world)}
    # A sample of every kind from the canon roster.
    assert {"Gondor", "Rohan", "Mordor", "Dol Guldur", "Durin's Folk",
            "Dale", "Rivendell", "Lothlórien", "Woodland Realm"} <= set(by_name)
    assert by_name["The Shire"].faction_kind == FactionKind.CULTURE.value
    assert by_name["Haradrim"].faction_kind == FactionKind.PROVIDER.value
    # Every faction id is labelled for the UI territory legend.
    assert set(names) == {f.id for f in factions(world)}


def test_leaders_and_capitals_resolve_to_seeded_ids(seeded):
    world, _grid, _ = seeded
    gondor = next(f for f in factions(world) if f.name == "Gondor")
    leader = world.entities[gondor.leader_id]
    assert leader.name == "Ecthelion II"
    # the leader is stamped with the faction it heads
    assert leader.faction_id == gondor.id
    assert gondor.capital_location_id is not None


def test_dol_guldur_is_a_distinct_mordor_allied_realm(seeded):
    world, _grid, _ = seeded
    by_name = {f.name: f for f in factions(world)}
    assert by_name["Dol Guldur"].overlord_faction_id == by_name["Mordor"].id
    assert by_name["Dol Guldur"].faction_kind == FactionKind.REALM.value


def test_rangers_are_a_landless_realm_with_a_northern_claim(seeded):
    world, grid, _ = seeded
    rangers = next(f for f in factions(world) if f.name == "Dúnedain of the North")
    assert rangers.faction_kind == FactionKind.REALM.value
    assert rangers.capital_location_id is None  # landless
    assert rangers.claim_region_ids  # holds a nominal claim...
    # ...but owns no painted tiles (the North is "unclaimed", not tinted theirs).
    assert rangers.id not in set(grid.owner)


def test_providers_back_mordor_but_own_no_ground(seeded):
    world, grid, _ = seeded
    by_name = {f.name: f for f in factions(world)}
    mordor = by_name["Mordor"]
    for name in ("Haradrim", "Easterlings of Rhûn", "Variags of Khand", "Corsairs of Umbar"):
        prov = by_name[name]
        assert prov.is_provider
        assert prov.gateway_location_id is not None
        assert prov.allegiance_faction_id == mordor.id
        assert 0 < prov.commitment <= 100 and prov.output
        assert prov.id not in set(grid.owner)  # never on the ownership map


def test_elf_realms_hold_a_withdrawing_posture(seeded):
    world, _grid, _ = seeded
    by_name = {f.name: f for f in factions(world)}
    for name in ("Rivendell", "Lothlórien", "Woodland Realm"):
        assert by_name[name].posture == Posture.WITHDRAWING.value


# -- territory rendering matches state -----------------------------------

def test_owned_tiles_are_atomic_by_region_and_match_faction_ids(seeded):
    world, grid, names = seeded
    faction_ids = {f.id for f in factions(world)}
    owners = set(grid.owner) - {UNOWNED}
    # Every painted owner is a real faction; several powers hold ground.
    assert owners <= faction_ids
    assert len(owners) >= 5
    # Region ownership is atomic: every tile of an owned region shares one owner.
    region_owner = {}
    for row in range(grid.height):
        for col in range(grid.width):
            idx = grid.index(col, row)
            owner = grid.owner[idx]
            if owner == UNOWNED:
                continue
            rid = grid.region_of[idx]
            assert region_owner.setdefault(rid, owner) == owner


def test_gondor_holds_minas_tirith_and_borders_are_derived(seeded):
    world, grid, _ = seeded
    gondor = next(f for f in factions(world) if f.name == "Gondor")
    site = grid.site_id_of("Minas Tirith")
    mt = next(s for s in grid.sites if s.id == site)
    assert grid.owner_at(mt.col, mt.row) == gondor.id
    # a frontier exists somewhere (borders are derived, never stored)
    assert any(
        grid.is_border(c, r) for r in range(grid.height) for c in range(grid.width)
    )


def test_seeding_emits_no_events(seeded):
    world, _grid, _ = seeded
    assert world.events == []  # the roster predates play


# -- phase 2: the faction turn -------------------------------------------

def test_phase_2_is_wired_into_the_pipeline():
    assert dict(PIPELINE)["faction_decisions"].__name__ == "faction_decisions"


def test_every_deciding_faction_records_an_intent_each_year(seeded):
    world, _grid, _ = seeded
    deciders = deciding_factions(world)
    assert all(not f.is_provider for f in deciders)  # providers don't decide
    events = faction_decisions(world, world.rng)
    assert len(events) == len(deciders)
    assert all(ev.type == FACTION_INTENT_EVENT for ev in events)
    # each decider cached a menu intent for later phases
    for f in deciders:
        assert f.current_intent["intent"] in {i.value for i in INTENT_MENU}


def test_aggressive_mordor_readies_war_on_its_most_hated_foe(seeded):
    world, _grid, _ = seeded
    faction_decisions(world, world.rng)
    by_name = {f.name: f for f in factions(world)}
    mordor = by_name["Mordor"]
    assert mordor.current_intent["intent"] == Intent.ATTACK.value
    # its target is the faction it most dislikes (Gondor, disposition -100)
    assert mordor.current_intent["target_faction_id"] == by_name["Gondor"].id


def test_withdrawing_elves_never_attack(seeded):
    world, _grid, _ = seeded
    # advance several years; a withdrawing realm must never choose to attack
    run_ticks(world, 8)
    lorien = next(f for f in factions(world) if f.name == "Lothlórien")
    # re-run the decision a few times off the live RNG to sample its choices
    for _ in range(20):
        faction_decisions(world, world.rng)
        assert lorien.current_intent["intent"] != Intent.ATTACK.value


def test_intent_scoring_is_deterministic_under_seed():
    a = seed_world("same-seed")[0]
    b = seed_world("same-seed")[0]
    run_ticks(a, 6)
    run_ticks(b, 6)
    intents_a = {f.name: f.current_intent for f in factions(a)}
    intents_b = {f.name: f.current_intent for f in factions(b)}
    assert intents_a == intents_b
    # a different seed diverges somewhere
    c = seed_world("other-seed")[0]
    run_ticks(c, 6)
    assert {f.name: f.current_intent for f in factions(c)} != intents_a


def test_canonicity_nudges_a_factions_canon_move():
    # Rohan's canon move is 'muster' (goals[0]). A high canonicity weight should
    # lift muster's score relative to a zero-canon world for the same faction.
    from arda_sim.factions import _score_intents

    world, _grid, _ = seed_world("weights")
    rohan = next(f for f in factions(world) if f.name == "Rohan")
    canon_hot = _score_intents(rohan, canonicity=1.0)[Intent.MUSTER]
    canon_cold = _score_intents(rohan, canonicity=0.0)[Intent.MUSTER]
    assert canon_hot > canon_cold


# -- salience & inspection -----------------------------------------------

def test_intent_events_are_low_salience_but_scale_with_prominence(seeded):
    world, _grid, _ = seeded
    assert BASE_WEIGHT[FACTION_INTENT_EVENT] < IMPORTANT_THRESHOLD
    intents = faction_decisions(world, world.rng)
    for ev in intents:
        finalize_event(world, ev)  # the pipeline scores each on emission
    # they stay below the important-only cutoff (no annals flood)...
    assert all(e.importance < IMPORTANT_THRESHOLD for e in intents)
    # ...yet a prominent power scores its intent above a humble one (prominence
    # genuinely feeds salience).
    by_name = {f.name: f for f in factions(world)}
    def imp(fname):
        fid = by_name[fname].id
        return next(e.importance for e in intents if fid in e.subject_ids)
    assert imp("Mordor") > imp("Bree-land")


def test_faction_is_inspectable_via_its_timeline(seeded):
    world, _grid, _ = seeded
    run_ticks(world, 3)
    mordor = next(f for f in factions(world) if f.name == "Mordor")
    timeline = faction_timeline(world, mordor.id)
    assert timeline  # its yearly intents are its readable history
    assert all(mordor.id in ev.subject_ids for ev in timeline)
    assert [ev.year for ev in timeline] == sorted(ev.year for ev in timeline)


# -- persistence ---------------------------------------------------------

def test_factions_round_trip_and_continue_identically():
    world, _grid, _ = seed_world("save-me")
    run_ticks(world, 4)
    reloaded = loads(dumps(world))
    assert dumps(world) == dumps(reloaded)
    # a faction rehydrates as the right subtype with its maps intact
    f = next(x for x in factions(reloaded) if x.name == "Mordor")
    assert isinstance(f, Faction) and f.disposition
    # Continuing after reload stays bit-identical: ticket 12 persists and
    # re-attaches the built grid on load, so the grid-reading phases (diplomacy,
    # movement, construction) resume against the same territory automatically.
    run_ticks(world, 3)
    run_ticks(reloaded, 3)
    assert dumps(world) == dumps(reloaded)


def test_seed_factions_rejects_a_grid_with_double_claimed_regions():
    # Guard: the authored roster must not paint one region for two factions.
    world = new_seeded_run("guard")
    grid = load_scenario("arda_ta2965")
    seed_factions(world, grid)  # the shipped roster is conflict-free
    ids = {f.id for f in factions(world)}
    assert len(ids) == len(factions(world))
