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

from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsView,
)

from ..armies import Army
from ..tiles import UNOWNED, TileGrid
from . import tile_render

# Scene pixels per tile. Big enough that motifs and labels are legible when
# zoomed in; the whole theatre still fits when zoomed out.
TILE = 24

# The zoom-out floor is dynamic — the whole map just fitting the viewport (see
# :meth:`MapView._min_scale`); this constant is only the fallback before the
# view has a real viewport. Zoom-in stays a fixed close-up cap.
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

# A battle marker: crossed swords that flash on the tile where a battle resolved,
# distinct from the salience ring (colour, motif, and its own z-layer above it).
# It lives longer than the pulse so a war reads even when both fire on one tile.
_BATTLE_MS = 1600
_BATTLE_Z = 6  # above salience pulses (z=5); its own layer, untouched by rebuilds
_BATTLE_STEEL = QColor(232, 236, 240)  # blade
_BATTLE_EDGE = QColor(120, 20, 20)  # dark red outline — the blood note

# -- site labels ------------------------------------------------------------
# Labels are screen-fixed annotations (ItemIgnoresTransformations), so they do
# not shrink with the map and would all pile up at far zoom. Tier gating is the
# chosen declutter mechanism — collision culling was considered and deferred
# (spec / ticket 02): lower-rank labels simply stay hidden until the view is
# zoomed in enough to give them room. Thresholds are tuned by eye against
# ``MapView._scale`` (fit-whole-map is ~0.01 on the shipped grid; the zoom-in
# cap is ``_MAX_SCALE`` = 8.0).
_LABEL_TIER1_SCALE = 0.5  # towns / forts (tier 1) appear from mid-zoom
_LABEL_TIER0_SCALE = 1.5  # ruins / everything else (tier 0) only when zoomed close
_LABEL_FONT_SIZE = 9  # deliberate point size — stop inheriting the app default

# -- march cue --------------------------------------------------------------
# A small faction-coloured arrowhead at a marching host's leading edge, pointing
# to its next path tile (ticket 06). Distances are fractions of a tile measured
# from the marker centre: the tip sits just outside the disc, the base overlaps
# it so the wedge reads as attached to the host. Kept small and semi-opaque so
# the disc+sprite marker stays dominant and it doesn't clutter full-map zoom.
_MARCH_CUE_TIP = TILE * 0.66  # tip distance from tile centre (leading edge)
_MARCH_CUE_BASE = TILE * 0.34  # base distance from tile centre
_MARCH_CUE_HALFWIDTH = TILE * 0.18  # half the arrowhead's base width
_MARCH_CUE_ALPHA = 205  # subtle, not solid


