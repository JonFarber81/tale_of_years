"""Armies & movement (build ticket 10): deterministic muster sizing, tile-path
movement by an integer budget, integer attrition off friendly ground, and the
muster/arrival/disband events — plus pipeline wiring, persistence, and the
snapshot-isolation discipline the phase shares with diplomacy.
"""

from arda_sim import armies as army_mod
from arda_sim.armies import (
    ARMY_ARRIVED_EVENT,
    ARMY_DISBANDED_EVENT,
    ARMY_MUSTERED_EVENT,
    Army,
    armies,
    army_at,
    find_path,
    movement,
    muster_size,
    tick_speed,
)
from arda_sim.characters import Race, Role, add_character
from arda_sim.entities import EntityStatus
from arda_sim.factions import (
    FactionKind,
    Intent,
    add_faction,
    factions,
    seed_world,
)
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import PIPELINE, run_years
from arda_sim.snapshot import snapshot_world
from arda_sim.tiles import Region, Site, Terrain, TileGrid
from arda_sim.world import World


# -- grid builders --------------------------------------------------------

def _grid(width, height, terrain=Terrain.PLAINS, sites=None, miles_per_tile=15):
    """A rectangular grid of one terrain, no regions, optional sites."""
    cells = [terrain] * (width * height)
    return TileGrid(
        width=width,
        height=height,
        terrain=cells,
        region_of=[0] * (width * height),
        regions={},
        sites=list(sites or []),
        miles_per_tile=miles_per_tile,
    )


def _army(world, grid, faction_id, col, row, path, miles_per_year=180, size=1000):
    army = Army(
        id=world.next_id(),
        kind="army",
        name="Host",
        created_year=world.current_year,
        faction_id=faction_id,
        col=col,
        row=row,
        size=size,
        path=[list(p) for p in path],
        miles_per_year=miles_per_year,
    )
    world.entities[army.id] = army
    return army


# -- pure sizing / pace ---------------------------------------------------

def test_movement_is_wired_into_the_pipeline_at_phase_4():
    names = [name for name, _ in PIPELINE]
    assert names[4] == "movement"
    assert dict(PIPELINE)["movement"].__name__ == "movement"


def test_muster_size_is_a_deterministic_function_of_strength():
    w = World.new_run("size")
    f = add_faction(w, "F", FactionKind.REALM)
    f.military_strength = 100
    assert muster_size(f) == army_mod.MUSTER_BASE + 100 * army_mod.MUSTER_PER_STRENGTH
    f.military_strength = 0
    assert muster_size(f) == army_mod.MUSTER_BASE  # a base levy even bare


def test_tick_speed_maps_a_miles_per_year_rate_to_an_integer_budget():
    # 180 mi/yr on 15-mile tiles clears one plains tile (cost 2) a month.
    assert tick_speed(180, 15) == 2
    assert tick_speed(360, 15) == 4  # a mounted host, twice as fast
    assert tick_speed(1, 15) >= 1  # never zero — a host always eventually moves


# -- pathfinding ----------------------------------------------------------

def test_find_path_is_empty_at_the_goal_and_walks_straight_across_plains():
    grid = _grid(5, 1)
    assert find_path(grid, (0, 0), (0, 0)) == []
    assert find_path(grid, (0, 0), (4, 0)) == [[1, 0], [2, 0], [3, 0], [4, 0]]


def test_find_path_routes_around_impassable_terrain_deterministically():
    # A wall of mountain at col 2 (rows 0..1) forces the path down and around.
    grid = _grid(4, 3)
    for r in (0, 1):
        grid.terrain[grid.index(2, r)] = Terrain.MOUNTAIN
    path = find_path(grid, (0, 0), (3, 0))
    assert path[-1] == [3, 0]
    assert [2, 0] not in path and [2, 1] not in path  # never steps on the wall
    assert find_path(grid, (0, 0), (3, 0)) == path  # same call, same route


