"""Run-summary metrics (issue #13): the war-layer tuning gauge folds the event
stream into musters / battles / decisive battles / hosts destroyed / median host
size / share-led, raw and per-century, purely from events.
"""

from arda_sim.armies import ARMY_DISBANDED_EVENT, ARMY_MUSTERED_EVENT
from arda_sim.entities import Event
from arda_sim.factions import seed_world
from arda_sim.metrics import WarSummary, war_summary
from arda_sim.pipeline import run_years
from arda_sim.war import BATTLE_EVENT


def _ev(etype, **payload):
    return Event(id=0, year=2965, type=etype, subject_ids=[], payload=payload)


def test_summary_counts_musters_battles_and_reads_sizes_and_led():
    events = [
        _ev(ARMY_MUSTERED_EVENT, size=1000, led=True),
        _ev(ARMY_MUSTERED_EVENT, size=3000, led=False),
        _ev(ARMY_MUSTERED_EVENT, size=2000, led=True),
        _ev(BATTLE_EVENT, tier="decisive"),
        _ev(BATTLE_EVENT, tier="marginal"),
        _ev(ARMY_DISBANDED_EVENT, cause="destroyed_in_battle"),
    ]
    s = war_summary(events, span_years=100)
    assert s.musters == 3
    assert s.battles == 2
    assert s.decisive_battles == 1
    assert s.hosts_destroyed == 1
    assert s.median_host_size == 2000  # median of 1000, 2000, 3000
    assert s.pct_led == 66  # 2 of 3, floored


def test_median_is_integer_for_an_even_count():
    events = [_ev(ARMY_MUSTERED_EVENT, size=n, led=True) for n in (1000, 2000, 3000, 5000)]
    assert war_summary(events, 50).median_host_size == 2500  # (2000+3000)//2


def test_per_century_normalises_over_the_span():
    s = WarSummary(span_years=50, musters=10, battles=4, decisive_battles=2,
                   hosts_destroyed=3, median_host_size=1000, pct_led=100)
    assert s.per_century(s.decisive_battles) == 4.0  # 2 over 50y → 4/century
    assert s.per_century(s.musters) == 20.0


def test_empty_stream_is_all_zero_not_a_crash():
    s = war_summary([], span_years=0)
    assert s.musters == 0 and s.median_host_size == 0 and s.pct_led == 0
    assert s.per_century(5) == 0.0  # zero span never divides by zero


def test_summary_reads_a_real_seeded_run():
    world, _grid, _ = seed_world("metrics-run")
    events = run_years(world, 20)
    s = war_summary(events, span_years=20)
    assert s.musters > 0  # a canon-pressured run puts hosts in the field
    assert s.median_host_size > 0
    assert 0 <= s.pct_led <= 100
