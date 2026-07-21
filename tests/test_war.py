"""War & battles (build ticket 11): field battles resolved by strength + a
bounded roll (strength dominates, upsets occur), multi-tick sieges that flip a
seat's ownership on the storm, razing vs. holding, named-death → succession,
provider hosts and corsair coastal raids — plus pipeline wiring, prose/salience,
persistence, and determinism. Every outcome-deciding comparison is integer.
"""

from collections import Counter

from arda_sim import war as war_mod
from arda_sim.armies import Army, armies
from arda_sim.characters import Race, Role, add_character
from arda_sim.chronicle import BASE_WEIGHT, finalize_event, render_text
from arda_sim.diplomacy import WAR_ENDED_EVENT
from arda_sim.entities import EntityStatus
from arda_sim.factions import (
    FactionKind,
    Posture,
    add_faction,
    factions,
    seed_world,
)
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import PIPELINE, run_years
from arda_sim.succession import SUCCESSION_EVENT, succession
from arda_sim.tiles import Site, Terrain, TileGrid, UNOWNED
from arda_sim.war import (
    BATTLE_EVENT,
    COASTAL_RAID_EVENT,
    CONQUEST_EVENT,
    RAZING_EVENT,
    SIEGE_EVENT,
    war,
)
from arda_sim.world import World


# -- builders -------------------------------------------------------------

def _grid(width, height, terrain=Terrain.PLAINS, sites=None, regions=None):
    region_of = [0] * (width * height)
    reg = {}
    if regions:
        reg = {rid: r for rid, r in regions.items()}
    return TileGrid(
        width=width,
        height=height,
        terrain=[terrain] * (width * height),
        region_of=region_of,
        regions=reg,
        sites=list(sites or []),
        miles_per_tile=15,
    )


def _army(world, faction_id, col, row, size=1000, leader_id=None, path=None):
    army = Army(
        id=world.next_id(),
        kind="army",
        name="Host",
        created_year=world.current_year,
        faction_id=faction_id,
        leader_id=leader_id,
        col=col,
        row=row,
        size=size,
        path=[list(p) for p in (path or [])],
    )
    world.entities[army.id] = army
    return army


def _at_war(a, b):
    a.at_war_with = sorted(set(a.at_war_with) | {b.id})
    b.at_war_with = sorted(set(b.at_war_with) | {a.id})


# =========================================================================
# Pipeline wiring
# =========================================================================

def test_war_is_wired_into_the_pipeline_at_phase_5():
    names = [name for name, _ in PIPELINE]
    assert names[5] == "war"
    assert dict(PIPELINE)["war"].__name__ == "war"


def test_war_is_a_no_op_without_a_grid():
    w = World.new_run("nogrid")
    a = add_faction(w, "A", FactionKind.REALM)
    b = add_faction(w, "B", FactionKind.REALM)
    _at_war(a, b)
    _army(w, a.id, 0, 0)
    _army(w, b.id, 0, 0)
    assert war(w, w.rng) == []  # inert until a grid is attached (ADR-0004)


# =========================================================================
# Field battles
# =========================================================================

def test_only_at_war_hosts_fight():
    w = World.new_run("peace")
    w.grid = grid = _grid(3, 1)
    a = add_faction(w, "A", FactionKind.REALM)
    b = add_faction(w, "B", FactionKind.REALM)  # NOT at war
    _army(w, a.id, 1, 0)
    _army(w, b.id, 1, 0)
    assert not [e for e in war(w, w.rng) if e.type == BATTLE_EVENT]


def test_hosts_sharing_or_bordering_a_tile_give_battle():
    w = World.new_run("clash")
    w.grid = _grid(4, 1)
    a = add_faction(w, "A", FactionKind.REALM)
    b = add_faction(w, "B", FactionKind.REALM)
    _at_war(a, b)
    _army(w, a.id, 1, 0)
    _army(w, b.id, 2, 0)  # adjacent
    battles = [e for e in war(w, w.rng) if e.type == BATTLE_EVENT]
    assert len(battles) == 1


