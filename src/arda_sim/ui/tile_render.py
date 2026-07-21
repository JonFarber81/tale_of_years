"""The tile theme: terrain sprites, faction tints, and per-tile painting.

Renders the :class:`~arda_sim.tiles.TileGrid` as a tile map (ADR-0001): each
terrain draws a **Kenney roguelike/RPG sprite** (CC0, bundled under
``references/tilesets/``) scaled to the cell; terrains the pack lacks
(mountain, hills, marsh) fall back to a flat colour plus a distinguishing
motif. Faction territory is a translucent owner tint over the terrain.

This is the render *theme* seam: the geometry (which tile, where) lives in the
view; the look (sprite, colour, motif) lives here. Sprite pixmaps load lazily on
first paint, so the colour helpers stay unit-testable headlessly (no
``QApplication``); only :func:`paint_terrain_tile` touches the spritesheet.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPixmap

from ..tiles import Terrain

# Spritesheet geometry: 16px tiles with a 1px margin (see the pack's
# spritesheetInfo.txt), so tile (col, row) starts at (col*17, row*17).
_SPRITE_PX = 16
_SPRITE_STRIDE = 17

# Terrain -> spritesheet cell (col, row). Terrains absent here (mountain, hills,
# marsh) have no fitting sprite in the pack and render procedurally instead.
_SPRITE_CELL: Dict[Terrain, Tuple[int, int]] = {
    Terrain.PLAINS: (5, 0),   # grass
    Terrain.BARREN: (6, 0),   # bare dirt
    Terrain.ROAD: (7, 2),     # cobbled path
    Terrain.SEA: (0, 0),      # water
    Terrain.LAKE: (0, 0),     # water
    Terrain.RIVER: (0, 0),    # water
    Terrain.MOUNTAIN: (7, 0),  # grey stone base (peak motif drawn on top)
    Terrain.HILLS: (5, 0),    # grass base (mound motif drawn on top)
}

# Forest = a dense opaque green base + a tree canopy on top, so it reads as
# thick woodland rather than spaced trees over grass.
_FOREST_BASE_CELL = (11, 11)   # solid dark-green undergrowth
_FOREST_CANOPY_CELL = (13, 9)  # round tree canopy

# People -> character-sheet cell (col, row) for a host's folk sprite (map-visuals
# ticket 03). These index the bundled Kenney *Characters* sheet (a separate CC0
# pack from the terrain sheet, same 16px/stride-17 geometry) — a real figure of
# the folk drawn over the faction colour, so the marker says *whose* (colour) and
# *what folk* (figure) at a glance. Cells picked from the sheet's base figures:
# skin/robe/beard/size distinguish the folk even at tile size.
_PEOPLE_CELL: Dict[str, Tuple[int, int]] = {
    "men": (0, 1),      # a plain human figure
    "elves": (1, 5),    # a fair, white-haired robed figure
    "dwarves": (1, 6),  # a stout bearded figure
    "orcs": (1, 3),     # a green-skinned figure
    "hobbits": (0, 10),  # a small child-sized figure
}
# Fallback cell for any unknown/missing people value — a plain human figure.
_PEOPLE_FALLBACK_CELL: Tuple[int, int] = (0, 0)

# Lazily loaded spritesheet pixmaps — each needs a running QGuiApplication, so
# they are only touched from paint (never at import or from the headless tests).
_sheet: Optional[QPixmap] = None
_char_sheet: Optional[QPixmap] = None


def _sheet_pixmap() -> QPixmap:
    global _sheet
    if _sheet is None:
        from .assets import tileset_path

        _sheet = QPixmap(str(tileset_path()))
    return _sheet


def _char_sheet_pixmap() -> QPixmap:
    """The Kenney Characters sheet, loaded lazily like :func:`_sheet_pixmap`."""
    global _char_sheet
    if _char_sheet is None:
        from .assets import character_tileset_path

        _char_sheet = QPixmap(str(character_tileset_path()))
    return _char_sheet


def _sprite_source(cell: Tuple[int, int]) -> QRectF:
    col, row = cell
    return QRectF(col * _SPRITE_STRIDE, row * _SPRITE_STRIDE, _SPRITE_PX, _SPRITE_PX)

# Base terrain colours (DF-style flat fills). Chosen to read at a glance and to
# stay distinct from every faction tint below.
_TERRAIN_RGB: Dict[Terrain, Tuple[int, int, int]] = {
    Terrain.PLAINS: (124, 168, 86),
    Terrain.FOREST: (74, 122, 60),
    Terrain.MOUNTAIN: (128, 122, 118),
    Terrain.HILLS: (150, 158, 96),
    Terrain.MARSH: (92, 116, 92),
    Terrain.BARREN: (176, 150, 108),
    Terrain.RIVER: (90, 140, 196),
    Terrain.LAKE: (86, 148, 200),
    Terrain.SEA: (58, 108, 168),
    Terrain.ROAD: (156, 130, 96),
}

# Faction tint palette, indexed by (faction_id - 1) % len. Deterministic so the
# same faction always draws the same colour across a run and across sessions.
_FACTION_RGB: Tuple[Tuple[int, int, int], ...] = (
    (60, 90, 200),   # blue
    (200, 60, 60),   # red
    (70, 160, 90),   # green
    (200, 150, 40),  # amber
    (150, 80, 190),  # violet
    (40, 170, 180),  # teal
    (210, 110, 60),  # orange
    (120, 120, 120),  # grey
)

# Alpha for the translucent owner overlay; the border stroke is fully opaque so
# frontiers (derived via TileGrid.is_border) read as crisp lines.
_OWNER_TINT_ALPHA = 96


def terrain_color(terrain: Terrain) -> QColor:
    """The flat base colour for a terrain."""
    return QColor(*_TERRAIN_RGB[terrain])


def faction_color(faction_id: int, alpha: int = 255) -> QColor:
    """A stable colour for a faction id (1-based), optionally translucent."""
    r, g, b = _FACTION_RGB[(faction_id - 1) % len(_FACTION_RGB)]
    return QColor(r, g, b, alpha)


def owner_tint(faction_id: int) -> QColor:
    """The translucent tint painted over an owned tile's terrain."""
    return faction_color(faction_id, _OWNER_TINT_ALPHA)


