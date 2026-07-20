"""The map canvas: the v7 image in a pannable, zoomable ``QGraphicsView``.

The image is a ``QGraphicsPixmapItem`` at the scene origin, so scene coordinates
*are* v7 pixel coordinates — the same coordinate space geometry is authored in
(ticket 01). Region polygons and location/army/Ring items will be added on top
as those systems land; today the scene holds only the backdrop.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from .assets import v7_map_path

_MIN_SCALE = 0.05
_MAX_SCALE = 8.0
_ZOOM_STEP = 1.15


class MapView(QGraphicsView):
    """Pan (drag) + zoom (wheel) over the v7 map backdrop."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        pixmap = QPixmap(str(v7_map_path()))
        self._backdrop: QGraphicsPixmapItem = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(self._backdrop.boundingRect())

        self.setDragMode(QGraphicsView.ScrollHandDrag)  # click-drag to pan
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self._scale = 1.0

    def wheelEvent(self, event) -> None:
        """Zoom toward the cursor, clamped so the map can't invert or vanish."""
        factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
        new_scale = self._scale * factor
        if new_scale < _MIN_SCALE or new_scale > _MAX_SCALE:
            return
        self._scale = new_scale
        self.scale(factor, factor)

    def fit_map(self) -> None:
        """Fit the whole backdrop in the viewport (used on first show)."""
        self.fitInView(self._backdrop, Qt.KeepAspectRatio)
        # Re-sync the tracked scale to the transform fitInView actually applied,
        # so the wheel-zoom clamps stay honest relative to the fitted view.
        self._scale = self.transform().m11()
