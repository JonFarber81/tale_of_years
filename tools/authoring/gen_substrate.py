"""Author the full TA-2965 substrate (build ticket 04).

Hand-authoring ~12,500 tiles as literal ASCII is neither reviewable nor
maintainable, so the *geography* is encoded here as coordinate primitives —
coastlines, mountain ranges, rivers, forests, roads — traced by eye over
``references/Middle Earth v7.jpg``. Running this module bakes those primitives
into the char-grid scenario the engine actually loads:

    python tools/authoring/gen_substrate.py            # writes the scenario JSON
    python tools/authoring/gen_substrate.py --preview  # + ASCII sanity dump

The committed artifact is ``src/arda_sim/scenarios/arda_ta2965.json``; this file
is the record of *how* it was authored and the seam for re-authoring. Output is
fully deterministic (no RNG) so re-running never churns the JSON.

Coordinate convention: tile ``(col, row)``; col runs west->east over WIDTH,
row runs north->south over HEIGHT, at 15 miles/tile (ADR-0001).
"""

from __future__ import annotations

import json
import string
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

WIDTH = 100
HEIGHT = 125
MILES_PER_TILE = 15

Pt = Tuple[int, int]

# Terrain char legend (matches the renderer's sprite/colour map in ui/assets.py).
LAND = "."          # plains — the default fill
SEA = "~"
LAKE = "l"
RIVER = "r"
ROAD = "="
MOUNTAIN = "^"
HILLS = "h"
FOREST = "f"
MARSH = "m"
BARREN = "b"

TERRAIN_LEGEND = {
    LAND: "plains",
    ROAD: "road",
    MOUNTAIN: "mountain",
    BARREN: "barren",
    FOREST: "forest",
    HILLS: "hills",
    LAKE: "lake",
    MARSH: "marsh",
    RIVER: "river",
    SEA: "sea",
}


# --------------------------------------------------------------------------
# Grid + brush primitives
# --------------------------------------------------------------------------

def _blank() -> List[List[str]]:
    return [[LAND for _ in range(WIDTH)] for _ in range(HEIGHT)]


def _in_bounds(col: int, row: int) -> bool:
    return 0 <= col < WIDTH and 0 <= row < HEIGHT


def _stamp(grid: List[List[str]], col: int, row: int, ch: str) -> None:
    if _in_bounds(col, row):
        grid[row][col] = ch


def _disk(grid: List[List[str]], col: int, row: int, radius: int, ch: str) -> None:
    """Paint a filled disk of the given tile radius (radius 0 = single tile)."""
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            if dc * dc + dr * dr <= radius * radius:
                _stamp(grid, col + dc, row + dr, ch)


def _polyline(grid: List[List[str]], pts: Sequence[Pt], ch: str, radius: int = 0) -> None:
    """Stamp a brush of ``radius`` along the segments joining ``pts``."""
    for (c0, r0), (c1, r1) in zip(pts, pts[1:]):
        steps = max(abs(c1 - c0), abs(r1 - r0)) or 1
        for i in range(steps + 1):
            c = round(c0 + (c1 - c0) * i / steps)
            r = round(r0 + (r1 - r0) * i / steps)
            _disk(grid, c, r, radius, ch)


def _blob(grid: List[List[str]], centers: Sequence[Tuple[int, int, int]], ch: str) -> None:
    """Paint overlapping disks (col, row, radius) — for forests and seas."""
    for col, row, radius in centers:
        _disk(grid, col, row, radius, ch)


def _fill_sea(grid: List[List[str]]) -> None:
    """Flood the map margins with sea from the west and south coastlines."""
    west = sorted(WEST_COAST, key=lambda p: p[1])          # keyed by row
    south = sorted(SOUTH_COAST, key=lambda p: p[0])        # keyed by col
    for row in range(HEIGHT):
        west_edge = _interp(west, row, by_x=False)
        for col in range(WIDTH):
            if col < west_edge:
                grid[row][col] = SEA
            elif col < SOUTH_SEA_MAX_COL and row > _interp(south, col, by_x=True):
                grid[row][col] = SEA


