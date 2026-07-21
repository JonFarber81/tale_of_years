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
from arda_sim.ui.annals_model import AnnalsModel, EventRole, render_event  # noqa: E402
from arda_sim.ui.annals_style import (  # noqa: E402
    AnnalsDelegate,
    BUCKET_OF_TYPE,
    BUCKETS,
    bucket_of,
)
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
    # Each year contributes a header row plus its event rows, newest-first.
    assert model.rowCount() == 4
    assert model.visible_event_count() == 2
    assert model.data(model.index(0)) == f"TA {START_YEAR + 1}"  # newest header
    assert model.is_header(0) and not model.is_header(1)
    assert model.data(model.index(2)) == f"TA {START_YEAR}"
    assert model.is_header(2) and not model.is_header(3)


def test_annals_year_headers_group_a_year_once(qapp):
    model = AnnalsModel()
    # Three events across two years, appended in two batches (the second batch
    # extends a year that already heads the feed — no duplicate divider).
    model.append_events([_event(START_YEAR), _event(START_YEAR + 1, importance=60)])
    model.append_events([Event(id=99, year=START_YEAR + 1, type="siege", importance=50)])
    headers = [
        model.data(model.index(r)) for r in range(model.rowCount()) if model.is_header(r)
    ]
    assert headers == [f"TA {START_YEAR + 1}", f"TA {START_YEAR}"]
    assert model.visible_event_count() == 3
    # Row 1 is the newest event of the newest year (the second-batch siege).
    assert model.event_at(1).type == "siege"
    # A cap/filter rebuild regroups identically.
    model.set_cap_year(START_YEAR + 1)
    model.set_cap_year(None)
    rebuilt = [
        model.data(model.index(r)) for r in range(model.rowCount()) if model.is_header(r)
    ]
    assert rebuilt == headers


def test_annals_event_role_exposes_structure(qapp):
    model = AnnalsModel()
    model.append_events([_event(START_YEAR, location_id=7)])
    assert model.data(model.index(0), EventRole) is None  # the header row
    event = model.data(model.index(1), EventRole)
    assert event is not None and event.location_id == 7  # placed
    assert model.event_at(1) is event


def test_bucket_mapping_covers_the_four_categories(qapp):
    assert bucket_of("battle") == "war"
    assert bucket_of("war_declared") == "war"  # declarations read as war
    assert bucket_of("army_mustered") == "war"
    assert bucket_of("treaty") == "diplomacy"
    assert bucket_of("marriage") == "diplomacy"  # the pact, not the cradle
    assert bucket_of("succession") == "dynasty"
    assert bucket_of("birth") == "dynasty"
    assert bucket_of("founding") == "construction"
    assert bucket_of("road_opened") == "construction"
    assert bucket_of("some_future_type") == "other"  # unmapped stays legible
    assert set(BUCKET_OF_TYPE.values()) == set(BUCKETS)


def test_annals_delegate_paints_all_row_kinds(qapp):
    # A paint smoke test: header, placed-important, and unplaced-dim rows all
    # render without touching a real window (offscreen pixmap).
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QStyleOptionViewItem

    model = AnnalsModel()
    model.show_all()
    model.append_events(
        [
            _event(START_YEAR, importance=90, location_id=3, text="a battle was joined"),
            _event(START_YEAR, importance=5, text="a quiet road was opened"),
        ]
    )
    delegate = AnnalsDelegate()
    pixmap = QPixmap(300, 24)
    for row in range(model.rowCount()):
        option = QStyleOptionViewItem()
        option.rect = pixmap.rect()
        painter = QPainter(pixmap)
        try:
            delegate.paint(painter, option, model.index(row))
        finally:
            painter.end()
        assert delegate.sizeHint(option, model.index(row)).height() > 0