def test_strength_dominates_on_average_but_upsets_occur():
    # The bigger host wins most of the time, yet a bounded roll lets the smaller
    # one snatch the occasional upset — never a coin flip, never a certainty.
    wins_for_big = 0
    upsets = 0
    trials = 200
    for i in range(trials):
        w = World.new_run(f"battle-{i}")
        w.grid = _grid(3, 1)
        big = add_faction(w, "Big", FactionKind.REALM)
        small = add_faction(w, "Small", FactionKind.REALM)
        _at_war(big, small)
        _army(w, big.id, 1, 0, size=1500)
        _army(w, small.id, 1, 0, size=1000)
        events = war(w, w.rng)
        battle = next(e for e in events if e.type == BATTLE_EVENT)
        if battle.payload["winner_faction_id"] == big.id:
            wins_for_big += 1
        else:
            upsets += 1
    assert wins_for_big > trials * 0.75  # strength dominates on average
    assert upsets > 0  # ...but upsets happen


def test_the_loser_bleeds_harder_than_the_winner():
    w = World.new_run("cas")
    w.grid = _grid(3, 1)
    a = add_faction(w, "A", FactionKind.REALM)
    b = add_faction(w, "B", FactionKind.REALM)
    _at_war(a, b)
    _army(w, a.id, 1, 0, size=5000)
    _army(w, b.id, 1, 0, size=800)
    battle = next(e for e in war(w, w.rng) if e.type == BATTLE_EVENT)
    assert battle.payload["loser_casualties"] > battle.payload["winner_casualties"]


def test_a_shattered_host_is_destroyed_not_merely_beaten():
    w = World.new_run("wipe")
    w.grid = _grid(3, 1)
    a = add_faction(w, "A", FactionKind.REALM)
    b = add_faction(w, "B", FactionKind.REALM)
    _at_war(a, b)
    _army(w, a.id, 1, 0, size=20000)
    tiny = _army(w, b.id, 1, 0, size=120)  # well under the destroy threshold once it loses
    war(w, w.rng)
    assert not tiny.alive and tiny.status == EntityStatus.DEAD.value


# =========================================================================
# Sieges & conquest
# =========================================================================

def _siege_world(seed, fort_kind="fort"):
    """A defender realm holding a walled capital, and an enemy host at its gate."""
    w = World.new_run(seed)
    seat = Site("Keep", 1, 0, fort_kind, 1)
    region = {1: __import__("arda_sim.tiles", fromlist=["Region"]).Region(1, "Home")}
    grid = _grid(3, 1, sites=[seat], regions=region)
    grid.region_of = [1, 1, 1]  # the whole strip is the defender's one region
    w.grid = grid
    defender = add_faction(w, "Defender", FactionKind.REALM, capital_location_id=1)
    attacker = add_faction(w, "Attacker", FactionKind.REALM, posture=Posture.DEFENSIVE)
    grid.owner = [defender.id, defender.id, defender.id]
    _at_war(attacker, defender)
    besieger = _army(w, attacker.id, 1, 0, size=3000)  # standing on the seat tile
    return w, grid, attacker, defender, besieger, seat


def test_a_siege_persists_across_ticks_before_the_seat_falls():
    w, grid, attacker, defender, besieger, seat = _siege_world("siege", fort_kind="city")
    siege_ticks = 0
    fell = False
    for _ in range(40):
        events = war(w, w.rng)
        if any(e.type == SIEGE_EVENT for e in events):
            siege_ticks += 1
        if any(e.type == CONQUEST_EVENT for e in events):
            fell = True
            break
    assert siege_ticks >= 2  # a city holds out for months, not one tick
    assert fell


def test_conquest_flips_ownership_of_the_fallen_realm():
    w, grid, attacker, defender, besieger, seat = _siege_world("conquer")
    for _ in range(40):
        events = war(w, w.rng)
        if any(e.type == CONQUEST_EVENT for e in events):
            break
    # A holding (defensive) conqueror annexes the land intact.
    assert all(owner == attacker.id for owner in grid.owner)
    assert not defender.alive  # last seat lost → extinguished
    assert set(defender.claim_region_ids) == {1}  # dormant claim kept


def test_a_ruthless_conqueror_razes_the_land_to_waste():
    w = World.new_run("raze")
    seat = Site("Keep", 1, 0, "town", 1)
    from arda_sim.tiles import Region
    grid = _grid(3, 1, sites=[seat], regions={1: Region(1, "Home")})
    grid.region_of = [1, 1, 1]
    w.grid = grid
    defender = add_faction(w, "Defender", FactionKind.REALM, capital_location_id=1)
    orc = add_faction(w, "Orcs", FactionKind.REALM, posture=Posture.AGGRESSIVE, aggression=95)
    grid.owner = [defender.id, defender.id, defender.id]
    _at_war(orc, defender)
    _army(w, orc.id, 1, 0, size=4000)
    razed = False
    for _ in range(40):
        events = war(w, w.rng)
        if any(e.type == RAZING_EVENT for e in events):
            razed = True
            break
    assert razed
    assert all(owner == UNOWNED for owner in grid.owner)  # laid waste, not annexed


