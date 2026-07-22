"""Sauron's rise & canonicity (issue #5): the phase-7 strength formula
(baseline × canonicity + emergent deltas, flattened at canonicity 0), the nine
Nazgûl (seeded, immortal, riding on high strength alone — pull is only urgency,
ADR-0016 — unmade with the Ring), the terminal outcomes and their world flags,
canon pressure as soft
weighting (intents biased, battle dice untouched), and persistence.
"""

import json
import random

from arda_sim import TICKS_PER_YEAR
from arda_sim.armies import muster_size
from arda_sim.characters import (
    DARK_LORD_TITLE,
    Race,
    Role,
    add_character,
    characters,
)
from arda_sim.entities import EntityStatus
from arda_sim.factions import (
    FactionKind,
    HUNT_STRENGTH_MIN,
    Intent,
    _HUNT_BLOCKED,
    _hunt_drive,
    add_faction,
    factions,
    seed_world,
)
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import PIPELINE, run_tick, run_years
from arda_sim.ring import (
    RING_DESTROYED_FLAG,
    RING_LOST_EVENT,
    RING_LYING_LOST_FLAG,
    SAURON_RECLAIMED_FLAG,
    RingTransfer,
    ring_system,
    the_ring,
    transfer_ring,
)
from arda_sim.sauron import (
    Hunt,
    NAZGUL_HUNT_EVENT,
    canon_baseline,
    compute_sauron_strength,
    dark_realm,
    hunts,
    nazgul,
    sauron_rise,
)
from arda_sim.war import _resolve_battle
from arda_sim.world import World


def _mordor(world):
    return dark_realm(world)


def _witch_king(world):
    return next(c for c in characters(world) if "Witch-king" in c.name)


def _sauron(world):
    return next(c for c in characters(world) if c.title == DARK_LORD_TITLE)


def _volcano_site(grid):
    return next(s for s in grid.sites if s.kind == "volcano")


# =========================================================================
# Seeding — the Nine
# =========================================================================

def test_nine_nazgul_seeded_at_their_canon_seats():
    world, grid, _names = seed_world("nine")
    the_nine = nazgul(world)
    assert len(the_nine) == 9
    mordor = _mordor(world)
    assert all(w.faction_id == mordor.id for w in the_nine)
    morgul = grid.site_id_of("Minas Morgul")
    guldur = grid.site_id_of("Dol Guldur")
    assert _witch_king(world).location_id == morgul
    assert sum(1 for w in the_nine if w.location_id == guldur) == 3
    assert sum(1 for w in the_nine if w.location_id == morgul) == 6


def test_nazgul_are_immortal_while_the_ring_endures():
    world, _grid, _names = seed_world("undying")
    run_years(world, 10)
    assert all(w.alive for w in nazgul(world))
    assert all(w.status != EntityStatus.DEPARTED.value for w in nazgul(world))


# =========================================================================
# The strength formula
# =========================================================================

def test_strength_follows_baseline_times_canonicity_plus_deltas():
    world, _grid, _names = seed_world("formula", canonicity=1.0)
    run_tick(world)
    mordor = _mordor(world)
    # A quiet first tick: no deltas, no pull — the strength IS the baseline.
    assert mordor.sauron_delta == 0
    assert mordor.sauron_strength == canon_baseline(world.current_year)


def test_half_canonicity_halves_the_baseline_term():
    world, _grid, _names = seed_world("half", canonicity=0.5)
    run_tick(world)
    assert _mordor(world).sauron_strength == canon_baseline(world.current_year) // 2


def test_canonicity_zero_flattens_to_the_emergent_deltas():
    world, _grid, _names = seed_world("flat", canonicity=0.0)
    run_tick(world)
    mordor = _mordor(world)
    assert mordor.sauron_strength == 0  # no baseline, no emergent history yet
    mordor.sauron_delta = 25  # a purely emergent surge...
    assert compute_sauron_strength(world, mordor) == 25  # ...is all there is