def _interp(ctrl: Sequence[Pt], key: int, by_x: bool) -> int:
    """Linear-interpolate the other coordinate for ``key`` along control points.

    ``by_x`` selects which coordinate is the independent axis: the points are
    ``(col, row)``, so ``by_x`` interpolates row-as-a-function-of-col (south
    coast) and ``not by_x`` interpolates col-as-a-function-of-row (west coast).
    """
    a, b = (0, 1) if by_x else (1, 0)  # (independent, dependent) index
    if key <= ctrl[0][a]:
        return ctrl[0][b]
    if key >= ctrl[-1][a]:
        return ctrl[-1][b]
    for p0, p1 in zip(ctrl, ctrl[1:]):
        if p0[a] <= key <= p1[a]:
            span = p1[a] - p0[a]
            t = (key - p0[a]) / span if span else 0
            return round(p0[b] + (p1[b] - p0[b]) * t)
    return ctrl[-1][b]


# --------------------------------------------------------------------------
# Geography, traced over the v7 map (west->east, north->south)
# --------------------------------------------------------------------------

# Belegaer's western coastline: a column threshold per row (sea lies west of it).
# The Lindon peninsula and the Gulf of Lune notch are the wiggles up north.
WEST_COAST: List[Pt] = [
    (10, 0), (6, 10), (13, 14), (5, 20), (17, 26), (9, 32),
    (8, 42), (10, 52), (13, 62), (16, 70), (19, 78), (22, 86),
    (24, 96), (25, 110), (24, 124),
]

# Southern coastline (Bay of Belfalas): a row threshold per column, applied only
# for the western/central columns — the eastern edge (Harad, Mordor, Núrnen) is
# land all the way to the bottom. Sea lies south of the threshold.
SOUTH_SEA_MAX_COL = 60
SOUTH_COAST: List[Pt] = [
    (18, 122), (26, 110), (34, 100), (40, 90), (46, 95),
    (52, 100), (58, 112), (SOUTH_SEA_MAX_COL, 124),
]

# Enclosed / inland waters as overlapping disks (col, row, radius).
SEAS: List[Tuple[int, int, int]] = [
    # Bay of Forochel (far NW).
    (22, 8, 3),
    # Sea of Rhûn (far east).
    (90, 42, 4), (92, 46, 3),
    # Sea of Núrnen (inside Mordor, SE).
    (77, 68, 3),
]

LAKES: List[Tuple[int, int, int]] = [
    (63, 22, 2),   # Long Lake (Esgaroth)
    (25, 20, 1),   # Lake Evendim (Nenuial)
]

# Mountain ranges as brushed polylines (radius sets range width).
MOUNTAINS: List[Tuple[List[Pt], int]] = [
    ([(14, 13), (16, 20), (17, 27), (18, 34)], 1),               # Ered Luin (Blue Mtns)
    ([(47, 17), (46, 25), (44, 33), (45, 41), (44, 50), (43, 54)], 1),  # Hithaeglir (Misty Mtns)
    ([(30, 57), (38, 58), (46, 58), (54, 57), (61, 55)], 1),     # Ered Nimrais (White Mtns)
    ([(61, 55), (64, 59), (67, 63), (71, 67), (74, 71), (76, 74)], 1),  # Ephel Dúath
    ([(63, 55), (69, 54), (75, 55), (80, 57), (82, 61)], 1),     # Ered Lithui (Ash Mtns)
    ([(51, 15), (58, 14), (65, 15), (71, 16)], 1),               # Ered Mithrin (Grey Mtns)
    ([(71, 16), (75, 18), (78, 20)], 1),                         # Iron Mountains
    ([(41, 13), (46, 12), (51, 13)], 1),                         # Mountains of Angmar
    ([(67, 19), (69, 21)], 1),                                   # Erebor (Lonely Mountain)
]

