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
    max_concurrent_hosts,
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
    leader = army_mod._coalition_leader(w, [f], f)
    assert leader is strong  # the ablest non-ruler, not the king himself
    enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=1)
    army_mod._raise_army(w, grid, f, (0, 0), enemy, [f])
    assert strong.role == Role.GENERAL.value  # took field command


def test_muster_target_is_a_war_enemy_only_not_mere_hostility():
    # Post-#13: a faction musters only when genuinely *at war*. Deep hostility with
    # no declared war is no longer a march objective (the at-war gate).
    w = World.new_run("target")
    grid = _grid(4, 1, sites=[Site("A", 0, 0, "town", 1), Site("B", 3, 0, "town", 2)])
    a = add_faction(w, "A", FactionKind.REALM, capital_location_id=1)
    hated = add_faction(w, "Hated", FactionKind.REALM, capital_location_id=2)
    a.disposition = {str(hated.id): -80}
    assert army_mod._march_target(w, a) is None  # hostility alone raises no host
    a.at_war_with = [hated.id]
    assert army_mod._march_target(w, a) is hated  # a live war does


def test_a_provider_is_never_a_march_objective():
    w = World.new_run("prov")
    a = add_faction(w, "A", FactionKind.REALM, capital_location_id=1)
    prov = add_faction(w, "P", FactionKind.PROVIDER, gateway_location_id=2)
    a.at_war_with = [prov.id]  # even at war, a provider holds no ground to march on
    assert army_mod._march_target(w, a) is None


def test_a_weak_realm_fields_a_single_standing_host():
    w = World.new_run("cap")
    grid = _grid(4, 1, sites=[Site("Seat", 0, 0, "town", 1), Site("Foe", 3, 0, "town", 2)])
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1, aggression=90)
    f.military_strength = 20  # below HOSTS_PER_STRENGTH: a single host at a time
    assert max_concurrent_hosts(f) == 1
    enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=2)
    f.at_war_with = [enemy.id]  # the at-war gate: a host needs a declared war
    f.current_intent = {"intent": Intent.MUSTER.value}
    first = movement(w, w.rng)
    second = movement(w, w.rng)
    assert sum(e.type == ARMY_MUSTERED_EVENT for e in first) == 1
    assert sum(e.type == ARMY_MUSTERED_EVENT for e in second) == 0  # at its one-host ceiling
    assert len([a for a in armies(w, alive_only=True) if a.faction_id == f.id]) == 1


def test_a_strong_realm_fields_up_to_its_strength_scaled_ceiling():
    w = World.new_run("cap")
    grid = _grid(6, 1, sites=[Site("Seat", 0, 0, "town", 1), Site("Foe", 5, 0, "town", 2)])
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1, aggression=90)
    f.military_strength = 80  # 1 + 80 // HOSTS_PER_STRENGTH(40) == 3 concurrent hosts
    assert max_concurrent_hosts(f) == 3
    enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=2)
    f.at_war_with = [enemy.id]
    f.current_intent = {"intent": Intent.MUSTER.value}
    # One host raised per tick (no cooldown while hosts are afield) up to the cap,
    # then no more — a bounded multi-front war, not an unbounded swarm.
    raised = [sum(e.type == ARMY_MUSTERED_EVENT for e in movement(w, w.rng)) for _ in range(5)]
    assert raised == [1, 1, 1, 0, 0]
    assert len([a for a in armies(w, alive_only=True) if a.faction_id == f.id]) == 3


