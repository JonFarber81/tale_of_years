"""Tile renderer: theme colours (headless) and view/inspection wiring (offscreen)."""

import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from arda_sim.tiles import UNOWNED, Terrain  # noqa: E402


# --- theme colours: no QApplication needed ----------------------------------


def test_terrain_colors_are_distinct_per_terrain():
    from arda_sim.ui.tile_render import terrain_color

    rgbs = {t: terrain_color(t).getRgb() for t in Terrain}
    assert len(set(rgbs.values())) == len(Terrain)  # no two terrains share a colour


def test_faction_color_is_stable_and_cycles():
    from arda_sim.ui.tile_render import faction_color

    assert faction_color(1).getRgb() == faction_color(1).getRgb()
    assert faction_color(1).getRgb() != faction_color(2).getRgb()
    # wraps around the palette deterministically (palette has 8 colours)
    assert faction_color(1).getRgb() == faction_color(9).getRgb()


def test_owner_tint_is_translucent():
    from arda_sim.ui.tile_render import owner_tint

    assert 0 < owner_tint(1).alpha() < 255


def test_people_sprite_cell_is_distinct_per_people_with_fallback():
    # The army-sprite map (map-visuals 03) is a pure headless lookup: each of the
    # five folk maps to its own spritesheet cell, and any unknown/missing value
    # falls back to a cell of its own.
    from arda_sim.ui.tile_render import people_sprite_cell

    peoples = ["men", "elves", "dwarves", "orcs", "hobbits"]
    cells = [people_sprite_cell(p) for p in peoples]
    assert len(set(cells)) == len(peoples)  # a distinct cell per folk
    fallback = people_sprite_cell("dragons")
    assert fallback not in cells  # unknown gets its own fallback cell
    assert people_sprite_cell(None) == fallback


# --- view + inspection: need an offscreen QApplication ----------------------


def _qt_platform_usable() -> bool:
    """Probe in a throwaway process whether a Qt platform can stand up (see
    test_ui_shell for why an in-process check would abort the suite)."""
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

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arda_sim.scenarios import load_scenario  # noqa: E402
from arda_sim.ui.app import build_window  # noqa: E402
from arda_sim.ui.map_view import TILE, MapView  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_tileset_sprite_sheet_loads(qapp):
    from arda_sim.ui.assets import tileset_path
    from arda_sim.ui.tile_render import _sheet_pixmap

    assert tileset_path().is_file()
    sheet = _sheet_pixmap()
    assert not sheet.isNull()  # the bundled Kenney sheet actually decoded


def test_character_sprite_sheet_loads(qapp):
    # The host people sprites (map-visuals 03) draw from a second bundled Kenney
    # pack — the Characters sheet — so verify it ships and decodes too.
    from arda_sim.ui.assets import character_tileset_path
    from arda_sim.ui.tile_render import _char_sheet_pixmap

    assert character_tileset_path().is_file()
    sheet = _char_sheet_pixmap()
    assert not sheet.isNull()


def test_map_view_lays_scene_out_in_tile_pixels(qapp):
    grid = load_scenario("gondor_stub")
    view = MapView(grid)
    rect = view._scene.sceneRect()
    assert (rect.width(), rect.height()) == (grid.width * TILE, grid.height * TILE)


def test_clicking_maps_scene_point_to_tile_coords(qapp):
    grid = load_scenario("gondor_stub")
    view = MapView(grid)
    seen = []
    view.tileClicked.connect(lambda c, r: seen.append((c, r)))
    # a scene point inside tile (3, 5) -> emits (3, 5)
    view._emit_tile_at(view.mapFromScene(QPointF(3 * TILE + 2, 5 * TILE + 2)))
    assert seen == [(3, 5)]


def test_clicking_out_of_bounds_emits_nothing(qapp):
    grid = load_scenario("gondor_stub")
    view = MapView(grid)
    seen = []
    view.tileClicked.connect(lambda c, r: seen.append((c, r)))
    view._emit_tile_at(view.mapFromScene(QPointF(-5, -5)))
    assert seen == []


def test_refresh_owners_reflects_owner_changes(qapp):
    grid = load_scenario("gondor_stub")
    view = MapView(grid)
    before = view._owner_item.pixmap().toImage()
    grid.set_owner(0, 0, 1)
    view.refresh_owners()
    after = view._owner_item.pixmap().toImage()
    assert before != after  # the tint layer actually redrew


def test_inspection_describes_clicked_tile(qapp):
    window = build_window("fellowship")
    try:
        # Inspect Minas Tirith wherever it is authored (derive the tile from the
        # site, so the test tracks substrate re-authoring instead of pinning a
        # coordinate that silently goes stale). It sits in the Gondor-owned block.
        mt = next(s for s in window._grid.sites if s.name == "Minas Tirith")
        text = window.describe_tile(mt.col, mt.row)
        # Most-specific-first (inspection-ui 02): the site headlines the
        # dossier, with its rank and its holder.
        assert "SITE" in text and "Minas Tirith" in text
        assert "Rank" in text and "City" in text
        assert "Gondor" in text  # the owner reads in the grid/context
    finally:
        window.close()


def test_site_labels_are_tier_gated_on_zoom(qapp):
    # Labels are screen-fixed annotations, so tier gating (label-declutter,
    # ticket 02) hides the low-rank ones at far zoom to stop them piling up:
    # cities are always labelled; ruins only appear once zoomed in close.
    window = build_window("fellowship")
    try:
        m = window._map
        tier0 = [lbl for lbl, tier in m._site_labels if tier == 0]
        tier2 = [lbl for lbl, tier in m._site_labels if tier == 2]
        assert tier0 and tier2  # the shipped grid has both cities and ruins

        m.fit_map()  # far: the whole map fits the viewport
        assert all(not lbl.isVisible() for lbl in tier0)  # ruins culled when far
        assert all(lbl.isVisible() for lbl in tier2)  # cities always shown

        m._apply_zoom(10_000)  # close: clamped to the zoom-in cap
        assert all(lbl.isVisible() for lbl in tier0)  # ruins appear up close
        assert all(lbl.isVisible() for lbl in tier2)  # cities still shown
    finally:
        window.close()


