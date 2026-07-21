"""Playback seam: forward-only sim, snapshot-per-tick cache, instant restore,
fast-forward past the frontier. Ticks are months (12/year). All headless — no Qt.
"""

import pytest

from arda_sim import START_YEAR, TICKS_PER_YEAR
from arda_sim.playback import Playback
from arda_sim.snapshot import Snapshot
from arda_sim.world import World, year_of_tick


def _playback(seed="fellowship"):
    return Playback(World.new_run(seed))


def test_frontier_starts_before_first_tick():
    pb = _playback()
    assert pb.first_tick == 0
    assert pb.frontier == -1
    assert not pb.has_snapshot(0)


def test_advance_caches_snapshot_and_returns_events():
    pb = _playback()
    snapshot, events = pb.advance()
    assert isinstance(snapshot, Snapshot)
    assert snapshot.tick == 0 and snapshot.year == START_YEAR
    assert pb.frontier == 0
    assert len(events) == 1  # the placeholder heartbeat
    assert pb.has_snapshot(0)


def test_restore_returns_the_same_cached_snapshot_object():
    pb = _playback()
    snapshot, _ = pb.advance()
    assert pb.restore(0) is snapshot  # instant, no replay


def test_restore_outside_frontier_raises():
    pb = _playback()
    pb.advance()
    with pytest.raises(KeyError):
        pb.restore(5)


def test_fast_forward_simulates_missing_ticks_only():
    pb = _playback()
    pb.advance()  # frontier now tick 0
    advanced = pb.fast_forward_to(3)
    assert len(advanced) == 3  # only the 3 missing ticks
    assert pb.frontier == 3
    assert [snap.tick for snap, _ in advanced] == [1, 2, 3]


def test_fast_forward_crosses_year_boundaries():
    pb = _playback()
    # advance a year and a month; the snapshot at tick TICKS_PER_YEAR is the new year
    advanced = pb.fast_forward_to(TICKS_PER_YEAR + 1)
    assert pb.frontier == TICKS_PER_YEAR + 1
    year_at_boundary = next(s for s, _ in advanced if s.tick == TICKS_PER_YEAR)
    assert year_at_boundary.year == START_YEAR + 1 == year_of_tick(TICKS_PER_YEAR)


def test_fast_forward_within_frontier_is_noop():
    pb = _playback()
    pb.fast_forward_to(5)
    assert pb.fast_forward_to(2) == []
    assert pb.frontier == 5


def test_scrub_then_continue_matches_forward_frontier():
    # Restoring an old snapshot must not disturb the live sim: after scrubbing
    # back, advancing continues from the true frontier.
    pb = _playback()
    pb.fast_forward_to(10)
    pb.restore(2)  # scrub back
    snapshot, _ = pb.advance()  # continue
    assert snapshot.tick == 11
    assert pb.frontier == 11
