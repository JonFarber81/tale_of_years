"""The main window: map canvas, timeline toolbar, annals dock, inspection dock.

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
from PySide6.QtWidgets import (
    QDockWidget,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QPushButton,
    QSlider,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import START_YEAR
from ..armies import Army
from ..characters import Character, render_bloodline
from ..diplomacy import NEUTRALITY, stance
from ..chronicle import AnnalsFilter, pulse_events, show_all_filter
from ..entities import Event
from ..factions import Faction
from ..playback import Playback
from ..snapshot import Snapshot
from ..tiles import UNOWNED, TileGrid
from ..world import format_tick
from .annals_model import AnnalsModel, EventRole
from .annals_style import (
    BUCKET_COLORS,
    BUCKET_LABELS,
    BUCKETS,
    AnnalsDelegate,
    types_in_bucket,
)
from . import tile_render
from .dossier_html import (
    NEUTRAL_ACCENT,
    banner,
    para,
    pre_block,
    section,
    stat_grid,
    text_lines,
)
from .event_dossier import render_event_dossier
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
        # Latest renderable state + the accumulated event stream, so tile/faction
        # inspection reads from snapshots and the feed, never the live world.
        self._latest_snapshot: Optional[Snapshot] = None
        self._events: List[Event] = []
        self._display_year = START_YEAR - 1
        self._syncing_slider = False
        # The frontier as last reported by the worker, in absolute ticks (never
        # read cross-thread from the worker-owned Playback). Nothing simulated yet,
        # so it sits one tick before the first tick (tick 0).
        self._frontier = -1
        self.setWindowTitle("The Tale of Years — the Third Age unfolds")

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
        # Prominent: the current date is the viewer's anchor in time.
        font = self._year_label.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self._year_label.setFont(font)
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
        chip_row.setSpacing(4)
        for bucket in BUCKETS:
            chip = QPushButton(BUCKET_LABELS[bucket], self)
            chip.setCheckable(True)
            chip.setChecked(True)
            chip.setToolTip(f"Show or hide {BUCKET_LABELS[bucket].lower()} events")
            color = BUCKET_COLORS[bucket].name()
            # Base rule renders an excluded chip dim; :checked overrides it to
            # full-strength (a negation selector proved unreliable here).
            chip.setStyleSheet(
                "QPushButton { padding: 1px 8px; border: 1px solid palette(mid);"
                f" border-left: 4px solid {color}; border-radius: 3px;"
                " color: palette(mid); }"
                " QPushButton:checked { color: palette(text); font-weight: bold; }"
            )
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
        annals_dock = QDockWidget("Annals", self)
        annals_dock.setWidget(annals_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, annals_dock)

        # Rich-text dossiers (inspection-ui ticket 01): scrollable, selectable,
        # and the anchor-capable surface the wishlisted cross-linking wants.
        self._inspection = QTextBrowser(self)
        self._inspection.setOpenLinks(False)
        self._inspection.setPlaceholderText("Select something on the map.")
        inspection_dock = QDockWidget("Inspection", self)
        inspection_dock.setWidget(self._inspection)
        self.addDockWidget(Qt.RightDockWidgetArea, inspection_dock)

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
        self._map.refresh_armies(self._armies_in(snapshot))
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
        """An annals row click: the event dossier, plus a map jump if placed.

        One gesture, two payoffs (annals-ui spec): every event row pushes its
        dossier into the Inspection dock; a placed event also pans the map to
        its site. Space-only by decision — the timeline, scrub cap, and filter
        are untouched. A year-header row does nothing.
        """
        event = self._annals_model.data(index, EventRole)
        if event is None:
            return
        self._inspection.setHtml(self.describe_event(event))
        if event.location_id is None:
            return
        site = self._grid.site_by_id(event.location_id)
        if site is not None:
            self._map.focus_tile(site.col, site.row)

    def describe_event(self, event: Event) -> str:
        """The event dossier for the inspection dock (annals-ui ticket 03)."""
        return render_event_dossier(
            event,
            faction_name=self._faction_display_name,
            site_name=lambda site_id: (
                site.name
                if site_id is not None
                and (site := self._grid.site_by_id(site_id)) is not None
                else None
            ),
            region_name=lambda rid: (
                region.name if (region := self._grid.regions.get(rid)) else None
            ),
        )

    def _faction_display_name(self, faction_id) -> str:
        if faction_id is None:
            return "an unknown power"
        return self._faction_names.get(faction_id, f"faction {faction_id}")

    # -- map -> inspection ----------------------------------------------

    def _on_tile_clicked(self, col: int, row: int) -> None:
        self._inspection.setHtml(self.describe_tile(col, row))

    def describe_tile(self, col: int, row: int) -> str:
        """The tile dossier (HTML) for the inspection dock.

        An owned tile appends its owning faction's dossier (state + recent
        events), so clicking anywhere in a realm inspects the power that holds
        it. (Ticket 01 keeps today's stacking order; the most-specific-first
        restructure is ticket 02.)
        """
        grid = self._grid
        terrain = grid.terrain_at(col, row)
        owner = grid.owner_at(col, row)
        region = grid.region_at(col, row)
        owner_label = (
            "unowned"
            if owner == UNOWNED
            else self._faction_names.get(owner, f"faction {owner}")
        )
        accent = self._owner_accent(owner)
        stats = [
            ("Terrain", terrain),
            ("Owner", owner_label),
            ("Region", region.name if region else "—"),
        ]
        for site in grid.sites:
            if site.col == col and site.row == row:
                rank = f", tier {site.tier}" if site.tier else ""
                stats.append(("Site", f"{site.name} ({site.kind}{rank})"))
        parts = [banner("Tile", f"({col}, {row})", accent), stat_grid(stats)]
        host = self._army_on(col, row)
        if host is not None:
            parts.append(self.describe_army(host))
        if owner != UNOWNED:
            faction = self._faction(owner)
            if faction is not None:
                parts.append(self.describe_faction(faction))
        return "".join(parts)

    def _owner_accent(self, faction_id: int) -> str:
        """The identity accent for a faction's dossier (neutral if unowned)."""
        if faction_id == UNOWNED:
            return NEUTRAL_ACCENT
        return tile_render.faction_color(faction_id).name()

    def _faction(self, faction_id: int) -> Optional[Faction]:
        """The faction record as of the displayed year (from the snapshot)."""
        if self._latest_snapshot is None:
            return None
        entity = self._latest_snapshot.entity(faction_id)
        return entity if isinstance(entity, Faction) else None

    def _armies_in(self, snapshot: Snapshot) -> List[Army]:
        """The living hosts in a snapshot, in id order (for the map layer)."""
        return [
            e
            for _id, e in sorted(snapshot.entities.items())
            if isinstance(e, Army) and e.alive
        ]

    def _army_on(self, col: int, row: int) -> Optional[Army]:
        """The lowest-id living host standing on a tile in the current snapshot."""
        if self._latest_snapshot is None:
            return None
        for army in self._armies_in(self._latest_snapshot):
            if army.col == col and army.row == row:
                return army
        return None

    def describe_army(self, army: Army) -> str:
        """A host dossier (HTML) for the inspection dock: leader, size, destination."""
        leader = None
        if army.leader_id is not None and self._latest_snapshot is not None:
            leader = self._latest_snapshot.entity(army.leader_id)
        faction = self._faction(army.faction_id) if army.faction_id else None
        faction_name = faction.name if faction is not None else "—"
        if army.dest_site_id is not None:
            dest_site = self._grid.site_by_id(army.dest_site_id)
            destination = dest_site.name if dest_site is not None else "the field"
        else:
            destination = "holding (in garrison)"
        accent = (
            self._owner_accent(army.faction_id) if army.faction_id else NEUTRAL_ACCENT
        )
        return banner("Host", army.name, accent) + stat_grid(
            [
                ("Faction", faction_name),
                ("Leader", leader.name if leader else "— (leaderless)"),
                ("Strength", army.size),
                ("Destination", destination),
            ]
        )

    def describe_faction(self, faction: Faction) -> str:
        """A faction dossier (HTML): banner, stats, then the deep sections."""
        leader = None
        if faction.leader_id is not None and self._latest_snapshot is not None:
            leader = self._latest_snapshot.entity(faction.leader_id)
        intent = faction.current_intent.get("intent", "—")
        parts = [
            banner(
                f"Faction · {faction.faction_kind}",
                faction.name,
                self._owner_accent(faction.id),
            ),
            stat_grid(
                [
                    ("Leader", leader.name if leader else "—"),
                    ("Succession", faction.succession_rule),
                    ("Posture", f"{faction.posture}   ·   {faction.aggression}"),
                    ("Strength", faction.military_strength),
                    ("Treasury", faction.treasury),
                    ("Prominence", faction.prominence),
                    ("Latest intent", intent),
                ]
            ),
        ]
        diplomacy = self._describe_diplomacy(faction)
        if diplomacy:
            parts.append(section("Diplomacy"))
            parts.append(text_lines(diplomacy))
        bloodline = self._describe_bloodline(leader)
        if bloodline:
            parts.append(section("Bloodline"))
            parts.append(pre_block(bloodline))
        recent = [
            ev
            for ev in self._events
            if faction.id in ev.subject_ids and ev.year <= self._display_year
        ][-5:]
        if recent:
            parts.append(section("Recent events"))
            parts.append(
                text_lines(
                    "\n".join(
                        f"TA {ev.year}: {ev.text or ev.type}"
                        for ev in reversed(recent)  # newest first
                    )
                )
            )
        return "".join(parts)

    def _describe_diplomacy(self, faction: Faction) -> Optional[str]:
        """This faction's standing toward others, as of the displayed year.

        Shows the fealty bonds (overlord, vassals) and every non-neutral stance,
        each with the raw disposition scalar. Read off the snapshot faction, so it
        reflects the scrubbed year, not the live world.
        """
        names = self._faction_names
        lines: List[str] = []
        if faction.overlord_faction_id is not None:
            lines.append(f"Overlord: {names.get(faction.overlord_faction_id, '—')}")
        if self._latest_snapshot is not None:
            vassals = sorted(
                names.get(e.id, str(e.id))
                for e in self._latest_snapshot.entities.values()
                if isinstance(e, Faction) and e.overlord_faction_id == faction.id
            )
            if vassals:
                lines.append(f"Vassals: {', '.join(vassals)}")
        related = (
            set(faction.at_war_with)
            | set(faction.treaties)
            | {int(k) for k in faction.disposition}
        )
        for other_id in sorted(related):
            other = self._faction(other_id)
            if other is None:
                continue
            label = stance(faction, other)
            if label == NEUTRALITY:
                continue
            disp = faction.disposition_toward(other_id)
            lines.append(f"{names.get(other_id, other_id)}: {label} ({disp:+d})")
        if not lines:
            return None
        return "\n".join(lines)

    def _describe_bloodline(self, leader: Optional[object]) -> Optional[str]:
        """The ruling leader's bloodline (dynasty view) as of the displayed year.

        A bloodline is a pure query over kinship id-fields; the snapshot exposes the
        same ``entities`` map those queries read, so it stands in for the live world.
        """
        if not isinstance(leader, Character) or self._latest_snapshot is None:
            return None
        return render_bloodline(self._latest_snapshot, leader.id)

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