def test_site_markers_follow_kind_and_tier_changes(qapp):
    # Markers are rebuilt from the live grid so they track a site's kind/tier as
    # construction grows or war razes it (ticket 04). refresh_sites is guarded by
    # a change-signature, so it is a no-op until a site actually moves.
    window = build_window("fellowship")
    try:
        m = window._map
        grid = window._grid
        assert len(m._site_markers) == len(grid.sites)  # one marker per site

        # No change -> the guard skips the rebuild (same item objects reused).
        before = list(m._site_markers)
        m.refresh_sites()
        assert m._site_markers is before or all(
            a is b for a, b in zip(m._site_markers, before)
        )

        # Grow a town into a city: the markers rebuild, and the site's label is
        # re-gated to its new (city) tier.
        town = next(s for s in grid.sites if s.kind == "town")
        idx = grid.sites.index(town)
        grid.set_site(town.id, "city", 2)
        m.refresh_sites()
        assert m._site_markers[idx] is not before[idx]  # that marker was redrawn
        assert m._site_labels[idx][1] == 2  # label now gated as a city
    finally:
        window.close()


def test_seeded_factions_paint_territory_with_a_frontier(qapp):
    # Real factions (ticket 07) own regions on the shipped map, so several
    # factions hold ground and a derived frontier exists somewhere.
    window = build_window("fellowship")
    try:
        grid = window._grid
        owned = {
            grid.owner_at(c, r)
            for r in range(grid.height)
            for c in range(grid.width)
        } - {UNOWNED}
        assert len(owned) >= 5  # many powers hold territory
        assert all(fid in window._faction_names for fid in owned)  # every tint labels a faction
        assert any(
            grid.is_border(c, r) for r in range(grid.height) for c in range(grid.width)
        )
    finally:
        window.close()


@pytest.mark.parametrize("terrain", [Terrain.MOUNTAIN, Terrain.HILLS, Terrain.MARSH])
def test_procedural_terrain_is_deterministic_per_tile(qapp, terrain):
    # The three procedural-fallback terrains (map-visuals 05) seed their per-tile
    # variation from the tile's (col, row), never a paint-time RNG — so painting
    # the same tile twice must yield byte-identical images.
    from PySide6.QtGui import QPainter, QPixmap

    from arda_sim.ui.map_view import TILE
    from arda_sim.ui.tile_render import paint_terrain_tile

    def render(col, row):
        pix = QPixmap(TILE, TILE)
        pix.fill()
        p = QPainter(pix)
        paint_terrain_tile(p, terrain, col * TILE, row * TILE, TILE)
        p.end()
        return pix.toImage()

    # Same tile, two independent paints -> byte-identical (no RNG at paint time).
    assert render(3, 7) == render(3, 7)
    assert render(3, 7).constBits() == render(3, 7).constBits()
    # The (col, row) seed actually perturbs the motif: a spread of tiles yields
    # more than one distinct render (not a constant, un-varied stamp).
    variants = {render(c, r).constBits() for c in range(6) for r in range(6)}
    assert len(variants) > 1


def test_refresh_armies_draws_one_marker_per_living_host(qapp):
    # A host marker (map-visuals 03) is a colour disc + people sprite per living
    # army; disbanded hosts draw nothing, and the layer rebuilds wholesale.
    from arda_sim.armies import Army
    from arda_sim.entities import EntityStatus

    window = build_window("fellowship")
    try:
        armies = [
            Army(id=90001, kind="army", name="Host A", created_year=2965, faction_id=1, col=2, row=3,
                 size=500, status=EntityStatus.ACTIVE.value),
            Army(id=90002, kind="army", name="Host B", created_year=2965, faction_id=5, col=4, row=6,
                 size=500, status=EntityStatus.ACTIVE.value),
            Army(id=90003, kind="army", name="Fallen", created_year=2965, faction_id=2, col=1, row=1,
                 size=0, status=EntityStatus.DEAD.value),
        ]
        window._map.refresh_armies(armies)
        assert len(window._map._army_items) == 2  # only the two living hosts
        # Redrawing replaces rather than accumulates.
        window._map.refresh_armies(armies[:1])
        assert len(window._map._army_items) == 1
    finally:
        window.close()


def test_marching_host_adds_a_direction_cue(qapp):
    # A host mid-march (non-empty path) draws its marker plus a direction cue,
    # so it yields MORE scene items than the same host idle (empty path); an
    # idle/garrisoned host adds no cue (map-visuals 06).
    from arda_sim.armies import Army
    from arda_sim.entities import EntityStatus

    window = build_window("fellowship")
    try:
        idle = Army(id=90101, kind="army", name="Garrison", created_year=2965,
                    faction_id=1, col=5, row=5, size=500,
                    status=EntityStatus.ACTIVE.value, path=[])
        window._map.refresh_armies([idle])
        idle_items = len(window._map._army_items)
        assert idle_items == 1  # marker only, no cue

        marching = Army(id=90101, kind="army", name="Garrison", created_year=2965,
                        faction_id=1, col=5, row=5, size=500,
                        status=EntityStatus.ACTIVE.value, path=[[6, 5], [7, 5]])
        window._map.refresh_armies([marching])
        assert len(window._map._army_items) > idle_items  # marker + cue
        assert len(window._map._army_items) == idle_items + 1  # exactly one cue
    finally:
        window.close()
