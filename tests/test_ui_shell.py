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
from arda_sim.ui.codex_pages import living_armies  # noqa: E402
from arda_sim.ring import the_ring  # noqa: E402
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


def test_marching_hosts_render_and_are_inspectable(qapp):
    # Playing the seeded app raises hosts that march across the map; the map
    # layer draws them and clicking a host's tile inspects it (ticket 10).
    window = build_window("campaign")  # roster + factions seeded
    try:
        for snap, evs in window._playback.fast_forward_to(12 * TICKS_PER_YEAR):
            window._on_frontier_changed(window._playback.frontier)
            window._on_tick_advanced(snap, evs)
        hosts = living_armies(window._latest_snapshot)
        assert hosts  # at least one host is afield
        # the map drew exactly one disc+sprite marker per living host; marching
        # hosts also add a direction-cue polygon (ticket 06), so count the
        # pixmap markers rather than every item in the army layer.
        from PySide6.QtWidgets import QGraphicsPixmapItem

        markers = [i for i in window._map._army_items if isinstance(i, QGraphicsPixmapItem)]
        assert len(markers) == len(hosts)
        host = hosts[0]
        text = window._pages.describe_tile(host.col, host.row)
        assert host.name in text and "Strength" in text and "Destination" in text
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


def test_field_and_siege_battles_fire_battle_markers(qapp):
    # A war tick raises crossed-swords markers on the map (ticket 07): a field
    # battle resolves to the winner army's tile (no location_id, payload names
    # the winner), a siege to its seat's tile (a real location_id).
    from arda_sim.armies import Army

    window = build_window("fellowship")
    try:
        site = window._grid.sites[0]
        winner = Army(
            id=4242, kind="army", created_year=START_YEAR, name="Victors",
            col=7, row=9, size=500,
        )
        snapshot = Snapshot(tick=0, year=START_YEAR, entities={winner.id: winner})

        field = _event(
            START_YEAR, type_="battle", importance=90, location_id=None,
            payload={"winner_army_id": winner.id, "loser_army_id": 9999},
        )
        siege = _event(
            START_YEAR, type_="siege", importance=90, location_id=site.id,
            payload={"besieger_faction_id": 1, "besieged_faction_id": 2},
        )
        # A battle whose winner army is gone from the snapshot must not crash —
        # it is simply skipped (destroyed hosts get pruned).
        orphan = _event(
            START_YEAR, type_="battle", importance=90, location_id=None,
            payload={"winner_army_id": 123456},
        )
        # The field battle alone: a marker, and NOT a salience pulse (it has no
        # location_id, so the pulse path skips it) — the two are distinct.
        window._on_tick_advanced(snapshot, [field])
        assert len(window._map._battle_markers) == 1
        assert window._map._pulses == []

        # The siege (real location_id) and the orphan (winner absent, skipped).
        window._on_tick_advanced(snapshot, [siege, orphan])
        assert len(window._map._battle_markers) == 2  # only the siege added one
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


def _dossier(event, names=None):
    from arda_sim.ui.event_dossier import render_event_dossier

    names = names or {}
    return render_event_dossier(
        event,
        faction_name=lambda fid: names.get(fid, f"faction {fid}"),
        site_name=lambda sid: {4: "Osgiliath"}.get(sid),
        region_name=lambda rid: {7: "Ithilien", 8: "Anórien"}.get(rid),
    )


def test_battle_dossier_reads_as_prose(qapp):
    event = Event(
        id=1, year=3018, type="battle", importance=70, location_id=4,
        subject_ids=[10, 20],
        text="Gondor met Mordor in battle",
        payload={
            "winner_faction_id": 10, "loser_faction_id": 20,
            "winner_army_id": 1, "loser_army_id": 2,
            "tier": "decisive", "winner_casualties": 400, "loser_casualties": 1800,
        },
    )
    text = _dossier(event, {10: "Gondor", 20: "Mordor"})
    assert "EVENT · WAR · NOTABLE" in text and "TA 3018" in text  # the banner
    assert "Gondor met Mordor in battle" in text
    assert "Gondor broke the host of Mordor before Osgiliath" in text
    assert "swept clear" in text  # the decisive tier reads differently
    assert "1,800" in text and "400" in text
    assert "winner_faction_id" not in text  # prose, not key/value dump


