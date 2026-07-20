"""The tile theme: terrain colours, faction tints, and per-tile painting.

Renders the :class:`~arda_sim.tiles.TileGrid` in the Dwarf-Fortress idiom —
each tile is a solid terrain colour with a small distinguishing motif, and
faction territory is a translucent owner tint painted over the terrain (ADR-0001).

This is the render *theme* seam: the geometry (which tile, where) lives in the
view; the look (colour, motif) lives here. A sprite atlas (the Kenney pack the
ADR names) can later replace :func:`paint_terrain_tile` without touching the
view. Colour lookups are Qt-only (no ``QApplication`` needed), so they stay
unit-testable headlessly.
"""

from __future__ import annotations

from typing import Dict, Tuple

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter

from ..tiles import Terrain

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


def paint_terrain_tile(
    painter: QPainter, terrain: Terrain, x: float, y: float, size: float
) -> None:
    """Paint one terrain tile at ``(x, y)`` with side ``size`` in scene units.

    Draws the flat base fill plus a light per-terrain motif so terrains stay
    legible without relying on colour alone (mountains get a peak, forests a
    tree, water a ripple, etc.).
    """
    rect = QRectF(x, y, size, size)
    base = terrain_color(terrain)
    painter.fillRect(rect, base)
    painter.setPen(base.darker(125))

    if terrain == Terrain.MOUNTAIN:
        peak = base.lighter(135)
        painter.setBrush(peak)
        painter.drawPolygon(
            _triangle(x + size * 0.5, y + size * 0.18, size * 0.34),
        )
    elif terrain == Terrain.HILLS:
        painter.setBrush(base.lighter(115))
        painter.drawEllipse(QRectF(x + size * 0.2, y + size * 0.4, size * 0.6, size * 0.5))
    elif terrain == Terrain.FOREST:
        painter.setBrush(base.darker(130))
        painter.drawPolygon(
            _triangle(x + size * 0.5, y + size * 0.2, size * 0.3),
        )
    elif terrain in (Terrain.RIVER, Terrain.LAKE, Terrain.SEA):
        painter.setPen(base.lighter(130))
        mid = y + size * 0.5
        painter.drawLine(int(x + size * 0.2), int(mid), int(x + size * 0.8), int(mid))
    elif terrain == Terrain.MARSH:
        painter.setPen(base.darker(140))
        for frac in (0.35, 0.6):
            yy = int(y + size * frac)
            painter.drawLine(int(x + size * 0.2), yy, int(x + size * 0.8), yy)
    elif terrain == Terrain.ROAD:
        painter.setPen(base.darker(135))
        painter.drawLine(int(x + size * 0.5), int(y), int(x + size * 0.5), int(y + size))


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