def test_emergent_spurs_and_checks_move_the_strength():
    world, _grid, _names = seed_world("delta", canonicity=1.0)
    mordor = _mordor(world)
    base = compute_sauron_strength(world, mordor)
    the_ring(world).pull = 40  # the Ring stirring feeds his awareness
    assert compute_sauron_strength(world, mordor) == base + 40 // 4
    # A fallen dark vassal (Dol Guldur) checks him.
    guldur = next(f for f in factions(world) if f.name == "Dol Guldur")
    guldur.status = EntityStatus.DEAD.value
    assert compute_sauron_strength(world, mordor) == base + 40 // 4 - 20


def test_canon_baseline_ramps_and_clamps():
    assert canon_baseline(2800) == canon_baseline(2900)  # flat before the ramp
    assert canon_baseline(2951) < canon_baseline(2990) < canon_baseline(3018)
    assert canon_baseline(3050) == canon_baseline(3018)  # flat at the top


def test_strength_scales_mordor_musters():
    world, _grid, _names = seed_world("muster")
    mordor = _mordor(world)
    quiet = muster_size(mordor)
    mordor.sauron_strength = 50
    assert muster_size(mordor) > quiet


def test_provider_commitment_climbs_toward_the_strength():
    world, _grid, _names = seed_world("providers", canonicity=1.0)
    variags = next(f for f in factions(world) if f.name == "Variags of Khand")
    before = variags.commitment
    run_years(world, 4)
    assert variags.commitment > before


# =========================================================================
# The hunt
# =========================================================================

def test_hunt_is_wired_between_movement_and_war():
    names = [name for name, _ in PIPELINE]
    assert names.index("movement") < names.index("hunt") < names.index("war")


def test_nazgul_do_not_ride_without_strength():
    world, _grid, _names = seed_world("nohunt")
    mordor = _mordor(world)
    mordor.sauron_strength = HUNT_STRENGTH_MIN - 1  # the Shadow is too weak...
    the_ring(world).pull = 100  # ...however loudly the Ring stirs
    run_tick(world)
    assert mordor.current_intent.get("intent") != Intent.HUNT.value
    assert hunts(world, alive_only=True) == []


def test_nazgul_ride_on_strength_even_when_the_ring_is_silent():
    # ADR-0016: strength alone unlocks the hunt — a quiet Ring is still hunted.
    # (Hunt-vs-war weighting is deferred to harness tuning, so we quiet Mordor's
    # own wars here to isolate the unlock: with no enemy to march on, a strong
    # Shadow rides for the Ring even though it lies wholly silent.)
    world, _grid, _names = seed_world("silent")
    mordor = _mordor(world)
    mordor.sauron_strength = 100  # a strong Shadow...
    mordor.disposition = {}  # ...with no foe to march against...
    mordor.aggression = 0  # ...and no appetite for open war
    the_ring(world).pull = 0  # a Ring gone wholly quiet (pull 0)
    run_tick(world)
    assert mordor.current_intent.get("intent") == Intent.HUNT.value
    assert len(hunts(world, alive_only=True)) == 1


def test_pull_is_urgency_not_a_gate_for_the_hunt():
    # The drive is blocked below the strength threshold, unlocked at/above it even
    # when the Ring is silent, and a louder Ring only raises the score (ADR-0016).
    world, _grid, _names = seed_world("urgency")
    mordor = _mordor(world)
    ring = the_ring(world)
    # The seeded Ring rests with a free bearer, so the hunt is never blocked for
    # being already in the Shadow's keeping.
    bearer = world.entities.get(ring.bearer_id)
    assert getattr(bearer, "faction_id", None) != mordor.id

    mordor.sauron_strength = HUNT_STRENGTH_MIN - 1
    ring.pull = 90
    assert _hunt_drive(world, mordor) == _HUNT_BLOCKED  # strength gates, not pull

    mordor.sauron_strength = HUNT_STRENGTH_MIN
    ring.pull = 0
    quiet = _hunt_drive(world, mordor)
    assert quiet > _HUNT_BLOCKED  # a silent Ring still unlocks the hunt

    ring.pull = 50
    louder = _hunt_drive(world, mordor)
    assert louder > quiet  # pull remains an additive urgency term


