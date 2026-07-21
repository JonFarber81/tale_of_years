"""UI shell smoke tests — run offscreen (no display needed).

These exercise construction and the sim-thread -> UI wiring at a light level;
the map/annals rendering itself is verified manually (see the ticket). The
Qt-independent behaviour lives in test_playback.py / test_annals is below.
"""

import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


def _qt_platform_usable() -> bool:
    """Whether a Qt platform can actually be initialized here.

    Creating a ``QApplication`` with a broken/absent platform plugin calls
    ``qFatal`` → ``abort()``, which crashes the interpreter uncatchably. We can't
    guard that in-process, so probe in a throwaway subprocess: if it can't stand
    up a ``QApplication``, skip the UI tests rather than aborting the whole suite
    (headless CI, or a corrupted local Qt install).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from PySide6.QtWidgets import QApplication; QApplication([])"],
            env=os.environ,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


if not _qt_platform_usable():
    pytest.skip(
        "no usable Qt platform plugin (headless or broken PySide6 install)",
        allow_module_level=True,
    )

from PySide6.QtWidgets import QApplication  # noqa: E402

from arda_sim import START_YEAR, TICKS_PER_YEAR  # noqa: E402
from arda_sim.entities import Event  # noqa: E402
from arda_sim.snapshot import Snapshot  # noqa: E402
from arda_sim.ui.annals_model import AnnalsModel, render_event  # noqa: E402
from arda_sim.ui.app import build_window  # noqa: E402
from arda_sim.world import format_tick  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _event(year, type_="battle", importance=50, **kw):
    # Default to an above-threshold event so the important-only feed shows it;
    # pass importance=0 to model an unimportant (e.g. heartbeat) event.
    return Event(id=year, year=year, type=type_, importance=importance, **kw)


def test_annals_model_appends_and_renders(qapp):
    model = AnnalsModel()
    model.append_events([_event(START_YEAR), _event(START_YEAR + 1)])
    assert model.rowCount() == 2
    idx = model.index(0)
    assert f"TA {START_YEAR}" in model.data(idx)


def test_annals_defaults_to_important_only_until_show_all(qapp):
    model = AnnalsModel()
    model.append_events([_event(START_YEAR, importance=0), _event(START_YEAR, importance=90)])
    assert model.rowCount() == 1  # only the important one shows by default
    assert model.raw_count() == 2  # both were received
    model.show_all()
    assert model.rowCount() == 2
    model.important_only()
    assert model.rowCount() == 1


def test_annals_cap_hides_later_years(qapp):
    model = AnnalsModel()
    model.append_events([_event(y) for y in range(START_YEAR, START_YEAR + 10)])
    model.set_cap_year(START_YEAR + 3)
    assert model.rowCount() == 4  # years START_YEAR..START_YEAR+3
    model.set_cap_year(None)
    assert model.rowCount() == 10


def test_render_event_uses_prose_text_when_present():
    ev = Event(id=1, year=3019, type="battle", text="the host of Rohan came at last")
    assert render_event(ev) == "TA 3019: the host of Rohan came at last"


def test_window_builds_and_starts_at_seed_year(qapp):
    window = build_window("fellowship")
    try:
        assert window._year_label.text() == f"TA {START_YEAR}"
        assert not window._scrub.isEnabled()  # nothing simulated yet
    finally:
        window.close()


def test_tick_advance_updates_label_and_annals(qapp):
    window = build_window("fellowship", seed_characters=False)  # heartbeat-only
    try:
        # Drive the worker's logic directly (synchronously) rather than through
        # the thread, so the smoke test is deterministic and display-free.
        snapshot, events = window._playback.advance()
        window._on_frontier_changed(window._playback.frontier)
        window._on_tick_advanced(snapshot, events)
        assert window._year_label.text() == format_tick(0)  # "TA 2965, Afteryule"
        # The lone heartbeat is unimportant, so the important-only feed hides it,
        # but the model did receive it — "show all" reveals it.
        assert window._annals_model.raw_count() == 1
        assert window._annals_model.rowCount() == 0
        window._annals_model.show_all()
        assert window._annals_model.rowCount() == 1
        assert window._scrub.isEnabled()
        assert window._scrub.maximum() == 0  # frontier is tick 0
    finally:
        window.close()


def test_worker_thread_advances_via_real_signals(qapp):
    from PySide6.QtCore import QEventLoop, QTimer

    window = build_window("fellowship")
    ticks = []
    window._worker.tickAdvanced.connect(lambda snap, _evs: ticks.append(snap.tick))
    try:
        window.speedChanged.emit(60.0)  # fast
        window.playRequested.emit()
        loop = QEventLoop()
        QTimer.singleShot(600, loop.quit)  # let the worker thread run a while
        loop.exec()
    finally:
        window.close()
    assert len(ticks) >= 3  # the background thread genuinely advanced
    assert ticks == sorted(ticks)  # in order, no gaps backwards


def test_show_all_toolbar_toggle_switches_the_feed(qapp):
    window = build_window("fellowship")
    try:
        # Feed an unimportant and an important event straight into the model.
        window._annals_model.append_events(
            [_event(START_YEAR, importance=0), _event(START_YEAR, importance=90)]
        )
        assert window._annals_model.rowCount() == 1  # important-only by default
        window._show_all_action.trigger()  # -> show all
        assert window._annals_model.rowCount() == 2
        window._show_all_action.trigger()  # -> back to important-only
        assert window._annals_model.rowCount() == 1
    finally:
        window.close()


def test_seeded_window_streams_visible_prose_into_the_annals(qapp):
    # The shipped app seeds the roster, so playing it a while fills the
    # important-only feed with real chronicle prose (not just heartbeats).
    window = build_window("fellowship")  # roster seeded by default
    try:
        for snap, evs in window._playback.fast_forward_to(20 * TICKS_PER_YEAR):
            window._on_frontier_changed(window._playback.frontier)
            window._on_tick_advanced(snap, evs)
        assert window._annals_model.rowCount() > 0  # important events are shown
        first = window._annals_model.data(window._annals_model.index(0))
        assert first.startswith("TA ") and "[" not in first  # rendered prose
    finally:
        window.close()


def test_inspecting_a_realm_shows_its_diplomacy_block(qapp):
    # Clicking a realm's territory renders a diplomacy dossier (stances + bonds)
    # from the displayed-year snapshot — the ticket-09 inspection surface.
    window = build_window("fellowship")  # roster + factions seeded
    try:
        for snap, evs in window._playback.fast_forward_to(3 * TICKS_PER_YEAR):
            window._on_frontier_changed(window._playback.frontier)
            window._on_tick_advanced(snap, evs)
        site = window._grid.site_id_of("Minas Tirith")
        tile = next(s for s in window._grid.sites if s.id == site)
        text = window.describe_tile(tile.col, tile.row)
        assert "Diplomacy:" in text  # the block rendered
        # Gondor's seeded temper surfaces as a non-neutral stance toward Mordor.
        assert "Mordor" in text and "hostility" in text
    finally:
        window.close()


def test_marching_hosts_render_and_are_inspectable(qapp):
    # Playing the seeded app raises hosts that march across the map; the map
    # layer draws them and clicking a host's tile inspects it (ticket 10).
    window = build_window("campaign")  # roster + factions seeded
    try:
        for snap, evs in window._playback.fast_forward_to(12 * TICKS_PER_YEAR):
            window._on_frontier_changed(window._playback.frontier)
            window._on_tick_advanced(snap, evs)
        hosts = window._armies_in(window._latest_snapshot)
        assert hosts  # at least one host is afield
        # the map drew a marker per living host
        assert len(window._map._army_items) == len(hosts)
        host = hosts[0]
        text = window.describe_tile(host.col, host.row)
        assert host.name in text and "Strength:" in text and "Destination:" in text
    finally:
        window.close()


def test_above_threshold_located_events_fire_a_map_pulse(qapp):
    window = build_window("fellowship")
    pulsed = []
    window._map.pulse = lambda col, row: pulsed.append((col, row))
    try:
        site = window._grid.sites[0]
        events = [
            _event(START_YEAR, importance=90, location_id=site.id),  # pulses
            _event(START_YEAR, importance=0, location_id=site.id),   # too dull
            _event(START_YEAR, importance=90, location_id=None),     # no place
        ]
        window._on_tick_advanced(Snapshot(tick=0, year=START_YEAR), events)
        assert pulsed == [(site.col, site.row)]
    finally:
        window.close()


def test_scrub_restore_caps_annals_without_new_events(qapp):
    window = build_window("fellowship", seed_characters=False)  # heartbeat-only
    try:
        window._annals_model.show_all()  # heartbeats are unimportant; test the cap
        # Simulate five whole years — 5 * TICKS_PER_YEAR monthly heartbeats. The
        # annals are year-grained, so the cap works at year boundaries even though
        # the scrub itself is month-grained.
        for snap, evs in window._playback.fast_forward_to(5 * TICKS_PER_YEAR - 1):
            window._on_frontier_changed(window._playback.frontier)
            window._on_tick_advanced(snap, evs)
        assert window._annals_model.rowCount() == 5 * TICKS_PER_YEAR  # every month shown

        # Scrub back to the first month of the third year (START_YEAR + 2): restore
        # its snapshot, cap the annals at that year, emit no new events.
        third_year_tick = 2 * TICKS_PER_YEAR
        snapshot = window._playback.restore(third_year_tick)
        window._on_tick_advanced(snapshot, [])
        assert window._year_label.text() == format_tick(third_year_tick)
        # Capped at year START_YEAR+2 -> years +0, +1, +2 remain (3 years of months).
        assert window._annals_model.rowCount() == 3 * TICKS_PER_YEAR
    finally:
        window.close()