def test_find_path_reaches_an_objective_on_otherwise_impassable_terrain():
    # A seat on a mountain (Barad-dûr) is still enterable by the besieging host.
    grid = _grid(3, 1)
    grid.terrain[grid.index(2, 0)] = Terrain.MOUNTAIN
    assert find_path(grid, (0, 0), (2, 0)) == [[1, 0], [2, 0]]


def test_find_path_returns_empty_when_the_goal_is_walled_off():
    grid = _grid(3, 1)
    grid.terrain[grid.index(1, 0)] = Terrain.SEA  # impassable, blocks the corridor
    assert find_path(grid, (0, 0), (2, 0)) == []


# -- movement advance -----------------------------------------------------

def test_movement_advances_a_fixed_number_of_tiles_per_year_under_the_budget():
    # On friendly plains (no attrition), a foot host clears exactly one tile a
    # month — twelve in a year — deterministically.
    grid = _grid(30, 1)
    w = World.new_run("advance")
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM)
    grid.owner = [f.id] * (grid.width * grid.height)  # all friendly: no attrition
    army = _army(w, grid, f.id, 0, 0, [[c, 0] for c in range(1, 25)])
    for _ in range(12):
        army_mod._advance(w, grid, army)
    assert army.col == 12 and army.size == 1000  # 12 tiles, unbled on home soil


def test_movement_is_quicker_on_roads_than_on_plains():
    road = _grid(30, 1, terrain=Terrain.ROAD)
    w = World.new_run("road")
    w.grid = road
    f = add_faction(w, "F", FactionKind.REALM)
    road.owner = [f.id] * (road.width * road.height)
    army = _army(w, road, f.id, 0, 0, [[c, 0] for c in range(1, 28)])
    for _ in range(6):
        army_mod._advance(w, road, army)
    assert army.col == 12  # cost-1 tiles: two a month, twelve in six months


def test_arrival_emits_an_event_and_the_host_garrisons():
    grid = _grid(4, 1, sites=[Site("Keep", 3, 0, "fortress", 9)])
    w = World.new_run("arrive")
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM)
    grid.owner = [f.id] * (grid.width * grid.height)
    army = _army(w, grid, f.id, 0, 0, [[1, 0], [2, 0], [3, 0]])
    army.dest_site_id = 9
    events = []
    for _ in range(4):
        events += army_mod._advance(w, grid, army)
    assert army.col == 3 and not army.path  # reached the objective
    arrivals = [e for e in events if e.type == ARMY_ARRIVED_EVENT]
    assert len(arrivals) == 1 and arrivals[0].location_id == 9
    assert army.dest_site_id is None  # now a standing garrison


# -- attrition ------------------------------------------------------------

def test_attrition_bleeds_a_marching_host_on_barren_hostile_ground():
    grid = _grid(6, 1, terrain=Terrain.BARREN)  # harsh land, and unowned = hostile
    w = World.new_run("bleed")
    f = add_faction(w, "F", FactionKind.REALM)
    army = _army(w, grid, f.id, 0, 0, [[c, 0] for c in range(1, 6)], size=1000)
    before = army.size
    army_mod._advance(w, grid, army)
    assert army.size == before - (army_mod.ATTR_HARSH + army_mod.ATTR_HOSTILE)


def test_attrition_deepens_the_longer_a_host_stays_off_friendly_soil():
    # "a host deep in hostile land bleeds": the off-friendly toll scales with the
    # run of marching ticks since it last stood on friendly soil (supply_lag).
    grid = _grid(12, 1)  # plains, unowned = hostile, but not harsh
    w = World.new_run("depth")
    f = add_faction(w, "F", FactionKind.REALM)
    army = _army(w, grid, f.id, 0, 0, [[c, 0] for c in range(1, 11)], size=100_000)
    losses = []
    prev = army.size
    for _ in range(4):
        army_mod._advance(w, grid, army)
        losses.append(prev - army.size)
        prev = army.size
    assert losses == [army_mod.ATTR_HOSTILE * n for n in (1, 2, 3, 4)]