# Forests as overlapping disks.
FORESTS: List[Tuple[int, int, int]] = [
    (61, 25, 3), (62, 30, 4), (63, 36, 4), (60, 41, 3),   # Mirkwood
    (49, 43, 2),   # Lórien (Lothlórien)
    (46, 48, 2),   # Fangorn
    (20, 42, 1),   # Old Forest
    (16, 45, 1),   # Eryn Vorn
    (42, 55, 1),   # Druadan / Firien Wood
    (42, 34, 1),   # Trollshaws
]

MARSHES: List[Tuple[int, int, int]] = [
    (57, 54, 2),   # Dead Marshes / Nindalf (Wetwang)
    (33, 40, 1),   # Midgewater Marshes (near Bree)
]

BARRENS: List[Tuple[int, int, int]] = [
    (70, 60, 3), (74, 61, 2),   # Plateau of Gorgoroth (inner Mordor)
    (64, 56, 1),                # Udûn / Dagorlad approach
    (55, 50, 1),                # Brown Lands (east bank of Anduin)
]

# Rivers as single-tile polylines (drawn last so they cut through land).
RIVERS: List[List[Pt]] = [
    # Anduin, the Great River — the spine of the theatre.
    [(50, 18), (51, 26), (50, 34), (52, 42), (53, 48), (54, 53),
     (53, 59), (52, 65), (51, 71), (49, 77), (47, 82)],
    # Gwathló (Greyflood) + Glanduin/Hoarwell tributaries.
    [(44, 41), (38, 43), (30, 44), (20, 45), (10, 45)],
    [(44, 33), (38, 40), (31, 44)],
    # Isen, the Iron River.
    [(41, 52), (32, 55), (22, 58), (14, 58)],
    # Lhûn (Lune) into the Gulf of Lune.
    [(16, 18), (18, 23), (20, 26)],
    # Baranduin (Brandywine) through the Shire.
    [(23, 30), (25, 36), (27, 42), (30, 45)],
    # Celduin (Running) + Carnen (Redwater) to the Sea of Rhûn.
    [(66, 21), (68, 27), (73, 33), (80, 39), (85, 42)],
    # Entwash, from the White Mountains to the Anduin.
    [(44, 51), (48, 55), (53, 58)],
    # Poros, marking Gondor's border with the south.
    [(60, 66), (56, 70), (50, 74)],
    # Morthond / Gilrain, Gondor's coastal rivers.
    [(40, 60), (39, 68), (39, 76)],
]

# Roads as single-tile polylines (drawn over land, under sites).
ROADS: List[List[Pt]] = [
    # Great East Road: Grey Havens -> Bree -> Rivendell -> Old Forest Road.
    [(20, 27), (26, 34), (32, 40), (40, 39), (47, 38), (51, 36),
     (56, 33), (62, 31), (68, 30)],
    # Greenway (North-South Road): Fornost -> Bree -> Tharbad -> Isengard.
    [(34, 30), (33, 36), (32, 40), (31, 44), (40, 52)],
    # The road on into Rohan and Gondor: Isengard -> Edoras -> Minas Tirith.
    [(40, 52), (42, 58), (48, 60), (52, 62), (55, 61)],
    # Harad Road: out of Ithilien to the southern edge (east of the Belfalas bay).
    [(58, 66), (60, 82), (61, 98), (62, 112), (62, 124)],
]

