"""The ring-seeking seeker — the tracer bullet (ADR-0015, issue #54).

A Ring left unborne at an empty place draws a generated **seeker** from a plausible
free realm who *journeys* to its tile, takes it up (a ``found`` transfer), and
carries it home to its own seat as an ordinary bearer. These tests exercise the
seam directly and check the playtest harness is no longer stranded at
~100 % ``lying_lost``.
"""

import random

from arda_sim.characters import Role, characters
from arda_sim.factions import seed_world
from arda_sim.journeys import RING_SEEKING, character_journeys, journeys
from arda_sim.playtest import aggregate, playtest_batch
from arda_sim.ring import RingTransfer, the_ring, transfer_ring


def _empty_site(world, grid):
    """A real site with no living character standing on it (most seats are empty)."""
    occupied = {c.location_id for c in characters(world, alive_only=True)}
    for site in sorted(grid.sites, key=lambda s: s.id):
        if site.id not in occupied:
            return site
    raise AssertionError("no empty site on the grid")


def test_seeker_journeys_to_a_stranded_ring_and_bears_it():
    world, grid, _ = seed_world("fellowship")
    ring = the_ring(world)
    seed_ids = set(world.entities)  # everyone present at seed

    lost = _empty_site(world, grid)
    transfer_ring(world, ring, to_location=lost.id, mode=RingTransfer.LOSS)
    ring.lost_ticks = 130  # already reckoned lying-lost
    assert not ring.borne

    rng = random.Random(0)
    for _ in range(3000):
        character_journeys(world, rng)
        if ring.borne:
            break

    assert ring.borne, "a seeker never took up the stranded Ring"
    bearer = world.entities[ring.bearer_id]
    assert bearer.id not in seed_ids, "the new bearer should be a freshly generated seeker"
    assert bearer.alive
    assert bearer.role == Role.RING_BEARER.value
    assert ring.lost_ticks == 0, "taking it up must reset the lying-lost clock"
    # having taken it up, the Ring is set on an errand to carry it to the seeker's
    # own seat — off the empty tile it was rescued from, into a populated realm.
    assert ring.on_errand
    assert ring.goal_site_id != lost.id


def test_only_one_seeker_takes_the_road_at_a_time():
    world, grid, _ = seed_world("fellowship")
    ring = the_ring(world)
    lost = _empty_site(world, grid)
    transfer_ring(world, ring, to_location=lost.id, mode=RingTransfer.LOSS)

    rng = random.Random(0)
    for _ in range(40):
        character_journeys(world, rng)
        if ring.borne:
            break
    seeking = [j for j in journeys(world, alive_only=True) if j.motive == RING_SEEKING]
    assert len(seeking) <= 1, "the bounded race spawns at most one seeker for the tracer"


def test_seek_draws_nothing_from_the_shared_stream():
    # Even with a stranded Ring the phase must not perturb the shared war/diplomacy
    # stream — the seeker draws only from its isolated per-tick RNG (ADR-0008).
    world, grid, _ = seed_world("fellowship")
    ring = the_ring(world)
    lost = _empty_site(world, grid)
    transfer_ring(world, ring, to_location=lost.id, mode=RingTransfer.LOSS)

    rng = random.Random(1234)
    before = rng.getstate()
    character_journeys(world, rng)  # spawns a seeker
    assert rng.getstate() == before


def test_harness_no_longer_stranded_at_lying_lost():
    """The regression seam (issue #54/#62): before the tracer every run ended
    ``lying_lost`` (the Ring marooned on an empty tile). Re-bearing it physically
    clears the lying-lost clock and lets the borne rolls run again, so *destroyed*
    / *sauron_reclaims* become reachable. ``seed-001`` is a pinned seed whose
    re-borne Ring is run down by the hunt and reclaimed — proof a terminal is
    reachable now; the rest end ``unresolved`` (the Ring alive in play, no terminal
    within horizon), never ``lying_lost``.
    """
    seeds = ["seed-001", "tracer-000", "base-000", "base-002"]
    agg = aggregate(playtest_batch(seeds, 60))
    reached = agg.ring_outcomes.get("destroyed", 0) + agg.ring_outcomes.get("sauron_reclaims", 0)
    assert agg.ring_outcomes.get("lying_lost", 0) == 0, (
        f"the Ring is stranded again: {agg.ring_outcomes}"
    )
    assert reached >= 1, f"no terminal reached across the batch: {agg.ring_outcomes}"
