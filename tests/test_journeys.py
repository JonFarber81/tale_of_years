"""Character journeys — the general character-mover (ADR-0015, issue #52).

The phase is a prefactor: no motive wires a journey yet, so it must be inert
(seeded runs byte-identical, no shared-RNG draws). These tests exercise the seam
(:func:`begin_journey`) and the phase directly at the headless seam.
"""

import random

from arda_sim.armies import _ablest
from arda_sim.characters import Role, characters
from arda_sim.driver import run
from arda_sim.entities import EntityStatus
from arda_sim.factions import seed_world
from arda_sim.journeys import (
    CHARACTER_ARRIVED_EVENT,
    Journey,
    begin_journey,
    character_journeys,
    journeys,
)
from arda_sim.persistence import dumps, loads


def _two_reachable_sites(grid):
    """A (start, dest) pair of real site ids with a plottable path between them."""
    from arda_sim.armies import find_path

    sites = sorted(grid.sites, key=lambda s: s.id)
    for start in sites:
        for dest in sites:
            if dest.id == start.id:
                continue
            if find_path(grid, (start.col, start.row), (dest.col, dest.row)):
                return start, dest
    raise AssertionError("no reachable pair of sites on the grid")


def test_character_advances_along_path_to_destination():
    world, grid, _ = seed_world("fellowship")
    start, dest = _two_reachable_sites(grid)

    char = characters(world)[0]
    char.location_id = start.id
    char.abroad = False

    journey = begin_journey(world, char, dest.id)
    assert journey is not None
    assert char.abroad is True
    assert (journey.col, journey.row) == (start.col, start.row)

    positions = [(journey.col, journey.row)]
    rng = random.Random(0)
    for _ in range(400):
        character_journeys(world, rng)
        positions.append((journey.col, journey.row))
        if char.location_id == dest.id:
            break

    # It travelled a real tile path (position changed) and arrived.
    assert len(set(positions)) > 1
    assert char.location_id == dest.id
    assert char.abroad is False
    assert journey.status == EntityStatus.DEAD.value
    assert not journeys(world, alive_only=True)


def test_arrival_emits_character_arrived_event():
    world, grid, _ = seed_world("fellowship")
    start, dest = _two_reachable_sites(grid)
    char = characters(world)[0]
    char.location_id = start.id
    begin_journey(world, char, dest.id)

    rng = random.Random(0)
    arrival_events = []
    for _ in range(400):
        arrival_events.extend(character_journeys(world, rng))
        if char.location_id == dest.id:
            break
    assert any(e.type == CHARACTER_ARRIVED_EVENT for e in arrival_events)


def test_begin_journey_rejects_degenerate_targets():
    world, grid, _ = seed_world("fellowship")
    start, _dest = _two_reachable_sites(grid)
    char = characters(world)[0]
    char.location_id = start.id

    # Already there.
    assert begin_journey(world, char, start.id) is None
    assert char.abroad is False


def test_abroad_character_skipped_by_leader_ladder():
    world, grid, _ = seed_world("fellowship")
    # Pick a faction with a candidate the ladder would otherwise draft.
    general = next(c for c in characters(world, alive_only=True) if c.role == Role.GENERAL.value)
    faction_ids = {general.faction_id}
    roles = (Role.GENERAL.value,)

    general.abroad = False
    assert _ablest(world, faction_ids, set(), roles) is not None

    general.abroad = True
    picked = _ablest(world, faction_ids, set(), roles)
    assert picked is None or picked.id != general.id


def test_phase_is_inert_no_journeys_no_events_no_shared_draws():
    world, _grid, _ = seed_world("fellowship")
    rng = random.Random(1234)
    state_before = rng.getstate()
    events = character_journeys(world, rng)
    assert events == []
    assert rng.getstate() == state_before  # drew nothing from the shared stream


def test_seeded_run_byte_identical():
    # The phase is inert, so a seeded run must equal itself byte-for-byte.
    assert dumps(run("fellowship", 30)) == dumps(run("fellowship", 30))


def test_journey_round_trips_through_persistence():
    world, grid, _ = seed_world("fellowship")
    start, dest = _two_reachable_sites(grid)
    char = characters(world)[0]
    char.location_id = start.id
    journey = begin_journey(world, char, dest.id)
    assert journey is not None

    restored = loads(dumps(world))
    rj = restored.entities[journey.id]
    assert isinstance(rj, Journey)
    assert rj.char_id == char.id
    assert rj.dest_site_id == dest.id
    assert rj.path == journey.path
    assert (rj.col, rj.row) == (journey.col, journey.row)
    assert restored.entities[char.id].abroad is True
