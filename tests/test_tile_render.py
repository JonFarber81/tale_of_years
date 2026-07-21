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
        assert f"Tile ({mt.col}, {mt.row})" in text
        assert "Owner: Gondor" in text
        assert "Minas Tirith" in text
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
