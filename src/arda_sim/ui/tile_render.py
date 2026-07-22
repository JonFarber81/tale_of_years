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

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

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
    "men": (0, 7),      # a harnessed warrior in a leather-strapped tunic
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
    otherwise a flat fill. Mountain, hills, and marsh have no fitting sprite in
    the pack, so they render as procedural motifs (:func:`_paint_mountain`,
    :func:`_paint_hills`, :func:`_paint_marsh`) with per-tile deterministic
    variation seeded from the tile's ``(col, row)`` — never a paint-time RNG, so
    a tile always renders identically.
    """
    rect = QRectF(x, y, size, size)

    if terrain == Terrain.FOREST:
        # Dense green base fills the whole cell (opaque); the canopy on top gives
        # the tree read. Base first so the canopy's transparent margins show
        # undergrowth, not the layers beneath.
        painter.drawPixmap(rect, _sheet_pixmap(), _sprite_source(_FOREST_BASE_CELL))
        painter.drawPixmap(rect, _sheet_pixmap(), _sprite_source(_FOREST_CANOPY_CELL))
        return

    if terrain in (Terrain.MOUNTAIN, Terrain.HILLS, Terrain.MARSH):
        # ``x, y`` are scene pixels (col*size, row*size), so the integer cell
        # coords recover the tile identity to seed its variation.
        col, row = int(x / size), int(y / size)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if terrain == Terrain.MOUNTAIN:
            _paint_mountain(painter, x, y, size, col, row)
        elif terrain == Terrain.HILLS:
            _paint_hills(painter, x, y, size, col, row)
        else:
            _paint_marsh(painter, x, y, size, col, row)
        painter.restore()
        return

    cell = _SPRITE_CELL.get(terrain)
    if cell is not None:
        painter.drawPixmap(rect, _sheet_pixmap(), _sprite_source(cell))
    else:
        painter.fillRect(rect, terrain_color(terrain))


def _tile_hash(col: int, row: int) -> int:
    """A cheap, stable hash of a tile's ``(col, row)`` for deterministic variation.

    Same seed as the spatial hashing used elsewhere in tile renderers — reproducible
    across runs and sessions, and decorrelated between neighbours so adjacent tiles
    don't share the same offsets.
    """
    return ((col * 73856093) ^ (row * 19349663)) & 0x7FFFFFFF


def _paint_mountain(
    painter: QPainter, x: float, y: float, s: float, col: int, row: int
) -> None:
    """A filled peak that fills the cell, so contiguous mountain tiles merge into a
    legible range at full-map zoom (the Misty Mountains test). Peak offset and
    height vary per tile; a snow cap and a lit/shadow split give it crag."""
    h = _tile_hash(col, row)
    # Rock massif fills the whole tile — neighbours abut into a solid range.
    painter.fillRect(QRectF(x, y, s, s), QColor(120, 116, 116))

    dx = ((h >> 3) % 7 - 3) / 10.0 * s          # main peak shifts +/-0.3s
    peak_h = 0.66 + ((h >> 6) % 4) * 0.06        # summit rises 0.66..0.84 of tile
    apex_x = x + 0.5 * s + dx
    apex_y = y + (1.0 - peak_h) * s
    base_y = y + s
    apex = QPointF(apex_x, apex_y)

    painter.setPen(Qt.NoPen)
    # Shadow (whole peak), then the sunlit left face over it.
    painter.setBrush(QColor(92, 88, 92))
    painter.drawPolygon(QPolygonF([apex, QPointF(x + s, base_y), QPointF(x, base_y)]))
    painter.setBrush(QColor(150, 148, 152))
    painter.drawPolygon(QPolygonF([apex, QPointF(x, base_y), QPointF(apex_x, base_y)]))

    # A secondary lower peak to one side breaks the tiling monotony.
    side = 1 if (h >> 4) & 1 else -1
    sec_x = apex_x + side * 0.34 * s
    sec_y = y + (0.42 + ((h >> 9) % 3) * 0.05) * s
    painter.setBrush(QColor(108, 104, 108))
    painter.drawPolygon(
        QPolygonF(
            [
                QPointF(sec_x, sec_y),
                QPointF(sec_x + 0.3 * s, base_y),
                QPointF(sec_x - 0.3 * s, base_y),
            ]
        )
    )

    # Snow cap: a jagged white wedge sitting just below the summit.
    cap_y = apex_y + 0.24 * s
    painter.setBrush(QColor(240, 242, 246))
    painter.drawPolygon(
        QPolygonF(
            [
                apex,
                QPointF(apex_x + 0.16 * s, cap_y),
                QPointF(apex_x + 0.04 * s, cap_y - 0.06 * s),
                QPointF(apex_x - 0.06 * s, cap_y),
                QPointF(apex_x - 0.16 * s, cap_y - 0.03 * s),
            ]
        )
    )
    # Ridge outline for a crisp summit at any zoom.
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(66, 62, 66), max(1.0, s * 0.045)))
    painter.drawPolyline(QPolygonF([QPointF(x, base_y), apex, QPointF(x + s, base_y)]))


def _paint_hills(
    painter: QPainter, x: float, y: float, s: float, col: int, row: int
) -> None:
    """Two rounded, flat-bottomed mounds (a back rise and a nearer one) with a top
    highlight, so the tile reads as rolling downland rather than a floating dot.
    Mound width and placement vary per tile."""
    h = _tile_hash(col, row)
    painter.fillRect(QRectF(x, y, s, s), QColor(150, 158, 96))
    painter.setPen(QPen(QColor(96, 112, 58), max(1.0, s * 0.04)))

    # Back mound: smaller, higher, lighter (reads as further away).
    bx = x + (0.06 + ((h >> 3) % 3) * 0.08) * s
    bw, bh = 0.5 * s, 0.34 * s
    b_base = y + (0.66 + ((h >> 5) % 3) * 0.05) * s
    painter.setBrush(QColor(160, 170, 104))
    painter.drawChord(QRectF(bx, b_base - bh, bw, bh * 2), 0, 180 * 16)

    # Front mound: wider, lower, darker, offset the other way.
    fx = x + (0.34 + ((h >> 8) % 3) * 0.07) * s
    fw, fh = 0.6 * s, 0.4 * s
    f_base = y + (0.82 + ((h >> 10) % 2) * 0.06) * s
    painter.setBrush(QColor(134, 150, 84))
    painter.drawChord(QRectF(fx, f_base - fh, fw, fh * 2), 0, 180 * 16)
    # Sunlit crown on the front mound.
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(174, 184, 116))
    painter.drawChord(
        QRectF(fx + 0.1 * fw, f_base - fh, fw * 0.55, fh * 1.5), 30 * 16, 130 * 16
    )


def _paint_marsh(
    painter: QPainter, x: float, y: float, s: float, col: int, row: int
) -> None:
    """Murky ground with dark standing-water pools and reed tufts at seeded
    positions — a wet, tufted read rather than a flat fill with two lines."""
    h = _tile_hash(col, row)
    painter.fillRect(QRectF(x, y, s, s), QColor(92, 116, 92))

    # A couple of standing-water pools with a paler sheen.
    painter.setPen(Qt.NoPen)
    for i in range(2):
        hh = h >> (i * 6)
        pw = (0.34 + (hh % 3) * 0.06) * s
        ph = pw * 0.6
        px = x + ((hh >> 2) % 5) / 6.0 * s
        py = y + (0.2 + ((hh >> 4) % 4) / 8.0) * s
        painter.setBrush(QColor(66, 94, 96))
        painter.drawEllipse(QRectF(px, py, pw, ph))
        painter.setBrush(QColor(120, 150, 148, 130))
        painter.drawEllipse(QRectF(px + pw * 0.2, py + ph * 0.15, pw * 0.4, ph * 0.3))

    # Reed tufts: a small fan of stems rising from a seeded base point.
    painter.setPen(QPen(QColor(156, 164, 100), max(1.0, s * 0.05)))
    for i in range(3):
        hh = h >> (i * 5 + 1)
        tx = x + (0.15 + (hh % 6) / 8.0) * s
        ty = y + (0.55 + ((hh >> 3) % 4) / 10.0) * s
        for dxf in (-0.06, 0.0, 0.06):
            painter.drawLine(
                QPointF(tx, ty),
                QPointF(tx + dxf * s, ty - (0.22 + (dxf != 0) * -0.04) * s),
            )
