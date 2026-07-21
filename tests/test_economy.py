"""Construction & economy (build ticket 12): yearly treasury income off owned
land, phase-6 build works (found/rebuild ruins, grow towns into cities, raise
fortresses at borders/passes, open roads), the contested-region skip, the
canonicity lean toward restoration, prose/salience, and the persistence of the
built map (owner grid + site kinds + roads). Every outcome is integer/RNG-clean.
"""

from arda_sim import economy as econ
from arda_sim.chronicle import BASE_WEIGHT, IMPORTANT_THRESHOLD, finalize_event, render_text
from arda_sim.economy import (
    FOUNDING_EVENT,
    ROAD_OPENED_EVENT,
    SETTLEMENT_GREW_EVENT,
    construction_economy,
    faction_income,
    faction_population,
)
from arda_sim.entities import EntityStatus
from arda_sim.factions import FactionKind, add_faction, factions, seed_world
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import PIPELINE, run_years
from arda_sim.tiles import Region, Site, Terrain, TileGrid, UNOWNED, default_tier
from arda_sim.world import World


# -- builders -------------------------------------------------------------

def _grid(width, height, terrain=Terrain.PLAINS, sites=None, regions=None, region_of=None):
    n = width * height
    return TileGrid(
        width=width,
        height=height,
        terrain=[terrain] * n,
        region_of=region_of if region_of is not None else [1] * n,
        regions=regions if regions is not None else {1: Region(1, "Land")},
        sites=list(sites or []),
        miles_per_tile=15,
    )


def _own_all(grid, faction_id):
    grid.owner = [faction_id] * (grid.width * grid.height)


def _building(world, name, treasury, **kw):
    """A realm that chose to build this year, flush with ``treasury``.

    Carries a realm-like ``prominence`` so its foundings score as they would in a
    seeded run (add_faction leaves derived scalars at 0 until territory is known).
    """
    f = add_faction(world, name, FactionKind.REALM, treasury=treasury, **kw)
    f.current_intent = {"intent": "build"}
    f.prominence = 40
    return f


def _at_war(a, b):
    a.at_war_with = sorted(set(a.at_war_with) | {b.id})
    b.at_war_with = sorted(set(b.at_war_with) | {a.id})


# =========================================================================
# Pipeline wiring
# =========================================================================

def test_construction_is_wired_into_the_pipeline_at_phase_6():
    names = [name for name, _ in PIPELINE]
    assert names[6] == "construction_economy"
    assert dict(PIPELINE)["construction_economy"].__name__ == "construction_economy"


def test_construction_is_a_no_op_without_a_grid():
    w = World.new_run("nogrid")
    _building(w, "A", 999)
    assert construction_economy(w, w.rng) == []


# =========================================================================
# Economy — income off the land
# =========================================================================

def test_income_is_the_sum_of_owned_terrain_yields():
    w = World.new_run("income")
    w.grid = grid = _grid(4, 1, terrain=Terrain.PLAINS)  # plains yield 3
    f = add_faction(w, "A", FactionKind.REALM)
    _own_all(grid, f.id)
    assert faction_income(w, grid)[f.id] == 4 * 3


def test_income_accrues_once_a_year_at_the_year_boundary():
    w = World.new_run("accrue")
    w.grid = grid = _grid(2, 1, terrain=Terrain.PLAINS)
    f = _building(w, "A", 0)
    _own_all(grid, f.id)
    yearly = faction_income(w, grid)[f.id]

    w.tick = 0  # month 1 — a harvest lands
    construction_economy(w, w.rng)
    assert f.treasury == yearly
    w.tick = 1  # month 2 — no harvest
    construction_economy(w, w.rng)
    assert f.treasury == yearly  # unchanged


def test_income_ignores_providers_and_the_dead():
    w = World.new_run("who")
    w.grid = grid = _grid(2, 1)
    prov = add_faction(w, "Haradrim", FactionKind.PROVIDER)
    dead = add_faction(w, "Fallen", FactionKind.REALM, status=EntityStatus.DEAD.value)
    grid.owner = [prov.id, dead.id]
    assert faction_income(w, grid) == {}  # neither draws income


def test_population_is_a_derived_aggregate_of_land_and_towns():
    w = World.new_run("pop")
    town = Site("Town", 0, 0, "town", 1, default_tier("town"))
    w.grid = grid = _grid(3, 1, sites=[town])
    f = add_faction(w, "A", FactionKind.REALM)
    _own_all(grid, f.id)
    # 3 tiles + one town's weight; nothing stored on the faction record.
    assert faction_population(w, grid, f.id) == 3 + econ._SETTLEMENT_POP["town"]
    assert not hasattr(f, "population")


