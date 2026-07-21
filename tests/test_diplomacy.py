"""Diplomacy & vassalage (build ticket 09): disposition drift toward a frozen
baseline, the pact ladder (treaty / marriage / vassalage / provider-pact), the
war-declaration flag owned here, and the make_peace seam ticket 11 will drive.
"""

from arda_sim import diplomacy as dip
from arda_sim.characters import Race, add_character, wed
from arda_sim.diplomacy import (
    ALLIANCE,
    HOSTILITY,
    MARRIAGE_EVENT,
    NEUTRALITY,
    PROVIDER_PACT_EVENT,
    TREATY_EVENT,
    VASSALAGE,
    VASSALAGE_EVENT,
    WAR_DECLARED_EVENT,
    WAR_ENDED_EVENT,
    diplomacy,
    make_peace,
    stance,
    vassals_of,
)
from arda_sim.entities import EntityStatus
from arda_sim.factions import FactionKind, Intent, add_faction, factions, seed_world
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import PIPELINE, run_years
from arda_sim.snapshot import snapshot_world
from arda_sim.world import World


def _two_realms(disp_ab: int = 80, disp_ba: int = 80):
    """Two bare realms with a frozen baseline equal to their opening disposition."""
    w = World.new_run("dip")
    a = add_faction(w, "A", FactionKind.REALM, aggression=40)
    b = add_faction(w, "B", FactionKind.REALM, aggression=40)
    a.disposition = {str(b.id): disp_ab}
    a.baseline_disposition = dict(a.disposition)
    b.disposition = {str(a.id): disp_ba}
    b.baseline_disposition = dict(b.disposition)
    return w, a, b


# -- pipeline & stance ----------------------------------------------------

def test_diplomacy_is_wired_into_the_pipeline():
    assert dict(PIPELINE)["diplomacy"].__name__ == "diplomacy"


def test_stance_derives_from_disposition_and_flags():
    w, a, b = _two_realms(80, 80)
    assert stance(a, b) == ALLIANCE  # warm scalar
    a.disposition = {str(b.id): 0}
    assert stance(a, b) == NEUTRALITY
    a.disposition = {str(b.id): -50}
    assert stance(a, b) == HOSTILITY
    # a signed treaty forces alliance even at a lukewarm scalar
    a.disposition = {str(b.id): 0}
    a.treaties = [b.id]
    assert stance(a, b) == ALLIANCE
    # war forces hostility regardless of the scalar
    a.treaties = []
    a.at_war_with = [b.id]
    assert stance(a, b) == HOSTILITY
    # a fealty bond (either direction) reads as vassalage
    a.at_war_with = []
    b.overlord_faction_id = a.id
    assert stance(a, b) == VASSALAGE and stance(b, a) == VASSALAGE


# -- background drift ------------------------------------------------------

def test_disposition_decays_a_step_toward_frozen_baseline_without_overshoot():
    w, a, b = _two_realms(80, 80)
    a.disposition = {str(b.id): 50}  # perturbed below its baseline of 80
    dip._decay_toward_baseline(w)
    assert a.disposition[str(b.id)] == 53  # one +3 step toward 80
    a.disposition = {str(b.id): 79}
    dip._decay_toward_baseline(w)
    assert a.disposition[str(b.id)] == 80  # clamps at baseline, never past it


def test_border_friction_only_sours_adjacent_unbound_pairs():
    world, grid, _ = seed_world("friction")
    adjacency = dip._faction_adjacencies(grid)
    before = {f.id: dict(f.disposition) for f in factions(world)}
    dip._apply_border_friction(world, adjacency)
    for a_id, neighbours in adjacency.items():
        a = world.entities[a_id]
        for b_id in neighbours:
            b = world.entities[b_id]
            key = str(b_id)
            if dip._bound(a, b):
                assert a.disposition.get(key, 0) == before[a_id].get(key, 0)
            else:
                assert a.disposition.get(key, 0) <= before[a_id].get(key, 0)


# -- the pact ladder (mechanics) ------------------------------------------