def test_nazgul_ride_when_strength_and_pull_are_high():
    world, _grid, _names = seed_world("hunt")
    mordor = _mordor(world)
    mordor.sauron_strength = 100
    the_ring(world).pull = 90
    run_tick(world)
    assert mordor.current_intent.get("intent") == Intent.HUNT.value
    riding = hunts(world, alive_only=True)
    assert len(riding) == 1
    assert set(riding[0].wraith_ids) == {w.id for w in nazgul(world)}
    assert any(
        e.type == NAZGUL_HUNT_EVENT and e.payload.get("phase") == "begun"
        for e in world.events
    )


def test_a_riding_hunt_does_not_turn_back_when_the_scent_fades():
    # ADR-0016: a strength-driven hunt is bounded by its search budget, not by the
    # scent — a Ring going quiet mid-chase no longer calls the Nine off.
    world, _grid, _names = seed_world("cold")
    mordor = _mordor(world)
    mordor.sauron_strength = 100
    the_ring(world).pull = 90
    run_tick(world)
    (hunt,) = hunts(world, alive_only=True)
    the_ring(world).pull = 0  # the Ring goes wholly quiet mid-chase
    run_tick(world)
    assert hunt.alive  # it rides on, undeterred by the lost scent
    assert not any(
        e.type == NAZGUL_HUNT_EVENT and e.payload.get("reason") == "lost_scent"
        for e in world.events
    )


def test_a_riding_hunt_turns_back_only_when_its_budget_is_spent():
    # With the scent-abort gone, the search budget is the sole patience bound: a
    # hunt whose budget is exhausted (and not standing on the quarry) turns back.
    world, _grid, _names = seed_world("spent")
    mordor = _mordor(world)
    mordor.sauron_strength = 100
    the_ring(world).pull = 90
    run_tick(world)
    (hunt,) = hunts(world, alive_only=True)
    the_ring(world).pull = 0  # quiet Ring — only the budget can end this now
    hunt.search_budget = 1  # one tick of patience left
    run_tick(world)
    assert not hunt.alive
    assert any(
        e.type == NAZGUL_HUNT_EVENT and e.payload.get("reason") == "search_spent"
        for e in world.events
    )


def test_a_quiet_ring_is_hunted_and_the_nine_reach_its_tile():
    # The headline behaviour (ADR-0016): under a strong Shadow the Nine ride to a
    # marooned, silent Ring (pull 0) and stand at last upon its very tile.
    world, grid, _names = seed_world("quiet-quarry")
    mordor = _mordor(world)
    mordor.sauron_strength = 100  # the Shadow is strong...
    mordor.disposition = {}  # ...with no foe to march against (isolate the unlock)...
    mordor.aggression = 0  # ...and no appetite for open war
    ring = the_ring(world)
    ring.pull = 0  # ...but the Ring lies wholly quiet
    # Maroon the quiet Ring in ruined Osgiliath, a short ride from Minas Morgul.
    osgiliath = grid.site_id_of("Osgiliath")
    site = grid.site_by_id(osgiliath)
    ring.bearer_id = None
    ring.location_id = osgiliath
    ring.col, ring.row = site.col, site.row

    run_tick(world)  # phase 2 unlocks the hunt on strength alone
    assert mordor.current_intent.get("intent") == Intent.HUNT.value
    (hunt,) = hunts(world, alive_only=True)

    reached = False
    for _ in range(60):  # ride, at most the search budget, tile by tile
        run_tick(world)
        if (hunt.col, hunt.row) == (ring.col, ring.row):
            reached = True
            break
        if not hunt.alive:
            break
    assert reached, "the Nine never reached the quiet Ring's tile"