def test_supply_lag_caps_and_resets_on_regaining_friendly_soil():
    grid = _grid(10, 1)
    w = World.new_run("reset")
    f = add_faction(w, "F", FactionKind.REALM)
    army = _army(w, grid, f.id, 0, 0, [[c, 0] for c in range(1, 10)], size=100_000)
    for _ in range(8):
        army_mod._advance(w, grid, army)
    assert army.supply_lag == army_mod.ATTR_LAG_CAP  # saturates, not unbounded
    grid.owner = [f.id] * grid.width  # the whole corridor is friendly now
    army_mod._advance(w, grid, army)
    assert army.supply_lag == 0  # regaining friendly soil resets the depth


def test_a_garrisoned_host_does_not_bleed():
    grid = _grid(3, 1, terrain=Terrain.BARREN)
    w = World.new_run("garrison")
    f = add_faction(w, "F", FactionKind.REALM)
    army = _army(w, grid, f.id, 1, 0, path=[], size=500)  # no path = in garrison
    army_mod._advance(w, grid, army)
    assert army.size == 500  # attrition only bites a host on the march


def test_a_host_bled_to_nothing_disbands_with_an_event():
    grid = _grid(30, 1, terrain=Terrain.MARSH)
    w = World.new_run("disband")
    f = add_faction(w, "F", FactionKind.REALM)
    army = _army(w, grid, f.id, 0, 0, [[c, 0] for c in range(1, 30)], size=60)
    events = []
    for _ in range(20):
        events += army_mod._advance(w, grid, army)
    assert not army.alive and army.status == EntityStatus.DEAD.value
    disbands = [e for e in events if e.type == ARMY_DISBANDED_EVENT]
    assert len(disbands) == 1 and disbands[0].payload["cause"] == "attrition"


def test_own_and_allied_soil_are_friendly_but_wilderness_is_not():
    w = World.new_run("friend")
    f = add_faction(w, "F", FactionKind.REALM)
    ally = add_faction(w, "Ally", FactionKind.REALM)
    f.treaties = [ally.id]
    friendly = army_mod._friendly_ids(w, f.id)
    assert f.id in friendly and ally.id in friendly
    from arda_sim.tiles import UNOWNED
    assert UNOWNED not in friendly  # unowned wilderness bleeds a host


# -- muster: leader, target, one-host cap ---------------------------------

def test_muster_picks_the_ablest_field_leader_and_makes_them_a_general():
    w = World.new_run("lead")
    grid = _grid(4, 1, sites=[Site("Seat", 0, 0, "town", 1)])
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1)
    ruler = add_character(w, "King", Race.MAN, 2900, role=Role.RULER, faction_id=f.id,
                          traits={"martial": 90, "leadership": 90})
    f.leader_id = ruler.id
    weak = add_character(w, "Squire", Race.MAN, 2900, faction_id=f.id,
                         traits={"martial": 30, "leadership": 30})
    strong = add_character(w, "Captain", Race.MAN, 2900, faction_id=f.id,
                           traits={"martial": 80, "leadership": 75})
    leader = army_mod._muster_leader(w, f)
    assert leader is strong  # the ablest non-ruler, not the king himself
    army_mod._raise_army(w, grid, f, (0, 0))
    assert strong.role == Role.GENERAL.value  # took field command


def test_muster_target_prefers_a_war_enemy_then_the_most_hated_seated_realm():
    w = World.new_run("target")
    grid = _grid(4, 1, sites=[Site("A", 0, 0, "town", 1), Site("B", 3, 0, "town", 2)])
    a = add_faction(w, "A", FactionKind.REALM, capital_location_id=1)
    hated = add_faction(w, "Hated", FactionKind.REALM, capital_location_id=2)
    a.disposition = {str(hated.id): -80}
    assert army_mod._march_target(w, a) is hated  # most-hated seated realm
    war_enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=2)
    a.at_war_with = [war_enemy.id]
    assert army_mod._march_target(w, a) is war_enemy  # a live war wins