def test_treaty_is_symmetric_and_warms_both_sides():
    w, a, b = _two_realms(45, 45)
    ev = dip._sign_treaty(w, a, b)
    assert a.has_treaty_with(b.id) and b.has_treaty_with(a.id)
    assert a.disposition_toward(b.id) == 65 and b.disposition_toward(a.id) == 65
    assert ev.type == TREATY_EVENT and set(ev.subject_ids) == {a.id, b.id}


def test_vassalage_bond_forms_and_dissolves_when_soured():
    w, a, b = _two_realms(0, 75)  # b adores a
    ev = dip._form_vassalage(w, overlord=a, vassal=b)
    assert b.overlord_faction_id == a.id and vassals_of(w, a.id) == [b]
    assert ev.type == VASSALAGE_EVENT and ev.payload["bond"] == "formed"
    # a vassal who comes to resent its overlord throws off the bond
    b.disposition = {str(a.id): -40}
    events = dip._dissolve_stale_vassalage(w)
    assert b.overlord_faction_id is None
    assert any(e.payload.get("bond") == "broken" for e in events)


def test_vassalage_dissolves_when_the_overlord_falls():
    w, a, b = _two_realms(0, 80)
    dip._form_vassalage(w, overlord=a, vassal=b)
    a.status = EntityStatus.DEAD.value  # overlord tombstoned
    dip._dissolve_stale_vassalage(w)
    assert b.overlord_faction_id is None


def test_marriage_weds_the_junior_spouse_into_the_senior_house():
    w = World.new_run("wed")
    senior = add_faction(w, "Senior", FactionKind.REALM)
    junior = add_faction(w, "Junior", FactionKind.REALM)
    senior.prominence, junior.prominence = 90, 20
    for f, g in ((senior, junior), (junior, senior)):
        f.disposition = {str(g.id): 60}
        f.baseline_disposition = dict(f.disposition)
    prince = add_character(w, "Prince", Race.MAN, 2900, sex="M", faction_id=senior.id)
    princess = add_character(w, "Princess", Race.MAN, 2900, sex="F", faction_id=junior.id)
    events = dip._make_marriage(w, senior, junior)
    assert events and events[0].type == MARRIAGE_EVENT
    assert prince.spouse_id == princess.id and princess.spouse_id == prince.id
    # the junior realm's princess weds into the senior house
    assert princess.faction_id == senior.id and prince.faction_id == senior.id
    assert senior.disposition_toward(junior.id) == 90  # +30 marriage jump


def test_marriage_is_a_no_op_without_an_eligible_opposite_sex_pair():
    w = World.new_run("nowed")
    a = add_faction(w, "A", FactionKind.REALM)
    b = add_faction(w, "B", FactionKind.REALM)
    add_character(w, "OnlyMan", Race.MAN, 2900, sex="M", faction_id=a.id)
    add_character(w, "AlsoMan", Race.MAN, 2900, sex="M", faction_id=b.id)
    assert dip._make_marriage(w, a, b) is None  # two men — no couple


def test_provider_pact_deepens_an_aligned_provider():
    w = World.new_run("prov")
    patron = add_faction(w, "Patron", FactionKind.REALM)
    prov = add_faction(
        w, "Outlanders", FactionKind.PROVIDER, commitment=30, gateway_location_id=1
    )
    prov.allegiance_faction_id = patron.id
    ev = dip._deepen_provider(w, patron, prov)
    assert prov.commitment == 40 and ev.type == PROVIDER_PACT_EVENT


# -- war: the flag is owned here ------------------------------------------

def test_attack_intent_raises_a_symmetric_war_flag_and_is_idempotent():
    w, a, b = _two_realms(-50, -50)
    a.current_intent = {"intent": Intent.ATTACK.value, "target_faction_id": b.id}
    events = dip._maybe_declare_war(w, a)
    assert a.is_at_war_with(b.id) and b.is_at_war_with(a.id)
    assert events[0].type == WAR_DECLARED_EVENT and events[0].payload["betrayal"] is False
    assert dip._maybe_declare_war(w, a) == []  # already at war — no second declaration


