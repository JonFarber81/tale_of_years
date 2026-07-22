"""The main window: map canvas, timeline toolbar, annals strip, Codex pane.

Owns the background sim thread and translates its ``(snapshot, events)`` per-tick
stream into UI updates. Playback commands go to the worker as queued signals
(thread-safe); snapshots come back and drive the date label (year + month), the
scrub slider (in absolute ticks), and the annals cap. The window renders only
from snapshots — never the live world.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from PySide6.QtCore import QMetaObject, Qt, QThread, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QDockWidget,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QPushButton,
    QSlider,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import START_YEAR
from ..armies import Army
from ..war import BATTLE_EVENT, SIEGE_EVENT
from ..chronicle import AnnalsFilter, pulse_events, show_all_filter
from ..entities import Event
from ..playback import Playback
from ..ring import the_ring
from ..snapshot import Snapshot
from ..tiles import TileGrid
from ..world import format_tick
from .annals_model import AnnalsModel, EventRole
from .annals_style import (
    BUCKET_COLORS,
    BUCKET_LABELS,
    BUCKETS,
    AnnalsDelegate,
    types_in_bucket,
)
from .codex import CodexAddress, CodexPane
from .codex_pages import CodexPages, RingTrendSample, living_armies
from .theme import BRONZE, serif_font
from .map_view import MapView
from .sim_worker import SimWorker

_MIN_TPS = 0.25
_MAX_TPS = 60.0
_DEFAULT_TPS = 2.0


class MainWindow(QMainWindow):
    """Watch-only shell over a seeded run."""

    # Playback commands, wired to the worker's slots across the thread boundary.
    playRequested = Signal()
    pauseRequested = Signal()
    stepRequested = Signal()
    speedChanged = Signal(float)
    seekRequested = Signal(int)

    def __init__(
        self,
        playback: Playback,
        grid: TileGrid,
        faction_names: Optional[Dict[int, str]] = None,
        faction_people: Optional[Dict[int, str]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._playback = playback
        self._grid = grid
        self._faction_names = faction_names or {}
        # faction id -> people string, forwarded to the map so host markers can
        # draw their folk's sprite over the faction colour (map-visuals 03).
        self._faction_people = faction_people or {}
        # Latest renderable state + the accumulated event stream, so tile/faction
        # inspection reads from snapshots and the feed, never the live world.
        self._latest_snapshot: Optional[Snapshot] = None
        self._events: List[Event] = []
        # Per-tick trace of the Ring's corruption/pull — snapshots carry only the
        # current scalars, so the Ring page's sparkline reads from a series the
        # window accumulates as time advances (like the event feed). Each sample
        # a RingTrendSample per tick; appended only on a forward advance so a
        # scrub-restore never duplicates or reorders it (issue #23).
        self._ring_trend: List[RingTrendSample] = []
        self._ring_trend_tick = -1
        self._display_year = START_YEAR - 1
        # The headless Codex page-render library (#39): the window keeps the
        # per-tick context flowing into it via update(), and delegates its Codex
        # router (_render_page) to it. It reads the grid and the faction-name
        # overrides once, and the live snapshot/events/trend each tick.
        self._pages = CodexPages(grid, self._faction_names)
        self._syncing_slider = False
        # The frontier as last reported by the worker, in absolute ticks (never
        # read cross-thread from the worker-owned Playback). Nothing simulated yet,
        # so it sits one tick before the first tick (tick 0).
        self._frontier = -1
        self.setWindowTitle("The Tale of Years — the Third Age unfolds")

        self._map = MapView(grid, self._faction_people, self)
        self._map.tileClicked.connect(self._on_tile_clicked)
        self.setCentralWidget(self._map)
        self._build_toolbar()
        self._annals_model = AnnalsModel(self)
        self._build_docks()
        self._start_worker(playback)

    # -- construction ----------------------------------------------------

    def _build_toolbar(self) -> None:
        bar = QToolBar("Timeline", self)
        bar.setMovable(False)
        self.addToolBar(bar)

        self._play_action = bar.addAction("▶ Play", self.playRequested.emit)
        self._pause_action = bar.addAction("⏸ Pause", self.pauseRequested.emit)
        self._step_action = bar.addAction("⏭ Step", self.stepRequested.emit)

        bar.addSeparator()
        bar.addWidget(QLabel(" Speed ", self))
        self._speed = QDoubleSpinBox(self)
        self._speed.setRange(_MIN_TPS, _MAX_TPS)
        self._speed.setValue(_DEFAULT_TPS)
        self._speed.setSuffix(" yr/s")
        self._speed.valueChanged.connect(self.speedChanged.emit)
        bar.addWidget(self._speed)

        bar.addSeparator()
        # The feed defaults to important-only; this toggles "show all" (ticket 06).
        self._show_all_action = bar.addAction("Show all", self._on_show_all_toggled)
        self._show_all_action.setCheckable(True)

        bar.addSeparator()
        # The scrub slider works in absolute ticks (months). It starts collapsed
        # at tick 0 and grows its maximum as the frontier advances.
        self._scrub = QSlider(Qt.Horizontal, self)
        self._scrub.setRange(0, 0)
        self._scrub.setEnabled(False)  # nothing simulated yet
        self._scrub.valueChanged.connect(self._on_scrub)
        bar.addWidget(self._scrub)

        self._year_label = QLabel(f"TA {START_YEAR}", self)
        self._year_label.setMinimumWidth(180)
        self._year_label.setAlignment(Qt.AlignCenter)
        # Prominent: the current date is the viewer's anchor in time. In the
        # chronicle's serif voice, gilt bronze — the running head of the annals.
        font = serif_font(self.font().pointSize() + 5, bold=True)
        self._year_label.setFont(font)
        self._year_label.setStyleSheet(f"color: {BRONZE.name()};")
        bar.addWidget(self._year_label)

    def _build_docks(self) -> None:
        annals_view = QListView(self)
        annals_view.setModel(self._annals_model)
        annals_view.setUniformItemSizes(True)  # keeps the virtualized list fast
        annals_view.setItemDelegate(AnnalsDelegate(annals_view))
        annals_view.clicked.connect(self._on_annals_event_clicked)
        self._annals_view = annals_view

        # The bucket chips: the color legend doubled as a filter (ticket 04).
        # All on by default; an unchecked chip hides its bucket's event types.
        self._bucket_chips: Dict[str, QPushButton] = {}
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(4, 4, 4, 0)
        chip_row.setSpacing(6)
        # Every chip is drawn bold in both states, so toggling checked never
        # changes its width. Earlier the bold was applied only on :checked, which
        # widened the label *after* the layout had reserved the non-bold width —
        # the surplus bled past the border and the chips overlapped. We reserve
        # the bold width up front and use colour alone to mark exclusion.
        bold_font = self.font()
        bold_font.setBold(True)
        bold_metrics = QFontMetrics(bold_font)
        for bucket in BUCKETS:
            label = BUCKET_LABELS[bucket]
            chip = QPushButton(label, self)
            chip.setCheckable(True)
            chip.setChecked(True)
            chip.setToolTip(f"Show or hide {label.lower()} events")
            color = BUCKET_COLORS[bucket].name()
            chip.setStyleSheet(
                "QPushButton { padding: 1px 8px; border: 1px solid palette(mid);"
                f" border-left: 4px solid {color}; border-radius: 3px;"
                " font-weight: bold; color: palette(mid); }"
                " QPushButton:checked { color: palette(text);"
                " border-color: palette(highlight); }"
            )
            # padding (8+8) + accent stripe (4) + borders (1+1) + a little slack,
            # so the styled sizeHint can never under-reserve the bold label.
            chip.setMinimumWidth(bold_metrics.horizontalAdvance(label) + 24)
            chip.toggled.connect(self._apply_annals_filter)
            chip_row.addWidget(chip)
            self._bucket_chips[bucket] = chip
        chip_row.addStretch(1)

        annals_panel = QWidget(self)
        panel_layout = QVBoxLayout(annals_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(2)
        panel_layout.addLayout(chip_row)
        panel_layout.addWidget(annals_view)
        # The Annals strip spans the window's foot (ADR-0014): the feed is the
        # chronicle's ticker, freeing the right side for the one Codex pane.
        # Both bottom corners belong to it explicitly — Qt's default corner
        # ownership would let the Codex dock reach down and cut the strip short.
        self.setCorner(Qt.BottomLeftCorner, Qt.BottomDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.BottomDockWidgetArea)
        annals_dock = QDockWidget("Annals", self)
        annals_dock.setTitleBarWidget(self._gilt_titlebar("Annals"))
        annals_dock.setWidget(annals_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, annals_dock)

        # The Codex (ADR-0014, #36): the single browser pane where every
        # dossier and index is a page. The pane owns navigation (history,
        # omnibox, links); this window owns what pages say (_render_page).
        self._codex = CodexPane(self._render_page, self)
        # Activating a page can move the map (ADR-0014's two-way link): opening a
        # host page centres its marker — the armies-index row jump of #17.
        self._codex.navigated.connect(self._on_codex_navigated)
        codex_dock = QDockWidget("Codex", self)
        codex_dock.setTitleBarWidget(self._gilt_titlebar("Codex"))
        codex_dock.setWidget(self._codex)
        self.addDockWidget(Qt.RightDockWidgetArea, codex_dock)

    def _gilt_titlebar(self, text: str) -> QLabel:
        """A dock's title as a gilt serif banner (Fusion won't colour the native
        title text via stylesheet, so we own the whole title bar). Replacing the
        title bar also pins these two core panes in place — no stray close/float.
        """
        label = QLabel(text, self)
        label.setFont(serif_font(self.font().pointSize() + 1, bold=True))
        label.setStyleSheet(
            f"color: {BRONZE.name()}; background: #1e1f23; padding: 4px 8px;"
        )
        return label

    def _start_worker(self, playback: Playback) -> None:
        self._thread = QThread(self)
        self._worker = SimWorker(playback)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.setup)
        self._thread.finished.connect(self._worker.deleteLater)
        self._worker.tickAdvanced.connect(self._on_tick_advanced)
        self._worker.frontierChanged.connect(self._on_frontier_changed)

        self.playRequested.connect(self._worker.play)
        self.pauseRequested.connect(self._worker.pause)
        self.stepRequested.connect(self._worker.step)
        self.speedChanged.connect(self._worker.set_speed)
        self.seekRequested.connect(self._worker.seek)

        self._thread.start()

    # -- worker -> UI ----------------------------------------------------

    def _on_tick_advanced(self, snapshot: Snapshot, events: List[Event]) -> None:
        self._latest_snapshot = snapshot
        self._display_year = snapshot.year
        if events:  # a live advance; a scrub-restore carries none
            self._annals_model.append_events(events)
            self._events.extend(events)
            self._fire_pulses(events)
            self._fire_battle_markers(snapshot, events)
        self._accumulate_ring_trend(snapshot)
        # Refresh the Codex's read context from this tick (runs on scrubs too, so
        # a scrubbed-to year renders from its own snapshot/trend).
        self._pages.update(
            snapshot=snapshot,
            events=self._events,
            display_year=self._display_year,
            ring_trend=self._ring_trend,
        )
        self._map.refresh_armies(living_armies(snapshot))
        self._map.refresh_ring(the_ring(snapshot))  # keep the Ring findable (ticket 13)
        # Follow site kind/tier churn (founded/grown/razed, ticket 04). Cheap: the
        # view skips the rebuild unless a marker actually changed. Runs on scrubs
        # too (which restore the shared grid) since those carry no events.
        self._map.refresh_sites()
        self._year_label.setText(format_tick(snapshot.tick))
        # Cap the annals (which are year-grained) when scrubbed behind the
        # frontier; live ticks are >= it. Restoring an earlier tick shows that
        # tick's whole year — finer scrubbing lives in the map, not the annals.
        behind = snapshot.tick < self._frontier
        self._annals_model.set_cap_year(snapshot.year if behind else None)
        self._sync_slider(snapshot.tick)

    def _fire_pulses(self, events: List[Event]) -> None:
        """Flash an on-map pulse for each above-threshold, located event."""
        for event in pulse_events(events):
            site = self._grid.site_by_id(event.location_id)
            if site is not None:
                self._map.pulse(site.col, site.row)

    def _fire_battle_markers(self, snapshot: Snapshot, events: List[Event]) -> None:
        """Mark the tile of each battle/siege this tick with a crossed-swords flash.

        Resolving the tile (ticket 07): a sited fight (a siege/storming) carries a
        ``location_id`` — the seat — so its tile comes straight from the grid. A
        field battle has no location and no col/row in its payload; the winner
        holds the field, so we place the marker on the winner army's tile, found
        in the snapshot by ``winner_army_id``. If the winner is gone from the
        snapshot (destroyed and pruned), the battle can't be placed — skip it.
        """
        armies_by_id = {a.id: a for a in living_armies(snapshot)}
        for event in events:
            if event.type not in (BATTLE_EVENT, SIEGE_EVENT):
                continue
            if event.location_id is not None:
                site = self._grid.site_by_id(event.location_id)
                if site is not None:
                    self._map.battle_marker(site.col, site.row)
                continue
            winner = armies_by_id.get(event.payload.get("winner_army_id"))
            if winner is not None:
                self._map.battle_marker(winner.col, winner.row)

    def _on_show_all_toggled(self) -> None:
        """Toolbar toggle: show every event vs. the default important-only feed."""
        self._apply_annals_filter()

    def _apply_annals_filter(self) -> None:
        """Compose the feed's filter from both controls.

        The show-all toggle picks the importance base; the bucket chips name
        the excluded types. They AND together (which buckets × how important),
        so flipping either control re-applies both.
        """
        base = (
            show_all_filter()
            if self._show_all_action.isChecked()
            else AnnalsFilter()
        )
        excluded = frozenset()
        for bucket, chip in self._bucket_chips.items():
            if not chip.isChecked():
                excluded |= types_in_bucket(bucket)
        self._annals_model.set_filter(replace(base, excluded_types=excluded or None))

    def _on_frontier_changed(self, frontier: int) -> None:
        """``frontier`` is the newest simulated tick."""
        self._frontier = frontier
        if not self._scrub.isEnabled():
            self._scrub.setEnabled(True)
        self._scrub.setMaximum(frontier)

    # -- annals -> map ---------------------------------------------------

    def _on_annals_event_clicked(self, index) -> None:
        """An annals row click: the event's Codex page, plus a map jump if placed.

        One gesture, two payoffs (annals-ui spec): every event row navigates
        the Codex to the event's page (so it sits in history like any other);
        a placed event also pans the map to its site. Space-only by decision —
        the timeline, scrub cap, and filter are untouched. A year-header row
        does nothing.
        """
        event = self._annals_model.data(index, EventRole)
        if event is None:
            return
        self._codex.navigate(CodexAddress("event", str(event.id)))
        if event.location_id is None:
            return
        site = self._grid.site_by_id(event.location_id)
        if site is not None:
            self._map.focus_tile(site.col, site.row)

    # -- the codex: addresses -> pages -----------------------------------

    def _on_tile_clicked(self, col: int, row: int) -> None:
        self._codex.navigate(CodexAddress("tile", f"{col},{row}"))

    def _on_codex_navigated(self, address: CodexAddress) -> None:
        """Codex → map: opening a host page centres/highlights its marker.

        The Codex↔map link runs both ways (ADR-0014); this direction is what
        makes an armies-index row *click and centre the map on that host* (#17).
        Only host pages jump the map — a host is the one page kind bound to a
        single live tile — and only when the host is present and afield.
        """
        if address.kind != "host" or self._latest_snapshot is None:
            return
        try:
            army_id = int(address.ident)
        except ValueError:
            return
        army = self._latest_snapshot.entity(army_id)
        if isinstance(army, Army) and army.alive:
            self._map.focus_tile(army.col, army.row)

    def _render_page(self, address: CodexAddress) -> Optional[str]:
        """The Codex's registry: resolve an address to page HTML.

        A one-line delegate to the headless :class:`CodexPages` (#39), which owns
        the whole ``describe_*`` / ``_*_page`` / ``_*_index`` render library. The
        pane calls this; ``None`` means a dead link and the pane draws its own
        no-such-page notice, so renderers stay total and never raise.
        """
        return self._pages.render(address)

    def _accumulate_ring_trend(self, snapshot: Snapshot) -> None:
        """Append the Ring's current corruption/pull for a forward advance only.

        Keyed off the tick so a scrub-restore (which replays an earlier, already
        recorded tick) never duplicates or reorders the trend series."""
        if snapshot.tick <= self._ring_trend_tick:
            return
        ring = the_ring(snapshot)
        if ring is None:
            return
        self._ring_trend_tick = snapshot.tick
        self._ring_trend.append(
            RingTrendSample(snapshot.tick, snapshot.year, ring.corruption, ring.pull)
        )

    # -- UI -> worker ----------------------------------------------------

    def _on_scrub(self, tick: int) -> None:
        if self._syncing_slider:  # programmatic move, not a user drag
            return
        self.seekRequested.emit(tick)

    def _sync_slider(self, tick: int) -> None:
        """Move the slider to ``tick`` without it looking like a user scrub."""
        self._syncing_slider = True
        try:
            self._scrub.setValue(tick)
        finally:
            self._syncing_slider = False

    # -- lifecycle -------------------------------------------------------

    def fit_map(self) -> None:
        """Fit the whole map in view. Call once after the window is shown."""
        self._map.fit_map()

    def closeEvent(self, event) -> None:
        """Stop the sim thread cleanly before the window goes away.

        Pause first via a blocking call *into* the worker thread so its QTimer is
        stopped where it lives (Qt forbids touching a timer from another thread);
        only then quit and join the thread.
        """
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "pause", Qt.BlockingQueuedConnection)
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
