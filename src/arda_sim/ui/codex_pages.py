"""The Codex page-render library: addresses → dossier/index HTML.

Extracted whole from :class:`~arda_sim.ui.mainwindow.MainWindow` (#39). Every
non-map Codex surface — the ``describe_*`` dossiers, the ``_*_page`` wrappers,
the ``_*_index`` rolls, and the search page — lives here as a method on
:class:`CodexPages`.

The class is **headless**: it holds no back-reference to the window, imports no
Qt widgets, and reads only a small stored context (the current snapshot, the
accumulated event stream, the displayed year, and the Ring's per-tick trend)
plus its set-once config (the tile grid and faction-name overrides). The window
refreshes that context once per tick via :meth:`update` and delegates its Codex
router to :meth:`render`. Because nothing here touches Qt, the renderers are
pure functions of ``(snapshot, config)`` and can be tested without a window.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Tuple

from .. import START_YEAR
from ..armies import Army
from ..characters import (
    TRAIT_KEYS,
    Character,
    Race,
    Role,
    ancestors,
    children_of,
)
from ..diplomacy import ALLIANCE, NEUTRALITY, VASSALAGE, stance
from ..economy import faction_population
from ..entities import Event, EntityStatus
from ..factions import FACTION_INTENT_EVENT, Faction, SuccessionRule
from ..ring import RING_TRANSFERRED_EVENT, Ring, RingTransfer, the_ring
from ..snapshot import Snapshot
from ..succession import presumptive_heir
from ..tiles import UNOWNED, TileGrid
from ..war import fortification
from .annals_style import BUCKET_COLORS, CONSTRUCTION, DYNASTY, WAR, bucket_of
from . import tile_render
from .codex import CodexAddress, render_search_page, search_matches
from .dossier_html import (
    DIM,
    NEUTRAL_ACCENT,
    banner,
    dim_para,
    esc,
    index_table,
    para,
    section,
    sparkline,
    stat_grid,
    tab_strip,
)
from .event_dossier import render_event_dossier

# Stance words wear the feed's color vocabulary (inspection-ui ticket 03):
# war-red for open war and hostility, the peaceable green for alliance/treaty,
# the dynasty purple for fealty bonds.
_WAR_COLOR = BUCKET_COLORS[WAR].name()
_AMITY_COLOR = BUCKET_COLORS[CONSTRUCTION].name()
_FEALTY_COLOR = BUCKET_COLORS[DYNASTY].name()

# The One Ring's dossier accent — the same warm gold as its map marker (ticket 13).
_RING_ACCENT = "#e9c46a"

# Dynasty-view node badges (#21): a warm gold marks the seated ruler, the
# dynasty purple the presumptive heir — read against the tree's linked nodes.
_RULER_BADGE = "#c99a3b"
_HEIR_BADGE = _FEALTY_COLOR

# The reader-facing life status word for a character dossier (#18): the entity
# status maps to plain speech — "active" is a person still in play, i.e. alive.
_STATUS_WORDS = {
    EntityStatus.ACTIVE.value: "alive",
    EntityStatus.DEAD.value: "dead",
    EntityStatus.DEPARTED.value: "departed",
    EntityStatus.DESTROYED.value: "destroyed",
}


class RingTrendSample(NamedTuple):
    """One per-tick reading of the Ring's scalars, for the trend sparkline (#23).

    The window accumulates the series (a scrub-safe writer keyed off the tick)
    and passes it into :meth:`CodexPages.update`; the Ring page reads it here."""

    tick: int
    year: int
    corruption: int
    pull: int


class _BearerStint(NamedTuple):
    """One span of the bearer timeline (#23): who held the Ring, when, and how it
    came to them. ``end`` is ``None`` while they still hold it; ``mode`` is
    ``None`` for the founding bearer, whose acquisition predates any transfer."""

    bearer_id: int
    start: int
    end: Optional[int]
    mode: Optional[str]


# Human-readable phrasing for each transfer mode, for the bearer timeline (#23).
# Keyed by the RingTransfer value; an unmapped mode falls back to its raw value.
_TRANSFER_LABELS = {
    RingTransfer.INHERITANCE.value: "inheritance",
    RingTransfer.GIFT.value: "gift",
    RingTransfer.THEFT.value: "theft",
    RingTransfer.FOUND.value: "finding",
    RingTransfer.WAR_CAPTURE.value: "war-capture",
}


def living_armies(snapshot: Snapshot) -> List[Army]:
    """The living hosts in a snapshot, in id order (for the map layer and index).

    A module function, not a method, because the window's map-refresh path reads
    it too — it is a pure fold over a snapshot, not part of the render context."""
    return [
        e
        for _id, e in sorted(snapshot.entities.items())
        if isinstance(e, Army) and e.alive
    ]


class CodexPages:
    """The Codex page-render library over a read-only per-tick context.

    Constructed once with the set-once config (tile grid, faction-name
    overrides); refreshed each tick via :meth:`update`; queried via
    :meth:`render`. Holds no window reference and no Qt — see the module
    docstring.
    """

    def __init__(
        self, grid: TileGrid, faction_names: Optional[Dict[int, str]] = None
    ) -> None:
        self._grid = grid
        self._faction_names = faction_names or {}
        # The per-tick render context, refreshed by update(). Empty until the
        # first tick lands: no snapshot, no events, the year one before the seed.
        self._latest_snapshot: Optional[Snapshot] = None
        self._events: List[Event] = []
        self._display_year = START_YEAR - 1
        self._ring_trend: List[RingTrendSample] = []

    def update(
        self,
        *,
        snapshot: Snapshot,
        events: List[Event],
        display_year: int,
        ring_trend: List[RingTrendSample],
    ) -> None:
        """Refresh the per-tick render context from the window.

        Called once per tick (including scrub-restores). The Ring-trend series is
        accumulated by the window — a tick-lifecycle writer that must not move
        here — and passed in whole; everything else is the displayed tick's view.
        """
        self._latest_snapshot = snapshot
        self._events = events
        self._display_year = display_year
        self._ring_trend = ring_trend

    # -- the codex: addresses -> pages -----------------------------------

    def render(self, address: CodexAddress) -> Optional[str]:
        """The Codex's registry: resolve an address to page HTML.

        ``None`` means a dead link (unknown kind, malformed ident, or an
        entity absent from the displayed year) — the pane renders its own
        no-such-page notice, so renderers stay total and never raise.
        """
        renderers = {
            "tile": self._tile_page,
            "site": self._site_page,
            "faction": self._faction_page,
            "character": self._character_page,
            "diplomacy": self._diplomacy_page,
            "dynasty": self._dynasty_page,
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

    def _character_page(self, ident: str) -> Optional[str]:
        char_id = self._int_ident(ident)
        char = self._character(char_id) if char_id is not None else None
        return self.describe_character(char) if char is not None else None

    def _diplomacy_page(self, ident: str) -> Optional[str]:
        """A Diplomacy tab (ADR-0014, #20): ``codex://diplomacy/faction:<id>``.

        The ident is **typed** exactly like the Dynasty tab's — a
        ``faction:<id>`` pair. Only ``faction`` is served; a malformed or
        unknown-type ident is a dead link (``None``), never a raise.
        """
        kind, sep, raw = ident.partition(":")
        if not sep or kind != "faction":
            return None
        faction_id = self._int_ident(raw)
        faction = self._faction(faction_id) if faction_id is not None else None
        if faction is None or self._latest_snapshot is None:
            return None
        return self.describe_diplomacy_page(faction)

    def _dynasty_page(self, ident: str) -> Optional[str]:
        """A Dynasty tab (ADR-0014): ``codex://dynasty/faction:<id>`` or
        ``codex://dynasty/character:<id>``.

        The ident is **typed** — a ``<type>:<id>`` pair naming what roots the
        tree. ``faction`` roots at the realm's current leader (its ruling
        bloodline); ``character`` (#18) roots at that person, so the same
        renderer serves both from a single typed ident. A malformed or
        unknown-type ident is a dead link (``None``), never a raise.
        """
        kind, sep, raw = ident.partition(":")
        if not sep or self._latest_snapshot is None:
            return None
        subject_id = self._int_ident(raw)
        if subject_id is None:
            return None
        if kind == "faction":
            faction = self._faction(subject_id)
            return self.describe_dynasty(faction) if faction is not None else None
        if kind == "character":
            char = self._character(subject_id)
            return (
                self.describe_character_dynasty(char) if char is not None else None
            )
        return None

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
        # The accumulated feed retains every delivered event, filtered or not, so
        # it is the one lookup path an event address needs.
        event = next((e for e in self._events if e.id == event_id), None)
        return self.describe_event(event) if event is not None else None

    def _ring_page(self, ident: str) -> Optional[str]:
        del ident  # there is only the One
        if self._latest_snapshot is None:
            return None
        ring = self._ring_in(self._latest_snapshot)
        return self.describe_ring(ring) if ring is not None else None

    def _index_page(self, ident: str) -> Optional[str]:
        """An index page. The ident is the index name, optionally followed by a
        ``/<sort>`` — so ``armies`` and ``armies/faction`` are the same page
        under different sort orders (each an ordinary history entry). Every
        listed index (#17/#19/#20/#18) is live; an unknown name is a dead link."""
        name, _, sort = ident.partition("/")
        if name == "armies":
            return self._armies_index(sort or None)
        if name == "factions":
            return self._factions_index(sort or None)
        if name == "characters":
            return self._characters_index(sort or None)
        if name == "wars":
            return self._wars_index(sort or None)
        return None

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

    # The characters-index columns, in display order: (header label, sort key,
    # descending?). The name column carries the row's link to the character
    # dossier; the roll opens most-prominent-first, so prominence is the default.
    _CHARACTER_COLUMNS = (
        ("Name", "name", False),
        ("Race", "race", False),
        ("Faction", "faction", False),
        ("Role", "role", False),
        ("Status", "status", False),
        ("Age", "age", True),
        ("Prominence", "prominence", True),
    )
    _DEFAULT_CHARACTER_SORT = "prominence"

    def _characters_index(self, sort: Optional[str]) -> str:
        """The Characters index (#18): every person in the snapshot as a table.

        Each row names a character (linking to their dossier), with race,
        faction (linked), role/title, life status, age, and prominence. Column
        headers are sort links; the roll defaults to prominence, greatest first.
        Snapshot-scoped like the rest of the Codex — dead and departed people
        stay listed (their records persist), so scrubbing changes who appears.
        """
        columns = {key: desc for _label, key, desc in self._CHARACTER_COLUMNS}
        if sort not in columns:
            sort = self._DEFAULT_CHARACTER_SORT
        characters = (
            self._characters_in(self._latest_snapshot)
            if self._latest_snapshot is not None
            else []
        )
        head = banner("Index", "Characters")
        if not characters:
            return head + dim_para("No people walk the record in the displayed year.")
        rows = [self._character_index_row(char) for char in characters]
        rows.sort(key=lambda row: row["sort"][sort], reverse=columns[sort])
        headers = [
            self._character_index_header(label, key, sort)
            for label, key, _desc in self._CHARACTER_COLUMNS
        ]
        return head + index_table(headers, (row["cells"] for row in rows))

    def _character_index_header(self, label: str, key: str, active: str) -> str:
        """A column header: a sort link, or bold plain text for the live sort."""
        if key == active:
            return f"<b>{esc(label)}</b>"
        return f'<a href="codex://index/characters/{key}">{esc(label)}</a>'

    def _character_index_row(self, char: Character) -> dict:
        """One person's index row: its sort values (per column key) and the
        pre-composed HTML cells (name linking to the dossier, faction linked)."""
        faction = (
            self._faction(char.faction_id)
            if char.faction_id is not None
            else None
        )
        faction_name = faction.name if faction is not None else None
        role = char.title or (
            char.role.title() if char.role and char.role != Role.NONE.value else "—"
        )
        status = self._character_status_word(char)
        age = char.age(self._display_year)
        cells = [
            self._codex_link("character", char.id, char.name),
            esc(char.race.title()),
            self._faction_cell(char.faction_id, faction_name),
            esc(role),
            esc(status),
            esc(age),
            esc(char.prominence),
        ]
        return {
            "cells": cells,
            "sort": {
                "name": char.name.lower(),
                "race": char.race.lower(),
                "faction": (faction_name or "").lower(),
                "role": role.lower(),
                "status": status,
                "age": age,
                "prominence": char.prominence,
            },
        }

    # The wars-index columns, in display order: (header label, sort key,
    # descending?). A relation is a symmetric pair, so both cells link to a
    # faction dossier; the roll opens grouped by relation (wars before treaties).
    _WARS_COLUMNS = (
        ("Relation", "relation", False),
        ("Between", "between", False),
        ("And", "and", False),
    )
    _DEFAULT_WARS_SORT = "relation"

    def _diplomatic_pairs(
        self, factions: List[Faction]
    ) -> List[Tuple[str, int, int]]:
        """The deduped ``(relation, id_a, id_b)`` bonds across the living factions.

        Wars and treaties are *symmetric* (each id sits on both parties' lists),
        so each unordered pair is emitted once — keyed by ``(relation, lo, hi)``
        of the two ids. Within a pair the two ids are ordered by faction name, so
        a row reads and sorts stably. A bond to a faction absent from the
        displayed year is dropped (nothing to link to)."""
        names = self._faction_names
        living = {faction.id for faction in factions}
        seen: set = set()
        pairs: List[Tuple[str, int, int]] = []
        for faction in factions:
            for relation, others in (
                ("war", faction.at_war_with),
                ("treaty", faction.treaties),
            ):
                for other_id in others:
                    if other_id not in living:
                        continue
                    key = (relation, *sorted((faction.id, other_id)))
                    if key in seen:
                        continue
                    seen.add(key)
                    a, b = sorted(
                        (faction.id, other_id),
                        key=lambda fid: names.get(fid, str(fid)).lower(),
                    )
                    pairs.append((relation, a, b))
        return pairs

    def _wars_index(self, sort: Optional[str]) -> str:
        """The Wars index (#20): every war and treaty as a sortable table.

        Each row is one symmetric relation — a war or a treaty — deduped to a
        single line, both sides linking to their faction dossiers. Column headers
        are sort links; the roll defaults to relation (wars before treaties).
        Reads only the displayed snapshot, like the rest of the Codex.
        """
        columns = {key: desc for _label, key, desc in self._WARS_COLUMNS}
        if sort not in columns:
            sort = self._DEFAULT_WARS_SORT
        factions = (
            self._factions_in(self._latest_snapshot)
            if self._latest_snapshot is not None
            else []
        )
        head = banner("Index", "Wars")
        pairs = self._diplomatic_pairs(factions)
        if not pairs:
            return head + dim_para(
                "No wars or treaties bind the realms in the displayed year."
            )
        rows = [self._wars_index_row(rel, a, b) for rel, a, b in pairs]
        rows.sort(key=lambda row: row["sort"][sort], reverse=columns[sort])
        headers = [
            self._wars_index_header(label, key, sort)
            for label, key, _desc in self._WARS_COLUMNS
        ]
        return head + index_table(headers, (row["cells"] for row in rows))

    def _wars_index_header(self, label: str, key: str, active: str) -> str:
        """A column header: a sort link, or bold plain text for the live sort."""
        if key == active:
            return f"<b>{esc(label)}</b>"
        return f'<a href="codex://index/wars/{key}">{esc(label)}</a>'

    def _wars_index_row(self, relation: str, a_id: int, b_id: int) -> dict:
        """One relation's index row: its sort values and the pre-composed HTML
        cells (the relation word colored, each side linking to its dossier)."""
        names = self._faction_names
        a_name = names.get(a_id, str(a_id))
        b_name = names.get(b_id, str(b_id))
        cells = [
            self._relation_html(relation),
            self._faction_cell(a_id, a_name),
            self._faction_cell(b_id, b_name),
        ]
        return {
            "cells": cells,
            "sort": {
                "relation": relation,
                "between": a_name.lower(),
                "and": b_name.lower(),
            },
        }

    @staticmethod
    def _relation_html(relation: str) -> str:
        """A relation word in the feed's colors: war reads bold red, treaty green."""
        if relation == "war":
            return f'<b style="color: {_WAR_COLOR}">War</b>'
        return f'<span style="color: {_AMITY_COLOR}">Treaty</span>'

    def _search_page(self, query: str) -> str:
        return render_search_page(
            query, search_matches(query, self._search_candidates())
        )

    def _search_candidates(self):
        """Every searchable (name, detail, address): factions → hosts →
        characters → sites.

        Snapshot-scoped like the rest of the Codex: the named entities present
        in the displayed snapshot plus the grid's sites. Characters (#18) join
        here — only those present in the displayed year, so scrubbing the
        timeline changes who is findable.
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
            for char in self._characters_in(self._latest_snapshot):
                candidates.append(
                    (
                        char.name,
                        self._character_detail(char),
                        CodexAddress("character", str(char.id)),
                    )
                )
        for site in self._grid.sites:
            candidates.append(
                (site.name, site.kind, CodexAddress("site", str(site.id)))
            )
        return candidates

    @staticmethod
    def _characters_in(snapshot: Snapshot) -> List[Character]:
        """Every character in a snapshot, in id order (dead/departed included —
        their records persist and stay searchable as historical figures)."""
        return [
            e
            for _id, e in sorted(snapshot.entities.items())
            if isinstance(e, Character)
        ]

    def _character_detail(self, char: Character) -> str:
        """A character's search detail line: race, then role/title, then a
        non-alive status — e.g. "Dúnedain · Steward of Gondor" or "Elf · departed".
        """
        bits = [char.race.title()]
        if char.title:
            bits.append(char.title)
        elif char.role and char.role != Role.NONE.value:
            bits.append(char.role.title())
        status = self._character_status_word(char)
        if status != "alive":
            bits.append(status)
        return " · ".join(bits)

    # -- events ----------------------------------------------------------

    def describe_event(self, event: Event) -> str:
        """The event dossier for the Codex event page (annals-ui ticket 03)."""
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

    def _event_line(self, event: Event) -> str:
        """A recent-events line wearing its bucket color as a leading dot,
        so the mini-history reads consistently with the annals feed."""
        color = BUCKET_COLORS.get(bucket_of(event.type))
        dot = (
            f'<span style="color: {color.name() if color else DIM}">●</span> '
        )
        return f"{dot}TA {event.year}: {esc(event.text or event.type)}"

    # -- tiles / sites / hosts -------------------------------------------

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

    def _character(self, char_id: int) -> Optional[Character]:
        """The character record as of the displayed year (from the snapshot).

        Snapshot-scoped like :meth:`_faction`: a character born after the
        displayed year is simply absent (``None``), so scrubbing the timeline
        changes who resolves. Dead and departed people persist in the snapshot,
        so their dossiers and dynasty links still read back."""
        if self._latest_snapshot is None:
            return None
        entity = self._latest_snapshot.entity(char_id)
        return entity if isinstance(entity, Character) else None

    def _armies_in(self, snapshot: Snapshot) -> List[Army]:
        """The living hosts in a snapshot, in id order (for the map layer)."""
        return living_armies(snapshot)

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

    # -- factions / diplomacy / dynasty ----------------------------------

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

    def _faction_tabs(self, faction: Faction, active: str) -> str:
        """The faction dossier's internal tab strip (ADR-0014): each entry an
        ordinary ``codex://`` page, so history/back reach every tab. Both the
        Overview and Dynasty pages emit this same strip, differing only in which
        entry is active — #20/#25 add their Diplomacy/Regions entries here once.
        """
        return tab_strip(
            [
                ("Overview", f"codex://faction/{faction.id}", active == "Overview"),
                (
                    "Diplomacy",
                    f"codex://diplomacy/faction:{faction.id}",
                    active == "Diplomacy",
                ),
                (
                    "Dynasty",
                    f"codex://dynasty/faction:{faction.id}",
                    active == "Dynasty",
                ),
            ]
        )

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
            self._faction_tabs(faction, active="Overview"),
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

    def describe_diplomacy_page(self, faction: Faction) -> str:
        """The Diplomacy tab (#20): the faction's whole diplomatic picture.

        A ``codex://diplomacy/faction:<id>`` page alongside Overview/Dynasty:
        its **active wars** and **treaties** as linked faction pairs, a
        **disposition list showing drift** from the frozen ``baseline_disposition``
        (so the reader sees how far each relation has moved from its authored
        attractor), and the faction's **standing intent** — read from the latest
        ``faction_intent`` event, honouring the intent-via-events decision rather
        than printing the transient ``current_intent`` scalar. Stances reuse the
        derived :func:`stance` and the established stance/fealty colors. Reads
        only the displayed snapshot, so it reflects the scrubbed year.
        """
        names = self._faction_names
        parts = [
            banner("Diplomacy", faction.name, self._owner_accent(faction.id)),
            self._faction_tabs(faction, active="Diplomacy"),
        ]

        wars = [
            self._faction_cell(fid, names.get(fid, str(fid)))
            for fid in sorted(
                faction.at_war_with,
                key=lambda f: names.get(f, str(f)).lower(),
            )
            if self._faction(fid) is not None
        ]
        parts.append(section("Active wars"))
        parts.append(
            para(
                '<span style="color: %s">At war with </span>%s'
                % (DIM, " · ".join(wars))
            )
            if wars
            else dim_para("At peace with all.")
        )

        treaties = [
            self._faction_cell(fid, names.get(fid, str(fid)))
            for fid in sorted(
                faction.treaties,
                key=lambda f: names.get(f, str(f)).lower(),
            )
            if self._faction(fid) is not None
        ]
        parts.append(section("Treaties"))
        parts.append(
            para(
                '<span style="color: %s">Sworn to </span>%s'
                % (DIM, " · ".join(treaties))
            )
            if treaties
            else dim_para("No standing pacts.")
        )

        drift = self._disposition_drift(faction)
        parts.append(section("Disposition (drift from baseline)"))
        parts.append(
            para("<br>".join(drift))
            if drift
            else dim_para("No feeling stirs toward any other power.")
        )

        parts.append(section("Standing intent"))
        intent = self._standing_intent(faction)
        parts.append(
            para(esc(intent))
            if intent
            else dim_para("This power has taken no counsel yet.")
        )
        return "".join(parts)

    def _disposition_drift(self, faction: Faction) -> List[str]:
        """Each related power's stance and how far its disposition has drifted.

        One line per faction this one has any bond or feeling toward (a war, a
        treaty, or a live/baseline disposition entry): the stance word colored,
        then the current scalar against its frozen baseline and the signed drift
        — so a relation warming toward alliance or souring toward war reads at a
        glance. Neutral pairs are kept here (unlike the Overview) precisely so
        their drift shows."""
        names = self._faction_names
        related = (
            set(faction.at_war_with)
            | set(faction.treaties)
            | {int(k) for k in faction.disposition}
            | {int(k) for k in faction.baseline_disposition}
        )
        lines: List[str] = []
        for other_id in sorted(
            related, key=lambda f: names.get(f, str(f)).lower()
        ):
            other = self._faction(other_id)
            if other is None:
                continue
            current = faction.disposition_toward(other_id)
            baseline = faction.baseline_toward(other_id)
            delta = current - baseline
            drift = f"drifted {delta:+d}" if delta else "at baseline"
            label = stance(faction, other)
            lines.append(
                f"{self._faction_cell(other_id, names.get(other_id, str(other_id)))}: "
                f"{self._stance_html(faction, other_id, label)} "
                f'<span style="color: {DIM}">'
                f"(now {current:+d}, baseline {baseline:+d} · {drift})</span>"
            )
        return lines

    def _standing_intent(self, faction: Faction) -> Optional[str]:
        """The faction's standing intent as its latest ``faction_intent`` prose.

        Honours the intent-via-events decision: rather than print the transient
        ``current_intent`` scalar, it reads the most recent intent event at/under
        the displayed year and reuses the chronicle sentence already stamped on
        it — the same words the annals show. ``None`` when none has fired yet."""
        latest = None
        for event in self._events:
            if (
                event.type == FACTION_INTENT_EVENT
                and faction.id in event.subject_ids
                and event.year <= self._display_year
            ):
                latest = event
        if latest is None:
            return None
        return latest.text or latest.type

    def describe_dynasty(self, faction: Faction) -> str:
        """The Dynasty tab (#21): the ruling bloodline as an indented, linked tree.

        Rooted at the faction's current leader, it draws forebears, self, then
        descendants — a linked HTML tree over the same kinship queries the heir
        walk reads (``ancestors``/``children_of``). Dead kin show ``†`` dimmed;
        the current ruler and the presumptive heir are badged; spouses hang
        inline off their partner (``⚭``), reachable but never walked as a branch.
        Every kin node is a ``codex://character/<id>`` link (live once #18 lands).
        """
        snapshot = self._latest_snapshot
        leader = None
        if faction.leader_id is not None and snapshot is not None:
            leader = snapshot.entity(faction.leader_id)
        parts = [
            banner("Dynasty", faction.name, self._owner_accent(faction.id)),
            self._faction_tabs(faction, active="Dynasty"),
        ]
        if not isinstance(leader, Character):
            parts.append(dim_para("This seat holds no ruling line to trace."))
            return "".join(parts)
        # Past the guard a leader resolved, so the snapshot is non-None.

        elective = faction.succession_rule == SuccessionRule.ELECTIVE.value
        heir = None if elective else presumptive_heir(snapshot, faction)
        if elective:
            parts.append(dim_para("Seat is elective — no fixed heir."))
        elif heir is not None:
            parts.append(
                para(
                    '<span style="color: %s">Presumptive heir: </span>%s'
                    % (DIM, self._kin_link(heir))
                )
            )

        lines: List[str] = []
        heir_id = heir.id if heir is not None else None
        for forebear in reversed(ancestors(snapshot, leader.id)):
            lines.append(self._dynasty_line(forebear, 0, leader.id, heir_id))
        lines.append(self._dynasty_line(leader, 0, leader.id, heir_id))
        self._append_dynasty_descendants(leader.id, 1, lines, leader.id, heir_id)
        parts.append(para("<br>".join(lines)))
        return "".join(parts)

    def _append_dynasty_descendants(
        self,
        char_id: int,
        depth: int,
        out: List[str],
        ruler_id: int,
        heir_id: Optional[int],
    ) -> None:
        """Walk the child links depth-first (each child's line before its own
        children, indented one deeper), appending an HTML line per descendant."""
        for child in children_of(self._latest_snapshot, char_id):
            out.append(self._dynasty_line(child, depth, ruler_id, heir_id))
            self._append_dynasty_descendants(
                child.id, depth + 1, out, ruler_id, heir_id
            )

    def _dynasty_line(
        self, char: Character, depth: int, ruler_id: int, heir_id: Optional[int]
    ) -> str:
        """One node's line: indentation, a branch glyph below the root, the linked
        node with its spouse and badges — dimmed whole when the kin is dead."""
        indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * depth
        branch = "└&nbsp;" if depth > 0 else ""
        node = self._kin_link(char)
        if char.spouse_id is not None and self._latest_snapshot is not None:
            spouse = self._latest_snapshot.entity(char.spouse_id)
            if isinstance(spouse, Character):
                node += f" ⚭ {self._kin_link(spouse)}"
        if char.id == ruler_id:
            node += self._dynasty_badge("Ruler", _RULER_BADGE)
        if heir_id is not None and char.id == heir_id:
            node += self._dynasty_badge("Heir", _HEIR_BADGE)
        line = indent + branch + node
        if not char.alive:  # the whole line dims for a dead kin
            return f'<span style="color: {DIM}">{line}</span>'
        return line

    @staticmethod
    def _kin_link(char: Character) -> str:
        """A kin node: a ``codex://character/<id>`` link, ``†`` if dead.

        Emitted unconditionally — until #18 registers the ``character`` kind
        these resolve to the pane's graceful no-such-page notice, and self-heal
        when it lands."""
        mark = "" if char.alive else " †"
        return (
            f'<a href="codex://character/{char.id}">{esc(char.name)}</a>{mark}'
        )

    @staticmethod
    def _dynasty_badge(text: str, color: str) -> str:
        """A small colored badge trailing a node (the ruler, the heir)."""
        return (
            f'&nbsp;<span style="color: {color}; font-size: small">'
            f"<b>[{esc(text)}]</b></span>"
        )

    # -- characters ------------------------------------------------------

    @staticmethod
    def _character_status_word(char: Character) -> str:
        """A character's life status in plain speech (alive / dead / departed)."""
        return _STATUS_WORDS.get(char.status, char.status)

    def _character_tabs(self, char: Character, active: str) -> str:
        """The character dossier's internal tab strip (ADR-0014, #18): Overview
        and Dynasty, each an ordinary ``codex://`` page so history/back reach
        both — mirroring the faction strip. The Dynasty entry roots the shared
        ``dynasty`` renderer at this character (``character:<id>``)."""
        return tab_strip(
            [
                ("Overview", f"codex://character/{char.id}", active == "Overview"),
                (
                    "Dynasty",
                    f"codex://dynasty/character:{char.id}",
                    active == "Dynasty",
                ),
            ]
        )

    def describe_character(self, char: Character) -> str:
        """A character dossier (#18): banner, stats, traits, allegiance, kin.

        Rendered through the shared dossier anatomy like every other page. Shows
        race, role/title, life status, age at the displayed year, prominence,
        and (**Elves only**) weariness; then the person's faction and current
        location as linked pages, the trait vector, and kin — spouse, parents,
        and children as linked character pages. Reads only the displayed
        snapshot, so a scrub reflects the person's state that year.
        """
        accent = (
            self._owner_accent(char.faction_id)
            if char.faction_id is not None
            else NEUTRAL_ACCENT
        )
        parts = [
            banner(f"Character · {char.race.title()}", char.name, accent),
            self._character_tabs(char, active="Overview"),
        ]
        stats = [
            ("Title", char.title),  # None drops the row
            (
                "Role",
                char.role.title()
                if char.role and char.role != Role.NONE.value
                else None,
            ),
            ("Status", self._character_status_word(char)),
            ("Age", char.age(self._display_year)),
            ("Prominence", char.prominence),
        ]
        if char.race == Race.ELF.value:
            stats.append(("Weariness", char.weariness))
        parts.append(stat_grid(stats))

        parts.append(section("Allegiance"))
        parts.append(para("<br>".join(self._character_allegiance(char))))

        parts.append(section("Traits"))
        parts.append(
            stat_grid(
                [(key.title(), char.traits.get(key, 0)) for key in TRAIT_KEYS]
            )
        )

        kin = self._character_kin(char)
        parts.append(section("Kin"))
        parts.append(
            para("<br>".join(kin))
            if kin
            else dim_para("No kin are recorded.")
        )
        return "".join(parts)

    @staticmethod
    def _labeled(label: str, value_html: str) -> str:
        """A dossier line: a dimmed ``Label:`` lead-in, then composed value HTML."""
        return f'<span style="color: {DIM}">{esc(label)}: </span>{value_html}'

    def _character_allegiance(self, char: Character) -> List[str]:
        """The faction and current location lines, each a linked page or a dash."""
        faction = (
            self._faction(char.faction_id)
            if char.faction_id is not None
            else None
        )
        faction_html = (
            self._codex_link("faction", faction.id, faction.name)
            if faction is not None
            else "—"
        )
        site = (
            self._grid.site_by_id(char.location_id)
            if char.location_id is not None
            else None
        )
        location_html = (
            self._codex_link("site", site.id, site.name)
            if site is not None
            else "—"
        )
        return [
            self._labeled("Faction", faction_html),
            self._labeled("Location", location_html),
        ]

    def _character_kin(self, char: Character) -> List[str]:
        """Spouse, parents, and children as linked lines, each omitted when empty.

        Reuses the kinship queries (``children_of``) and the snapshot for spouse
        and parents rather than re-walking id fields — every kin a
        ``codex://character/<id>`` link, dead kin marked ``†`` (see :meth:`_kin_link`).
        """
        snapshot = self._latest_snapshot
        lines: List[str] = []
        if char.spouse_id is not None and snapshot is not None:
            spouse = snapshot.entity(char.spouse_id)
            if isinstance(spouse, Character):
                lines.append(self._labeled("Spouse", self._kin_link(spouse)))
        parents = [
            p
            for pid in char.parent_ids
            if snapshot is not None
            and isinstance((p := snapshot.entity(pid)), Character)
        ]
        if parents:
            joined = ", ".join(self._kin_link(p) for p in parents)
            lines.append(self._labeled("Parents", joined))
        children = (
            children_of(snapshot, char.id) if snapshot is not None else []
        )
        if children:
            joined = ", ".join(self._kin_link(c) for c in children)
            lines.append(self._labeled("Children", joined))
        return lines

    def describe_character_dynasty(self, char: Character) -> str:
        """The Dynasty tab rooted at a character (#18): the family line as an
        indented, linked tree — forebears, self, then descendants.

        The ``character`` variant of the shared ``dynasty`` renderer (ADR-0014):
        it reuses the same kinship walk and node rendering as the faction
        variant, only rooting the tree at the person rather than a realm's
        leader. A ruling person is badged; there is no presumptive-heir line (a
        seat's concern, not a person's).
        """
        snapshot = self._latest_snapshot
        accent = (
            self._owner_accent(char.faction_id)
            if char.faction_id is not None
            else NEUTRAL_ACCENT
        )
        parts = [
            banner("Dynasty", char.name, accent),
            self._character_tabs(char, active="Dynasty"),
        ]
        ruler_id = char.id if char.role == Role.RULER.value else None
        lines: List[str] = []
        for forebear in reversed(ancestors(snapshot, char.id)):
            lines.append(self._dynasty_line(forebear, 0, ruler_id, None))
        lines.append(self._dynasty_line(char, 0, ruler_id, None))
        self._append_dynasty_descendants(char.id, 1, lines, ruler_id, None)
        parts.append(para("<br>".join(lines)))
        return "".join(parts)

    # -- the One Ring ----------------------------------------------------

    def describe_ring(self, ring: Ring) -> str:
        """The One Ring dossier (HTML): where it is, its scalars, and its journey —
        a bearer timeline, a corruption trend, and any current errand.

        The journey view (issue #23): the raw scalars alone hid the story the sim
        tracks, so the page adds a bearer timeline (from the transfer feed), a
        sparkline over the accumulated trend, and a linked errand target."""
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
        parts.extend(self._ring_errand(ring))
        parts.extend(self._ring_trend_section())
        parts.extend(self._ring_bearer_timeline(ring))
        return "".join(parts)

    def _ring_errand(self, ring: Ring) -> List[str]:
        """The Ring's current errand, if any: the goal site named and linked.

        Deliberate movement toward a goal (``goal_site_id``/``path``); with no
        errand afoot the section is omitted rather than shown empty."""
        if ring.goal_site_id is None:
            return []
        site = self._grid.site_by_id(ring.goal_site_id)
        target = (
            self._codex_link("site", site.id, site.name)
            if site is not None
            else "an unknown place"
        )
        return [section("Errand"), para(f"Bound for {target}.")]

    def _ring_trend_section(self) -> List[str]:
        """A corruption/pull sparkline over the accumulated per-tick trend.

        Reads the stored ``_ring_trend`` series (never the live world), capped
        at the displayed year so a scrub traces the Ring only as far as time had
        gone. Needs at least two samples to trace a line."""
        samples = [s for s in self._ring_trend if s.year <= self._display_year]
        if len(samples) < 2:
            return []
        corruption = [s.corruption for s in samples]
        pull = [s.pull for s in samples]
        rows = stat_grid(
            [
                ("Corruption", f"{sparkline(corruption)}  {corruption[0]} → {corruption[-1]}"),
                ("Pull", f"{sparkline(pull)}  {pull[0]} → {pull[-1]}"),
            ]
        )
        return [section("Trend"), rows]

    def _ring_bearer_timeline(self, ring: Ring) -> List[str]:
        """The ordered roll of everyone who has borne the Ring — each with the
        years they held it and the mode by which it came to them.

        Reconstructed from the accumulated ``ring_transferred`` feed (its payload
        carries the mode and both ends of every handover), capped at the displayed
        year. ``bearer_history`` names only *who*, not when or how, so the timeline
        is built from the events, not that list; the list still seeds the founding
        bearer, whose acquisition predates play and fires no transfer event."""
        stints = self._ring_stints(ring)
        if not stints:
            return []
        lines = [self._bearer_stint_line(stint) for stint in stints]
        return [section("Bearers"), para("<br>".join(lines))]

    def _ring_stints(self, ring: Ring) -> List[_BearerStint]:
        """The bearer stints, oldest-first (see :class:`_BearerStint`).

        An interval where the Ring lay unborne opens no stint — it simply ends
        the prior bearer's."""
        transfers = sorted(
            (
                ev
                for ev in self._events
                if ev.type == RING_TRANSFERRED_EVENT
                and ring.id in ev.subject_ids
                and ev.year <= self._display_year
            ),
            key=lambda ev: (ev.year, ev.id),
        )
        stints: List[_BearerStint] = []
        open_bearer: Optional[int] = None
        open_start = ring.created_year
        open_mode: Optional[str] = None
        if ring.bearer_history:
            open_bearer = ring.bearer_history[0]
        for ev in transfers:
            if open_bearer is not None:
                stints.append(_BearerStint(open_bearer, open_start, ev.year, open_mode))
                open_bearer = None
            to_bearer = ev.payload.get("to_bearer_id")
            if to_bearer is not None:
                open_bearer, open_start, open_mode = (
                    int(to_bearer),
                    ev.year,
                    ev.payload.get("mode"),
                )
        if open_bearer is not None:
            stints.append(_BearerStint(open_bearer, open_start, None, open_mode))
        return stints

    def _bearer_stint_line(self, stint: _BearerStint) -> str:
        """One bearer-timeline row: the span, the linked bearer, the transfer mode."""
        span = (
            f"TA {stint.start}–{stint.end}"
            if stint.end is not None
            else f"TA {stint.start}–present"
        )
        bearer = (
            self._latest_snapshot.entity(stint.bearer_id)
            if self._latest_snapshot is not None
            else None
        )
        who = (
            self._codex_link("character", stint.bearer_id, bearer.name)
            if bearer is not None
            else "an unknown bearer"
        )
        via = (
            f", via {esc(_TRANSFER_LABELS.get(stint.mode, stint.mode))}"
            if stint.mode
            else ""
        )
        return f"{span} — {who}{via}"
