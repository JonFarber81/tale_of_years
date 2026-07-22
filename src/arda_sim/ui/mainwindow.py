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
from ..characters import Character, render_bloodline
from ..diplomacy import ALLIANCE, NEUTRALITY, VASSALAGE, stance
from ..economy import faction_population
from ..war import BATTLE_EVENT, SIEGE_EVENT, fortification
from ..chronicle import AnnalsFilter, pulse_events, show_all_filter
from ..entities import Event
from ..factions import Faction
from ..playback import Playback
from ..ring import Ring, the_ring
from ..snapshot import Snapshot
from ..tiles import UNOWNED, TileGrid
from ..world import format_tick
from .annals_model import AnnalsModel, EventRole
from .annals_style import (
    BUCKET_COLORS,
    BUCKET_LABELS,
    BUCKETS,
    CONSTRUCTION,
    DYNASTY,
    WAR,
    AnnalsDelegate,
    bucket_of,
    types_in_bucket,
)
from . import tile_render
from .codex import CodexAddress, CodexPane, render_search_page, search_matches
from .dossier_html import (
    DIM,
    NEUTRAL_ACCENT,
    banner,
    dim_para,
    esc,
    index_table,
    para,
    pre_block,
    section,
    stat_grid,
)

# Stance words wear the feed's color vocabulary (inspection-ui ticket 03):
# war-red for open war and hostility, the peaceable green for alliance/treaty,
# the dynasty purple for fealty bonds.
_WAR_COLOR = BUCKET_COLORS[WAR].name()
_AMITY_COLOR = BUCKET_COLORS[CONSTRUCTION].name()
_FEALTY_COLOR = BUCKET_COLORS[DYNASTY].name()
from .event_dossier import render_event_dossier
from .map_view import MapView
from .sim_worker import SimWorker

_MIN_TPS = 0.25
_MAX_TPS = 60.0
_DEFAULT_TPS = 2.0

