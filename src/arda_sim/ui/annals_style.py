"""Annals feed styling: the category buckets and the styled row delegate.

The four **category buckets** (see CONTEXT.md, "Annals & inspection") are a
presentation grouping over event types — the single type→bucket mapping lives
here so the row accents, the filter chips (ticket 04), and the event dossier
(ticket 03) all read the same one. An unmapped type falls in the neutral
``other`` bucket, so a newly-introduced event type renders legibly rather than
breaking the feed.

:class:`AnnalsDelegate` paints the two row kinds the model exposes: a year
header (``TA NNNN`` divider band) and an event row (bucket accent stripe,
importance-weighted text, pin glyph on placed events). Every row shares one
height so the view's uniform-item-size fast path holds across centuries.
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPolygon
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ..armies import ARMY_ARRIVED_EVENT, ARMY_DISBANDED_EVENT, ARMY_MUSTERED_EVENT
from ..characters import BIRTH_EVENT, DEATH_EVENT, DEPARTED_EVENT
from ..chronicle import IMPORTANT_THRESHOLD
from ..diplomacy import (
    MARRIAGE_EVENT,
    PROVIDER_PACT_EVENT,
    TREATY_EVENT,
    VASSALAGE_EVENT,
    WAR_DECLARED_EVENT,
    WAR_ENDED_EVENT,
)
from ..economy import FOUNDING_EVENT, ROAD_OPENED_EVENT, SETTLEMENT_GREW_EVENT
from ..entities import Event
from ..succession import ABSORPTION_EVENT, LINE_FAILED_EVENT, SUCCESSION_EVENT
from ..war import (
    BATTLE_EVENT,
    COASTAL_RAID_EVENT,
    CONQUEST_EVENT,
    RAZING_EVENT,
    SIEGE_EVENT,
)
from .annals_model import EventRole

# The four scannable buckets plus the neutral fallback.
WAR = "war"
DIPLOMACY = "diplomacy"
DYNASTY = "dynasty"
CONSTRUCTION = "construction"
OTHER = "other"

BUCKETS = (WAR, DIPLOMACY, DYNASTY, CONSTRUCTION)

# The single type→bucket mapping (chips and the dossier reuse this).
BUCKET_OF_TYPE: Dict[str, str] = {
    # war: the fighting itself, the hosts that carry it, and its declarations —
    # a war declared or ended reads as war to the chronicle's eye, wherever the
    # sim decides it.
    BATTLE_EVENT: WAR,
    SIEGE_EVENT: WAR,
    CONQUEST_EVENT: WAR,
    RAZING_EVENT: WAR,
    COASTAL_RAID_EVENT: WAR,
    ARMY_MUSTERED_EVENT: WAR,
    ARMY_ARRIVED_EVENT: WAR,
    ARMY_DISBANDED_EVENT: WAR,
    WAR_DECLARED_EVENT: WAR,
    WAR_ENDED_EVENT: WAR,
    # diplomacy: the peaceful bonds, marriage included — the chronicle groups a
    # dynastic match with the pacts it warms, not the cradle and the grave.
    TREATY_EVENT: DIPLOMACY,
    MARRIAGE_EVENT: DIPLOMACY,
    VASSALAGE_EVENT: DIPLOMACY,
    PROVIDER_PACT_EVENT: DIPLOMACY,
    # dynasty: lives, lines, and the seats they pass to.
    BIRTH_EVENT: DYNASTY,
    DEATH_EVENT: DYNASTY,
    DEPARTED_EVENT: DYNASTY,
    SUCCESSION_EVENT: DYNASTY,
    LINE_FAILED_EVENT: DYNASTY,
    ABSORPTION_EVENT: DYNASTY,
    # construction: the built world changing in peace.
    FOUNDING_EVENT: CONSTRUCTION,
    SETTLEMENT_GREW_EVENT: CONSTRUCTION,
    ROAD_OPENED_EVENT: CONSTRUCTION,
}


def bucket_of(event_type: str) -> str:
    """The category bucket an event type reads under (``other`` if unmapped)."""
    return BUCKET_OF_TYPE.get(event_type, OTHER)


# Mid-tone hues that read against both light and dark palettes; ``other`` is
# painted from the live palette instead so it stays theme-neutral.
BUCKET_COLORS: Dict[str, QColor] = {
    WAR: QColor("#b8483d"),
    DIPLOMACY: QColor("#3d7ab8"),
    DYNASTY: QColor("#8a5cb8"),
    CONSTRUCTION: QColor("#4c9a5e"),
}

_STRIPE_W = 3  # the bucket accent stripe, px
_PAD = 6  # horizontal padding inside a row, px
_V_PAD = 3  # vertical padding, px
_PIN_W = 12  # room reserved for the placed-event pin glyph, px


class AnnalsDelegate(QStyledItemDelegate):
    """Paints year-header bands and bucket-accented, importance-weighted event
    rows. All rows share one height (uniform-item-size fast path)."""

    # -- geometry ---------------------------------------------------------

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        height = option.fontMetrics.height() + 2 * _V_PAD
        return QSize(option.rect.width(), height)

    # -- painting ---------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        event: Optional[Event] = index.data(EventRole)
        painter.save()
        try:
            if event is None:
                self._paint_header(painter, option, index.data(Qt.DisplayRole))
            else:
                self._paint_event(painter, option, event, index.data(Qt.DisplayRole))
        finally:
            painter.restore()

    def _paint_header(
        self, painter: QPainter, option: QStyleOptionViewItem, text: str
    ) -> None:
        rect = option.rect
        painter.fillRect(rect, option.palette.alternateBase())
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(option.palette.text().color())
        text_rect = rect.adjusted(_PAD, 0, -_PAD, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text or "")
        # A hairline rule carries the divider across the rest of the band.
        fm = option.fontMetrics
        rule_x = text_rect.left() + fm.horizontalAdvance(text or "") + _PAD
        if rule_x < text_rect.right():
            rule = option.palette.mid().color()
            painter.setPen(rule)
            mid_y = rect.center().y()
            painter.drawLine(rule_x, mid_y, text_rect.right(), mid_y)

    def _paint_event(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        event: Event,
        text: str,
    ) -> None:
        rect = option.rect
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, option.palette.highlight())
        accent = BUCKET_COLORS.get(bucket_of(event.type))
        if accent is None:  # the neutral bucket takes its tone from the theme
            accent = option.palette.mid().color()
        painter.fillRect(
            QRect(rect.left(), rect.top(), _STRIPE_W, rect.height()), accent
        )
        # Importance decides the text's weight: full-strength bold at/above the
        # important cut, dimmed regular below it (visible under "show all").
        important = event.importance >= IMPORTANT_THRESHOLD
        font = option.font
        font.setBold(important)
        painter.setFont(font)
        text_color = (
            option.palette.highlightedText().color()
            if option.state & QStyle.State_Selected
            else option.palette.text().color()
        )
        if not important:
            text_color = QColor(text_color)
            text_color.setAlpha(140)
        painter.setPen(text_color)
        placed = event.location_id is not None
        text_rect = rect.adjusted(
            _STRIPE_W + _PAD, 0, -(_PIN_W + _PAD) if placed else -_PAD, 0
        )
        fm = option.fontMetrics
        elided = fm.elidedText(text or "", Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
        if placed:
            self._paint_pin(painter, option, text_color)

    def _paint_pin(
        self, painter: QPainter, option: QStyleOptionViewItem, color: QColor
    ) -> None:
        """A small map pin (head + point) at the row's right edge — the placed-
        event affordance; inert until ticket 02 wires the click."""
        rect = option.rect
        cx = rect.right() - _PIN_W // 2 - 2
        cy = rect.center().y() - 2
        head = 5
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPoint(cx, cy), head // 2 + 1, head // 2 + 1)
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(cx - 2, cy + 2),
                    QPoint(cx + 2, cy + 2),
                    QPoint(cx, cy + 6),
                ]
            )
        )
