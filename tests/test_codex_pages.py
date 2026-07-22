"""The Codex page-render library (issue #39): ``CodexPages`` without a window.

Every ``describe_*`` dossier, ``_*_page`` wrapper, and ``_*_index`` roll is a
pure function of ``(snapshot, config)`` — so these tests build a ``CodexPages``
straight from a seeded run and assert on the rendered HTML, no ``QMainWindow``,
no sim thread, no event loop. Only PySide6's presence is required (the render
helpers construct ``QColor`` accents); the offscreen-Qt window guard lives in
test_ui_shell.py, which owns the shell/thread/playback tests.

These migrated whole from test_ui_shell.py when the renderers left the window:
same seeds, same "advance then assert on HTML" shape, minus the harness.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")  # codex_pages imports Qt for its colour accents

from arda_sim import START_YEAR, TICKS_PER_YEAR  # noqa: E402
from arda_sim.armies import Army  # noqa: E402
from arda_sim.characters import Character, new_seeded_run  # noqa: E402
from arda_sim.entities import Event  # noqa: E402
from arda_sim.factions import Faction, seed_factions  # noqa: E402
from arda_sim.playback import Playback  # noqa: E402
from arda_sim.ring import seed_ring, the_ring  # noqa: E402
from arda_sim.scenarios import load_scenario  # noqa: E402
from arda_sim.snapshot import Snapshot  # noqa: E402
from arda_sim.validate import check_grid  # noqa: E402
from arda_sim.world import World  # noqa: E402
from arda_sim.ui.codex import CodexAddress  # noqa: E402
from arda_sim.ui.codex_pages import (  # noqa: E402
    CodexPages,
    _RingTrendSample,
    _AMITY_COLOR,
    _FEALTY_COLOR,
    _WAR_COLOR,
)
from arda_sim.ui.dossier_html import DIM  # noqa: E402

# The shipped theatre, matching arda_sim.ui.app._SCENARIO — build_pages mirrors
# build_window's seeding, minus the Qt window.
_SCENARIO = "arda_ta2965"


def build_pages(seed="fellowship", *, seed_characters=True, canonicity=1.0):
    """A ``CodexPages`` and the ``Playback`` feeding it, for a fresh seeded run.

    The headless twin of ``arda_sim.ui.app.build_window``: same scenario grid,
    same canon roster/faction/Ring seeding, but no window — so the renderers can
    be exercised without standing up Qt widgets or a sim thread.
    """
    grid = load_scenario(_SCENARIO)
    check_grid(grid)
    if seed_characters:
        world = new_seeded_run(seed, canonicity=canonicity)
        faction_names = seed_factions(world, grid)
        seed_ring(world, grid)  # the One Ring, borne by Bilbo (ticket 13)
    else:
        world = World.new_run(seed, canonicity=canonicity)
        faction_names = {}
    world.grid = grid
    playback = Playback(world)
    return CodexPages(grid, faction_names), playback


def _feed(pages, snapshots):
    """Drive ``pages.update`` over a stream of ``(snapshot, events)`` like the
    window's tick handler does — accumulating the event log and the scrub-safe
    Ring-trend series (keyed off the tick), then refreshing the render context.
    Returns the last snapshot fed."""
    events = list(pages._events)
    trend = list(pages._ring_trend)
    trend_tick = trend[-1].tick if trend else -1
    last = pages._latest_snapshot
    for snap, evs in snapshots:
        if evs:
            events.extend(evs)
        if snap.tick > trend_tick:
            ring = the_ring(snap)
            if ring is not None:
                trend_tick = snap.tick
                trend.append(
                    _RingTrendSample(snap.tick, snap.year, ring.corruption, ring.pull)
                )
        pages.update(
            snapshot=snap,
            events=events,
            display_year=snap.year,
            ring_trend=trend,
        )
        last = snap
    return last


def _advance(pages, playback, n=1):
    """Advance ``n`` ticks, feeding each into ``pages``. Returns the last snapshot."""
    return _feed(pages, (playback.advance() for _ in range(n)))


def _advance_to(pages, playback, target_tick):
    """Fast-forward to ``target_tick``, feeding each tick. Returns the last snapshot."""
    return _feed(pages, playback.fast_forward_to(target_tick))


def _seeded_faction(pages, playback, name):
    """Advance one tick and return the named Faction from the displayed snapshot."""
    _advance(pages, playback, 1)
    return next(
        f
        for f in pages._latest_snapshot.entities.values()
        if isinstance(f, Faction) and f.name == name
    )


def _event(year, type_="battle", importance=50, **kw):
    # Default to an above-threshold event so the important-only feed shows it;
    # pass importance=0 to model an unimportant (e.g. heartbeat) event.
    return Event(id=year, year=year, type=type_, importance=importance, **kw)


def _host(id_, name, size, faction_id=None, **kw):
    return Army(
        id=id_, kind="army", created_year=START_YEAR, name=name, size=size,
        faction_id=faction_id, **kw,
    )


def _faction_entity(id_, name, **kw):
    return Faction(
        id=id_, kind="faction", created_year=START_YEAR, name=name, **kw
    )


# -- tile / site / host dossiers -----------------------------------------


def test_inspecting_a_realm_shows_its_diplomacy_block():
    # A realm's open ground headlines the faction with full depth (a diplomacy
    # dossier of stances + bonds) — the ticket-09 inspection surface.
    pages, playback = build_pages("fellowship")  # roster + factions seeded
    _advance_to(pages, playback, 3 * TICKS_PER_YEAR)
    # Open owned ground (no site, no host) headlines the faction with full
    # depth (inspection-ui 02). Find such a Gondor tile.
    grid = pages._grid
    gondor = next(k for k, v in pages._faction_names.items() if v == "Gondor")
    sited = {(s.col, s.row) for s in grid.sites}
    col, row = next(
        (c, r)
        for r in range(grid.height)
        for c in range(grid.width)
        if grid.owner_at(c, r) == gondor and (c, r) not in sited
    )
    text = pages.describe_tile(col, row)
    assert "FACTION" in text and "DIPLOMACY" in text  # full depth
    # Gondor's seeded temper surfaces as a non-neutral stance toward Mordor.
    assert "Mordor" in text and "hostility" in text
    # The stance word wears the war red; the disposition number is dimmed.
    assert _WAR_COLOR in text and f'color: {DIM}">(' in text


def test_site_subject_gets_trimmed_faction_context():
    # A site headlines; its holder demotes to leader + strength + stance line —
    # no DIPLOMACY/BLOODLINE/RECENT EVENTS sections (inspection-ui 02).
    pages, playback = build_pages("fellowship")
    mt = next(s for s in pages._grid.sites if s.name == "Minas Tirith")
    _advance(pages, playback, 1)
    text = pages.describe_tile(mt.col, mt.row)
    assert "SITE" in text and "GONDOR" in text  # holder's context section
    assert "Leader" in text and "Strength" in text
    for full_depth_only in ("DIPLOMACY", "BLOODLINE", "RECENT EVENTS"):
        assert full_depth_only not in text


def test_bare_unowned_tile_stays_short():
    pages, _playback = build_pages("fellowship")
    grid = pages._grid
    sited = {(s.col, s.row) for s in grid.sites}
    from arda_sim.tiles import UNOWNED

    col, row = next(
        (c, r)
        for r in range(grid.height)
        for c in range(grid.width)
        if grid.owner_at(c, r) == UNOWNED and (c, r) not in sited
    )
    text = pages.describe_tile(col, row)
    assert "TILE" in text and f"({col}, {row})" in text
    assert "unowned" in text
    assert "FACTION" not in text and "SITE" not in text


def test_host_dossier_shows_siege_progress_only_mid_siege():
    from arda_sim.war import fortification

    pages, _playback = build_pages("fellowship")
    mt = next(s for s in pages._grid.sites if s.name == "Minas Tirith")
    host = Army(
        id=999, kind="army", created_year=3000, name="Host of Test",
        col=mt.col, row=mt.row, size=500,
    )
    assert "Siege" not in pages.describe_army(host)  # not investing
    host.siege_progress = 91
    text = pages.describe_army(host)
    assert f"91 / {fortification(mt)}" in text  # progress vs the walls
    assert "Stands" in text and "Minas Tirith" in text  # the locator line


# -- faction dossier ------------------------------------------------------


def test_faction_grid_drops_prominence_and_intent():
    pages, playback = build_pages("fellowship")
    snap = _advance(pages, playback, 1)
    faction = next(
        f
        for f in snap.entities.values()
        if isinstance(f, Faction) and f.name == "Gondor"
    )
    text = pages.describe_faction(faction)
    assert "Treasury" in text  # the grid is there...
    assert "Prominence" not in text and "Latest intent" not in text


def test_stance_words_wear_the_feed_colors():
    ally = Faction(
        id=1, kind="faction", created_year=3000, name="A", at_war_with=[2]
    )
    at_war = CodexPages._stance_html(ally, 2, "hostility")
    assert "at war" in at_war and _WAR_COLOR in at_war and "<b" in at_war  # bold red
    hostile = CodexPages._stance_html(ally, 3, "hostility")
    assert "hostility" in hostile and _WAR_COLOR in hostile and "<b" not in hostile
    assert _AMITY_COLOR in CodexPages._stance_html(ally, 3, "alliance")
    assert _FEALTY_COLOR in CodexPages._stance_html(ally, 3, "vassalage")


def test_recent_event_lines_wear_bucket_dots():
    from arda_sim.ui.annals_style import BUCKET_COLORS

    pages, _playback = build_pages("fellowship")
    line = pages._event_line(
        Event(id=1, year=3010, type="battle", text="a battle was joined")
    )
    assert "●" in line and BUCKET_COLORS["war"].name() in line
    neutral = pages._event_line(Event(id=2, year=3010, type="mystery"))
    assert DIM in neutral  # unmapped types dot in the neutral gray


def test_faction_dossier_wears_its_map_color():
    from arda_sim.ui import tile_render

    pages, playback = build_pages("fellowship")
    snap = _advance(pages, playback, 1)
    faction = next(
        f
        for f in snap.entities.values()
        if isinstance(f, Faction) and f.name == "Gondor"
    )
    html = pages.describe_faction(faction)
    assert tile_render.faction_color(faction.id).name() in html


def test_faction_dossier_shows_a_dynasty_tab_and_drops_the_bloodline_block():
    # The faction page grows a tab strip (Overview here, Dynasty a codex:// link)
    # and the old inline plain-text Bloodline section is gone (#21).
    pages, playback = build_pages("fellowship")
    gondor = _seeded_faction(pages, playback, "Gondor")
    html = pages.describe_faction(gondor)
    assert "Overview" in html and "Dynasty" in html
    assert f"codex://dynasty/faction:{gondor.id}" in html
    assert "BLOODLINE" not in html and "<pre" not in html


def test_faction_dossier_shows_a_diplomacy_tab():
    # The faction page's tab strip carries a Diplomacy entry (a codex:// link)
    # alongside Overview and Dynasty (#20).
    pages, playback = build_pages("fellowship")
    gondor = _seeded_faction(pages, playback, "Gondor")
    html = pages.describe_faction(gondor)
    assert "Overview" in html and "Diplomacy" in html and "Dynasty" in html
    assert f"codex://diplomacy/faction:{gondor.id}" in html


# -- dynasty page ---------------------------------------------------------


def test_dynasty_tree_hangs_spouses_inline_and_marks_the_dead():
    # Rohan's line: Thengel weds Morwen — she hangs off his node (⚭, linked),
    # not walked as a branch. A dead kin shows † and dims.
    from arda_sim.entities import EntityStatus

    pages, playback = build_pages("fellowship")
    rohan = _seeded_faction(pages, playback, "Rohan")
    morwen = next(
        e
        for e in pages._latest_snapshot.entities.values()
        if isinstance(e, Character) and e.name == "Morwen"
    )
    html = pages.describe_dynasty(rohan)
    assert "⚭" in html and f"codex://character/{morwen.id}" in html
    assert "†" not in html  # all alive at seed
    morwen.status = EntityStatus.DEAD.value
    assert "†" in pages.describe_dynasty(rohan)  # the dead are marked


def test_dynasty_page_notes_an_elective_seat_has_no_heir():
    # An elective realm previews no fixed heir: an explicit note, no [Heir] badge.
    from arda_sim.factions import SuccessionRule

    pages, playback = build_pages("fellowship")
    gondor = _seeded_faction(pages, playback, "Gondor")
    gondor.succession_rule = SuccessionRule.ELECTIVE.value
    html = pages.describe_dynasty(gondor)
    assert "elective" in html.lower()
    assert "[Heir]" not in html


# -- armies index ---------------------------------------------------------


def test_armies_index_lists_hosts_as_linked_rows_sorted_by_strength():
    # The Armies index (#17): every host afield, greatest first by default,
    # each row's name linking to its host page.
    pages, _playback = build_pages("fellowship")
    gondor = next(k for k, v in pages._faction_names.items() if v == "Gondor")
    rohan = next(k for k, v in pages._faction_names.items() if v == "Rohan")
    small = _host(100, "Lesser Host", 200, faction_id=gondor, col=1, row=1)
    great = _host(101, "Greater Host", 5000, faction_id=rohan, col=2, row=2)
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={100: small, 101: great}
    )
    html = pages._index_page("armies")
    assert "INDEX" in html and "Armies" in html
    # Every column the ticket asks for heads the table.
    for header in ("Host", "Faction", "Leader", "Strength", "Destination",
                   "Target", "Siege"):
        assert header in html
    # Each host names a row that links to its host page.
    assert 'href="codex://host/100"' in html and "Lesser Host" in html
    assert 'href="codex://host/101"' in html and "Greater Host" in html
    assert "5000" in html and "200" in html  # strengths render
    # Faction cells link to the faction pages.
    assert f'href="codex://faction/{rohan}"' in html
    # Default sort is strength descending: the great host precedes the lesser.
    assert html.index("Greater Host") < html.index("Lesser Host")


def test_armies_index_re_sorts_by_the_ident_sort_key():
    # codex://index/armies/<key> renders the same page under a different sort;
    # the active column head is bold text, the rest are sort links.
    pages, _playback = build_pages("fellowship")
    gondor = next(k for k, v in pages._faction_names.items() if v == "Gondor")
    rohan = next(k for k, v in pages._faction_names.items() if v == "Rohan")
    # Strength order (great, lesser) is the reverse of name order (Greater<Lesser).
    great = _host(101, "Greater Host", 5000, faction_id=gondor, col=2, row=2)
    lesser = _host(100, "Lesser Host", 200, faction_id=rohan, col=1, row=1)
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={100: lesser, 101: great}
    )
    by_host = pages._index_page("armies/host")
    # Sorted by host name ascending now: Greater before Lesser holds, but by a
    # different key — assert the active header flipped and a strength link exists.
    assert "<b>Host</b>" in by_host  # active sort head is bold, not a link
    assert 'href="codex://index/armies/strength"' in by_host  # others are links
    # An unknown sort key falls back to the default (strength), not a dead page.
    assert pages._index_page("armies/nonsense") == pages._index_page("armies")


def test_armies_index_shows_destination_target_and_siege():
    from arda_sim.war import fortification

    pages, _playback = build_pages("fellowship")
    mt = next(s for s in pages._grid.sites if s.name == "Minas Tirith")
    gondor = next(k for k, v in pages._faction_names.items() if v == "Gondor")
    mordor = next(k for k, v in pages._faction_names.items() if v == "Mordor")
    # A host besieging Minas Tirith, marching against Mordor.
    host = _host(
        200, "Besiegers", 900, faction_id=gondor, col=mt.col, row=mt.row,
        dest_site_id=mt.id, target_faction_id=mordor, siege_progress=40,
    )
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={200: host}
    )
    html = pages._index_page("armies")
    assert f'href="codex://site/{mt.id}"' in html  # destination links to the seat
    assert f'href="codex://faction/{mordor}"' in html  # target realm links
    assert f"40 / {fortification(mt)}" in html  # siege progress vs the walls


def test_armies_index_is_empty_when_no_hosts_are_afield():
    pages, _playback = build_pages("fellowship")
    pages._latest_snapshot = Snapshot(tick=0, year=START_YEAR, entities={})
    html = pages._index_page("armies")
    assert "Armies" in html and "No hosts are afield" in html


# -- factions index -------------------------------------------------------


def test_factions_index_lists_factions_as_linked_rows():
    # The Factions index (#19): every power as a table, each name row linking
    # to its dossier — read off the real seeded snapshot with live populations.
    pages, playback = build_pages("fellowship")
    _advance(pages, playback, 1)
    gondor = next(k for k, v in pages._faction_names.items() if v == "Gondor")
    html = pages._index_page("factions")
    assert "INDEX" in html and "Factions" in html
    # Every column the ticket asks for heads the table.
    for header in ("Faction", "Kind", "Population", "Strength", "Treasury",
                   "Leader", "Wars"):
        assert header in html
    # Each faction names a row that links to its dossier.
    assert f'href="codex://faction/{gondor}"' in html and "Gondor" in html


def test_factions_index_re_sorts_by_the_ident_sort_key():
    # codex://index/factions/<key> renders the same page under a different sort;
    # the active column head is bold text, the rest are sort links.
    pages, _playback = build_pages("fellowship")
    # Treasury order (rich, poor) is the reverse of name order (Poor<Rich).
    rich = _faction_entity(9001, "Rich Realm", treasury=5000, military_strength=10)
    poor = _faction_entity(9002, "Poor Realm", treasury=10, military_strength=90)
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={9001: rich, 9002: poor}
    )
    by_treasury = pages._index_page("factions/treasury")
    assert "<b>Treasury</b>" in by_treasury  # active sort head is bold
    assert 'href="codex://index/factions/name"' in by_treasury  # others link
    assert by_treasury.index("Rich Realm") < by_treasury.index("Poor Realm")
    # Sorting by name reverses that order.
    by_name = pages._index_page("factions/name")
    assert "<b>Faction</b>" in by_name
    assert by_name.index("Poor Realm") < by_name.index("Rich Realm")
    # An unknown sort key falls back to the default, not a dead page.
    assert pages._index_page("factions/nonsense") == pages._index_page("factions")


def test_factions_index_shows_population_and_linked_wars():
    # Population reads through economy.faction_population, and each war names
    # the enemy realm with a link to its dossier.
    pages, _playback = build_pages("fellowship")
    gondor = next(k for k, v in pages._faction_names.items() if v == "Gondor")
    mordor = next(k for k, v in pages._faction_names.items() if v == "Mordor")
    from arda_sim.economy import faction_population

    expected = faction_population(None, pages._grid, gondor)
    realm = _faction_entity(gondor, "Gondor", at_war_with=[mordor])
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={gondor: realm}
    )
    html = pages._index_page("factions")
    assert str(expected) in html  # the derived population renders
    assert f'href="codex://faction/{mordor}"' in html  # the war enemy links


def test_factions_index_is_empty_when_no_factions_stand():
    pages, _playback = build_pages("fellowship")
    pages._latest_snapshot = Snapshot(tick=0, year=START_YEAR, entities={})
    html = pages._index_page("factions")
    assert "Factions" in html and "No factions stand" in html


# -- wars index -----------------------------------------------------------


def test_wars_index_lists_wars_and_treaties_as_deduped_linked_pairs():
    # The Wars index (#20): every war and treaty a single row, both sides
    # linking to their dossiers — a symmetric bond appears once, not per side.
    pages, _playback = build_pages("fellowship")
    a = _faction_entity(9001, "Arnor", at_war_with=[9002], treaties=[9003])
    b = _faction_entity(9002, "Barad", at_war_with=[9001])  # war reciprocated
    c = _faction_entity(9003, "Cardolan", treaties=[9001])  # treaty reciprocated
    pages._faction_names.update({9001: "Arnor", 9002: "Barad", 9003: "Cardolan"})
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={9001: a, 9002: b, 9003: c}
    )
    html = pages._index_page("wars")
    assert "INDEX" in html and "Wars" in html
    for header in ("Relation", "Between", "And"):
        assert header in html
    assert "War" in html and "Treaty" in html
    # Both sides of each pair link to their dossier.
    for fid in (9001, 9002, 9003):
        assert f'href="codex://faction/{fid}"' in html
    # The war is deduped to one row: Arnor's name shows up exactly across
    # its two rows (war with Barad, treaty with Cardolan), never doubled.
    assert html.count("codex://faction/9002") == 1  # Barad, war, once
    assert html.count("codex://faction/9003") == 1  # Cardolan, treaty, once


def test_wars_index_re_sorts_by_the_ident_sort_key():
    # codex://index/wars/<key> renders the same page under a different sort;
    # the active head is bold, the rest link. An unknown key falls back.
    pages, _playback = build_pages("fellowship")
    a = _faction_entity(9001, "Zeal", at_war_with=[9002])
    b = _faction_entity(9002, "Anga", at_war_with=[9001])
    pages._faction_names.update({9001: "Zeal", 9002: "Anga"})
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={9001: a, 9002: b}
    )
    by_between = pages._index_page("wars/between")
    assert "<b>Between</b>" in by_between  # active sort head is bold
    assert 'href="codex://index/wars/relation"' in by_between  # others link
    # Ordered within the pair by name: Anga precedes Zeal.
    assert by_between.index("Anga") < by_between.index("Zeal")
    # An unknown sort key falls back to the default, not a dead page.
    assert pages._index_page("wars/nonsense") == pages._index_page("wars")


def test_wars_index_is_empty_when_no_bonds_stand():
    pages, _playback = build_pages("fellowship")
    lone = _faction_entity(9001, "Hermit")
    pages._faction_names.update({9001: "Hermit"})
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={9001: lone}
    )
    html = pages._index_page("wars")
    assert "Wars" in html and "No wars or treaties" in html


def test_wars_index_drops_bonds_to_absent_factions():
    # A war/treaty against a faction not in the displayed year has nothing to
    # link to, so it is dropped rather than rendering a bare id.
    pages, _playback = build_pages("fellowship")
    a = _faction_entity(9001, "Arnor", at_war_with=[7777])  # 7777 absent
    pages._faction_names.update({9001: "Arnor"})
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={9001: a}
    )
    html = pages._index_page("wars")
    assert "No wars or treaties" in html
    assert "7777" not in html


# -- diplomacy page -------------------------------------------------------


def test_diplomacy_page_shows_wars_treaties_drift_and_intent():
    # codex://diplomacy/faction:<id> resolves through the diplomacy renderer and
    # shows active wars, treaties, disposition drift from baseline, and intent.
    pages, _playback = build_pages("fellowship")
    foe = _faction_entity(9002, "Mordor-ish")
    ally = _faction_entity(9003, "Rohan-ish")
    realm = _faction_entity(
        9001,
        "Gondor-ish",
        at_war_with=[9002],
        treaties=[9003],
        disposition={"9002": -80, "9003": 55},
        baseline_disposition={"9002": -60, "9003": 55},
    )
    pages._faction_names.update(
        {9001: "Gondor-ish", 9002: "Mordor-ish", 9003: "Rohan-ish"}
    )
    pages._latest_snapshot = Snapshot(
        tick=0,
        year=START_YEAR,
        entities={9001: realm, 9002: foe, 9003: ally},
    )
    pages._events.append(
        _event(
            START_YEAR,
            type_="faction_intent",
            subject_ids=[9001],
            text="Gondor-ish made ready for war against Mordor-ish.",
        )
    )
    pages._display_year = START_YEAR
    html = pages.render(CodexAddress("diplomacy", "faction:9001"))
    text_marks = ("DIPLOMACY", "ACTIVE WARS", "TREATIES", "DRIFT", "STANDING INTENT")
    for mark in text_marks:
        assert mark in html.upper()
    # Wars and treaties link both parties' dossiers.
    assert 'href="codex://faction/9002"' in html
    assert 'href="codex://faction/9003"' in html
    # Drift shows current vs. baseline and the signed delta (−80 vs −60).
    assert "-80" in html and "-60" in html and "drifted -20" in html
    assert "at baseline" in html  # the ally hasn't moved (55 == 55)
    # Intent reads from the latest faction_intent event's prose.
    assert "made ready for war" in html
    # The active tab is Diplomacy.
    assert "codex://faction/9001" in html  # Overview tab links back


def test_diplomacy_page_is_quiet_for_an_isolated_realm():
    pages, _playback = build_pages("fellowship")
    lone = _faction_entity(9001, "Hermit")
    pages._faction_names.update({9001: "Hermit"})
    pages._latest_snapshot = Snapshot(
        tick=0, year=START_YEAR, entities={9001: lone}
    )
    pages._display_year = START_YEAR
    html = pages.describe_diplomacy_page(lone)
    assert "At peace with all" in html
    assert "No standing pacts" in html
    assert "taken no counsel" in html  # no intent event yet


# -- the One Ring page ----------------------------------------------------


def test_ring_page_shows_bearer_timeline_trend_and_errand():
    from arda_sim.ring import RING_TRANSFERRED_EVENT, RingTransfer

    pages, playback = build_pages("fellowship")  # the Ring seeded with Bilbo
    # Advance a few ticks so the corruption/pull trend accrues samples.
    _advance(pages, playback, 3)
    ring = the_ring(pages._latest_snapshot)
    seed_bearer_id = ring.bearer_history[0]

    # A second bearer, acquired by gift — a transfer event drives the timeline.
    other = next(
        e
        for eid, e in pages._latest_snapshot.entities.items()
        if e.kind == "character" and eid != seed_bearer_id
    )
    pages._events.append(
        Event(
            id=99999,
            year=pages._display_year,
            type=RING_TRANSFERRED_EVENT,
            subject_ids=[ring.id, seed_bearer_id, other.id],
            payload={
                "mode": RingTransfer.GIFT.value,
                "from_bearer_id": seed_bearer_id,
                "to_bearer_id": other.id,
            },
        )
    )
    # An errand afoot: bound for a named site, drawn as a link.
    goal = pages._grid.sites[0]
    ring.goal_site_id = goal.id
    ring.path = [[ring.col + 1, ring.row]]

    plain = pages.describe_ring(ring)  # assertions target the raw HTML

    # Bearer timeline: the second bearer, its acquisition mode, linked out.
    assert "Bearers".upper() in plain.upper()
    assert "codex://character/%d" % other.id in plain and "via gift" in plain
    assert "present" in plain  # the current bearer's open-ended stint
    # Trend: a sparkline block glyph over the accrued series.
    assert "Trend".upper() in plain.upper()
    assert any(block in plain for block in "▁▂▃▄▅▆▇█")
    # Errand: the goal site named and linked.
    assert "codex://site/%d" % goal.id in plain and goal.name in plain


def test_ring_page_errand_and_trend_absent_when_idle():
    pages, playback = build_pages("fellowship")
    _advance(pages, playback, 1)  # a single sample: no trend line yet
    ring = the_ring(pages._latest_snapshot)
    ring.goal_site_id = None  # no errand
    html = pages.describe_ring(ring)
    assert "ERRAND" not in html.upper()  # omitted, not shown empty
    assert "TREND" not in html.upper()  # one sample can't trace a line
    # The founding bearer still shows, held to the present.
    assert "BEARERS" in html.upper() and "present" in html