# =========================================================================
# Construction — founding, rebuilding, growth, roads
# =========================================================================

def test_treasury_gates_building():
    ruin = Site("Osgiliath", 1, 0, "ruin", 1)
    w = World.new_run("broke")
    w.tick = 1  # month 2: no harvest, so the treasury gate is exact
    w.grid = grid = _grid(3, 1, sites=[ruin])
    f = _building(w, "A", econ._COST_FOUND_TOWN - 1)  # a coin short
    _own_all(grid, f.id)
    assert construction_economy(w, w.rng) == []
    assert grid.site_by_id(ruin.id).kind == "ruin"  # nothing built

    f.treasury = econ._COST_FOUND_TOWN  # now it can pay
    events = construction_economy(w, w.rng)
    assert [e.type for e in events] == [FOUNDING_EVENT]
    assert grid.site_by_id(ruin.id).kind == "town"


def test_a_ruin_is_rebuilt_into_a_settlement():
    ruin = Site("Osgiliath", 1, 0, "ruin", 1)
    w = World.new_run("rebuild")
    w.tick = 1  # month 2: isolate the build cost from the yearly harvest
    w.grid = grid = _grid(3, 1, sites=[ruin])
    f = _building(w, "Gondor", 999)
    _own_all(grid, f.id)
    event = construction_economy(w, w.rng)[0]
    assert event.type == FOUNDING_EVENT and event.payload["rebuilt"] is True
    site = grid.site_by_id(ruin.id)
    assert site.kind == "town" and site.tier == 1
    assert f.treasury == 999 - econ._COST_FOUND_TOWN


def test_a_war_razed_ruin_can_be_rebuilt_in_peace():
    # War (ticket 11) drops a stormed seat to a ruin; once a realm holds that
    # ground again, peacetime construction raises it anew — the 11->12 seam.
    from arda_sim.war import _conquer
    from arda_sim.armies import Army

    seat = Site("Keep", 1, 0, "city", 1)
    w = World.new_run("razed")
    w.grid = grid = _grid(3, 1, sites=[seat])
    attacker = add_faction(w, "Orcs", FactionKind.REALM, aggression=95)  # ruthless -> razes
    besieged = add_faction(w, "Men", FactionKind.REALM)
    _own_all(grid, besieged.id)
    _at_war(attacker, besieged)
    host = Army(id=w.next_id(), kind="army", name="Host", created_year=w.current_year,
                faction_id=attacker.id, col=1, row=0, size=5000)
    w.entities[host.id] = host

    _conquer(w, grid, w.rng, host, attacker, besieged, seat)
    assert grid.site_by_id(seat.id).kind == "ruin"  # thrown down

    # A realm takes the empty ground and rebuilds the ruin.
    settler = _building(w, "Settlers", 999)
    _own_all(grid, settler.id)
    construction_economy(w, w.rng)
    assert grid.site_by_id(seat.id).kind == "town"


def test_a_town_grows_into_a_city():
    town = Site("Town", 1, 0, "town", 1, default_tier("town"))
    w = World.new_run("grow")
    w.grid = grid = _grid(3, 1, sites=[town])  # no ruin/pass, so growth is the work
    f = _building(w, "A", 999)
    _own_all(grid, f.id)
    event = construction_economy(w, w.rng)[0]
    assert event.type == SETTLEMENT_GREW_EVENT
    site = grid.site_by_id(town.id)
    assert site.kind == "city" and site.tier == 2


def test_a_fortress_rises_at_a_border_or_pass():
    # A pass is a natural fortress site: founding there raises a fort, not a town.
    a_pass = Site("The Pass", 1, 0, "pass", 1)
    w = World.new_run("fort")
    w.grid = grid = _grid(3, 1, sites=[a_pass])
    f = _building(w, "A", 999)
    _own_all(grid, f.id)
    event = construction_economy(w, w.rng)[0]
    assert event.type == FOUNDING_EVENT and event.payload["kind"] == "fort"
    assert grid.site_by_id(a_pass.id).kind == "fort"


def test_construction_skips_a_contested_region():
    # An at-war enemy host stands in the only buildable region -> no work there.
    from arda_sim.armies import Army

    ruin = Site("Osgiliath", 1, 0, "ruin", 1)
    w = World.new_run("contested")
    w.grid = grid = _grid(3, 1, sites=[ruin])  # one region (id 1) over the whole map
    f = _building(w, "A", 999)
    enemy = add_faction(w, "Enemy", FactionKind.REALM)
    _own_all(grid, f.id)
    _at_war(f, enemy)
    host = Army(id=w.next_id(), kind="army", name="Raiders", created_year=w.current_year,
                faction_id=enemy.id, col=2, row=0, size=1000)
    w.entities[host.id] = host
    assert construction_economy(w, w.rng) == []
    assert grid.site_by_id(ruin.id).kind == "ruin"