def test_annals_defaults_to_important_only_until_show_all(qapp):
    model = AnnalsModel()
    model.append_events([_event(START_YEAR, importance=0), _event(START_YEAR, importance=90)])
    assert model.visible_event_count() == 1  # only the important one shows by default
    assert model.raw_count() == 2  # both were received
    model.show_all()
    assert model.visible_event_count() == 2
    model.important_only()
    assert model.visible_event_count() == 1


def test_annals_cap_hides_later_years(qapp):
    model = AnnalsModel()
    model.append_events([_event(y) for y in range(START_YEAR, START_YEAR + 10)])
    model.set_cap_year(START_YEAR + 3)
    assert model.visible_event_count() == 4  # years START_YEAR..START_YEAR+3
    model.set_cap_year(None)
    assert model.visible_event_count() == 10


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
        assert window._annals_model.visible_event_count() == 1
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
        assert window._annals_model.visible_event_count() == 1  # important-only default
        window._show_all_action.trigger()  # -> show all
        assert window._annals_model.visible_event_count() == 2
        window._show_all_action.trigger()  # -> back to important-only
        assert window._annals_model.visible_event_count() == 1
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
        assert window._annals_model.visible_event_count() > 0  # important events shown
        model = window._annals_model
        assert model.is_header(0)  # the newest year's divider heads the feed
        assert model.data(model.index(0)).startswith("TA ")
        first_event = model.data(model.index(1))  # first event row under it
        assert first_event and "[" not in first_event  # rendered prose, no fallback
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


def test_annals_click_pans_map_to_a_placed_event(qapp):
    # Clicking a placed event row centers the map on its site with a transient
    # pulse; header rows and unplaced events move nothing (annals-ui ticket 02).
    window = build_window("fellowship")
    focused = []
    window._map.focus_tile = lambda col, row: focused.append((col, row))
    try:
        site = window._grid.sites[0]
        window._annals_model.append_events(
            [
                _event(START_YEAR, importance=90, location_id=site.id),
                _event(START_YEAR + 1, importance=90),  # unplaced
            ]
        )
        model = window._annals_model
        rows_before = model.rowCount()
        window._on_annals_event_clicked(model.index(0))  # header: no-op
        window._on_annals_event_clicked(model.index(1))  # unplaced event: no-op
        assert focused == []
        window._on_annals_event_clicked(model.index(3))  # the placed event
        assert focused == [(site.col, site.row)]
        # The jump is space-only: the feed itself is untouched.
        assert model.rowCount() == rows_before
    finally:
        window.close()


def test_focus_tile_centers_the_view_and_pulse_expires(qapp):
    from PySide6.QtCore import QEventLoop, QTimer

    window = build_window("fellowship")
    try:
        view = window._map
        view.resize(160, 120)  # small viewport so centering must scroll
        site = window._grid.sites[0]
        view.focus_tile(site.col, site.row)
        center = view.mapToScene(view.viewport().rect().center())
        from arda_sim.ui.map_view import TILE

        assert abs(center.x() - (site.col * TILE + TILE / 2)) <= TILE
        assert abs(center.y() - (site.row * TILE + TILE / 2)) <= TILE
        # The highlight is transient: the pulse animation cleans itself up.
        assert len(view._pulses) == 1
        loop = QEventLoop()
        QTimer.singleShot(1200, loop.quit)  # outlives the ~900ms pulse
        loop.exec()
        assert view._pulses == []
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
        assert window._annals_model.visible_event_count() == 5 * TICKS_PER_YEAR

        # Scrub back to the first month of the third year (START_YEAR + 2): restore
        # its snapshot, cap the annals at that year, emit no new events.
        third_year_tick = 2 * TICKS_PER_YEAR
        snapshot = window._playback.restore(third_year_tick)
        window._on_tick_advanced(snapshot, [])
        assert window._year_label.text() == format_tick(third_year_tick)
        # Capped at year START_YEAR+2 -> years +0, +1, +2 remain (3 years of months).
        assert window._annals_model.visible_event_count() == 3 * TICKS_PER_YEAR
    finally:
        window.close()