def test_a_cornered_bearer_can_be_captured_and_the_ring_reclaimed():
    world, grid, _names = seed_world("reclaim")
    ring = the_ring(world)
    wraith = _witch_king(world)
    # The wraith seizes the Ring (the capture the hunt exists to attempt)...
    transfer_ring(world, ring, to_bearer=wraith, mode=RingTransfer.THEFT)
    # ...standing at the dark seat itself, so delivery is immediate.
    barad_dur = grid.site_id_of("Barad-dûr")
    wraith.location_id = barad_dur
    site = grid.site_by_id(barad_dur)
    ring.col, ring.row = site.col, site.row
    for _ in range(3):  # wraith tick delivers; the Dark Lord's tick is terminal
        run_tick(world)
        if world.flags.get(SAURON_RECLAIMED_FLAG):
            break
    assert world.flags.get(SAURON_RECLAIMED_FLAG) is True
    assert ring.bearer_id == _sauron(world).id
    claimed = [e for e in world.events if e.payload.get("terminal") is True]
    assert len(claimed) == 1


# =========================================================================
# Terminal outcomes
# =========================================================================

def _world_at_the_fire(seed="doom"):
    """A run standing one step from active Orodruin, the Ring borne and bound
    there on an errand."""
    world, grid, _names = seed_world(seed)
    world.tick = (3010 - 2965) * TICKS_PER_YEAR  # Orodruin long active
    ring = the_ring(world)
    volcano = _volcano_site(grid)
    bearer = world.entities[ring.bearer_id]
    ring.col, ring.row = volcano.col + 1, volcano.row  # one tile out
    ring.goal_site_id = volcano.id
    ring.path = [[volcano.col, volcano.row]]
    ring.move_points = 100  # ample budget: the next step arrives
    return world, grid, ring, bearer, volcano


def test_destruction_tombstones_the_ring_and_unmakes_the_nine():
    world, grid, ring, bearer, volcano = _world_at_the_fire()
    run_tick(world)
    assert ring.status == EntityStatus.DESTROYED.value
    assert ring.bearer_id is None and ring.location_id == volcano.id
    assert world.flags.get(RING_DESTROYED_FLAG) is True
    assert all(w.status == EntityStatus.DESTROYED.value for w in nazgul(world))
    assert _sauron(world).status == EntityStatus.DESTROYED.value


def test_destruction_is_impossible_before_orodruin_wakes():
    world, grid, ring, bearer, volcano = _world_at_the_fire("early")
    world.tick = 0  # TA 2965 — the Fire is not lit
    run_tick(world)
    assert ring.status == EntityStatus.ACTIVE.value


def test_mordor_collapses_by_extinction_over_the_following_ticks():
    world, grid, ring, bearer, volcano = _world_at_the_fire("collapse")
    mordor = _mordor(world)
    run_tick(world)
    assert mordor.alive  # not felled in the same breath...
    run_years(world, 4)
    assert not mordor.alive  # ...but the Shadow's realm crumbles to nothing
    assert mordor.sauron_strength == 0
    assert mordor.claim_region_ids  # a dormant claim marks where it stood


def test_ring_lying_long_unfelt_raises_the_lost_flag_and_clears_on_finding():
    world, grid, _names = seed_world("lost")
    ring = the_ring(world)
    empty_site = next(
        s.id
        for s in grid.sites
        if all(c.location_id != s.id for c in characters(world, alive_only=True))
    )
    transfer_ring(world, ring, to_location=empty_site, mode=RingTransfer.LOSS)
    ring.pull = 0
    emitted = []
    for _ in range(130):  # drive the Ring phase alone: nothing else interferes
        emitted.extend(ring_system(world, world.rng))
    assert world.flags.get(RING_LYING_LOST_FLAG) is True
    assert any(e.type == RING_LOST_EVENT for e in emitted)
    finder = characters(world, alive_only=True)[0]
    transfer_ring(world, ring, to_bearer=finder, mode=RingTransfer.FOUND)
    assert world.flags.get(RING_LYING_LOST_FLAG) is False