# Key sites (col, row, kind, name), placed at their v7 positions.
SITES: List[Tuple[int, int, str, str]] = [
    # -- Gondor --
    (52, 62, "city", "Minas Tirith"),
    (55, 61, "ruin", "Osgiliath"),
    (60, 62, "fort", "Minas Morgul"),
    (54, 58, "fort", "Cair Andros"),
    (58, 60, "fort", "Henneth Annûn"),
    (52, 72, "town", "Pelargir"),
    (44, 75, "town", "Linhir"),
    (40, 78, "city", "Dol Amroth"),
    # -- Rohan / Isengard --
    (42, 58, "city", "Edoras"),
    (38, 57, "fort", "Helm's Deep"),
    (41, 59, "town", "Dunharrow"),
    (40, 52, "fort", "Isengard"),
    # -- Eriador / Arnor --
    (32, 40, "town", "Bree"),
    (34, 30, "ruin", "Fornost"),
    (30, 28, "ruin", "Annúminas"),
    (24, 38, "town", "Michel Delving"),
    (18, 27, "city", "Grey Havens"),
    (38, 37, "ruin", "Weathertop"),
    (30, 46, "ruin", "Tharbad"),
    (47, 38, "city", "Rivendell"),
    (44, 12, "ruin", "Carn Dûm"),
    # -- Rhovanion / Wilderland --
    (49, 43, "city", "Caras Galadhon"),
    (46, 40, "ruin", "Moria"),
    (60, 38, "fort", "Dol Guldur"),
    (64, 22, "city", "Thranduil's Halls"),
    (63, 24, "town", "Esgaroth"),
    (66, 20, "town", "Dale"),
    (68, 20, "fort", "Erebor"),
    # -- Mordor --
    (74, 60, "fort", "Barad-dûr"),
    (70, 61, "volcano", "Mount Doom"),
    (63, 55, "gate", "The Morannon"),
    (62, 60, "fort", "Cirith Ungol"),
]

# Off-map provider gateways at edge tiles (ADR-0001 §World extent).
GATEWAYS: List[Tuple[int, int, str, str]] = [
    (62, 124, "gateway", "Harad Road (Poros)"),
    (99, 48, "gateway", "East Rhovanion"),
    (84, 124, "gateway", "SE Nurn"),
    (30, 124, "gateway", "Umbar Sea"),
]

# Region label seeds (col, row, name). Every land tile within RADIUS of the
# nearest seed takes that region's label; the rest is unlabelled backdrop
# (far north Forodwaith, deep Harad) per ADR-0001.
REGION_SEEDS: List[Tuple[int, int, str]] = [
    # Eriador / Arnor
    (16, 16, "Forlindon"), (18, 32, "Harlindon"), (21, 24, "Lindon"),
    (25, 38, "The Shire"), (33, 28, "Arthedain"), (31, 44, "Cardolan"),
    (42, 32, "Rhudaur"), (22, 48, "Minhiriath"), (28, 56, "Enedwaith"),
    (45, 42, "Eregion"), (44, 13, "Angmar"),
    # Rhovanion / Wilderland
    (56, 45, "Wilderland"), (62, 30, "Mirkwood"), (49, 43, "Lórien"),
    (46, 48, "Fangorn"), (52, 36, "Vales of Anduin"), (55, 50, "Brown Lands"),
    (66, 20, "Dale"), (69, 19, "Erebor"), (64, 24, "Woodland Realm"),
    (87, 47, "Rhûn"), (67, 42, "East Bight"), (50, 52, "The Wold"),
    # Dunland / Rohan
    (37, 48, "Dunland"), (44, 60, "Rohan"), (39, 57, "Westemnet"),
    (50, 59, "Eastemnet"),
    # Gondor
    (48, 62, "Anórien"), (58, 63, "Ithilien"), (48, 71, "Lebennin"),
    (42, 78, "Belfalas"), (33, 73, "Anfalas"), (41, 66, "Lamedon"),
    (52, 64, "Gondor"), (52, 90, "Harondor"),
    # Mordor
    (69, 59, "Gorgoroth"), (73, 64, "Mordor"), (76, 71, "Nurn"), (64, 57, "Udûn"),
    # Harad backdrop edge
    (58, 112, "Near Harad"),
    # Finer marches, downs, moors, and ranges
    (30, 20, "North Downs"), (28, 24, "Evendim"), (44, 20, "Ettenmoors"),
    (43, 35, "Trollshaws"), (46, 30, "Misty Mountains"), (30, 60, "Druwaith Iaur"),
    (34, 68, "Pinnath Gelin"), (26, 74, "Andrast"), (46, 57, "White Mountains"),
    (56, 52, "Emyn Muil"), (60, 53, "Dagorlad"), (56, 60, "Emyn Arnen"),
    (42, 55, "Druadan Forest"), (72, 17, "Grey Mountains"), (78, 22, "Withered Heath"),
    (81, 27, "Iron Hills"),
]

