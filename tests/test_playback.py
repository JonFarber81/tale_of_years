"""Playback seam: forward-only sim, snapshot-per-year cache, instant restore,
fast-forward past the frontier. All headless — no Qt.
"""

import pytest

from arda_sim import START_YEAR
from arda_sim.playback import Playback
from arda_sim.snapshot import Snapshot
from arda_sim.world import World


def _playback(seed="fellowship"):
    return Playback(World.new_run(seed))


def test_frontier_starts_before_first_year():
    pb = _playback()
    assert pb.first_year == START_YEAR
    assert pb.frontier == START_YEAR - 1
    assert not pb.has_snapshot(START_YEAR)


def test_advance_year_caches_snapshot_and_returns_events():
    pb = _playback()
    snapshot, events = pb.advance_year()
    assert isinstance(snapshot, Snapshot)
    assert snapshot.year == START_YEAR
    assert pb.frontier == START_YEAR
    assert len(events) == 1  # the placeholder heartbeat
    assert pb.has_snapshot(START_YEAR)


def test_restore_returns_the_same_cached_snapshot_object():
    pb = _playback()
    snapshot, _ = pb.advance_year()
    assert pb.restore(START_YEAR) is snapshot  # instant, no replay


def test_restore_outside_frontier_raises():
    pb = _playback()
    pb.advance_year()
    with pytest.raises(KeyError):
        pb.restore(START_YEAR + 5)


def test_fast_forward_simulates_missing_years_only():
    pb = _playback()
    pb.advance_year()  # frontier now START_YEAR
    advanced = pb.fast_forward_to(START_YEAR + 3)
    assert len(advanced) == 3  # only the 3 missing years
    assert pb.frontier == START_YEAR + 3
    assert [snap.year for snap, _ in advanced] == [
        START_YEAR + 1,
        START_YEAR + 2,
        START_YEAR + 3,
    ]


def test_fast_forward_within_frontier_is_noop():
    pb = _playback()
    pb.fast_forward_to(START_YEAR + 5)
    assert pb.fast_forward_to(START_YEAR + 2) == []
    assert pb.frontier == START_YEAR + 5


def test_scrub_then_continue_matches_forward_frontier():
    # Restoring an old snapshot must not disturb the live sim: after scrubbing
    # back, advancing continues from the true frontier.
    pb = _playback()
    pb.fast_forward_to(START_YEAR + 10)
    pb.restore(START_YEAR + 2)  # scrub back
    snapshot, _ = pb.advance_year()  # continue
    assert snapshot.year == START_YEAR + 11
    assert pb.frontier == START_YEAR + 11