def test_declaring_war_on_a_treaty_partner_is_a_betrayal_that_tears_the_pact():
    w, a, b = _two_realms(45, 45)
    dip._sign_treaty(w, a, b)  # disposition now 65 both ways
    a.current_intent = {"intent": Intent.ATTACK.value, "target_faction_id": b.id}
    events = dip._maybe_declare_war(w, a)
    assert events[0].payload["betrayal"] is True
    assert not a.has_treaty_with(b.id) and not b.has_treaty_with(a.id)
    assert a.disposition_toward(b.id) == -5  # 65 + (-70) betrayal jump


def test_providers_are_never_war_targets():
    w = World.new_run("nowar")
    a = add_faction(w, "A", FactionKind.REALM)
    prov = add_faction(w, "P", FactionKind.PROVIDER, gateway_location_id=1)
    a.current_intent = {"intent": Intent.ATTACK.value, "target_faction_id": prov.id}
    assert dip._maybe_declare_war(w, a) == [] and not a.is_at_war_with(prov.id)


def test_make_peace_clears_the_flag_symmetrically_and_is_the_only_peace_path():
    w, a, b = _two_realms(-60, -60)
    a.at_war_with, b.at_war_with = [b.id], [a.id]
    ev = make_peace(w, a, b)
    assert ev.type == WAR_ENDED_EVENT
    assert not a.is_at_war_with(b.id) and not b.is_at_war_with(a.id)
    assert make_peace(w, a, b) is None  # no longer at war — nothing to end


def test_phase3_never_makes_peace_on_its_own():
    # war_ended is a seam for ticket 11: phase 3 declares wars but never ends them.
    world, _grid, _ = seed_world("no-peace")
    events = run_years(world, 30)
    assert not any(e.type == WAR_ENDED_EVENT for e in events)


# -- integration: determinism, symmetry, persistence ----------------------

def test_diplomacy_actually_fires_and_is_deterministic_under_seed():
    a = seed_world("dup-seed")[0]
    b = seed_world("dup-seed")[0]
    events_a = run_years(a, 25)
    run_years(b, 25)
    assert dumps(a) == dumps(b)
    # the phase genuinely does something over a run
    kinds = {e.type for e in events_a}
    assert kinds & {
        TREATY_EVENT, MARRIAGE_EVENT, WAR_DECLARED_EVENT,
        VASSALAGE_EVENT, PROVIDER_PACT_EVENT,
    }
    # a different seed diverges
    c = seed_world("other-seed")[0]
    run_years(c, 25)
    assert dumps(c) != dumps(a)


def test_war_flags_stay_symmetric_across_a_seeded_run():
    world, _grid, _ = seed_world("sym-war")
    run_years(world, 20)
    for f in factions(world):
        for enemy_id in f.at_war_with:
            assert f.id in world.entities[enemy_id].at_war_with


def test_diplomacy_state_round_trips_through_save_load():
    world, _grid, _ = seed_world("dip-save")
    run_years(world, 8)
    blob = dumps(world)
    reloaded = loads(blob)
    assert dumps(reloaded) == blob  # baseline + at_war_with + treaties all round-trip
    mordor = next(f for f in factions(reloaded) if f.name == "Mordor")
    assert mordor.baseline_disposition  # the frozen attractor survived


def test_diplomacy_resumes_bit_identically_when_the_grid_is_re_attached():
    # A reloaded world carries no grid until ticket 12 (ADR-0004), so its phase-3
    # grid branches (border friction, vassalage offers) are inert and it diverges
    # from the live run. Re-attaching an identically-painted grid — which is exactly
    # what ticket 12 will restore — makes the RNG resume through phase 3 exact.
    world, _grid, _ = seed_world("dip-resume")
    run_years(world, 6)
    reloaded = loads(dumps(world))
    reloaded.grid = seed_world("dip-resume")[1]  # same seed → identical territory
    run_years(world, 4)
    run_years(reloaded, 4)
    assert dumps(world) == dumps(reloaded)


def test_disposition_change_does_not_leak_into_an_earlier_snapshot():
    # the reassign-not-mutate discipline: a snapshot keeps the values it captured.
    w, a, b = _two_realms(50, 50)
    snap = snapshot_world(w, 0)
    dip._adjust(a, b.id, 40)
    assert snap.entity(a.id).disposition_toward(b.id) == 50  # snapshot frozen
    assert a.disposition_toward(b.id) == 90  # live world moved