def test_siege_and_conquest_and_razing_dossiers(qapp):
    siege = Event(
        id=2, year=3019, type="siege", importance=45, location_id=4,
        payload={"besieger_faction_id": 20, "besieged_faction_id": 10,
                 "progress": 30, "required": 90},
    )
    text = _dossier(siege, {10: "Gondor", 20: "Mordor"})
    assert "Mordor pressed the siege of Osgiliath, seat of Gondor." in text
    assert "30 of the 90" in text

    conquest = Event(
        id=3, year=3019, type="conquest", importance=90, location_id=4,
        subject_ids=[10, 20],
        payload={"conqueror_faction_id": 20, "razed": True, "regions": [7, 8]},
    )
    text = _dossier(conquest, {10: "Gondor", 20: "Mordor"})
    assert "Osgiliath fell, and with it the realm of Gondor passed to Mordor." in text
    assert "Lands taken: Ithilien, Anórien." in text
    assert "did not stay to rule" in text  # the razed flag reads in prose

    razing = Event(
        id=4, year=3019, type="razing", importance=80, location_id=4,
        subject_ids=[10, 20],
        payload={"razer_faction_id": 20, "regions": [7]},
    )
    text = _dossier(razing, {20: "Mordor"})
    assert "Mordor laid Osgiliath and the lands about it waste." in text
    assert "Left in ruin, held by none: Ithilien." in text


def test_generic_dossier_fallback_resolves_faction_ids(qapp):
    treaty = Event(
        id=5, year=3010, type="treaty", importance=40,
        text="Gondor and Rohan swore friendship",
        payload={"initiator_faction_id": 10, "warmth": 25, "note": None},
    )
    text = _dossier(treaty, {10: "Gondor"})
    assert "EVENT · DIPLOMACY · NOTABLE" in text and "TA 3010" in text
    assert "initiator: Gondor" in text  # id resolved, suffix dropped
    assert "warmth: 25" in text
    assert "note" not in text  # None values are skipped

    bare = Event(id=6, year=3011, type="some_future_type", importance=10)
    text = _dossier(bare)
    # Empty payload stays sane: just the banner, no body paragraphs.
    assert "EVENT · OTHER · MINOR" in text and "TA 3011" in text
    assert "<p" not in text


def test_dossier_html_primitives(qapp):
    from arda_sim.ui.dossier_html import NEUTRAL_ACCENT, banner, stat_grid, section

    b = banner("Faction · realm", "Gondor", "#3f7fb8")
    assert 'bgcolor="#3f7fb8"' in b  # the identity accent bar
    assert "FACTION · REALM" in b and "Gondor" in b  # kind-tag caps, name as-is
    assert 'bgcolor="%s"' % NEUTRAL_ACCENT in banner("Tile", "(3, 4)")

    grid = stat_grid([("Strength", 4200), ("Treasury", None), ("Leader", "Denethor")])
    assert "Strength" in grid and "4200" in grid and "Denethor" in grid
    assert "Treasury" not in grid  # None values drop their row
    assert stat_grid([]) == ""

    assert "<b>DIPLOMACY</b>" in section("Diplomacy")


def test_sparkline_traces_a_series_shape(qapp):
    from arda_sim.ui.dossier_html import sparkline

    assert sparkline([]) == ""  # nothing to trace
    assert sparkline([7]) == "▁"  # a single point sits at the floor
    assert sparkline([4, 4, 4]) == "▁▁▁"  # a flat series is all floor, never blank
    rising = sparkline([0, 1, 2, 3, 4, 5, 6, 7])
    assert rising[0] == "▁" and rising[-1] == "█"  # min→floor, max→ceiling
    assert len(rising) == 8
    # A series longer than the width is sampled down, endpoints preserved.
    long = sparkline(list(range(100)), width=10)
    assert len(long) == 10 and long[0] == "▁" and long[-1] == "█"


def test_index_table_lays_out_headers_and_rows(qapp):
    from arda_sim.ui.dossier_html import index_table

    html = index_table(
        ["Host", '<a href="codex://index/armies/strength">Strength</a>'],
        [['<a href="codex://host/9">Great Host</a>', "5000"]],
    )
    assert "<table" in html and html.count("<tr>") == 2  # header row + one body row
    assert "Host" in html and "Strength" in html
    # Cells are pre-composed HTML: links pass through untouched, not escaped.
    assert 'href="codex://host/9"' in html and "Great Host" in html and "5000" in html


