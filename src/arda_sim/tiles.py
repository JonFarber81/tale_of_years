"""The tile substrate: the grid that *is* the world (see ADR-0001).

The world is a fixed grid of terrain tiles at ~15 miles/tile. Terrain and region
labels are **config** (fixed per scenario, never serialized into run state);
per-tile **`owner_faction_id` is the only authoritative mutable state**, so
territory is per-tile and borders are *derived*, not stored. Movement is
tile-to-tile with per-terrain cost. Everything here is headless and deterministic
— no Qt, integer-only outcome comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterator, List, Optional, Tuple

# A tile with no owning faction. Faction ids are entity ids (monotonic from 1),
# so 0 is a safe "unowned" sentinel that never collides with a real faction.
UNOWNED = 0


class Terrain(str, Enum):
    PLAINS = "plains"
    FOREST = "forest"
    MOUNTAIN = "mountain"
    HILLS = "hills"
    MARSH = "marsh"
    BARREN = "barren"
    RIVER = "river"
    LAKE = "lake"
    SEA = "sea"
    ROAD = "road"

    def __str__(self) -> str:
        return self.value


# Per-terrain land-movement cost (integer "tile-effort"; higher = slower) and
# passability. Impassable terrain has cost None. Integers keep movement
# deterministic (no float in an outcome-deciding comparison).
_MOVEMENT: Dict[Terrain, Optional[int]] = {
    Terrain.ROAD: 1,
    Terrain.PLAINS: 2,
    Terrain.BARREN: 3,
    Terrain.FOREST: 3,
    Terrain.HILLS: 4,
    Terrain.MARSH: 5,
    Terrain.RIVER: 6,  # fordable, but slow
    Terrain.MOUNTAIN: None,  # impassable without a pass (passes are future work)
    Terrain.LAKE: None,
    Terrain.SEA: None,
}

# Deterministic orthogonal neighbour order: N, E, S, W. Fixed so any traversal
# (border scan, future pathfinding) is reproducible.
_NEIGHBOR_OFFSETS: Tuple[Tuple[int, int], ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))


def move_cost(terrain: Terrain) -> Optional[int]:
    """Land-movement cost for a terrain, or None if impassable."""
    return _MOVEMENT[terrain]


def is_passable(terrain: Terrain) -> bool:
    """Whether land movers can enter this terrain at all."""
    return _MOVEMENT[terrain] is not None


@dataclass(frozen=True)
class Region:
    """A named label over a set of tiles — identity/prose only, never an owner."""

    id: int
    name: str


@dataclass
class Site:
    """A named place anchored to a tile (settlement, fortress, ruin).

    ``id`` is a deterministic config-space id (assigned by sorted name in
    :func:`load_grid`), distinct from the entity id space — it is the stable
    handle a character's ``location_id`` points at, mirroring how region ids work.

    ``name``/``col``/``row``/``id`` are fixed config, but ``kind`` and ``tier``
    become *run state* once construction (build ticket 12) founds, grows, or razes
    a settlement — a razed ``city`` drops to ``ruin``, a rebuilt ruin rises to a
    ``town``, and a grown town becomes a ``city``. That mutable slice is persisted
    and restored alongside the owner grid (see :meth:`TileGrid.site_state`).
    """

    name: str
    col: int
    row: int
    kind: str
    id: int = 0
    tier: int = 0  # settlement rank (0 = ruin/none, 1 = town/fort, 2 = city)


@dataclass
class TileGrid:
    """The world grid. Terrain/region/site data is config; ``owner`` is state.

    Tiles are stored row-major in flat lists indexed by ``row * width + col`` —
    compact for ~13k tiles and cheap to serialize.
    """

    width: int
    height: int
    terrain: List[Terrain]  # config: len width*height
    region_of: List[int]  # config: region id per tile (UNOWNED-style 0 = none)
    regions: Dict[int, Region]  # config: id -> Region
    sites: List[Site] = field(default_factory=list)  # config
    miles_per_tile: int = 15
    owner: List[int] = field(default_factory=list)  # STATE: faction id per tile
    # STATE: tile indices paved into roads by construction (build ticket 12).
    # Terrain is otherwise config; these deltas are the only terrain that changes
    # at runtime, so they persist and are re-applied on top of the config grid.
    paved: List[int] = field(default_factory=list)

    def site_id_of(self, name: str) -> Optional[int]:
        """The config-space id of the site with this name, or None if absent."""
        for site in self.sites:
            if site.name == name:
                return site.id
        return None

    def site_by_id(self, site_id: int) -> Optional[Site]:
        """The site with this config-space id, or None."""
        for site in self.sites:
            if site.id == site_id:
                return site
        return None

    def site_at(self, col: int, row: int) -> Optional[Site]:
        """The site standing on a tile, or None (the first if several share it)."""
        for site in self.sites:
            if site.col == col and site.row == row:
                return site
        return None

    def set_site(self, site_id: int, kind: str, tier: int) -> None:
        """Change a site's ``kind``/``tier`` in place (construction/razing, ticket 12)."""
        site = self.site_by_id(site_id)
        if site is not None:
            site.kind = kind
            site.tier = tier

    def site_state(self) -> List[List]:
        """The mutable site slice — ``[[id, kind, tier], ...]`` in id order.

        Only ``kind``/``tier`` change at runtime; the rest is config, so this is
        all that persists (with the owner grid) to restore the built world.
        """
        return [[s.id, s.kind, s.tier] for s in sorted(self.sites, key=lambda s: s.id)]

    def load_site_state(self, state: List[List]) -> None:
        """Restore site ``kind``/``tier`` from :meth:`site_state` output (by id)."""
        for sid, kind, tier in state:
            self.set_site(sid, kind, tier)

    def __post_init__(self) -> None:
        n = self.width * self.height
        if len(self.terrain) != n or len(self.region_of) != n:
            raise ValueError("terrain/region_of length must equal width*height")
        if not self.owner:
            self.owner = [UNOWNED] * n
        elif len(self.owner) != n:
            raise ValueError("owner length must equal width*height")

    # -- indexing --------------------------------------------------------

    def index(self, col: int, row: int) -> int:
        return row * self.width + col

    def in_bounds(self, col: int, row: int) -> bool:
        return 0 <= col < self.width and 0 <= row < self.height

    # -- config lookups --------------------------------------------------

    def terrain_at(self, col: int, row: int) -> Terrain:
        return self.terrain[self.index(col, row)]

    def region_at(self, col: int, row: int) -> Optional[Region]:
        rid = self.region_of[self.index(col, row)]
        return self.regions.get(rid) if rid else None

    def passable(self, col: int, row: int) -> bool:
        return is_passable(self.terrain_at(col, row))

    def move_cost(self, col: int, row: int) -> Optional[int]:
        return move_cost(self.terrain_at(col, row))

    # -- state -----------------------------------------------------------

    def owner_at(self, col: int, row: int) -> int:
        return self.owner[self.index(col, row)]

    def set_owner(self, col: int, row: int, faction_id: int) -> None:
        self.owner[self.index(col, row)] = faction_id

    def pave(self, index: int) -> None:
        """Turn a tile into a road (construction, ticket 12), recording the delta.

        The paved index is remembered so the road survives save/load: terrain is
        config and reloads clean, then every paved tile is laid down again on top.
        """
        self.terrain[index] = Terrain.ROAD
        if index not in self.paved:
            self.paved.append(index)

    def apply_paved(self, indices: List[int]) -> None:
        """Re-lay every persisted road onto a freshly-loaded (config) grid."""
        for index in indices:
            self.pave(index)

    # -- topology --------------------------------------------------------

    def neighbors(self, col: int, row: int) -> Iterator[Tuple[int, int]]:
        """In-bounds orthogonal neighbours in fixed N, E, S, W order."""
        for dc, dr in _NEIGHBOR_OFFSETS:
            nc, nr = col + dc, row + dr
            if self.in_bounds(nc, nr):
                yield nc, nr

    def is_border(self, col: int, row: int) -> bool:
        """Whether an owned tile touches a differently-owned neighbour.

        Derived, never stored — this is what "contested"/frontier is built from.
        Unowned tiles are not borders.
        """
        owner = self.owner_at(col, row)
        if owner == UNOWNED:
            return False
        return any(self.owner_at(nc, nr) != owner for nc, nr in self.neighbors(col, row))

    def iter_tiles(self) -> Iterator[Tuple[int, int, Terrain]]:
        """Yield ``(col, row, terrain)`` in row-major order."""
        for row in range(self.height):
            for col in range(self.width):
                yield col, row, self.terrain[self.index(col, row)]

    # -- state (de)serialization -----------------------------------------

    def owner_rle(self) -> List[List[int]]:
        """Run-length-encode the owner grid as ``[[faction_id, count], ...]``.

        Ownership is contiguous, so RLE keeps per-year snapshots small. This is
        the only tile state that persists; terrain/regions are config.
        """
        runs: List[List[int]] = []
        for value in self.owner:
            if runs and runs[-1][0] == value:
                runs[-1][1] += 1
            else:
                runs.append([value, 1])
        return runs

    def load_owner_rle(self, runs: List[List[int]]) -> None:
        """Restore the owner grid from :meth:`owner_rle` output."""
        owner: List[int] = []
        for value, count in runs:
            owner.extend([value] * count)
        if len(owner) != self.width * self.height:
            raise ValueError("RLE owner length must equal width*height")
        self.owner = owner