# The One Ring's dossier accent — the same warm gold as its map marker (ticket 13).
_RING_ACCENT = "#e9c46a"


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
        self._display_year = START_YEAR - 1
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
                " QPushButton:checked { color: palette(text); }"
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
        codex_dock.setWidget(self._codex)
        self.addDockWidget(Qt.RightDockWidgetArea, codex_dock)

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
        self._map.refresh_armies(self._armies_in(snapshot))
        self._map.refresh_ring(self._ring_in(snapshot))  # keep the Ring findable (ticket 13)
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
        armies_by_id = {a.id: a for a in self._armies_in(snapshot)}
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
        army_id = self._int_ident(address.ident)
        army = self._latest_snapshot.entity(army_id) if army_id is not None else None
        if isinstance(army, Army) and army.alive:
            self._map.focus_tile(army.col, army.row)

    def _render_page(self, address: CodexAddress) -> Optional[str]:
        """The Codex's registry: resolve an address to page HTML.

        ``None`` means a dead link (unknown kind, malformed ident, or an
        entity absent from the displayed year) — the pane renders its own
        no-such-page notice, so renderers stay total and never raise.
        """
        renderers = {
            "tile": self._tile_page,
            "site": self._site_page,
            "faction": self._faction_page,
            "host": self._host_page,
            "event": self._event_page,
            "ring": self._ring_page,
            "index": self._index_page,
            "search": self._search_page,
        }
        renderer = renderers.get(address.kind)
        return renderer(address.ident) if renderer else None

    @staticmethod
    def _int_ident(ident: str) -> Optional[int]:
        """An entity-id ident, or None for garbage (a dead link, not a crash)."""
        try:
            return int(ident)
        except ValueError:
            return None

    def _tile_page(self, ident: str) -> Optional[str]:
        try:
            col, row = (int(part) for part in ident.split(","))
        except ValueError:
            return None
        if not (0 <= col < self._grid.width and 0 <= row < self._grid.height):
            return None
        return self.describe_tile(col, row)

    def _site_page(self, ident: str) -> Optional[str]:
        site_id = self._int_ident(ident)
        site = self._grid.site_by_id(site_id) if site_id is not None else None
        return self.describe_site(site) if site is not None else None

    def _faction_page(self, ident: str) -> Optional[str]:
        faction_id = self._int_ident(ident)
        faction = self._faction(faction_id) if faction_id is not None else None
        return self.describe_faction(faction) if faction is not None else None

    def _host_page(self, ident: str) -> Optional[str]:
        army_id = self._int_ident(ident)
        if army_id is None or self._latest_snapshot is None:
            return None
        army = self._latest_snapshot.entity(army_id)
        return self.describe_army(army) if isinstance(army, Army) else None

    def _event_page(self, ident: str) -> Optional[str]:
        event_id = self._int_ident(ident)
        if event_id is None:
            return None
        # The feed retains every delivered event, filtered or not, so it is
        # the one lookup path an event address needs.
        event = self._annals_model.event_by_id(event_id)
        return self.describe_event(event) if event is not None else None

    def _ring_page(self, ident: str) -> Optional[str]:
        del ident  # there is only the One
        if self._latest_snapshot is None:
            return None
        ring = self._ring_in(self._latest_snapshot)
        return self.describe_ring(ring) if ring is not None else None

    # The still-stubbed indexes; each table lands with its own issue. Armies
    # (#17) and Factions (#19) are live below, so neither is a blurb.
    _INDEX_BLURBS = {
        "wars": "The wars and bonds between realms. Its table arrives with #20.",
    }

    def _index_page(self, ident: str) -> Optional[str]:
        """An index page. The ident is the index name, optionally followed by a
        ``/<sort>`` — so ``armies`` and ``armies/faction`` are the same page
        under different sort orders (each an ordinary history entry)."""
        name, _, sort = ident.partition("/")
        if name == "armies":
            return self._armies_index(sort or None)
        if name == "factions":
            return self._factions_index(sort or None)
        blurb = self._INDEX_BLURBS.get(name)
        if blurb is None:
            return None
        return banner("Index", name.title()) + dim_para(blurb)

    # The armies-index columns, in display order: (header label, sort key,
    # descending?). A host's own name column carries the row's link to its
    # host page; the roll opens greatest-host-first, so strength is the default.
    _ARMY_COLUMNS = (
        ("Host", "host", False),
        ("Faction", "faction", False),
        ("Leader", "leader", False),
        ("Strength", "strength", True),
        ("Destination", "destination", False),
        ("Target", "target", False),
        ("Siege", "siege", True),
    )
    _DEFAULT_ARMY_SORT = "strength"

    def _armies_index(self, sort: Optional[str]) -> str:
        """The Armies index (#17): every host afield as a sortable table.

        Each row names a host (linking to its host page, whose activation
        centres the map on the marker — the ticket's click-to-centre), with its
        faction, leader, strength, destination, target realm, and siege. Column
        headers are sort links; the roll defaults to strength, greatest first.
        Reads only the displayed snapshot, like the rest of the Codex.
        """
        columns = {key: desc for _label, key, desc in self._ARMY_COLUMNS}
        if sort not in columns:
            sort = self._DEFAULT_ARMY_SORT
        armies = (
            self._armies_in(self._latest_snapshot)
            if self._latest_snapshot is not None
            else []
        )
        head = banner("Index", "Armies")
        if not armies:
            return head + dim_para("No hosts are afield in the displayed year.")
        rows = [self._army_index_row(army) for army in armies]
        rows.sort(key=lambda row: row["sort"][sort], reverse=columns[sort])
        headers = [
            self._army_index_header(label, key, sort)
            for label, key, _desc in self._ARMY_COLUMNS
        ]
        return head + index_table(headers, (row["cells"] for row in rows))

    def _army_index_header(self, label: str, key: str, active: str) -> str:
        """A column header: a sort link, or bold plain text for the live sort."""
        if key == active:
            return f"<b>{esc(label)}</b>"
        return f'<a href="codex://index/armies/{key}">{esc(label)}</a>'

    def _army_index_row(self, army: Army) -> dict:
        """One host's index row: its sort values (per column key) and the
        pre-composed HTML cells (host/faction/target/destination as links)."""
        snapshot = self._latest_snapshot
        faction_name = (
            self._faction_names.get(army.faction_id)
            if army.faction_id is not None
            else None
        )
        leader = (
            snapshot.entity(army.leader_id)
            if army.leader_id is not None and snapshot is not None
            else None
        )
        leader_name = leader.name if leader is not None else "—"
        dest_site = (
            self._grid.site_by_id(army.dest_site_id)
            if army.dest_site_id is not None
            else None
        )
        if dest_site is not None:
            destination = dest_site.name
        elif army.dest_site_id is not None:
            destination = "the field"
        else:
            destination = "—"  # holding in garrison
        target_name = (
            self._faction_names.get(army.target_faction_id)
            if army.target_faction_id is not None
            else None
        )
        siege = self._siege_line(army, self._host_seat(army)) or "—"
        cells = [
            self._codex_link("host", army.id, army.name),
            self._faction_cell(army.faction_id, faction_name),
            esc(leader_name),
            esc(army.size),
            self._codex_link("site", dest_site.id, dest_site.name)
            if dest_site is not None
            else esc(destination),
            self._faction_cell(army.target_faction_id, target_name),
            esc(siege),
        ]
        return {
            "cells": cells,
            "sort": {
                "host": army.name.lower(),
                "faction": (faction_name or "").lower(),
                "leader": leader_name.lower(),
                "strength": army.size,
                "destination": destination.lower(),
                "target": (target_name or "").lower(),
                "siege": army.siege_progress,
            },
        }

    def _faction_cell(self, faction_id: Optional[int], name: Optional[str]) -> str:
        """A faction table cell: a link to its page, or a dash when there is none."""
        if faction_id is None or name is None:
            return "—"
        return self._codex_link("faction", faction_id, name)

    @staticmethod
    def _codex_link(kind: str, ident: object, label: object) -> str:
        """An in-Codex ``codex://`` anchor (ident/label escaped)."""
        return f'<a href="codex://{kind}/{esc(ident)}">{esc(label)}</a>'

    # The factions-index columns, in display order: (header label, sort key,
    # descending?). The name column carries the row's link to its faction
    # dossier; the roll opens greatest-realm-first, so population is the default.
    _FACTION_COLUMNS = (
        ("Faction", "name", False),
        ("Kind", "kind", False),
        ("Population", "population", True),
        ("Strength", "strength", True),
        ("Treasury", "treasury", True),
        ("Leader", "leader", False),
        ("Wars", "wars", True),
    )
    _DEFAULT_FACTION_SORT = "population"

    def _factions_in(self, snapshot: Snapshot) -> List[Faction]:
        """The living factions in a snapshot, in id order."""
        return [
            e
            for _id, e in sorted(snapshot.entities.items())
            if isinstance(e, Faction) and e.alive
        ]

    def _factions_index(self, sort: Optional[str]) -> str:
        """The Factions index (#19): every power as a sortable table.

        Each row names a faction (linking to its dossier), with its kind,
        population, military strength, treasury, leader, and wars. Column
        headers are sort links; the roll defaults to population, greatest first.
        Reads only the displayed snapshot, like the rest of the Codex.
        """
        columns = {key: desc for _label, key, desc in self._FACTION_COLUMNS}
        if sort not in columns:
            sort = self._DEFAULT_FACTION_SORT
        factions = (
            self._factions_in(self._latest_snapshot)
            if self._latest_snapshot is not None
            else []
        )
        head = banner("Index", "Factions")
        if not factions:
            return head + dim_para("No factions stand in the displayed year.")
        rows = [self._faction_index_row(faction) for faction in factions]
        rows.sort(key=lambda row: row["sort"][sort], reverse=columns[sort])
        headers = [
            self._faction_index_header(label, key, sort)
            for label, key, _desc in self._FACTION_COLUMNS
        ]
        return head + index_table(headers, (row["cells"] for row in rows))

    def _faction_index_header(self, label: str, key: str, active: str) -> str:
        """A column header: a sort link, or bold plain text for the live sort."""
        if key == active:
            return f"<b>{esc(label)}</b>"
        return f'<a href="codex://index/factions/{key}">{esc(label)}</a>'

    def _faction_index_row(self, faction: Faction) -> dict:
        """One faction's index row: its sort values (per column key) and the
        pre-composed HTML cells (name/leader/wars as links)."""
        snapshot = self._latest_snapshot
        leader = (
            snapshot.entity(faction.leader_id)
            if faction.leader_id is not None and snapshot is not None
            else None
        )
        leader_name = leader.name if leader is not None else "—"
        # A pure grid aggregate (economy.py): the world arg is unused, so the
        # displayed snapshot's grid is all it needs.
        population = faction_population(None, self._grid, faction.id)
        names = self._faction_names
        war_ids = sorted(faction.at_war_with, key=lambda f: names.get(f, str(f)))
        wars = " · ".join(
            self._faction_cell(fid, names.get(fid)) for fid in war_ids
        )
        cells = [
            self._codex_link("faction", faction.id, faction.name),
            esc(faction.faction_kind),
            esc(population),
            esc(faction.military_strength),
            esc(faction.treasury),
            esc(leader_name),
            wars or "—",
        ]
        return {
            "cells": cells,
            "sort": {
                "name": faction.name.lower(),
                "kind": faction.faction_kind.lower(),
                "population": population,
                "strength": faction.military_strength,
                "treasury": faction.treasury,
                "leader": leader_name.lower(),
                "wars": len(faction.at_war_with),
            },
        }

    def _search_page(self, query: str) -> str:
        return render_search_page(
            query, search_matches(query, self._search_candidates())
        )

    def _search_candidates(self):
        """Every searchable (name, detail, address), factions → hosts → sites.

        Shell scope (#36): entities with proper names in the displayed
        snapshot plus the grid's sites — enough to prove the plumbing.
        Characters join with #18's finder.
        """
        candidates = []
        if self._latest_snapshot is not None:
            for _id, entity in sorted(self._latest_snapshot.entities.items()):
                if isinstance(entity, Faction):
                    candidates.append(
                        (
                            entity.name,
                            entity.faction_kind,
                            CodexAddress("faction", str(entity.id)),
                        )
                    )
            for army in self._armies_in(self._latest_snapshot):
                holder = self._faction_names.get(army.faction_id)
                candidates.append(
                    (
                        army.name,
                        f"host of {holder}" if holder else "host",
                        CodexAddress("host", str(army.id)),
                    )
                )
        for site in self._grid.sites:
            candidates.append(
                (site.name, site.kind, CodexAddress("site", str(site.id)))
            )
        return candidates

    def describe_tile(self, col: int, row: int) -> str:
        """The dossier (HTML) a map click renders, most-specific-first.

        The click resolves to one **dossier subject** — a host standing on the
        tile, else a site there, else the owning faction, else the bare tile
        (see CONTEXT.md) — which headlines with full depth; anything else
        renders only as trimmed context beneath it. The One Ring, when it is on
        the clicked tile, trumps them all: it headlines, with the ordinary tile
        subject kept as context beneath.
        """
        ring = self._ring_on(col, row)
        base = self._describe_tile_subject(col, row)
        if ring is not None:
            return self.describe_ring(ring) + base
        return base

    def _describe_tile_subject(self, col: int, row: int) -> str:
        """The tile's ordinary dossier subject (host / site / faction / tile)."""
        host = self._army_on(col, row)
        if host is not None:
            return self.describe_army(host)
        site = next(
            (s for s in self._grid.sites if s.col == col and s.row == row), None
        )
        if site is not None:
            return self.describe_site(site)
        owner = self._grid.owner_at(col, row)
        if owner != UNOWNED:
            faction = self._faction(owner)
            if faction is not None:
                return self.describe_faction(faction) + self._ground_line(col, row)
        return self._describe_bare_tile(col, row)

    def _describe_bare_tile(self, col: int, row: int) -> str:
        """Unowned, unsettled, unoccupied ground — the boring case stays short."""
        grid = self._grid
        region = grid.region_at(col, row)
        return banner("Tile", f"({col}, {row})") + stat_grid(
            [
                ("Terrain", grid.terrain_at(col, row)),
                ("Region", region.name if region else "—"),
                ("Owner", "unowned"),
            ]
        )

    def _ground_line(self, col: int, row: int) -> str:
        """A dim locator for the clicked ground under a faction-subject dossier."""
        grid = self._grid
        region = grid.region_at(col, row)
        where = f" in {region.name}" if region else ""
        return para(
            f'<span style="color: {DIM}">Ground: '
            f"{esc(grid.terrain_at(col, row))}{esc(where)} ({col}, {row})</span>"
        )

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

    def _ring_in(self, snapshot: Snapshot) -> Optional[Ring]:
        """The One Ring in a snapshot (there is at most one), or ``None``.

        A snapshot exposes the same ``entities`` map the query reads, so the sim's
        own :func:`arda_sim.ring.the_ring` stands in for the live world here.
        """
        return the_ring(snapshot)

    def _ring_on(self, col: int, row: int) -> Optional[Ring]:
        """The One Ring if it stands on this tile in the current snapshot."""
        if self._latest_snapshot is None:
            return None
        ring = self._ring_in(self._latest_snapshot)
        if ring is not None and (ring.col, ring.row) == (col, row):
            return ring
        return None

    def describe_ring(self, ring: Ring) -> str:
        """The One Ring dossier (HTML): where it is, its scalars, and its full
        transfer/bearer journey — inspectable from the tile it rests on."""
        if ring.borne and self._latest_snapshot is not None:
            bearer = self._latest_snapshot.entity(ring.bearer_id)
            possession = f"borne by {bearer.name}" if bearer is not None else "borne"
        else:
            site = self._grid.site_by_id(ring.location_id) if ring.location_id else None
            possession = f"lying at {site.name}" if site is not None else "lying where it fell"
        parts = [
            banner("The One Ring", "The One Ring", _RING_ACCENT),
            stat_grid(
                [
                    ("Possession", possession),
                    ("Corruption", ring.corruption),
                    ("Pull", ring.pull),
                    ("Bearers", len(ring.bearer_history)),
                ]
            ),
        ]
        journey = self._ring_journey(ring)
        if journey:
            parts.append(section("Journey"))
            parts.append(para("<br>".join(journey)))
        return "".join(parts)

    def _ring_journey(self, ring: Ring) -> List[str]:
        """The Ring's transfer/bearer history as dossier lines (oldest first).

        Read off the accumulated feed (never the live world), capped at the
        displayed year so a scrub reads the journey only as far as it had gone.
        """
        events = sorted(
            (
                ev
                for ev in self._events
                if ring.id in ev.subject_ids and ev.year <= self._display_year
            ),
            key=lambda ev: (ev.year, ev.id),
        )
        return [f"TA {ev.year}: {esc(ev.text or ev.type)}" for ev in events]

    def describe_army(self, army: Army) -> str:
        """A host-subject dossier (HTML): strength first, siege when investing,
        a locator for where it stands, and its faction as trimmed context."""
        leader = None
        if army.leader_id is not None and self._latest_snapshot is not None:
            leader = self._latest_snapshot.entity(army.leader_id)
        faction = self._faction(army.faction_id) if army.faction_id else None
        if army.dest_site_id is not None:
            dest_site = self._grid.site_by_id(army.dest_site_id)
            destination = dest_site.name if dest_site is not None else "the field"
        else:
            destination = "holding (in garrison)"
        accent = (
            self._owner_accent(army.faction_id) if army.faction_id else NEUTRAL_ACCENT
        )
        stats = [
            ("Strength", army.size),  # the hero stat leads
            ("Leader", leader.name if leader else "— (leaderless)"),
            ("Faction", faction.name if faction is not None else "—"),
            ("Destination", destination),
        ]
        # A host investing a seat shows the drama the map can't: how far the
        # walls have been worn down (Army.siege_progress was invisible before).
        seat = self._host_seat(army)
        siege = self._siege_line(army, seat)
        if siege is not None:
            stats.insert(1, ("Siege", siege))
        parts = [banner("Host", army.name, accent), stat_grid(stats)]
        parts.append(self._host_locator(army, seat))
        if faction is not None:
            parts.append(self._faction_context(faction))
        return "".join(parts)

    def _host_seat(self, army: Army):
        """The settlement on the host's tile, if any — the seat it may besiege.

        Shared by the host dossier and the armies index so the two never price a
        host's siege differently."""
        return next(
            (s for s in self._grid.sites if s.col == army.col and s.row == army.row),
            None,
        )

    def _siege_line(self, army: Army, seat) -> Optional[str]:
        """``progress / walls`` while a host invests ``seat``, else ``None``."""
        if army.siege_progress > 0 and seat is not None:
            return f"{army.siege_progress} / {fortification(seat)}"
        return None

    def _host_locator(self, army: Army, seat) -> str:
        """One dim line placing the host: seat, region, and whose land it is."""
        grid = self._grid
        region = grid.region_at(army.col, army.row)
        owner = grid.owner_at(army.col, army.row)
        bits = []
        if seat is not None:
            bits.append(f"at {seat.name}")
        if region is not None:
            bits.append(f"in {region.name}")
        if owner != UNOWNED:
            bits.append(f"land of {self._faction_names.get(owner, f'faction {owner}')}")
        where = ", ".join(bits) if bits else f"at ({army.col}, {army.row})"
        return para(f'<span style="color: {DIM}">Stands {esc(where)}</span>')

    def describe_site(self, site) -> str:
        """A site-subject dossier (HTML): rank, ground, and the holder as context."""
        owner = self._grid.owner_at(site.col, site.row)
        rank = site.kind.title()
        if site.tier:
            rank = f"{rank} · tier {site.tier}"
        region = self._grid.region_at(site.col, site.row)
        parts = [
            banner("Site", site.name, self._owner_accent(owner)),
            stat_grid(
                [
                    ("Rank", rank),
                    (
                        "Owner",
                        "unowned"
                        if owner == UNOWNED
                        else self._faction_names.get(owner, f"faction {owner}"),
                    ),
                    ("Region", region.name if region else "—"),
                    ("Terrain", self._grid.terrain_at(site.col, site.row)),
                ]
            ),
        ]
        if owner != UNOWNED:
            faction = self._faction(owner)
            if faction is not None:
                parts.append(self._faction_context(faction))
        return "".join(parts)

    def _faction_context(self, faction: Faction) -> str:
        """The trimmed faction section under a host/site subject: leader,
        strength, and a one-line stance summary — full depth is one click
        away on the realm's open ground."""
        leader = None
        if faction.leader_id is not None and self._latest_snapshot is not None:
            leader = self._latest_snapshot.entity(faction.leader_id)
        parts = [
            section(faction.name),
            stat_grid(
                [
                    ("Leader", leader.name if leader else "—"),
                    ("Strength", faction.military_strength),
                ]
            ),
        ]
        summary = self._stance_summary(faction)
        if summary:
            parts.append(para(f'<span style="color: {DIM}">{esc(summary)}</span>'))
        return "".join(parts)

    def _stance_summary(self, faction: Faction) -> Optional[str]:
        """One line of the bonds that matter: wars, treaties, fealty."""
        names = self._faction_names
        bits: List[str] = []
        wars = sorted(names.get(f, str(f)) for f in faction.at_war_with)
        if wars:
            bits.append(f"at war with {', '.join(wars)}")
        treaties = sorted(names.get(f, str(f)) for f in faction.treaties)
        if treaties:
            bits.append(f"treaty with {', '.join(treaties)}")
        if faction.overlord_faction_id is not None:
            bits.append(f"vassal of {names.get(faction.overlord_faction_id, '—')}")
        return " · ".join(bits) if bits else None

    def describe_faction(self, faction: Faction) -> str:
        """A faction dossier (HTML): banner, stats, then the deep sections."""
        leader = None
        if faction.leader_id is not None and self._latest_snapshot is not None:
            leader = self._latest_snapshot.entity(faction.leader_id)
        # Prominence and the yearly intent are sim internals — dropped from the
        # grid by decision; intent still reads via faction-intent events below.
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
                ]
            ),
        ]
        diplomacy_lines = self._describe_diplomacy(faction)
        if diplomacy_lines:
            parts.append(section("Diplomacy"))
            parts.append(para("<br>".join(diplomacy_lines)))
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
                para(
                    "<br>".join(
                        self._event_line(ev) for ev in reversed(recent)  # newest first
                    )
                )
            )
        return "".join(parts)

    def _event_line(self, event: Event) -> str:
        """A recent-events line wearing its bucket color as a leading dot,
        so the mini-history reads consistently with the annals feed."""
        color = BUCKET_COLORS.get(bucket_of(event.type))
        dot = (
            f'<span style="color: {color.name() if color else DIM}">●</span> '
        )
        return f"{dot}TA {event.year}: {esc(event.text or event.type)}"

    def _describe_diplomacy(self, faction: Faction) -> Optional[List[str]]:
        """This faction's standing toward others, as HTML lines (or None).

        Shows the fealty bonds (overlord, vassals) and every non-neutral stance
        — stance words colored, the raw disposition scalar dimmed after. Read
        off the snapshot faction, so it reflects the scrubbed year, not the
        live world.
        """
        names = self._faction_names
        lines: List[str] = []
        fealty = f'color: {_FEALTY_COLOR}'
        if faction.overlord_faction_id is not None:
            overlord = esc(names.get(faction.overlord_faction_id, "—"))
            lines.append(f'Overlord: <span style="{fealty}">{overlord}</span>')
        if self._latest_snapshot is not None:
            vassals = sorted(
                names.get(e.id, str(e.id))
                for e in self._latest_snapshot.entities.values()
                if isinstance(e, Faction) and e.overlord_faction_id == faction.id
            )
            if vassals:
                joined = esc(", ".join(vassals))
                lines.append(f'Vassals: <span style="{fealty}">{joined}</span>')
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
            lines.append(
                f"{esc(names.get(other_id, other_id))}: "
                f"{self._stance_html(faction, other_id, label)} "
                f'<span style="color: {DIM}">({disp:+d})</span>'
            )
        return lines or None

    @staticmethod
    def _stance_html(faction: Faction, other_id: int, label: str) -> str:
        """The stance word in the feed's colors: open war reads bold red,
        mere hostility red, alliance green, vassalage purple."""
        if other_id in faction.at_war_with:
            return f'<b style="color: {_WAR_COLOR}">at war</b>'
        color = {
            ALLIANCE: _AMITY_COLOR,
            VASSALAGE: _FEALTY_COLOR,
        }.get(label, _WAR_COLOR)
        return f'<span style="color: {color}">{esc(label)}</span>'

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