def test_dossier_html_escapes_hostile_names(qapp):
    from arda_sim.ui.dossier_html import banner, stat_grid

    b = banner("Site", "R&D <keep>")
    assert "R&amp;D &lt;keep&gt;" in b and "<keep>" not in b
    grid = stat_grid([("Owner", "Barad<dûr> & co")])
    assert "&lt;dûr&gt;" in grid and "&amp;" in grid


def test_tile_click_renders_html_dossier_into_the_browser(qapp):
    window = build_window("fellowship")
    try:
        site = window._grid.site_id_of("Minas Tirith")
        tile = next(s for s in window._grid.sites if s.id == site)
        window._on_tile_clicked(tile.col, tile.row)
        plain = window._codex.browser.toPlainText()
        assert "SITE" in plain and "Minas Tirith" in plain  # the site headlines
        html = window._pages.describe_tile(tile.col, tile.row)
        assert "<table" in html  # genuinely rich text, not escaped plain text
    finally:
        window.close()


def _seeded_faction(window, name):
    """Advance one tick and return the named Faction from the displayed snapshot."""
    snap, _ = window._playback.advance()
    window._on_tick_advanced(snap, [])
    return next(
        f
        for f in snap.entities.values()
        if f.__class__.__name__ == "Faction" and f.name == name
    )


def test_dynasty_page_renders_a_linked_badged_tree(qapp):
    # codex://dynasty/faction:<id> draws the ruling bloodline: every kin a
    # character link, the seated ruler and the presumptive heir badged. Back
    # returns to the faction Overview (ordinary history).
    from arda_sim.ui.codex import CodexAddress

    window = build_window("fellowship")
    try:
        gondor = _seeded_faction(window, "Gondor")
        window._codex.navigate(CodexAddress("faction", str(gondor.id)))
        window._codex.open_url(f"codex://dynasty/faction:{gondor.id}")
        html = window._codex.browser.toHtml()
        text = window._codex.browser.toPlainText()
        assert "DYNASTY" in text
        assert "[Ruler]" in text and "[Heir]" in text  # both badged
        ecthelion = window._latest_snapshot.entity(gondor.leader_id)
        assert f"codex://character/{ecthelion.id}" in html  # kin are links
        # Following a kin link is a dead link until #18 registers `character`.
        window._codex.open_url(f"codex://character/{ecthelion.id}")
        assert "No such page" in window._codex.browser.toPlainText()
        window._codex.go_back()  # back to the dynasty tree
        window._codex.go_back()  # back to the Overview tab
        assert "FACTION" in window._codex.browser.toPlainText()
    finally:
        window.close()


def test_malformed_dynasty_ident_is_a_dead_link(qapp):
    from arda_sim.ui.codex import CodexAddress

    window = build_window("fellowship")
    try:
        _seeded_faction(window, "Gondor")  # a snapshot exists
        for ident in ("faction:banana", "character:1", "999999", "faction:999999"):
            window._codex.navigate(CodexAddress("dynasty", ident))
            assert "No such page" in window._codex.browser.toPlainText()
    finally:
        window.close()


def test_annals_click_pushes_dossier_into_the_codex(qapp):
    window = build_window("fellowship")
    window._map.focus_tile = lambda col, row: None
    try:
        # Deliver the event through the tick handler (not straight into the
        # annals model) so the Codex's event lookup — which reads the accumulated
        # event stream (#39) — can resolve the click to its dossier.
        window._on_tick_advanced(
            Snapshot(tick=0, year=START_YEAR),
            [_event(START_YEAR, type_="treaty", importance=90)],  # unplaced
        )
        model = window._annals_model
        window._on_annals_event_clicked(model.index(1))  # the event row
        shown = window._codex.browser.toPlainText()
        assert "EVENT · DIPLOMACY · NOTABLE" in shown and f"TA {START_YEAR}" in shown
        window._on_annals_event_clicked(model.index(0))  # header: pane untouched
        assert "DIPLOMACY" in window._codex.browser.toPlainText()
    finally:
        window.close()


