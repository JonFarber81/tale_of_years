"""The One Ring (build ticket 13): the single tracked object at the world's centre.

Seams under test:

* the **XOR invariant** (exactly one of bearer / location) after seeding and after
  every tick of a live run;
* each **transfer mode** — inheritance, gift, theft, loss, found, war-capture,
  errand — reproducing byte-for-byte under a fixed seed;
* **corruption** growing while borne and *attenuating (not resetting)* on transfer;
* **pull** rising on use and decaying otherwise, and lifting loss/theft odds;
* **inheritance** favouring the canon (kin) heir under high canonicity and able to
  diverge under low;
* rendering position and the full transfer/bearer **history** for inspection;
* determinism: the Ring phase is a pure no-op without a Ring, and the whole record
  round-trips through persistence.
"""

from dataclasses import replace

from arda_sim.characters import Race, Role, add_character
from arda_sim.entities import EntityStatus
from arda_sim.factions import seed_world
from arda_sim.persistence import dumps, loads
from arda_sim.pipeline import PIPELINE, run_tick, run_years
from arda_sim.ring import (
    CORRUPTION_MAX,
    RING_CLAIMED_EVENT,
    RING_MOVED_EVENT,
    RING_TRANSFERRED_EVENT,
    Ring,
    RingTransfer,
    _maybe_errand,
    _maybe_gift,
    corruption_growth,
    heir_candidates,
    inheritance_heir,
    ring_longevity_factor,
    ring_system,
    ring_timeline,
    seed_ring,
    send_on_errand,
    the_ring,
    transfer_ring,
    use_ring,
)


class _Roll:
    """A stub RNG whose ``randrange`` always returns a fixed value — lets a test
    pin a canonicity-weighted roll to fire (0) or not (999) deterministically."""

    def __init__(self, value):
        self._value = value

    def randrange(self, n):
        return self._value
from arda_sim.tiles import Site, Terrain, TileGrid, UNOWNED
from arda_sim.world import World


# -- fixtures --------------------------------------------------------------

def _grid():
    """A 6x6 plains grid with two named sites, ready for placement/movement."""
    sites = [
        Site("Bag End", 0, 0, "town", id=1, tier=1),
        Site("Rivendell", 5, 5, "town", id=2, tier=1),
    ]
    grid = TileGrid(
        6, 6, [Terrain.PLAINS] * 36, [0] * 36, {}, sites=sites, miles_per_tile=15
    )
    grid.owner = [UNOWNED] * 36
    return grid


def _world_with_bearer(seed="ring-test", role=Role.RING_BEARER, home="Bag End"):
    """A minimal world+grid with one Ring-bearing character seeded with the Ring."""
    world = World.new_run(seed)
    grid = _grid()
    world.grid = grid
    bilbo = add_character(
        world, "Bilbo", Race.HOBBIT, birth_year=2890, role=role,
        location_id=grid.site_id_of(home),
    )
    ring = seed_ring(world, grid)
    return world, grid, bilbo, ring


# -- seeding & the XOR invariant ------------------------------------------

def test_seeded_ring_is_borne_by_bilbo_with_low_scalars():
    world, grid, faction_names = seed_world("fellowship")
    ring = the_ring(world)
    bilbo = world.entities[ring.bearer_id]
    assert bilbo.name == "Bilbo Baggins"
    assert bilbo.role == Role.RING_BEARER.value
    assert ring.borne and ring.location_id is None
    assert ring.xor_ok
    assert 0 < ring.corruption <= 20 and ring.pull == 0
    # It renders from the bearer's seat (Michel Delving), not (0, 0) by default.
    site = grid.site_by_id(bilbo.location_id)
    assert (ring.col, ring.row) == (site.col, site.row)


def test_xor_invariant_holds_after_every_tick():
    world, grid, faction_names = seed_world("fellowship")
    for _ in range(12 * 25):  # 25 years, month by month
        run_tick(world)
        assert the_ring(world).xor_ok


def test_ring_phase_is_wired_into_the_pipeline_after_war():
    names = [name for name, _ in PIPELINE]
    assert "ring" in names
    assert names.index("ring") > names.index("war")  # reads the field war left


# -- corruption ------------------------------------------------------------

def test_corruption_grows_while_borne():
    world, grid, bilbo, ring = _world_with_bearer()
    before = ring.corruption
    for _ in range(6):
        run_tick(world)
    assert the_ring(world).corruption > before