def people_sprite_cell(people: Optional[str]) -> Tuple[int, int]:
    """The spritesheet ``(col, row)`` for a people's host sprite, or the fallback.

    A pure lookup with no spritesheet access, so it stays importable and testable
    headlessly (no ``QGuiApplication``), like the colour helpers above.
    """
    return _PEOPLE_CELL.get(people, _PEOPLE_FALLBACK_CELL)


def paint_people_sprite(
    painter: QPainter, people: Optional[str], x: float, y: float, size: float
) -> None:
    """Blit a people's character sprite scaled into the cell at ``(x, y)``.

    Mirrors :func:`paint_terrain_tile`, but draws from the Kenney *Characters*
    sheet: it touches that lazily-loaded pixmap, so it needs a running
    QGuiApplication (never called from the headless tests).
    """
    painter.drawPixmap(
        QRectF(x, y, size, size),
        _char_sheet_pixmap(),
        _sprite_source(people_sprite_cell(people)),
    )


def paint_terrain_tile(
    painter: QPainter, terrain: Terrain, x: float, y: float, size: float
) -> None:
    """Paint one terrain tile at ``(x, y)`` with side ``size`` in scene units.

    Draws the terrain's Kenney sprite scaled into the cell where one exists;
    otherwise a flat fill. Mountain and hills add a motif over their stone/grass
    base (the pack has no summit sprite); marsh renders fully procedurally.
    """
    rect = QRectF(x, y, size, size)
    base = terrain_color(terrain)

    if terrain == Terrain.FOREST:
        # Dense green base fills the whole cell (opaque); the canopy on top gives
        # the tree read. Base first so the canopy's transparent margins show
        # undergrowth, not the layers beneath.
        painter.drawPixmap(rect, _sheet_pixmap(), _sprite_source(_FOREST_BASE_CELL))
        painter.drawPixmap(rect, _sheet_pixmap(), _sprite_source(_FOREST_CANOPY_CELL))
        return

    cell = _SPRITE_CELL.get(terrain)
    if cell is not None:
        painter.drawPixmap(rect, _sheet_pixmap(), _sprite_source(cell))
    else:
        painter.fillRect(rect, base)

    if terrain == Terrain.MOUNTAIN:
        painter.setPen(base.darker(150))
        painter.setBrush(base.lighter(150))
        painter.drawPolygon(_triangle(x + size * 0.5, y + size * 0.18, size * 0.34))
    elif terrain == Terrain.HILLS:
        painter.setPen(QColor(70, 90, 50))
        painter.setBrush(base.darker(115))
        painter.drawEllipse(QRectF(x + size * 0.22, y + size * 0.42, size * 0.56, size * 0.46))
    elif terrain == Terrain.MARSH:
        painter.setPen(base.darker(140))
        for frac in (0.35, 0.6):
            yy = int(y + size * frac)
            painter.drawLine(int(x + size * 0.2), yy, int(x + size * 0.8), yy)


def _triangle(cx: float, top_y: float, half: float):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF

    return QPolygonF(
        [
            QPointF(cx, top_y),
            QPointF(cx - half, top_y + half * 1.8),
            QPointF(cx + half, top_y + half * 1.8),
        ]
    )