REGION_RADIUS = 22   # tiles beyond this from any seed stay unlabelled backdrop
WATER = {SEA, LAKE, RIVER}


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def build_terrain() -> List[List[str]]:
    g = _blank()
    _fill_sea(g)
    _blob(g, SEAS, SEA)
    for pts, radius in MOUNTAINS:
        _polyline(g, pts, MOUNTAIN, radius)
    _hill_skirts(g)  # ring each massif in hills for a legible, passable skirt
    _blob(g, FORESTS, FOREST)
    _blob(g, MARSHES, MARSH)
    _blob(g, BARRENS, BARREN)
    _blob(g, LAKES, LAKE)
    for river in RIVERS:
        _polyline(g, river, RIVER)
    for road in ROADS:
        _polyline(g, road, ROAD)
    return g


def _hill_skirts(g: List[List[str]]) -> None:
    """Wrap each mountain massif in a one-tile ring of hills (over plains only)."""
    hills: List[Pt] = []
    for row in range(HEIGHT):
        for col in range(WIDTH):
            if g[row][col] != MOUNTAIN:
                continue
            for dc in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    nc, nr = col + dc, row + dr
                    if _in_bounds(nc, nr) and g[nr][nc] == LAND:
                        hills.append((nc, nr))
    for c, r in hills:
        g[r][c] = HILLS


def build_regions(terrain: List[List[str]]) -> Tuple[List[List[str]], Dict[str, str]]:
    """Voronoi-assign each land tile to its nearest region seed (within radius)."""
    names = [name for _, _, name in REGION_SEEDS]
    pool = string.ascii_uppercase + string.ascii_lowercase + string.digits
    if len(names) > len(pool):
        raise ValueError("too many regions for the single-char legend")
    # Deterministic char per region, keyed by sorted name.
    char_of = {name: pool[i] for i, name in enumerate(sorted(names))}
    legend = {char_of[name]: name for name in names}

    grid = [["." for _ in range(WIDTH)] for _ in range(HEIGHT)]
    for row in range(HEIGHT):
        for col in range(WIDTH):
            if terrain[row][col] in WATER:
                continue
            best_d = REGION_RADIUS * REGION_RADIUS + 1
            best_name = None
            for sc, sr, name in REGION_SEEDS:
                d = (sc - col) ** 2 + (sr - row) ** 2
                if d < best_d:
                    best_d = d
                    best_name = name
            if best_name is not None:
                grid[row][col] = char_of[best_name]
    return grid, legend


def build_scenario() -> Dict:
    terrain = build_terrain()
    regions, region_legend = build_regions(terrain)
    sites = [
        {"col": c, "row": r, "kind": kind, "name": name}
        for c, r, kind, name in (*SITES, *GATEWAYS)
    ]
    return {
        "name": "arda_ta2965",
        "description": (
            "The full TA-2965 War-of-the-Ring theatre traced over the v7 map "
            "(build ticket 04): terrain tile grid, region labels, sites, and "
            "off-map provider gateways."
        ),
        "width": WIDTH,
        "height": HEIGHT,
        "miles_per_tile": MILES_PER_TILE,
        "terrain_legend": TERRAIN_LEGEND,
        "terrain": ["".join(row) for row in terrain],
        "region_legend": region_legend,
        "regions": ["".join(row) for row in regions],
        "sites": sites,
    }


def _preview(scenario: Dict) -> str:
    return "\n".join(scenario["terrain"])


OUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src" / "arda_sim" / "scenarios" / "arda_ta2965.json"
)


def main(argv: List[str]) -> int:
    scenario = build_scenario()
    if "--preview" in argv:
        sys.stdout.write(_preview(scenario) + "\n")
        n_regions = len(scenario["region_legend"])
        n_sites = len(scenario["sites"])
        sys.stderr.write(f"\n{n_regions} regions, {n_sites} sites\n")
    OUT_PATH.write_text(json.dumps(scenario, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stderr.write(f"wrote {OUT_PATH}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