def test_map_clicks_enter_codex_history_and_back_returns(qapp):
    # Two tile clicks are two pages; Back re-renders the first (issue #36).
    from arda_sim.ui.codex import CodexAddress

    window = build_window("fellowship")
    try:
        mt = next(s for s in window._grid.sites if s.name == "Minas Tirith")
        barad = next(s for s in window._grid.sites if "Barad" in s.name)
        window._on_tile_clicked(mt.col, mt.row)
        window._on_tile_clicked(barad.col, barad.row)
        assert window._codex.history.current == CodexAddress(
            "tile", f"{barad.col},{barad.row}"
        )
        assert barad.name in window._codex.browser.toPlainText()
        window._codex.go_back()
        assert mt.name in window._codex.browser.toPlainText()
        window._codex.go_forward()
        assert barad.name in window._codex.browser.toPlainText()
    finally:
        window.close()


def test_omnibox_search_renders_a_results_page_of_links(qapp):
    # Enter in the omnibox navigates to a search page; its hits are codex://
    # links, and following one lands on the entity's page (still in history).
    window = build_window("fellowship")
    try:
        window._codex.omnibox.setText("minas")
        window._codex._on_search()
        text = window._codex.browser.toPlainText()
        assert "SEARCH" in text and "Minas Tirith" in text
        mt = window._grid.site_id_of("Minas Tirith")
        assert f'href="codex://site/{mt}"' in window._codex.browser.toHtml()
        window._codex.open_url(f"codex://site/{mt}")
        assert "SITE" in window._codex.browser.toPlainText()
        window._codex.go_back()  # the search page is an ordinary history entry
        assert "SEARCH" in window._codex.browser.toPlainText()
    finally:
        window.close()


def test_codex_anchor_clicks_navigate_pages(qapp):
    # The browser's anchorClicked path (a QUrl, not a string) navigates too —
    # the mechanism every future in-dossier link (#22) rides on.
    from PySide6.QtCore import QUrl

    window = build_window("fellowship")
    try:
        gondor = next(k for k, v in window._faction_names.items() if v == "Gondor")
        snap, _ = window._playback.advance()
        window._on_tick_advanced(snap, [])
        window._codex.open_url(QUrl(f"codex://faction/{gondor}"))
        assert "Gondor" in window._codex.browser.toPlainText()
        # Foreign schemes are ignored, not navigated.
        before = window._codex.history.current
        window._codex.open_url(QUrl("https://example.com/"))
        assert window._codex.history.current == before
    finally:
        window.close()


def _host(id_, name, size, faction_id=None, **kw):
    from arda_sim.armies import Army

    return Army(
        id=id_, kind="army", created_year=START_YEAR, name=name, size=size,
        faction_id=faction_id, **kw,
    )


def _faction_entity(id_, name, **kw):
    from arda_sim.factions import Faction

    return Faction(
        id=id_, kind="faction", created_year=START_YEAR, name=name, **kw
    )


def test_malformed_diplomacy_ident_is_a_dead_link(qapp):
    from arda_sim.ui.codex import CodexAddress

    window = build_window("fellowship")
    try:
        _seeded_faction(window, "Gondor")  # a snapshot exists
        for ident in ("faction:banana", "character:1", "999999", "faction:999999"):
            window._codex.navigate(CodexAddress("diplomacy", ident))
            assert "No such page" in window._codex.browser.toPlainText()
    finally:
        window.close()


def test_opening_a_host_page_centres_the_map_on_its_marker(qapp):
    # Activating a host page (an armies-index row click, a search hit, any
    # codex://host link) centres/highlights the map on that host (#17).
    window = build_window("fellowship")
    focused = []
    window._map.focus_tile = lambda col, row: focused.append((col, row))
    try:
        host = _host(300, "Wandering Host", 400, col=5, row=6)
        window._latest_snapshot = Snapshot(
            tick=0, year=START_YEAR, entities={300: host}
        )
        window._codex.open_url("codex://host/300")
        assert focused == [(5, 6)]
        # Non-host pages, and dead host links, move nothing.
        window._codex.open_url("codex://index/armies")
        window._codex.open_url("codex://host/999999")
        assert focused == [(5, 6)]
    finally:
        window.close()