def test_a_realm_splits_its_hosts_across_multiple_enemies():
    w = World.new_run("fronts")
    grid = _grid(
        6,
        3,
        sites=[
            Site("Seat", 0, 1, "town", 1),
            Site("FoeA", 5, 0, "town", 2),
            Site("FoeB", 5, 2, "town", 3),
        ],
    )
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1, aggression=90)
    f.military_strength = 200  # well past the ceiling: cap == MAX_CONCURRENT_HOSTS (4)
    assert max_concurrent_hosts(f) == 4
    foe_a = add_faction(w, "A", FactionKind.REALM, capital_location_id=2)
    foe_b = add_faction(w, "B", FactionKind.REALM, capital_location_id=3)
    foe_a.military_strength = 50  # the stronger threat: concentrate here first
    foe_b.military_strength = 10
    f.at_war_with = [foe_a.id, foe_b.id]
    f.current_intent = {"intent": Intent.MUSTER.value}
    for _ in range(4):  # four hosts, one per tick
        movement(w, w.rng)
    hosts = [h for h in armies(w, alive_only=True) if h.faction_id == f.id]
    targets = sorted(h.target_faction_id for h in hosts)
    # concentrate before spreading: the stronger foe (A) draws the first three hosts
    # (a two-host head-start plus a reinforcement), then the surplus opens a second
    # front on the weaker foe (B) — a bounded two-front war, not an even scatter.
    assert targets == sorted([foe_a.id, foe_a.id, foe_a.id, foe_b.id])


def test_a_host_stands_down_when_its_war_ends():
    # A host must not outlive the war that raised it: once peace is made (or its
    # foe leaves play), it disbands instead of zombie-garrisoning a former enemy's
    # seat forever — which would otherwise pin a multi-front realm at its ceiling.
    w = World.new_run("standdown")
    grid = _grid(4, 1, sites=[Site("Seat", 0, 0, "town", 1), Site("Foe", 3, 0, "town", 2)])
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1, aggression=90)
    f.military_strength = 20
    enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=2)
    f.at_war_with = [enemy.id]
    f.current_intent = {"intent": Intent.MUSTER.value}
    movement(w, w.rng)  # host raised, marching on the enemy
    assert [a.target_faction_id for a in armies(w, alive_only=True)] == [enemy.id]
    f.at_war_with = []  # the war ends (peace made / foe subdued elsewhere)
    enemy.at_war_with = []
    events = movement(w, w.rng)
    assert any(e.type == ARMY_DISBANDED_EVENT for e in events)  # it stood down
    assert not [a for a in armies(w, alive_only=True) if a.faction_id == f.id]


# -- muster cadence: at-war gate + size-scaled cooldown (issue #13) --------

def _war_setup(w, aggression=90):
    """A lead realm at war with a seated enemy, ready to muster (grid attached)."""
    grid = _grid(6, 1, sites=[Site("Seat", 0, 0, "town", 1), Site("Foe", 5, 0, "town", 2)])
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1, aggression=aggression)
    f.military_strength = 40
    enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=2)
    f.at_war_with = [enemy.id]
    f.current_intent = {"intent": Intent.MUSTER.value}
    return grid, f, enemy


def test_a_faction_at_peace_cannot_muster():
    w = World.new_run("peace-gate")
    grid = _grid(4, 1, sites=[Site("Seat", 0, 0, "town", 1)])
    w.grid = grid
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1, aggression=99)
    f.military_strength = 40
    f.current_intent = {"intent": Intent.MUSTER.value}  # wants force, but no war
    assert not [e for e in movement(w, w.rng) if e.type == ARMY_MUSTERED_EVENT]


def test_a_spent_host_rests_under_a_size_scaled_cooldown():
    w = World.new_run("cooldown")
    grid, f, enemy = _war_setup(w)
    host = [a for a in armies(w, alive_only=True)]
    movement(w, w.rng)
    host = next(a for a in armies(w, alive_only=True) if a.faction_id == f.id)
    assert f.muster_cooldown_until == 0  # a standing host sets no cooldown yet
    army_mod.end_host(w, host)  # the host leaves play
    assert f.muster_cooldown_until == w.current_year + host.cooldown_years
    assert host.cooldown_years >= army_mod.MUSTER_COOLDOWN_BASE
    # Within the cooldown the faction cannot raise another, even wanting to.
    host.status = __import__("arda_sim.entities", fromlist=["EntityStatus"]).EntityStatus.DEAD.value
    assert not army_mod._can_muster(w, f)


def test_cooldown_scales_up_with_the_size_of_the_host_raised():
    small = army_mod.host_cooldown_years(1000)
    large = army_mod.host_cooldown_years(30000)
    assert small < large  # a greater hosting depletes the realm for longer
    assert large <= army_mod.MUSTER_COOLDOWN_CAP  # ...but bounded


# -- coalition Gathering + leader ladder (issue #13) -----------------------