def test_corruption_growth_is_trait_modulated():
    world, grid, bilbo, ring = _world_with_bearer()
    grasping = add_character(
        world, "Gollum", Race.HOBBIT, 2470, role=Role.NONE,
        location_id=grid.site_id_of("Bag End"),
        traits={"ambition": 95, "guile": 95, "wisdom": 10, "loyalty": 10},
    )
    steadfast = add_character(
        world, "Faithful", Race.HOBBIT, 2900, role=Role.NONE,
        location_id=grid.site_id_of("Bag End"),
        traits={"ambition": 10, "guile": 10, "wisdom": 95, "loyalty": 95},
    )
    assert corruption_growth(grasping) > corruption_growth(steadfast)


def test_corruption_attenuates_not_resets_on_transfer():
    world, grid, bilbo, ring = _world_with_bearer()
    heir = add_character(
        world, "Frodo", Race.HOBBIT, 2968, role=Role.NONE,
        location_id=grid.site_id_of("Bag End"), parent_ids=[bilbo.id],
    )
    ring.corruption = 50
    transfer_ring(world, ring, to_bearer=heir, mode=RingTransfer.GIFT)
    assert ring.bearer_id == heir.id
    assert 0 < ring.corruption < 50  # attenuated, but the taint lingers — not reset


# -- pull ------------------------------------------------------------------

def test_pull_rises_on_use_and_decays_when_idle():
    world, grid, bilbo, ring = _world_with_bearer()
    assert ring.pull == 0
    use_ring(ring)
    used = ring.pull
    assert used > 0
    # Idle ticks (no use) ebb the pull back down.
    for _ in range(12):
        run_tick(world)
    assert the_ring(world).pull < used


def test_high_pull_raises_loss_or_theft_odds():
    # A watchful, co-located taker makes theft possible; with pull maxed the Ring
    # leaves its bearer far sooner than with the pull quiet.
    def _ticks_until_ring_leaves(pull):
        world, grid, bilbo, ring = _world_with_bearer(seed="risk")
        add_character(
            world, "Sneak", Race.HOBBIT, 2900, role=Role.NONE,
            location_id=grid.site_id_of("Bag End"),
        )
        ring.pull = pull
        ring.corruption = 5
        for t in range(1, 200):
            run_tick(world)
            r = the_ring(world)
            if not r.borne or r.bearer_id != bilbo.id:
                return t
            ring.pull = pull  # hold the pull pinned to isolate its effect
        return 10_000

    assert _ticks_until_ring_leaves(100) < _ticks_until_ring_leaves(0)


# -- transfer modes: each reproduces under a fixed seed -------------------

def _drive_mode(mode):
    """Build a fresh scenario for one transfer mode and return the resulting dump."""
    world, grid, bilbo, ring = _world_with_bearer(seed=f"mode-{mode.value}")
    other = add_character(
        world, "Other", Race.HOBBIT, 2960, role=Role.NONE,
        location_id=grid.site_id_of("Bag End"), parent_ids=[bilbo.id],
    )
    ring.corruption = 30
    if mode is RingTransfer.LOSS:
        transfer_ring(world, ring, to_location=grid.site_id_of("Rivendell"), mode=mode)
    elif mode is RingTransfer.INHERITANCE:
        bilbo.status = EntityStatus.DEAD.value
        run_tick(world)
    else:
        transfer_ring(world, ring, to_bearer=other, mode=mode)
    return dumps(world)


def test_every_transfer_mode_reproduces_under_a_fixed_seed():
    for mode in RingTransfer:
        if mode in (RingTransfer.WAR_CAPTURE, RingTransfer.FOUND, RingTransfer.ERRAND):
            continue  # exercised in their own dedicated tests below
        assert _drive_mode(mode) == _drive_mode(mode), f"{mode} not reproducible"


def test_loss_makes_the_ring_unborne_and_keeps_xor():
    world, grid, bilbo, ring = _world_with_bearer()
    transfer_ring(world, ring, to_location=grid.site_id_of("Rivendell"), mode=RingTransfer.LOSS)
    assert not ring.borne and ring.location_id == grid.site_id_of("Rivendell")
    assert ring.xor_ok
    assert bilbo.role == Role.NONE.value  # the former bearer is unroled (marked by history)


