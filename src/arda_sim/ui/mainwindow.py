"""The main window: map canvas, timeline toolbar, annals dock, inspection dock.

Owns the background sim thread and translates its ``(year, snapshot, events)``
stream into UI updates. Playback commands go to the worker as queued signals
(thread-safe); snapshots come back and drive the year label, the scrub slider,
and the annals cap. The window renders only from snapshots — never the live world.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QMetaObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QDoubleSpinBox,
    QLabel,
    QListView,
    QMainWindow,
    QSlider,
    QToolBar,
    QWidget,
)

from .. import START_YEAR
from ..entities import Event
from ..playback import Playback
from ..snapshot import Snapshot
from ..tiles import UNOWNED, TileGrid
from .annals_model import AnnalsModel
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
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._playback = playback
        self._grid = grid
        self._faction_names = faction_names or {}
        self._syncing_slider = False
        # The frontier as last reported by the worker (never read cross-thread
        # from the worker-owned Playback). Nothing simulated yet.
        self._frontier = START_YEAR - 1
        self.setWindowTitle("arda_history — the Third Age unfolds")

        self._map = MapView(grid, self)
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
        self._scrub = QSlider(Qt.Horizontal, self)
        self._scrub.setRange(START_YEAR, START_YEAR)
        self._scrub.setEnabled(False)  # nothing simulated yet
        self._scrub.valueChanged.connect(self._on_scrub)
        bar.addWidget(self._scrub)

        self._year_label = QLabel(f"TA {START_YEAR}", self)
        self._year_label.setMinimumWidth(110)
        self._year_label.setAlignment(Qt.AlignCenter)
        # Prominent: the current year is the viewer's anchor in time.
        font = self._year_label.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self._year_label.setFont(font)
        bar.addWidget(self._year_label)

    def _build_docks(self) -> None:
        annals_view = QListView(self)
        annals_view.setModel(self._annals_model)
        annals_view.setUniformItemSizes(True)  # keeps the virtualized list fast
        annals_dock = QDockWidget("Annals", self)
        annals_dock.setWidget(annals_view)
        self.addDockWidget(Qt.RightDockWidgetArea, annals_dock)

        self._inspection_label = QLabel("Select something on the map.", self)
        self._inspection_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._inspection_label.setWordWrap(True)
        self._inspection_label.setMargin(8)
        inspection_dock = QDockWidget("Inspection", self)
        inspection_dock.setWidget(self._inspection_label)
        self.addDockWidget(Qt.RightDockWidgetArea, inspection_dock)

    def _start_worker(self, playback: Playback) -> None:
        self._thread = QThread(self)
        self._worker = SimWorker(playback)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.setup)
        self._thread.finished.connect(self._worker.deleteLater)
        self._worker.yearAdvanced.connect(self._on_year_advanced)
        self._worker.frontierChanged.connect(self._on_frontier_changed)

        self.playRequested.connect(self._worker.play)
        self.pauseRequested.connect(self._worker.pause)
        self.stepRequested.connect(self._worker.step)
        self.speedChanged.connect(self._worker.set_speed)
        self.seekRequested.connect(self._worker.seek)

        self._thread.start()

    # -- worker -> UI ----------------------------------------------------

    def _on_year_advanced(self, snapshot: Snapshot, events: List[Event]) -> None:
        if events:  # a live advance; a scrub-restore carries none
            self._annals_model.append_events(events)
        year = snapshot.year
        self._year_label.setText(f"TA {year}")
        # Cap the annals when scrubbed behind the frontier; live years are >= it.
        self._annals_model.set_cap_year(None if year >= self._frontier else year)
        self._sync_slider(year)

    def _on_frontier_changed(self, frontier: int) -> None:
        self._frontier = frontier
        if not self._scrub.isEnabled():
            self._scrub.setEnabled(True)
        self._scrub.setMaximum(frontier)

    # -- map -> inspection ----------------------------------------------

    def _on_tile_clicked(self, col: int, row: int) -> None:
        self._inspection_label.setText(self.describe_tile(col, row))

    def describe_tile(self, col: int, row: int) -> str:
        """Human-readable summary of a tile for the inspection dock."""
        grid = self._grid
        terrain = grid.terrain_at(col, row)
        owner = grid.owner_at(col, row)
        region = grid.region_at(col, row)
        owner_label = (
            "unowned"
            if owner == UNOWNED
            else self._faction_names.get(owner, f"faction {owner}")
        )
        lines = [
            f"Tile ({col}, {row})",
            f"Terrain: {terrain}",
            f"Owner: {owner_label}",
            f"Region: {region.name if region else '—'}",
        ]
        for site in grid.sites:
            if site.col == col and site.row == row:
                lines.append(f"Site: {site.name} ({site.kind})")
        return "\n".join(lines)

    # -- UI -> worker ----------------------------------------------------

    def _on_scrub(self, year: int) -> None:
        if self._syncing_slider:  # programmatic move, not a user drag
            return
        self.seekRequested.emit(year)

    def _sync_slider(self, year: int) -> None:
        """Move the slider to ``year`` without it looking like a user scrub."""
        self._syncing_slider = True
        try:
            self._scrub.setValue(year)
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