def test_conquest_ends_the_wars_of_an_extinguished_realm():
    w, grid, attacker, defender, besieger, seat = _siege_world("endwar")
    ended = False
    for _ in range(40):
        events = war(w, w.rng)
        if any(e.type == WAR_ENDED_EVENT for e in events):
            ended = True
            break
    assert ended
    assert not attacker.is_at_war_with(defender.id)


# =========================================================================
# Named death → succession
# =========================================================================

def test_a_death_roll_is_heavier_on_the_losing_side_and_blunted_by_martial():
    # The losing general dies far more often than the winning one; a high-martial
    # captain survives more than a weak one. Pure integer roll, tested statistically.
    def death_rate(base, martial, trials=400):
        deaths = 0
        for i in range(trials):
            w = World.new_run(f"death-{base}-{martial}-{i}")
            c = add_character(w, "Cpt", Race.MAN, 2900, traits={"martial": martial})
            if war_mod._maybe_slay(w, w.rng, c, base) is not None:
                deaths += 1
        return deaths
    assert death_rate(war_mod._DEATH_BP_LOSER, 50) > death_rate(war_mod._DEATH_BP_WINNER, 50)
    assert death_rate(war_mod._DEATH_BP_LOSER, 90) < death_rate(war_mod._DEATH_BP_LOSER, 10)


def test_a_slain_ruler_vacates_the_seat_and_succession_seats_the_heir():
    # War kills the defending ruler; next tick's succession (phase 2) installs the
    # heir — the "violent death triggers succession" contract.
    w = World.new_run("succ")
    from arda_sim.tiles import Region
    seat = Site("Keep", 1, 0, "town", 1)
    grid = _grid(3, 1, sites=[seat], regions={1: Region(1, "Home")})
    grid.region_of = [1, 1, 1]
    w.grid = grid
    realm = add_faction(w, "Realm", FactionKind.REALM, capital_location_id=1)
    king = add_character(w, "King", Race.MAN, 2900, role=Role.RULER,
                         faction_id=realm.id, location_id=1, traits={"martial": 0})
    heir = add_character(w, "Heir", Race.MAN, 2940, role=Role.HEIR,
                         faction_id=realm.id, parent_ids=[king.id])
    realm.leader_id = king.id
    # Slay the king directly (the roll is exercised statistically elsewhere).
    war_mod._maybe_slay(w, w.rng, king, 10_000)
    assert not king.alive
    events = succession(w, w.rng)
    assert any(e.type == SUCCESSION_EVENT for e in events)
    assert realm.leader_id == heir.id


# =========================================================================
# Providers at war
# =========================================================================

def test_a_committed_provider_sends_a_host_when_its_patron_is_at_war():
    w = World.new_run("provider")
    gate = Site("Gate", 0, 0, "gateway", 1)
    enemy_seat = Site("City", 3, 0, "city", 2)
    from arda_sim.tiles import Region
    grid = _grid(4, 1, sites=[gate, enemy_seat], regions={1: Region(1, "R")})
    w.grid = grid
    patron = add_faction(w, "Patron", FactionKind.REALM)
    enemy = add_faction(w, "Enemy", FactionKind.REALM, capital_location_id=2)
    _at_war(patron, enemy)
    provider = add_faction(w, "Haradrim", FactionKind.PROVIDER,
                           gateway_location_id=1, commitment=40)
    provider.allegiance_faction_id = patron.id
    provider.output = {"heavy_infantry": 60, "mumakil": 10}
    war(w, w.rng)
    host = next((a for a in armies(w, alive_only=True) if a.faction_id == provider.id), None)
    assert host is not None and host.col == 0  # raised at its gateway
    assert host.target_faction_id == enemy.id  # marching on the patron's foe


def test_provider_unit_modifiers_lend_extra_weight():
    w = World.new_run("units")
    plain = add_faction(w, "Plain", FactionKind.PROVIDER)
    heavy = add_faction(w, "Heavy", FactionKind.PROVIDER)
    heavy.output = {"mumakil": 20, "heavy_infantry": 60}
    assert war_mod._provider_factor(heavy) > war_mod._provider_factor(plain)