def test_dead_codex_links_render_a_no_such_page_notice(qapp):
    from arda_sim.ui.codex import CodexAddress

    window = build_window("fellowship")
    try:
        for address in (
            CodexAddress("faction", "999999"),  # no such entity
            CodexAddress("tile", "banana"),  # malformed ident
            CodexAddress("mystery", "1"),  # unknown kind
        ):
            window._codex.navigate(address)
            assert "No such page" in window._codex.browser.toPlainText()
    finally:
        window.close()


def test_ring_page_is_addressable(qapp):
    from arda_sim.ui.codex import CodexAddress

    window = build_window("fellowship")  # seeded: the Ring is with Bilbo
    try:
        snap, _ = window._playback.advance()
        window._on_tick_advanced(snap, [])
        window._codex.navigate(CodexAddress("ring", "one"))
        text = window._codex.browser.toPlainText()
        assert "THE ONE RING" in text and "Possession" in text
    finally:
        window.close()


def test_ring_errand_path_overlay_draws_and_clears(qapp):
    window = build_window("fellowship")
    try:
        snap, evs = window._playback.advance()
        window._on_tick_advanced(snap, evs)
        ring = the_ring(window._latest_snapshot)
        assert window._map._ring_path_item is None  # no errand at seed → no trail

        ring.path = [[ring.col + 1, ring.row], [ring.col + 2, ring.row]]
        window._map.refresh_ring(ring)
        assert window._map._ring_path_item is not None  # the planned route is drawn

        ring.path = []  # errand ended
        window._map.refresh_ring(ring)
        assert window._map._ring_path_item is None  # the trail is cleared
    finally:
        window.close()


def test_bucket_chips_filter_the_feed(qapp):
    # The color legend doubles as a filter: unchecking a chip hides its
    # bucket's events; unmapped types stay visible whatever the chips say.
    window = build_window("fellowship")
    try:
        model = window._annals_model
        model.append_events(
            [
                _event(START_YEAR, type_="battle", importance=90),
                _event(START_YEAR, type_="treaty", importance=90),
                _event(START_YEAR, type_="succession", importance=90),
                _event(START_YEAR, type_="founding", importance=90),
                _event(START_YEAR, type_="some_future_type", importance=90),
            ]
        )
        assert model.visible_event_count() == 5  # all chips on by default
        chips = window._bucket_chips
        chips["war"].click()  # off
        assert model.visible_event_count() == 4
        shown = {
            model.event_at(r).type
            for r in range(model.rowCount())
            if not model.is_header(r)
        }
        assert "battle" not in shown and "some_future_type" in shown
        for bucket in ("diplomacy", "dynasty", "construction"):
            chips[bucket].click()
        assert model.visible_event_count() == 1  # only the unmapped type remains
        chips["war"].click()  # re-enabling restores the rows
        assert model.visible_event_count() == 2
    finally:
        window.close()


def test_bucket_chips_compose_with_the_importance_toggle(qapp):
    window = build_window("fellowship")
    try:
        model = window._annals_model
        model.append_events(
            [
                _event(START_YEAR, type_="battle", importance=90),
                _event(START_YEAR, type_="treaty", importance=5),
            ]
        )
        assert model.visible_event_count() == 1  # the dull treaty needs show-all
        window._show_all_action.trigger()
        assert model.visible_event_count() == 2
        window._bucket_chips["diplomacy"].click()  # chips AND with show-all
        assert model.visible_event_count() == 1
        window._show_all_action.trigger()  # important-only again, chip still off
        assert model.visible_event_count() == 1  # just the battle
        window._bucket_chips["diplomacy"].click()
        window._show_all_action.trigger()
        assert model.visible_event_count() == 2  # both controls released
    finally:
        window.close()


def test_zoom_out_stops_at_fit_the_map(qapp):
    # The zoom-out floor is dynamic: however hard you spin the wheel, the scale
    # never drops below "the whole map just fits the viewport".
    window = build_window("fellowship")
    try:
        window.resize(900, 700)
        window.show()  # realize the layout so the viewport has its true size
        qapp.processEvents()
        view = window._map
        for _ in range(60):  # far more notches than the old fixed floor allowed
            view._apply_zoom(1 / 1.15)
        floor = view._min_scale()
        assert view._scale == floor  # landed exactly on the clamp
        assert floor > 0.05  # a real cap, not the old postage-stamp scale
        # And zooming back in still works, up to the fixed close-up cap.
        for _ in range(200):
            view._apply_zoom(1.15)
        assert view._scale == 8.0
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