# =========================================================================
# Canon pressure — soft weighting only
# =========================================================================

def test_canonicity_never_touches_battle_dice():
    """Identical battles under canonicity 1 and 0 resolve identically given the
    same dice — canon pressure biases who *acts*, never how a clash falls."""
    outcomes = []
    for canonicity in (1.0, 0.0):
        world, grid, _names = seed_world("dice", canonicity=canonicity)
        a = add_faction(world, "A", FactionKind.REALM, aggression=50)
        b = add_faction(world, "B", FactionKind.REALM, aggression=50)
        from tests.test_war import _army  # the war suite's bespoke host builder

        attacker = _army(world, a.id, 5, 5, size=3000)
        defender = _army(world, b.id, 5, 5, size=2500)
        events = _resolve_battle(
            world, grid, random.Random(42), attacker, defender, seat_site=None
        )
        battle = next(e for e in events if e.type == "battle")
        outcomes.append(
            (
                battle.payload["tier"],
                battle.payload["winner_casualties"],
                battle.payload["loser_casualties"],
                attacker.size,
                defender.size,
            )
        )
    assert outcomes[0] == outcomes[1]


def test_runs_differing_only_in_canonicity_diverge():
    def event_types(canonicity):
        world, _grid, _names = seed_world("diverge", canonicity=canonicity)
        run_years(world, 5)
        return [e.type for e in world.events]

    assert event_types(1.0) != event_types(0.0)
    assert event_types(1.0) == event_types(1.0)  # while staying deterministic


def test_role_seeking_is_canonicity_weighted():
    def heir_made(canonicity):
        world, _grid, _names = seed_world("roles", canonicity=canonicity)
        thengel = next(c for c in characters(world) if c.name == "Thengel")
        child = add_character(
            world,
            "Éofor",
            Race.MAN,
            birth_year=2940,
            role=Role.NONE,
            faction_id=thengel.faction_id,
            parent_ids=[thengel.id],
        )
        for year in range(30):  # thirty annual rolls off the derived stream
            world.tick = year * TICKS_PER_YEAR
            sauron_rise(world, world.rng)
        return child.role == Role.HEIR.value

    assert heir_made(1.0) is True
    assert heir_made(0.0) is False


# =========================================================================
# Inspectability & persistence
# =========================================================================

def test_strength_and_flags_survive_a_save_load_round_trip():
    world, _grid, _names = seed_world("persist")
    run_years(world, 2)
    world.flags[RING_LYING_LOST_FLAG] = True
    reloaded = loads(dumps(world))
    assert reloaded.flags == world.flags
    assert dark_realm(reloaded).sauron_strength == _mordor(world).sauron_strength
    assert len(nazgul(reloaded)) == 9


def test_a_hunt_round_trips_as_its_own_entity():
    world, _grid, _names = seed_world("hunttrip")
    mordor = _mordor(world)
    mordor.sauron_strength = 100
    the_ring(world).pull = 90
    run_tick(world)
    (hunt,) = hunts(world, alive_only=True)
    reloaded = loads(dumps(world))
    again = reloaded.entities[hunt.id]
    assert isinstance(again, Hunt)
    assert again.wraith_ids == hunt.wraith_ids


def test_a_v3_save_without_flags_migrates_cleanly():
    world = World.new_run("v3")
    data = json.loads(dumps(world))
    del data["state"]["flags"]
    data["provenance"]["schema_version"] = 3
    reloaded = loads(json.dumps(data))
    assert reloaded.flags == {}