def test_allies_at_war_combine_into_one_coalition_host():
    w = World.new_run("coalition")
    grid = _grid(6, 1, sites=[Site("Seat", 0, 0, "town", 1), Site("Foe", 5, 0, "town", 2)])
    w.grid = grid
    lead = add_faction(w, "Lead", FactionKind.REALM, capital_location_id=1, aggression=90)
    ally = add_faction(w, "Ally", FactionKind.REALM)
    enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=2)
    lead.military_strength = ally.military_strength = 40
    lead.treaties = [ally.id]
    ally.treaties = [lead.id]
    lead.at_war_with = ally.at_war_with = [enemy.id]  # both share the war
    lead.current_intent = {"intent": Intent.MUSTER.value}
    movement(w, w.rng)
    hosts = [a for a in armies(w, alive_only=True) if a.faction_id in (lead.id, ally.id)]
    assert len(hosts) == 1  # one combined host, not two
    host = hosts[0]
    assert host.faction_id == lead.id  # owned by the lead
    assert set(host.contributor_ids) == {lead.id, ally.id}
    # summed levies (mustered_size is the raise-time strength, before any march attrition)
    assert host.mustered_size == army_mod.muster_size(lead) + army_mod.muster_size(ally)


def test_the_leader_ladder_falls_back_to_the_heir_then_a_generated_captain():
    w = World.new_run("ladder")
    f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1)
    king = add_character(w, "King", Race.MAN, 2900, role=Role.RULER, faction_id=f.id)
    f.leader_id = king.id
    heir = add_character(w, "Heir", Race.MAN, 2940, role=Role.HEIR, faction_id=f.id,
                         traits={"martial": 60})
    # No field-eligible non-heir → the heir leads (rung 2).
    assert army_mod._coalition_leader(w, [f], f) is heir
    # With the heir gone too, a generated captain is raised (rung 3).
    heir.status = __import__("arda_sim.entities", fromlist=["EntityStatus"]).EntityStatus.DEAD.value
    captain = army_mod._coalition_leader(w, [f], f)
    assert captain is not None and captain is not king
    assert captain.role == Role.GENERAL.value
    assert captain.parent_ids == []  # non-dynastic, outside the succession line


def test_a_generated_captain_is_deterministic():
    def cap_traits(seed):
        w = World.new_run(seed)
        f = add_faction(w, "F", FactionKind.REALM, capital_location_id=1)
        return army_mod.generate_captain(w, f).traits
    assert cap_traits("gcap") == cap_traits("gcap")  # same run → same captain


# -- per-faction march pace (issue #13) ------------------------------------

def test_march_pace_is_per_faction_and_a_coalition_uses_the_leads():
    w = World.new_run("pace")
    grid = _grid(6, 1, sites=[Site("Seat", 0, 0, "town", 1), Site("Foe", 5, 0, "town", 2)])
    w.grid = grid
    from arda_sim.factions import People, faction_march_speed
    rohan = add_faction(w, "Riders", FactionKind.REALM, capital_location_id=1,
                        people=People.MEN, march_speed=320)
    dwarves = add_faction(w, "Khazad", FactionKind.REALM, people=People.DWARVES)
    assert faction_march_speed(rohan) == 320  # authored override
    assert faction_march_speed(dwarves) < faction_march_speed(rohan)  # dwarves slower
    enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=2)
    rohan.military_strength = 40
    rohan.at_war_with = [enemy.id]
    rohan.current_intent = {"intent": Intent.MUSTER.value}
    movement(w, w.rng)
    host = next(a for a in armies(w, alive_only=True) if a.faction_id == rohan.id)
    assert host.miles_per_year == 320  # the host marches at the lead's pace


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
    # Musters follow war, and war is now gated by the rising Shadow (ADR-0012): a
    # run opens in peace and hosts take the field only once the West wakes to
    # Mordor, in the War-of-the-Ring window — so this run must reach that far.
    world, _grid, _ = seed_world("campaign")
    events = run_years(world, 45)
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
    # Long enough to reach the (now Shadow-gated) wars that put a host on the map.
    world, _grid, _ = seed_world("army-save")
    run_years(world, 45)
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
