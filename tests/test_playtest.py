"""Playtest harness: the end-of-run chronicle fold and the batch comparator.

Both are read-only folds over a finished run (like :mod:`metrics`) — they read a
world's events and end state, never a tick — so the tests exercise them on a
real seeded run and on hand-built stubs.
"""

from arda_sim.entities import Event
from arda_sim.factions import seed_world
from arda_sim.pipeline import run_years
from arda_sim.playtest import (
    RunChronicle,
    aggregate,
    play_one,
    playtest_batch,
    run_chronicle,
)
from arda_sim.ring import RING_DESTROYED_FLAG, SAURON_RECLAIMED_FLAG


def test_chronicle_folds_a_real_seeded_run():
    world, grid, _ = seed_world("chronicle-run")
    run_years(world, 45)
    ch = run_chronicle(world, grid, 45, seed="chronicle-run")

    assert ch.seed == "chronicle-run"
    assert ch.span_years == 45
    # The war gauge is carried whole, so a chronicle is a superset of the summary.
    assert ch.war.musters > 0
    # The standing partitions the land-holding factions; providers are excluded.
    assert ch.survivors  # someone is left holding ground
    assert "Gondor" in ch.survivors or "Gondor" in ch.extinguished
    # It renders without raising and names its sections.
    text = ch.as_text()
    assert "The Fate of the Ring" in text
    assert "Standing at the End" in text


def test_ring_outcome_reads_flag_and_dates_it_from_the_stream():
    world, grid, _ = seed_world("ring-outcome")
    world.flags[RING_DESTROYED_FLAG] = True
    world.events.append(
        Event(id=1, year=3019, type="ring_destroyed", subject_ids=[], payload={"bearer_id": 1})
    )
    ch = run_chronicle(world, grid, 60)
    assert ch.ring_outcome == "destroyed"
    assert ch.ring_outcome_year == 3019


def test_transient_claim_is_not_the_reclaim_terminal():
    world, grid, _ = seed_world("transient-claim")
    world.flags[SAURON_RECLAIMED_FLAG] = True
    # A mortal's transient claim (terminal=False) must not be dated as the terminal.
    world.events.append(
        Event(id=1, year=2990, type="ring_claimed", subject_ids=[], payload={"terminal": False})
    )
    world.events.append(
        Event(id=2, year=3005, type="ring_claimed", subject_ids=[], payload={"terminal": True})
    )
    ch = run_chronicle(world, grid, 60)
    assert ch.ring_outcome == "sauron_reclaims"
    assert ch.ring_outcome_year == 3005  # the terminal claim, not the flare


def test_unresolved_ring_has_no_outcome_year():
    world, grid, _ = seed_world("unresolved")
    ch = run_chronicle(world, grid, 5)
    assert ch.ring_outcome == "unresolved"
    assert ch.ring_outcome_year is None


def test_as_facts_is_flat_and_jsonable():
    ch = play_one("facts-run", 30)
    facts = ch.as_facts()
    assert facts["seed"] == "facts-run"
    assert set(facts) >= {"ring_outcome", "conquests", "decisive_battles", "survivors"}
    assert isinstance(facts["survivors"], list)


def _stub(seed, outcome, survivors, conquests=0, decisive=0):
    from arda_sim.metrics import WarSummary

    war = WarSummary(
        span_years=60, musters=0, battles=0, decisive_battles=decisive,
        conquests=conquests, evasions=0, hosts_destroyed=0,
        median_host_size=0, pct_led=0,
    )
    return RunChronicle(
        seed=seed, span_years=60, ring_outcome=outcome, ring_outcome_year=None,
        survivors=tuple(survivors), extinguished=(), war=war,
    )


def test_aggregate_counts_outcomes_and_survival_rate():
    chronicles = [
        _stub("a", "destroyed", ["Gondor", "Rohan"], conquests=2, decisive=1),
        _stub("b", "sauron_reclaims", ["Mordor"], conquests=6, decisive=3),
        _stub("c", "destroyed", ["Gondor"], conquests=4, decisive=2),
        _stub("d", "lying_lost", ["Gondor", "Rohan"], conquests=0, decisive=0),
    ]
    agg = aggregate(chronicles)
    assert agg.runs == 4
    assert agg.ring_outcomes == {"destroyed": 2, "sauron_reclaims": 1, "lying_lost": 1}
    assert agg.median_conquests == 3  # (2+4)//2 of sorted 0,2,4,6
    assert agg.survival_rate["Gondor"] == 75  # 3 of 4 runs
    assert agg.survival_rate["Mordor"] == 25


def test_batch_runs_every_seed_to_the_same_span():
    chronicles = playtest_batch(["s1", "s2"], 20)
    assert [c.seed for c in chronicles] == ["s1", "s2"]
    assert all(c.span_years == 20 for c in chronicles)