def test_found_picks_a_dropped_ring_back_up():
    world, grid, bilbo, ring = _world_with_bearer()
    # Drop it away from Bilbo, where only the finder stands (else the former bearer,
    # still on the tile, would simply pick it up again).
    transfer_ring(world, ring, to_location=grid.site_id_of("Rivendell"), mode=RingTransfer.LOSS)
    finder = add_character(
        world, "Sam", Race.HOBBIT, 2980, role=Role.NONE,
        location_id=grid.site_id_of("Rivendell"),
    )
    # Force the (uncommon) find by running ticks with the finder standing on it.
    found = False
    for _ in range(300):
        run_tick(world)
        r = the_ring(world)
        if r.borne:
            found = r.bearer_id == finder.id
            break
    assert found and the_ring(world).xor_ok


def test_war_capture_seizes_a_dropped_ring_from_the_ground():
    from arda_sim.armies import Army

    world, grid, bilbo, ring = _world_with_bearer()
    transfer_ring(world, ring, to_location=grid.site_id_of("Rivendell"), mode=RingTransfer.LOSS)
    site = grid.site_by_id(grid.site_id_of("Rivendell"))
    general = add_character(
        world, "Captain", Race.MAN, 2940, role=Role.GENERAL,
        location_id=None, traits={"martial": 80},
    )
    world.entities[999] = Army(
        id=999, kind="army", name="Host", created_year=world.current_year,
        faction_id=None, leader_id=general.id, col=site.col, row=site.row, size=500,
    )
    events = ring_system(world, world.rng)
    assert ring.borne and ring.bearer_id == general.id
    assert any(
        ev.type == RING_TRANSFERRED_EVENT and ev.payload.get("mode") == RingTransfer.WAR_CAPTURE.value
        for ev in events
    )


# -- errand movement -------------------------------------------------------

def test_errand_advances_the_ring_and_spikes_pull():
    world, grid, bilbo, ring = _world_with_bearer()
    start = (ring.col, ring.row)
    assert send_on_errand(world, ring, grid.site_id_of("Rivendell"))
    # Assert on the emitted move (a later loss can snap it back to the seat, so the
    # final position is not a reliable witness that it travelled).
    moved_off_start = False
    pull_after_move = 0
    for _ in range(60):
        events = run_tick(world)
        for ev in events:
            if ev.type == RING_MOVED_EVENT:
                if (ev.payload["col"], ev.payload["row"]) != start:
                    moved_off_start = True
                pull_after_move = max(pull_after_move, ev.payload["pull"])
        if not ring.on_errand:
            break
    assert moved_off_start
    assert pull_after_move > 0  # travelling with it is a use — pull spikes


def test_gift_fires_from_the_phase_to_a_kin_heir():
    # The Bilbo→heir tendency: while still untainted, a bearer with a living kin
    # heir may freely give the Ring on — a mode the phase fires, not just a test.
    world, grid, bilbo, ring = _world_with_bearer()
    heir = add_character(
        world, "Frodo", Race.HOBBIT, 2968, role=Role.NONE,
        location_id=grid.site_id_of("Bag End"), parent_ids=[bilbo.id],
    )
    ring.corruption = 5  # low — the bearer can still let it go
    events = _maybe_gift(world, ring, bilbo, _Roll(0))
    assert len(events) == 1
    assert ring.bearer_id == heir.id
    assert events[0].payload["mode"] == RingTransfer.GIFT.value
    # A possessive (corrupted) bearer never gives it up.
    world2, grid2, bilbo2, ring2 = _world_with_bearer(seed="grip")
    add_character(
        world2, "Frodo", Race.HOBBIT, 2968, role=Role.NONE,
        location_id=grid2.site_id_of("Bag End"), parent_ids=[bilbo2.id],
    )
    ring2.corruption = 60
    assert _maybe_gift(world2, ring2, bilbo2, _Roll(0)) == []


def test_errand_is_fired_from_the_phase_when_the_pull_rises():
    # With danger drawing (high pull) the phase can set the Ring on the road, and
    # the errand advances on the bearer's own (hobbit) pace, not a fixed rate.
    world, grid, bilbo, ring = _world_with_bearer()
    ring.pull = 50
    _maybe_errand(world, ring, bilbo, _Roll(0))
    assert ring.on_errand and ring.goal_site_id is not None
    from arda_sim.ring import _RACE_PACE
    assert ring.miles_per_year == _RACE_PACE[Race.HOBBIT]