def test_corsairs_raid_the_coast_without_seizing_a_seat():
    w = World.new_run("corsair")
    from arda_sim.tiles import Region
    # A 2x2: a sea tile so the enemy's shore counts as coastal.
    grid = TileGrid(
        width=2, height=2,
        terrain=[Terrain.SEA, Terrain.PLAINS, Terrain.PLAINS, Terrain.PLAINS],
        region_of=[0, 1, 1, 1],
        regions={1: Region(1, "Shore")},
        sites=[Site("Port", 1, 0, "town", 1)],
    )
    w.grid = grid
    patron = add_faction(w, "Patron", FactionKind.REALM)
    coastal = add_faction(w, "Coastal", FactionKind.REALM, capital_location_id=1)
    coastal.military_strength = 50
    grid.owner = [UNOWNED, coastal.id, coastal.id, coastal.id]
    _at_war(patron, coastal)
    corsair = add_faction(w, "Corsairs", FactionKind.PROVIDER,
                          gateway_location_id=1, commitment=40)
    corsair.allegiance_faction_id = patron.id
    corsair.output = {"raiders": 40, "ships": 20}
    # A raiding season is a seeded once-a-year roll; over several years a committed
    # corsair is near-certain to put to sea at least once.
    raids = []
    for year in range(8):
        w.tick = year * 12  # a year boundary (month 1), where raids are rolled
        raids += [e for e in war(w, w.rng) if e.type == COASTAL_RAID_EVENT]
    assert raids  # the shore was harried
    assert coastal.military_strength < 50  # pillaged
    assert coastal.alive and grid.owner_at(1, 0) == coastal.id  # seat not seized
    # a corsair never marches a land host
    assert not any(a.faction_id == corsair.id for a in armies(w, alive_only=True))


# =========================================================================
# Prose, salience, determinism, persistence
# =========================================================================

def test_war_events_carry_prose_and_salience():
    for etype in (BATTLE_EVENT, SIEGE_EVENT, CONQUEST_EVENT, RAZING_EVENT, COASTAL_RAID_EVENT):
        assert etype in BASE_WEIGHT and BASE_WEIGHT[etype] > 0
    w = World.new_run("prose")
    w.grid = _grid(3, 1)
    a = add_faction(w, "Gondor", FactionKind.REALM)
    b = add_faction(w, "Mordor", FactionKind.REALM)
    _at_war(a, b)
    _army(w, a.id, 1, 0, size=3000)
    _army(w, b.id, 1, 0, size=1000)
    battle = next(e for e in war(w, w.rng) if e.type == BATTLE_EVENT)
    finalize_event(w, battle, {})
    assert battle.text and battle.importance > 0
    assert render_text(w, battle, {}) is not None


def test_all_outcome_math_is_integer():
    # Effective strength, fortification, and siege progress are all int — no float
    # ever reaches an outcome-deciding comparison (the float-determinism policy).
    w = World.new_run("ints")
    w.grid = _grid(3, 1, terrain=Terrain.HILLS)
    f = add_faction(w, "F", FactionKind.REALM)
    army = _army(w, f.id, 1, 0, size=1234)
    eff = war_mod._effective_strength(w, w.grid, army, defending=True)
    assert isinstance(eff, int)
    assert isinstance(war_mod._fortification(Site("S", 0, 0, "city", 1)), int)


def test_war_runs_and_reshapes_the_map_over_a_seeded_run():
    world, grid, _ = seed_world("great-war")
    events = run_years(world, 40)
    kinds = Counter(e.type for e in events)
    assert kinds[BATTLE_EVENT] + kinds[SIEGE_EVENT] > 0  # there was fighting
    # some realm was conquered over four decades of canon-pressured war
    assert kinds[CONQUEST_EVENT] > 0


def test_war_is_deterministic_under_seed():
    a = seed_world("war-dup")[0]
    b = seed_world("war-dup")[0]
    run_years(a, 30)
    run_years(b, 30)
    assert dumps(a) == dumps(b)
    c = seed_world("war-other")[0]
    run_years(c, 30)
    assert dumps(c) != dumps(a)


def test_siege_state_round_trips_through_save_load():
    world, grid, _ = seed_world("war-save")
    run_years(world, 20)
    blob = dumps(world)
    reloaded = loads(blob)
    assert dumps(reloaded) == blob  # siege_progress and all army state round-trip
