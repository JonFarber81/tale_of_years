"""The map canvas: the tile grid drawn as a pannable, zoomable DF-style map.

The world *is* a grid of terrain tiles (ADR-0001), so the scene is laid out in
**tile-pixel** coordinates: tile ``(col, row)`` occupies scene rect
``(col*TILE, row*TILE, TILE, TILE)``. Three stacked layers draw it:

* a **terrain** pixmap — static config, rendered once;
* an **owner-tint** pixmap — faction territory, regenerated via :meth:`refresh_owners`
  whenever ownership changes (borders derived from the grid, not stored);
* **site** markers + labels on top.

Left-drag pans, wheel zooms toward the cursor, and a click that doesn't drag
emits :attr:`tileClicked` so the window can inspect that tile.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from ..armies import Army
from ..tiles import UNOWNED, TileGrid
from . import tile_render

# Scene pixels per tile. Big enough that motifs and labels are legible when
# zoomed in; the whole theatre still fits when zoomed out.
TILE = 24

_MIN_SCALE = 0.05
_MAX_SCALE = 8.0
_ZOOM_STEP = 1.15
# A press-to-release move shorter than this (in view pixels) counts as a click,
# not a pan — so tile selection survives the ScrollHandDrag pan mode.
_CLICK_SLOP = 4

# A salience pulse: how long the transient flash lives (ms) and how far it grows.
_PULSE_MS = 900
_PULSE_GROWTH = 1.6
_PULSE_BASE_RADIUS = TILE * 0.7


class MapView(QGraphicsView):
    """Pan/zoom over the tile grid; click a tile to select it."""

    tileClicked = Signal(int, int)  # (col, row)

    def __init__(self, grid: TileGrid, parent=None) -> None:
        super().__init__(parent)
        self._grid = grid
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setSceneRect(0, 0, grid.width * TILE, grid.height * TILE)

        self._terrain_item: QGraphicsPixmapItem = self._scene.addPixmap(self._render_terrain())
        self._owner_item: QGraphicsPixmapItem = self._scene.addPixmap(QPixmap())
        self._owner_item.setZValue(1)
        self._add_sites()
        self.refresh_owners()
        # Army markers, rebuilt each tick from the snapshot's hosts (ticket 10).
        self._army_items: List[QGraphicsItem] = []

        self.setDragMode(QGraphicsView.ScrollHandDrag)  # left-drag to pan
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHints(QPainter.Antialiasing)
        self.setBackgroundBrush(Qt.black)
        self._scale = 1.0
        self._press_pos: Optional[QPointF] = None
        # Live salience-pulse animations, kept referenced so Qt doesn't collect
        # them mid-flight; each removes its own item and drops itself on finish.
        self._pulses: List[QVariantAnimation] = []

    # -- layers ----------------------------------------------------------

    def _render_terrain(self) -> QPixmap:
        """Draw the static terrain layer once into a pixmap."""
        pixmap = QPixmap(self._grid.width * TILE, self._grid.height * TILE)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        for col, row, terrain in self._grid.iter_tiles():
            tile_render.paint_terrain_tile(painter, terrain, col * TILE, row * TILE, TILE)
        painter.end()
        return pixmap

    def refresh_owners(self) -> None:
        """Regenerate the faction-tint layer from the grid's current owners.

        Owned tiles get a translucent tint; border tiles (touching a different
        owner — derived, never stored) get a crisp faction-coloured stroke.
        """
        grid = self._grid
        pixmap = QPixmap(grid.width * TILE, grid.height * TILE)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setPen(Qt.NoPen)
        for row in range(grid.height):
            for col in range(grid.width):
                owner = grid.owner_at(col, row)
                if owner == UNOWNED:
                    continue
                rect = QRectF(col * TILE, row * TILE, TILE, TILE)
                painter.fillRect(rect, tile_render.owner_tint(owner))
                if grid.is_border(col, row):
                    painter.setPen(tile_render.faction_color(owner))
                    painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
                    painter.setPen(Qt.NoPen)
        painter.end()
        self._owner_item.setPixmap(pixmap)

    def refresh_armies(self, armies: Iterable[Army]) -> None:
        """Redraw the host markers for the current tick from the snapshot's armies.

        Each living host is a faction-coloured disc on its tile, so the viewer can
        follow campaigns marching across the map. Cheap to rebuild wholesale —
        there are only a handful of hosts afield at once.
        """
        for item in self._army_items:
            self._scene.removeItem(item)
        self._army_items = []
        for army in armies:
            if not army.alive:
                continue
            cx = army.col * TILE + TILE / 2
            cy = army.row * TILE + TILE / 2
            color = tile_render.faction_color(army.faction_id or UNOWNED)
            marker = self._scene.addEllipse(
                cx - TILE * 0.34,
                cy - TILE * 0.34,
                TILE * 0.68,
                TILE * 0.68,
                QPen(QColor(20, 20, 20), 2),
                color,
            )
            marker.setZValue(4)  # above sites, below salience pulses
            self._army_items.append(marker)

    def _add_sites(self) -> None:
        """Draw a marker + haloed label for each authored site."""
        from PySide6.QtGui import QColor

        for site in self._grid.sites:
            cx = site.col * TILE + TILE / 2
            cy = site.row * TILE + TILE / 2
            marker = self._scene.addEllipse(
                cx - TILE * 0.28,
                cy - TILE * 0.28,
                TILE * 0.56,
                TILE * 0.56,
                QColor(20, 20, 20),
                QColor(245, 235, 200),
            )
            marker.setZValue(2)
            label = self._scene.addText(site.name)
            label.setDefaultTextColor(QColor(20, 20, 20))
            label.setPos(cx + TILE * 0.3, cy - TILE * 0.7)
            label.setZValue(3)

    # -- interaction -----------------------------------------------------

    def wheelEvent(self, event) -> None:
        """Zoom toward the cursor, clamped so the map can't invert or vanish."""
        factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
        new_scale = self._scale * factor
        if new_scale < _MIN_SCALE or new_scale > _MAX_SCALE:
            return
        self._scale = new_scale
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        self._press_pos = event.position() if hasattr(event, "position") else event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        pos = event.position() if hasattr(event, "position") else event.pos()
        if self._press_pos is not None:
            moved = (pos - self._press_pos).manhattanLength()
            if moved <= _CLICK_SLOP:
                self._emit_tile_at(pos)
        self._press_pos = None

    def _emit_tile_at(self, view_pos) -> None:
        point = view_pos.toPoint() if hasattr(view_pos, "toPoint") else view_pos
        scene = self.mapToScene(point)
        col = int(scene.x() // TILE)
        row = int(scene.y() // TILE)
        if self._grid.in_bounds(col, row):
            self.tileClicked.emit(col, row)

    def fit_map(self) -> None:
        """Fit the whole grid in the viewport (used on first show)."""
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._scale = self.transform().m11()

    # -- salience pulses -------------------------------------------------

    def pulse(self, col: int, row: int) -> None:
        """Flash a transient ring at a tile to draw the eye to a salient event.

        A ring that grows and fades over ~1s, then removes itself. Purely
        decorative and self-cleaning, so firing several a year is harmless.
        """
        cx = col * TILE + TILE / 2
        cy = row * TILE + TILE / 2
        ring: QGraphicsEllipseItem = self._scene.addEllipse(
            QRectF(), QPen(QColor(255, 226, 138), 2), Qt.NoBrush
        )
        ring.setZValue(5)

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(_PULSE_MS)

        def on_tick(t: float) -> None:
            radius = _PULSE_BASE_RADIUS * (1.0 + _PULSE_GROWTH * t)
            ring.setRect(cx - radius, cy - radius, 2 * radius, 2 * radius)
            ring.setOpacity(max(0.0, 1.0 - t))

        def on_done() -> None:
            self._scene.removeItem(ring)
            if anim in self._pulses:
                self._pulses.remove(anim)

        anim.valueChanged.connect(on_tick)
        anim.finished.connect(on_done)
        on_tick(0.0)
        self._pulses.append(anim)
        anim.start()