def test_a_road_is_opened_from_a_settlement():
    fort = Site("Keep", 1, 0, "fort", 1, default_tier("fort"))  # not growable, not un-settled
    w = World.new_run("road")
    w.grid = grid = _grid(3, 1, terrain=Terrain.HILLS, sites=[fort])  # hills: paveable
    f = _building(w, "A", 999)
    _own_all(grid, f.id)
    event = construction_economy(w, w.rng)[0]
    assert event.type == ROAD_OPENED_EVENT
    paved = grid.index(event.payload["col"], event.payload["row"])
    assert grid.terrain[paved] == Terrain.ROAD and paved in grid.paved


def test_road_building_also_skips_a_contested_region():
    # The contested-region skip covers roads too, not just foundings/growth.
    from arda_sim.armies import Army

    fort = Site("Keep", 1, 0, "fort", 1, default_tier("fort"))
    w = World.new_run("road-war")
    w.grid = grid = _grid(3, 1, terrain=Terrain.HILLS, sites=[fort])
    f = _building(w, "A", 999)
    enemy = add_faction(w, "Enemy", FactionKind.REALM)
    _own_all(grid, f.id)
    _at_war(f, enemy)
    host = Army(id=w.next_id(), kind="army", name="Raiders", created_year=w.current_year,
                faction_id=enemy.id, col=2, row=0, size=1000)
    w.entities[host.id] = host
    assert construction_economy(w, w.rng) == []  # no road paved under threat


def test_canonicity_leans_toward_restoration_over_growth():
    # With both a rebuildable ruin and a growable town affordable, a canon-leaning
    # realm founds (restores) first; the canon bonus outweighs the score gap+jitter.
    ruin = Site("Osgiliath", 0, 0, "ruin", 1)
    town = Site("Town", 2, 0, "town", 2, default_tier("town"))
    w = World.new_run("canon", canonicity=1.0)
    w.grid = grid = _grid(3, 1, sites=[ruin, town])
    f = _building(w, "A", 999)
    _own_all(grid, f.id)
    event = construction_economy(w, w.rng)[0]
    assert event.type == FOUNDING_EVENT  # restoration chosen over growth


# =========================================================================
# Prose & salience
# =========================================================================

def test_construction_events_carry_salience_and_prose():
    for etype in (FOUNDING_EVENT, SETTLEMENT_GREW_EVENT, ROAD_OPENED_EVENT):
        assert etype in BASE_WEIGHT
    ruin = Site("Osgiliath", 1, 0, "ruin", 1)
    w = World.new_run("prose")
    w.grid = grid = _grid(3, 1, sites=[ruin])
    f = _building(w, "Gondor", 999)
    _own_all(grid, f.id)
    event = construction_economy(w, w.rng)[0]
    finalize_event(w, event, {ruin.id: ruin.name})
    assert event.importance >= IMPORTANT_THRESHOLD  # a founding reads in the feed
    assert render_text(w, event, {ruin.id: ruin.name})  # has prose


# =========================================================================
# Determinism & persistence
# =========================================================================

def test_construction_is_deterministic_under_seed():
    def run():
        w, grid, _ = seed_world("determinism")
        run_years(w, 15)
        return [(e.type, tuple(e.subject_ids), e.location_id) for e in w.events
                if e.type in (FOUNDING_EVENT, SETTLEMENT_GREW_EVENT, ROAD_OPENED_EVENT)]

    assert run() == run()


def test_the_built_map_survives_save_and_load():
    w, grid, _ = seed_world("built-map")
    run_years(w, 20)
    blob = dumps(w)
    restored = loads(blob)
    # The grid comes back, and its mutable slice round-trips byte-for-byte.
    assert restored.grid is not None
    assert restored.grid.owner == w.grid.owner
    assert restored.grid.site_state() == w.grid.site_state()
    assert restored.grid.paved == w.grid.paved
    assert dumps(restored) == blob


def test_a_grid_run_resumes_bit_identically_across_save_load():
    reference, _, _ = seed_world("resume")
    run_years(reference, 24)
    ref_blob = dumps(reference)

    interrupted, _, _ = seed_world("resume")
    run_years(interrupted, 10)
    resumed = loads(dumps(interrupted))  # save + reload mid-run (grid must restore)
    run_years(resumed, 14)
    assert dumps(resumed) == ref_blob