def test_a_provider_is_never_a_march_objective():
    w = World.new_run("prov")
    a = add_faction(w, "A", FactionKind.REALM, capital_location_id=1)
    prov = add_faction(w, "P", FactionKind.PROVIDER, gateway_location_id=2)
    a.disposition = {str(prov.id): -100}
    assert army_mod._march_target(w, a) is None


def test_a_faction_musters_only_one_standing_host_at_a_time():
    w = World.new_run("cap")
    grid = _grid(4, 1, sites=[Site("Seat", 0, 0, "town", 1)])
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1, aggression=90)
    f.military_strength = 40
    f.current_intent = {"intent": Intent.MUSTER.value}
    first = movement(w, w.rng)
    second = movement(w, w.rng)
    assert sum(e.type == ARMY_MUSTERED_EVENT for e in first) == 1
    assert sum(e.type == ARMY_MUSTERED_EVENT for e in second) == 0  # cap holds
    assert len([a for a in armies(w, alive_only=True) if a.faction_id == f.id]) == 1


def test_army_at_finds_the_host_standing_on_a_tile():
    w = World.new_run("at")
    grid = _grid(4, 1)
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM)
    army = _army(w, grid, f.id, 2, 0, path=[])
    assert army_at(w, 2, 0) is army and army_at(w, 0, 0) is None


# -- integration: the phase does no work without a grid -------------------

def test_movement_is_a_no_op_without_a_grid():
    w = World.new_run("nogrid")
    add_faction(w, "F", FactionKind.REALM, capital_location_id=1, aggression=99)
    assert movement(w, w.rng) == []  # ADR-0004: inert until a grid is attached


# -- integration: seeded run, determinism, persistence, snapshots ---------

def test_armies_muster_and_march_over_a_seeded_run():
    world, _grid, _ = seed_world("campaign")
    events = run_years(world, 10)
    kinds = {e.type for e in events}
    assert ARMY_MUSTERED_EVENT in kinds
    assert armies(world)  # hosts exist on the map
    # a mustered host is inspectable — leader, size, and a destination all read.
    marched = [a for a in armies(world) if a.dest_site_id is not None or a.size > 0]
    assert marched


def test_movement_is_deterministic_under_seed():
    a = seed_world("dup")[0]
    b = seed_world("dup")[0]
    run_years(a, 12)
    run_years(b, 12)
    assert dumps(a) == dumps(b)  # same seed → bit-identical campaigns
    c = seed_world("other")[0]
    run_years(c, 12)
    assert dumps(c) != dumps(a)


def test_army_state_round_trips_through_save_load():
    world, _grid, _ = seed_world("army-save")
    run_years(world, 8)
    blob = dumps(world)
    reloaded = loads(blob)
    assert dumps(reloaded) == blob  # position, path, size, leader all round-trip
    assert any(isinstance(e, Army) for e in reloaded.entities.values())


def test_a_marching_host_does_not_leak_into_an_earlier_snapshot():
    # the reassign-not-mutate discipline: a snapshot keeps the march it captured.
    grid = _grid(10, 1)
    w = World.new_run("snap")
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM)
    grid.owner = [f.id] * grid.width
    army = _army(w, grid, f.id, 0, 0, [[c, 0] for c in range(1, 9)])
    snap = snapshot_world(w, 0)
    army_mod._advance(w, grid, army)
    assert snap.entity(army.id).col == 0  # snapshot frozen at the start tile
    assert len(snap.entity(army.id).path) == 8  # its whole march preserved
    assert army.col == 1 and len(army.path) == 7  # the live host advanced