class MapView(QGraphicsView):
    """Pan/zoom over the tile grid; click a tile to select it."""

    tileClicked = Signal(int, int)  # (col, row)

    def __init__(
        self,
        grid: TileGrid,
        faction_people: Optional[Dict[int, str]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._grid = grid
        # faction id -> people string, so a host marker can draw its folk's sprite
        # over the faction colour (map-visuals ticket 03). Empty until threaded.
        self._faction_people: Dict[int, str] = faction_people or {}
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
        self._update_label_visibility()  # initial tier gating at the default scale
        self._press_pos: Optional[QPointF] = None
        # Live salience-pulse animations, kept referenced so Qt doesn't collect
        # them mid-flight; each removes its own item and drops itself on finish.
        self._pulses: List[QVariantAnimation] = []
        # Live battle-marker animations, on their own list/z-layer so a
        # refresh_armies/refresh_owners rebuild never touches them (ticket 07).
        self._battle_markers: List[QVariantAnimation] = []

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

        Each living host is a faction-coloured backing disc with its people's
        sprite blitted on top, so the viewer reads *whose* (colour) and *what
        folk* (sprite) at a glance — and armies stay distinct from site markers.
        Cheap to rebuild wholesale — only a handful of hosts are afield at once.
        """
        for item in self._army_items:
            self._scene.removeItem(item)
        self._army_items = []
        for army in armies:
            if not army.alive:
                continue
            item = self._army_marker(army)
            self._scene.addItem(item)
            self._army_items.append(item)
            cue = self._march_cue(army)
            if cue is not None:
                self._scene.addItem(cue)
                self._army_items.append(cue)

    def _march_cue(self, army: Army) -> Optional[QGraphicsPolygonItem]:
        """A subtle direction arrowhead for a host mid-march, else ``None``.

        Points from the host's tile toward its next path tile — a small wedge at
        the marker's leading edge that says *this host is moving that way*.
        Idle/garrisoned hosts (empty ``path``) get no cue. Added as a plain scene
        item so it scales with the map like the marker it rides on.
        """
        if not army.path:
            return None
        dx = army.path[0][0] - army.col
        dy = army.path[0][1] - army.row
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:  # already on the next tile (degenerate) — no direction
            return None
        ux, uy = dx / length, dy / length
        px, py = -uy, ux  # unit perpendicular, for the base corners
        cx = army.col * TILE + TILE / 2
        cy = army.row * TILE + TILE / 2
        tip = QPointF(cx + ux * _MARCH_CUE_TIP, cy + uy * _MARCH_CUE_TIP)
        base_cx = cx + ux * _MARCH_CUE_BASE
        base_cy = cy + uy * _MARCH_CUE_BASE
        left = QPointF(
            base_cx + px * _MARCH_CUE_HALFWIDTH, base_cy + py * _MARCH_CUE_HALFWIDTH
        )
        right = QPointF(
            base_cx - px * _MARCH_CUE_HALFWIDTH, base_cy - py * _MARCH_CUE_HALFWIDTH
        )
        color = QColor(tile_render.faction_color(army.faction_id or UNOWNED))
        color.setAlpha(_MARCH_CUE_ALPHA)
        cue = QGraphicsPolygonItem(QPolygonF([tip, left, right]))
        cue.setBrush(color)
        cue.setPen(QPen(QColor(20, 20, 20), 0.5))  # thin dark edge for legibility
        cue.setZValue(4)  # with the marker: above sites/labels, below pulses (z=5)
        return cue

    def _army_marker(self, army: Army) -> QGraphicsPixmapItem:
        """A scene pixmap for one host: a faction-coloured disc (dark outline)
        with the people sprite scaled on top, sized to one tile.

        Rendered into a supersampled pixmap then scaled back down for a smooth
        disc edge, and added as a plain scene item so it scales *with* the map
        (hosts are map objects, not screen-fixed annotations).
        """
        ss = 4  # supersample factor: draw big, then scale the item to one tile
        span = TILE * ss
        pixmap = QPixmap(span, span)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        # Backing disc: slightly smaller than the old 0.68·TILE marker.
        color = tile_render.faction_color(army.faction_id or UNOWNED)
        diam = span * 0.60
        off = (span - diam) / 2
        painter.setPen(QPen(QColor(20, 20, 20), 2 * ss))
        painter.setBrush(color)
        painter.drawEllipse(QRectF(off, off, diam, diam))
        # People sprite centred over the disc, scaled into the cell.
        people = self._faction_people.get(army.faction_id)
        sprite = span * 0.72
        s_off = (span - sprite) / 2
        tile_render.paint_people_sprite(painter, people, s_off, s_off, sprite)
        painter.end()

        item = QGraphicsPixmapItem(pixmap)
        item.setScale(1.0 / ss)
        item.setPos(army.col * TILE, army.row * TILE)
        item.setZValue(4)  # above sites/labels, below salience pulses (z=5)
        return item

    def _add_sites(self) -> None:
        """Draw a marker + haloed label for each authored site.

        Markers are map objects and scale with the view; labels are annotations
        that hold a constant screen size (``ItemIgnoresTransformations``) and are
        tier-gated on zoom (see :meth:`_update_label_visibility`). Each label is
        kept on ``self._site_labels`` as ``(item, tier)`` so zoom changes can
        toggle its visibility.
        """
        label_font = QFont()
        label_font.setPointSize(_LABEL_FONT_SIZE)
        label_font.setBold(True)

        # (label_item, tier) pairs, toggled by _update_label_visibility on zoom.
        self._site_labels: List[tuple] = []

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
            label.setFont(label_font)
            # Light text over a dark halo reads over any terrain.
            label.setDefaultTextColor(QColor(245, 235, 200))
            # A halo: a zero-offset dark blur behind the glyphs (not a shadow).
            halo = QGraphicsDropShadowEffect()
            halo.setBlurRadius(4)
            halo.setColor(QColor(10, 10, 10))
            halo.setOffset(0, 0)
            label.setGraphicsEffect(halo)
            # Screen-fixed: the label keeps its size at any zoom. Its origin is
            # pinned to the mapped scene point, so the offset is re-tuned by eye
            # (the old value was tuned for scene-scaled text) to sit up-right of
            # the marker.
            label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            label.setPos(cx + TILE * 0.30, cy - TILE * 0.55)
            label.setZValue(3)
            self._site_labels.append((label, site.tier))

    def _update_label_visibility(self) -> None:
        """Tier-gate the site labels for the current zoom (``self._scale``).

        Cities (tier 2) are always labelled; towns/forts (tier 1) appear from a
        mid-zoom threshold; ruins and everything else (tier 0) only when zoomed
        close. This is the declutter mechanism — collision culling is out of
        scope (spec / ticket 02).
        """
        for label, tier in self._site_labels:
            if tier >= 2:
                visible = True
            elif tier == 1:
                visible = self._scale >= _LABEL_TIER1_SCALE
            else:
                visible = self._scale >= _LABEL_TIER0_SCALE
            label.setVisible(visible)

    # -- interaction -----------------------------------------------------

    def wheelEvent(self, event) -> None:
        """Zoom toward the cursor, clamped between fit-the-map and close-up."""
        self._apply_zoom(_ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP)

    def _apply_zoom(self, factor: float) -> None:
        """Scale by ``factor``, landing exactly on a clamp rather than skipping it."""
        new_scale = min(max(self._scale * factor, self._min_scale()), _MAX_SCALE)
        if new_scale == self._scale:
            return
        factor = new_scale / self._scale
        self._scale = new_scale
        self.scale(factor, factor)
        self._update_label_visibility()

    def _min_scale(self) -> float:
        """The zoom-out floor: the whole map just fits the viewport.

        Depends on the live viewport size, so it is computed per zoom rather
        than fixed — a bigger window may zoom out further in absolute scale yet
        never past "the entire map is visible".
        """
        scene = self._scene.sceneRect()
        viewport = self.viewport().rect()
        if scene.isEmpty() or viewport.isEmpty():
            return _MIN_SCALE
        return min(
            viewport.width() / scene.width(), viewport.height() / scene.height()
        )

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
        self._update_label_visibility()

    def focus_tile(self, col: int, row: int) -> None:
        """Center the view on a tile and flash a pulse there.

        The annals-click jump (annals-ui ticket 02): a pan plus the same
        transient, self-cleaning ring the salience pulses use — nothing
        persists on the map afterwards.
        """
        self.centerOn(col * TILE + TILE / 2, row * TILE + TILE / 2)
        self.pulse(col, row)

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

    # -- battle markers --------------------------------------------------

    def battle_marker(self, col: int, row: int) -> None:
        """Flash a crossed-swords mark on the tile where a battle resolved.

        Visually distinct from the salience pulse: a steel-and-blood *motif*
        (two crossed blades) rather than an expanding ring, on its own z-layer
        (``_BATTLE_Z`` = 6, above the z=5 pulse) so both read when they coincide.
        Self-cleaning — a brief flare-then-fade that removes its own scene item
        and drops itself from ``self._battle_markers`` on finish, mirroring
        :meth:`pulse`. It lives on that list, never in ``self._army_items``, so a
        refresh_armies/refresh_owners rebuild leaves it untouched.
        """
        item = self._scene.addPixmap(self._crossed_swords_pixmap())
        # Centre the one-tile motif on the tile centre and scale with the map.
        item.setOffset(-TILE / 2, -TILE / 2)
        item.setPos(col * TILE + TILE / 2, row * TILE + TILE / 2)
        item.setZValue(_BATTLE_Z)

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(_BATTLE_MS)

        def on_tick(t: float) -> None:
            # A sharp flare in, then a slow fade out; a slight overshoot in size
            # gives the "clash" its impact before it settles and dims away.
            item.setScale(1.0 + 0.35 * (1.0 - t))
            item.setOpacity(1.0 if t < 0.15 else max(0.0, 1.0 - (t - 0.15) / 0.85))

        def on_done() -> None:
            self._scene.removeItem(item)
            if anim in self._battle_markers:
                self._battle_markers.remove(anim)

        anim.valueChanged.connect(on_tick)
        anim.finished.connect(on_done)
        on_tick(0.0)
        self._battle_markers.append(anim)
        anim.start()

    def _crossed_swords_pixmap(self) -> QPixmap:
        """A one-tile crossed-swords glyph: two steel blades with a dark-red
        outline, supersampled for a clean edge then scaled onto the item."""
        ss = 4
        span = TILE * ss
        pixmap = QPixmap(span, span)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        c = span / 2
        reach = span * 0.34  # how far each blade runs from centre
        for sign in (1, -1):  # the two crossing diagonals
            painter.setPen(QPen(_BATTLE_EDGE, span * 0.11, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(
                QPointF(c - reach, c - sign * reach),
                QPointF(c + reach, c + sign * reach),
            )
        for sign in (1, -1):
            painter.setPen(QPen(_BATTLE_STEEL, span * 0.055, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(
                QPointF(c - reach, c - sign * reach),
                QPointF(c + reach, c + sign * reach),
            )
        painter.end()
        item_pixmap = pixmap.scaled(
            TILE, TILE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        return item_pixmap