# Settlement rank a site of each kind starts at (build ticket 12). Non-settlement
# markers (gate/pass/volcano/gateway) and ruins carry no rank.
_KIND_TIER: Dict[str, int] = {"city": 2, "town": 1, "fort": 1}


def default_tier(kind: str) -> int:
    """The settlement rank a freshly-loaded site of this ``kind`` starts at."""
    return _KIND_TIER.get(kind, 0)


def load_grid(scenario: Dict) -> TileGrid:
    """Build a :class:`TileGrid` from a scenario dict (deterministically).

    Region ids are assigned in sorted-legend-key order, so the same scenario
    always yields the same ids. The ``terrain``/``regions`` rows are char grids
    decoded via their legends.
    """
    width, height = scenario["width"], scenario["height"]
    terrain_legend = {ch: Terrain(name) for ch, name in scenario["terrain_legend"].items()}

    terrain_rows = scenario["terrain"]
    _check_grid(terrain_rows, width, height, "terrain")
    terrain = [terrain_legend[ch] for row in terrain_rows for ch in row]

    # deterministic region ids: sorted legend chars -> 1, 2, 3, ...
    region_legend = scenario.get("region_legend", {})
    char_to_id = {ch: i for i, ch in enumerate(sorted(region_legend), start=1)}
    regions = {char_to_id[ch]: Region(char_to_id[ch], name) for ch, name in region_legend.items()}

    region_rows = scenario.get("regions") or ["." * width for _ in range(height)]
    _check_grid(region_rows, width, height, "regions")
    region_of = [char_to_id.get(ch, UNOWNED) for row in region_rows for ch in row]

    # Deterministic site ids: sorted site names -> 1, 2, 3, ... (config-space,
    # like region ids), so a character's location_id is stable across processes.
    site_ids = {name: i for i, name in enumerate(sorted(s["name"] for s in scenario.get("sites", [])), start=1)}
    sites = [
        Site(s["name"], s["col"], s["row"], s["kind"], site_ids[s["name"]], default_tier(s["kind"]))
        for s in scenario.get("sites", [])
    ]

    return TileGrid(
        width=width,
        height=height,
        terrain=terrain,
        region_of=region_of,
        regions=regions,
        sites=sites,
        miles_per_tile=scenario.get("miles_per_tile", 15),
    )


def _check_grid(rows: List[str], width: int, height: int, what: str) -> None:
    if len(rows) != height or any(len(r) != width for r in rows):
        raise ValueError(f"{what} grid must be {height} rows of {width} chars")