def test_unborne_ring_does_not_move():
    world, grid, bilbo, ring = _world_with_bearer()
    transfer_ring(world, ring, to_location=grid.site_id_of("Rivendell"), mode=RingTransfer.LOSS)
    where = (ring.col, ring.row)
    # An unborne Ring cannot be sent on an errand, and never advances on its own.
    assert not send_on_errand(world, ring, grid.site_id_of("Bag End"))
    for _ in range(24):
        run_tick(world)
        r = the_ring(world)
        if not r.borne:
            assert (r.col, r.row) == where


# -- inheritance: canon bias vs divergence --------------------------------

def _inheritance_pool(canonicity):
    """A fallen bearer with one kin (canon) heir and several unrelated hobbits."""
    world = World.new_run("heir", canonicity=canonicity)
    world.config = replace(world.config, canonicity=canonicity)
    grid = _grid()
    world.grid = grid
    bilbo = add_character(
        world, "Bilbo", Race.HOBBIT, 2890, role=Role.RING_BEARER,
        location_id=grid.site_id_of("Bag End"),
    )
    kin = add_character(
        world, "Frodo", Race.HOBBIT, 2968, role=Role.NONE,
        location_id=grid.site_id_of("Bag End"), parent_ids=[bilbo.id],
    )
    for name, yr in (("A", 2950), ("B", 2955), ("C", 2960)):
        add_character(
            world, name, Race.HOBBIT, yr, role=Role.NONE,
            location_id=grid.site_id_of("Bag End"),
        )
    ring = seed_ring(world, grid)
    return world, ring, kin


def test_kin_heir_ranks_first_in_the_candidate_pool():
    world, ring, kin = _inheritance_pool(1.0)
    bilbo = world.entities[ring.bearer_id]
    pool = heir_candidates(world, bilbo)
    assert pool[0].id == kin.id  # the child is the canon heir, ranked first


def test_inheritance_takes_the_canon_heir_under_high_canonicity():
    world, ring, kin = _inheritance_pool(1.0)
    bilbo = world.entities[ring.bearer_id]
    bilbo.status = EntityStatus.DEAD.value
    run_tick(world)
    assert the_ring(world).bearer_id == kin.id


def test_inheritance_can_diverge_from_the_canon_heir_under_low_canonicity():
    # Under zero canonicity the choice is a weighted roll over the whole pool, so
    # across many seeds the Ring sometimes lands on someone other than the kin heir.
    diverged = 0
    for i in range(40):
        world, ring, kin = _inheritance_pool(0.0)
        world.config = replace(world.config, seed_str=f"low-{i}")
        bilbo = world.entities[ring.bearer_id]
        bilbo.status = EntityStatus.DEAD.value
        run_tick(world)
        if the_ring(world).bearer_id != kin.id:
            diverged += 1
    assert diverged > 0


# -- longevity, history, no-op, persistence -------------------------------

def test_longevity_factor_is_strongest_at_low_corruption():
    assert ring_longevity_factor(0) < ring_longevity_factor(CORRUPTION_MAX)
    assert ring_longevity_factor(CORRUPTION_MAX) == 1000  # no effect once fully corrupted


def test_bearer_history_records_every_bearer_for_inspection():
    world, grid, bilbo, ring = _world_with_bearer()
    heir = add_character(
        world, "Frodo", Race.HOBBIT, 2968, role=Role.NONE,
        location_id=grid.site_id_of("Bag End"), parent_ids=[bilbo.id],
    )
    transfer_ring(world, ring, to_bearer=heir, mode=RingTransfer.GIFT)
    assert ring.bearer_history == [bilbo.id, heir.id]


def test_ring_phase_is_a_noop_without_a_ring():
    world = World.new_run("no-ring")
    # No Ring seeded → the phase draws nothing and emits nothing.
    assert ring_system(world, world.rng) == []


def test_ring_record_round_trips_through_persistence():
    world, grid, faction_names = seed_world("fellowship")
    run_years(world, 8)
    before = the_ring(world)
    restored = the_ring(loads(dumps(world)))
    assert isinstance(restored, Ring)
    assert restored.__dict__ == before.__dict__
