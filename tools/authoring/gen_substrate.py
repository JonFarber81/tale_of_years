"""Author the full TA-2965 substrate (build ticket 04; re-authored to match the
canonical "West of Middle-earth at the End of the Third Age" map).

Hand-authoring ~13,000 tiles as literal ASCII is neither reviewable nor
maintainable, so the *geography* is encoded here as **fractional coordinates**
(0..1 across the frame) traced by eye over the reference map, then baked into the
char-grid scenario the engine loads. Fractions (not raw tiles) keep the authoring
legible and let the grid resolution change without re-tracing.

    python tools/authoring/gen_substrate.py            # writes the scenario JSON
    python tools/authoring/gen_substrate.py --preview  # + ASCII sanity dump

The committed artifact is ``src/arda_sim/scenarios/arda_ta2965.json``; this file
is the record of *how* it was authored. Output is deterministic (no RNG) so
re-running never churns the JSON. A coloured PNG preview lives in
``tools/authoring/preview_png.py``.

Coordinate convention: the frame is landscape to match the reference (west->east
wider than north->south). ``P(x, y)`` maps a fraction to tile ``(col, row)``;
col runs west->east, row runs north->south.
"""

from __future__ import annotations

import json
import string
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

# Landscape frame, matching the reference map's ~1.32:1 aspect. ~13k tiles.
WIDTH = 132
HEIGHT = 100
MILES_PER_TILE = 15

Pt = Tuple[int, int]
FPt = Tuple[float, float]

# Terrain char legend (matches the renderer's colour map in ui/tile_render.py).
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


def P(x: float, y: float) -> Pt:
    """Map a fractional frame coordinate (0..1) to a tile ``(col, row)``."""
    return (round(x * (WIDTH - 1)), round(y * (HEIGHT - 1)))


def R(frac: float) -> int:
    """Map a fractional radius/length to a whole number of tiles."""
    return max(0, round(frac * WIDTH))


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


def _fpolyline(grid: List[List[str]], fpts: Sequence[FPt], ch: str, radius: int = 0) -> None:
    _polyline(grid, [P(x, y) for x, y in fpts], ch, radius)


def _fblobs(grid: List[List[str]], blobs: Sequence[Tuple[float, float, float]], ch: str) -> None:
    """Paint overlapping disks given as fractional ``(x, y, radius)``."""
    for x, y, rad in blobs:
        c, r = P(x, y)
        _disk(grid, c, r, R(rad), ch)


def _fblobs_where(
    grid: List[List[str]],
    blobs: Sequence[Tuple[float, float, float]],
    ch: str,
    only: str,
) -> None:
    """Like ``_fblobs`` but only repaints tiles currently holding ``only``."""
    for x, y, rad in blobs:
        c, r = P(x, y)
        radius = R(rad)
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if dc * dc + dr * dr <= radius * radius:
                    nc, nr = c + dc, r + dr
                    if _in_bounds(nc, nr) and grid[nr][nc] == only:
                        grid[nr][nc] = ch


# --------------------------------------------------------------------------
# The coastline, as a closed land polygon (sea = everything outside it)
# --------------------------------------------------------------------------
# Traced clockwise from the north edge down the west coast (Belegaer), around the
# Bay of Belfalas, to the south edge, then the frame's south/east/north edges
# (pushed just outside 0..1 so the whole eastern and northern landmass counts as
# interior). Ray-casting fills every tile outside this outline with sea, which
# captures the Gulf of Lune notch and the concave Bay of Belfalas that a simple
# per-row threshold could not.
LAND_OUTLINE: List[FPt] = [
    (0.135, -0.05),   # west coast meets the north edge
    # -- west coast (Belegaer), north -> south --
    (0.115, 0.02),
    (0.075, 0.05),    # Forlindon (north)
    (0.052, 0.11),
    (0.055, 0.17),    # Forlindon (west shoulder)
    (0.078, 0.215),
    (0.105, 0.235),   # Gulf of Lune — north shore, mouth
    (0.150, 0.252),
    (0.190, 0.272),   # Grey Havens (head of the gulf)
    (0.150, 0.298),   # Gulf of Lune — south shore, back out
    (0.098, 0.312),
    (0.088, 0.35),    # Harlindon coast
    (0.095, 0.395),
    (0.122, 0.44),    # Minhiriath coast
    (0.155, 0.478),   # Lond Daer (mouth of Gwathló)
    (0.198, 0.525),
    (0.243, 0.578),   # Enedwaith coast
    (0.285, 0.635),
    (0.312, 0.685),
    (0.318, 0.723),   # Andrast — the SW cape's tip
    # -- Bay of Belfalas, west shore -> north shore -> east shore --
    (0.352, 0.712),   # Anfalas (Langstrand)
    (0.393, 0.706),
    (0.432, 0.706),   # Dol Amroth (cape)
    (0.468, 0.712),   # Belfalas
    (0.505, 0.728),   # Ethir Anduin (the Mouths of Anduin)
    (0.516, 0.80),    # east shore of the bay, running south
    (0.506, 1.05),    # bottom edge, just east of the delta
    # -- frame edges: south, east, north (land to the border) --
    (1.05, 1.05),     # SE corner (Khand)
    (1.05, -0.05),    # NE corner (Rhûn)
]


def _point_in_poly(col: int, row: int, poly: Sequence[Pt]) -> bool:
    """Ray-cast test: is tile-centre ``(col, row)`` inside the polygon?"""
    x, y = col + 0.5, row + 0.5
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            x_cross = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < x_cross:
                inside = not inside
    return inside


def _fill_sea(grid: List[List[str]]) -> None:
    poly = [P(x, y) for x, y in LAND_OUTLINE]
    for row in range(HEIGHT):
        for col in range(WIDTH):
            if not _point_in_poly(col, row, poly):
                grid[row][col] = SEA


# --------------------------------------------------------------------------
# Geography, traced over the reference (west->east, north->south)
# --------------------------------------------------------------------------

# Enclosed / inland waters as fractional (x, y, radius) disks.
SEAS: List[Tuple[float, float, float]] = [
    (0.150, 0.055, 0.032),   # Ice Bay of Forochel (far NW)
    (0.128, 0.038, 0.026),   # ... opening the bay to Belegaer, as on the map
    (0.830, 0.400, 0.058),   # Sea of Rhûn (far east)
    (0.865, 0.445, 0.040),
    (0.725, 0.715, 0.036),   # Sea of Núrnen (inside Mordor, SE)
]

# Islands stamped back over the sea after the coast fill.
ISLANDS: List[Tuple[float, float, float]] = [
    (0.495, 0.795, 0.011),   # Tolfalas, at the mouth of the Bay of Belfalas
]

LAKES: List[Tuple[float, float, float]] = [
    (0.655, 0.205, 0.020),   # Long Lake (Esgaroth / Lake-town)
    (0.235, 0.185, 0.017),   # Lake Evendim (Nenuial)
    (0.563, 0.520, 0.013),   # Nen Hithoel, above Rauros in the Emyn Muil
]

# Mountain ranges as brushed fractional polylines (radius sets range width).
MOUNTAINS: List[Tuple[List[FPt], int]] = [
    # Ered Luin (Blue Mtns) — two arms, cut by the Gulf of Lune as on the map.
    ([(0.128, 0.095), (0.140, 0.165), (0.148, 0.225)], 1),               # north arm
    ([(0.150, 0.305), (0.163, 0.355), (0.172, 0.400)], 1),               # south arm (Harlindon)
    ([(0.500, 0.11), (0.490, 0.18), (0.476, 0.26), (0.470, 0.33),
      (0.464, 0.40), (0.459, 0.47), (0.455, 0.535)], 1),                  # Hithaeglir (Misty Mtns)
    # Ered Mithrin (Grey Mtns) — forking east around the Withered Heath.
    ([(0.500, 0.11), (0.550, 0.10), (0.600, 0.105), (0.640, 0.112)], 1),
    ([(0.640, 0.112), (0.690, 0.100), (0.742, 0.102)], 1),               # north prong
    ([(0.640, 0.112), (0.688, 0.132), (0.735, 0.150)], 1),               # south prong
    ([(0.790, 0.148), (0.830, 0.152), (0.868, 0.158)], 1),               # Iron Hills (east-west)
    ([(0.400, 0.075), (0.448, 0.062), (0.492, 0.078)], 1),               # Mountains of Angmar
    ([(0.440, 0.055), (0.452, 0.072)], 0),                               # Carn Dûm massif
    ([(0.440, 0.55), (0.475, 0.565), (0.512, 0.576), (0.550, 0.585),
      (0.585, 0.590), (0.608, 0.596)], 1),                               # Ered Nimrais (White Mtns)
    ([(0.618, 0.565), (0.632, 0.60), (0.648, 0.635), (0.663, 0.667),
      (0.675, 0.695), (0.680, 0.715)], 1),                               # Ephel Dúath (Mtns of Shadow)
    ([(0.636, 0.565), (0.676, 0.560), (0.720, 0.566), (0.762, 0.578),
      (0.802, 0.592), (0.845, 0.606), (0.882, 0.622)], 1),              # Ered Lithui (Ash Mtns)
    ([(0.680, 0.715), (0.725, 0.740), (0.775, 0.742), (0.822, 0.720),
      (0.858, 0.680), (0.878, 0.640)], 1),                              # Mordor's southern rim (encloses Nurn)
    ([(0.655, 0.158), (0.664, 0.168)], 0),                               # Erebor (the Lonely Mountain)
]

# Named hill country as fractional disks (stamped over plains only, so they
# never eat a mountain range, coast, or forest).
HILLS_BLOBS: List[Tuple[float, float, float]] = [
    (0.212, 0.162, 0.012),   # Emyn Uial (Hills of Evendim), NW of the lake
    (0.305, 0.172, 0.014),   # North Downs (Fornost at their southern edge)
    (0.325, 0.330, 0.013),   # South Downs
    (0.362, 0.232, 0.011),   # Weather Hills (Weathertop at the south end)
    (0.215, 0.272, 0.008),   # Tower Hills (Emyn Beraid), east of the Lune
    (0.435, 0.135, 0.014),   # Ettenmoors
    (0.552, 0.512, 0.015), (0.578, 0.518, 0.015),   # Emyn Muil, ringing Nen Hithoel
    (0.435, 0.648, 0.012),   # Pinnath Gelin (the Green Hills)
    (0.618, 0.632, 0.008),   # Emyn Arnen, in Ithilien
]

# Forests as overlapping fractional disks.
FORESTS: List[Tuple[float, float, float]] = [
    # Mirkwood — the great forest of Rhovanion, a broad block east of Anduin
    # with the East Bight biting into its eastern edge (left unforested).
    (0.605, 0.150, 0.050), (0.650, 0.165, 0.048), (0.618, 0.205, 0.055),   # N Mirkwood
    (0.660, 0.210, 0.050), (0.620, 0.260, 0.058), (0.665, 0.262, 0.050),   # mid-north
    (0.610, 0.315, 0.055), (0.655, 0.320, 0.048), (0.616, 0.375, 0.052),   # mid-south
    (0.650, 0.375, 0.044), (0.622, 0.430, 0.045),                          # S Mirkwood (Dol Guldur)
    (0.535, 0.425, 0.030),   # Lothlórien
    (0.498, 0.505, 0.030), (0.484, 0.525, 0.024),   # Fangorn
    (0.310, 0.312, 0.017),   # Old Forest
    (0.140, 0.440, 0.016),   # Eryn Vorn
    (0.420, 0.245, 0.020),   # Trollshaws
    (0.333, 0.282, 0.011),   # Chetwood (by Bree)
    (0.552, 0.585, 0.015),   # Druadan / Firien Wood
]

# Clearings carved back out of forest (stamped after forests, forest-only).
CLEARINGS: List[Tuple[float, float, float]] = [
    (0.690, 0.298, 0.032),   # the East Bight, bitten out of Mirkwood's east edge
]

MARSHES: List[Tuple[float, float, float]] = [
    (0.585, 0.545, 0.026),   # Dead Marshes / Nindalf (Wetwang)
    (0.330, 0.420, 0.020),   # Nîn-in-Eilph (Swanfleet), by Tharbad
    (0.352, 0.292, 0.010),   # Midgewater Marshes (near Bree)
]

BARRENS: List[Tuple[float, float, float]] = [
    (0.688, 0.615, 0.036), (0.712, 0.622, 0.030),   # Plateau of Gorgoroth (inner Mordor)
    (0.628, 0.552, 0.020),                          # Dagorlad (Battle Plain)
    (0.588, 0.462, 0.022), (0.600, 0.485, 0.018),   # Brown Lands, north of the Emyn Muil
    (0.820, 0.630, 0.030),                          # Lithlad (ash plain, east of Mordor)
    (0.580, 0.845, 0.048), (0.622, 0.905, 0.050),   # South Gondor / Near Harad — desert
    (0.548, 0.920, 0.040),
]

# Rivers as single-tile fractional polylines (drawn late so they cut through land).
RIVERS: List[List[FPt]] = [
    # Anduin, the Great River — the spine of the theatre. Through Nen Hithoel
    # and over Rauros, past Cair Andros and Osgiliath, then swinging south-west
    # past Pelargir to the Ethir.
    [(0.500, 0.120), (0.512, 0.200), (0.525, 0.280), (0.536, 0.340),
     (0.545, 0.400), (0.552, 0.460), (0.557, 0.505), (0.563, 0.520),
     (0.570, 0.545), (0.582, 0.562), (0.594, 0.578), (0.602, 0.596),
     (0.602, 0.625), (0.588, 0.652), (0.550, 0.680), (0.520, 0.703),
     (0.505, 0.728)],
    # Gwathló (Greyflood), fed by Glanduin, out at Lond Daer.
    [(0.440, 0.400), (0.385, 0.420), (0.330, 0.432), (0.262, 0.452),
     (0.195, 0.470), (0.155, 0.478)],
    # Mitheithel (Hoarwell), from the Ettenmoors south to the Gwathló.
    [(0.440, 0.160), (0.440, 0.245), (0.436, 0.325), (0.440, 0.400)],
    # Bruinen (Loudwater), from Rivendell to the Gwathló.
    [(0.470, 0.242), (0.462, 0.305), (0.450, 0.362), (0.440, 0.400)],
    # Isen (Angren), from the Gap of Rohan to the sea.
    [(0.455, 0.532), (0.418, 0.552), (0.368, 0.577), (0.308, 0.602),
     (0.258, 0.616)],
    # Adorn, a tributary of Isen.
    [(0.440, 0.582), (0.400, 0.586), (0.368, 0.577)],
    # Lhûn (Lune), into the Gulf of Lune.
    [(0.155, 0.150), (0.170, 0.205), (0.188, 0.262)],
    # Baranduin (Brandywine), through the Shire to the southern sea.
    [(0.245, 0.220), (0.262, 0.300), (0.278, 0.380), (0.298, 0.445),
     (0.298, 0.510), (0.268, 0.560)],
    # Celduin (Running) to the Sea of Rhûn, fed by Carnen.
    [(0.655, 0.205), (0.685, 0.270), (0.722, 0.340), (0.760, 0.398),
     (0.792, 0.420)],
    # Carnen (Redwater), from the Iron Hills to the Celduin.
    [(0.836, 0.162), (0.812, 0.262), (0.782, 0.340), (0.752, 0.386)],
    # Celebrant (Silverlode), from the Misty Mtns through Lórien to Anduin.
    [(0.470, 0.400), (0.508, 0.420), (0.540, 0.432), (0.556, 0.462)],
    # Entwash, from the White Mountains to its mouths at Anduin below Rauros.
    [(0.500, 0.585), (0.525, 0.555), (0.556, 0.545), (0.570, 0.548)],
    # Limlight, from Fangorn's eaves to the Anduin.
    [(0.490, 0.500), (0.522, 0.490), (0.552, 0.485)],
    # Morthond (Blackroot), from the Dwimorberg vale down to Edhellond.
    [(0.470, 0.618), (0.462, 0.668), (0.466, 0.706)],
    # Gilrain, through Lamedon and Linhir to the bay.
    [(0.508, 0.618), (0.500, 0.666), (0.492, 0.710)],
    # Erui, out of Lossarnach across Lebennin to Anduin above Pelargir.
    [(0.532, 0.612), (0.540, 0.648), (0.549, 0.676)],
    # Lefnui, from the western White Mountains along Anfalas to the sea.
    [(0.428, 0.590), (0.402, 0.648), (0.375, 0.700)],
    # Poros, Gondor's border with the South, joining Anduin above the delta.
    [(0.630, 0.680), (0.588, 0.696), (0.528, 0.703)],
    # Harnen, the frontier of Near Harad, west to the sea.
    [(0.660, 0.850), (0.618, 0.872), (0.578, 0.886), (0.516, 0.900)],
    # Forest River, from the Grey Mountains through north Mirkwood to Long Lake.
    [(0.605, 0.135), (0.632, 0.168), (0.648, 0.190), (0.655, 0.205)],
]

# Roads as single-tile fractional polylines (over land, under sites).
ROADS: List[List[FPt]] = [
    # Great East Road: Grey Havens -> Bree -> Rivendell -> High Pass -> Old
    # Forest Road across Mirkwood.
    [(0.190, 0.272), (0.245, 0.298), (0.310, 0.300), (0.380, 0.290),
     (0.440, 0.262), (0.470, 0.242), (0.482, 0.238), (0.505, 0.232),
     (0.552, 0.238), (0.605, 0.245), (0.660, 0.242)],
    # Greenway (North-South Road): Fornost -> Bree -> Tharbad -> Isengard.
    [(0.300, 0.200), (0.308, 0.252), (0.310, 0.300), (0.320, 0.362),
     (0.330, 0.432), (0.385, 0.482), (0.440, 0.528)],
    # The Rohan road: Isengard -> Edoras -> Minas Tirith (skirting the Nimrais).
    [(0.440, 0.528), (0.470, 0.556), (0.500, 0.570), (0.532, 0.576),
     (0.556, 0.586), (0.585, 0.596)],
    # Harad Road: out of Ithilien across the Poros to the southern edge.
    [(0.575, 0.660), (0.600, 0.750), (0.622, 0.850), (0.636, 0.950),
     (0.640, 1.00)],
]

# Key sites (fractional x, y, kind, name), placed at their reference positions.
SITES: List[Tuple[float, float, str, str]] = [
    # -- Gondor --
    (0.585, 0.596, "city", "Minas Tirith"),
    (0.602, 0.596, "ruin", "Osgiliath"),
    (0.626, 0.616, "fort", "Minas Morgul"),
    (0.594, 0.575, "fort", "Cair Andros"),
    (0.616, 0.606, "fort", "Henneth Annûn"),
    (0.550, 0.680, "town", "Pelargir"),
    (0.500, 0.666, "town", "Linhir"),
    (0.485, 0.646, "town", "Calembel"),
    (0.440, 0.695, "city", "Dol Amroth"),
    (0.462, 0.712, "town", "Edhellond"),
    (0.428, 0.662, "town", "Ethring"),
    # -- Rohan / Isengard --
    (0.500, 0.570, "city", "Edoras"),
    (0.470, 0.566, "fort", "Helm's Deep"),
    (0.490, 0.586, "town", "Dunharrow"),
    (0.532, 0.560, "town", "Aldburg"),
    (0.440, 0.528, "fort", "Isengard"),
    # -- Eriador / Arnor --
    (0.310, 0.300, "town", "Bree"),
    (0.270, 0.290, "town", "Hobbiton"),
    (0.255, 0.302, "town", "Michel Delving"),
    (0.300, 0.200, "ruin", "Fornost"),
    (0.245, 0.185, "ruin", "Annúminas"),
    (0.215, 0.272, "ruin", "Emyn Beraid"),
    (0.190, 0.272, "city", "Grey Havens"),
    (0.365, 0.255, "ruin", "Weathertop"),
    (0.330, 0.432, "ruin", "Tharbad"),
    (0.155, 0.478, "ruin", "Lond Daer"),
    (0.470, 0.242, "city", "Rivendell"),
    (0.448, 0.070, "ruin", "Carn Dûm"),
    (0.500, 0.104, "fort", "Mount Gundabad"),
    (0.482, 0.238, "pass", "High Pass"),
    (0.466, 0.398, "pass", "Redhorn Pass"),
    # -- Rhovanion / Wilderland --
    (0.535, 0.430, "city", "Caras Galadhon"),
    (0.470, 0.410, "ruin", "Moria"),
    (0.558, 0.505, "ruin", "Argonath"),
    (0.525, 0.280, "town", "Carrock"),
    (0.620, 0.400, "fort", "Dol Guldur"),
    (0.618, 0.172, "city", "Thranduil's Halls"),
    (0.643, 0.200, "town", "Esgaroth"),
    (0.658, 0.180, "town", "Dale"),
    (0.660, 0.163, "fort", "Erebor"),
    # -- Mordor --
    (0.710, 0.625, "fort", "Barad-dûr"),
    (0.685, 0.620, "volcano", "Mount Doom"),
    (0.636, 0.565, "gate", "The Morannon"),
    (0.633, 0.606, "pass", "Cirith Ungol"),
    (0.652, 0.600, "fort", "Durthang"),
    (0.685, 0.672, "town", "Nurn"),
]

# Off-map provider gateways at edge tiles (ADR-0001 §World extent).
GATEWAYS: List[Tuple[float, float, str, str]] = [
    (0.640, 1.00, "gateway", "Harad Road (Poros)"),
    (1.00, 0.420, "gateway", "East Rhûn"),
    (0.850, 1.00, "gateway", "SE Khand"),
    (0.285, 1.00, "gateway", "Umbar Sea"),
    (0.165, 0.00, "gateway", "Forochel"),
]

# Region label seeds (fractional x, y, name). Every land tile within RADIUS of the
# nearest seed takes that region's label; the rest is unlabelled backdrop (far
# north Forodwaith, deep Harad) per ADR-0001.
REGION_SEEDS: List[Tuple[float, float, str]] = [
    # Eriador / Arnor
    (0.060, 0.140, "Forlindon"), (0.100, 0.360, "Harlindon"), (0.140, 0.235, "Lindon"),
    (0.262, 0.300, "The Shire"), (0.292, 0.220, "Arthedain"), (0.330, 0.380, "Cardolan"),
    (0.420, 0.280, "Rhudaur"), (0.238, 0.440, "Minhiriath"), (0.312, 0.552, "Enedwaith"),
    (0.462, 0.380, "Eregion"), (0.444, 0.090, "Angmar"),
    (0.240, 0.190, "Evendim"), (0.312, 0.160, "North Downs"), (0.420, 0.160, "Ettenmoors"),
    (0.420, 0.250, "Trollshaws"), (0.470, 0.300, "Misty Mountains"),
    # Rhovanion / Wilderland
    (0.560, 0.340, "Wilderland"), (0.618, 0.280, "Mirkwood"), (0.535, 0.430, "Lórien"),
    (0.492, 0.510, "Fangorn"), (0.545, 0.300, "Vales of Anduin"), (0.592, 0.490, "Brown Lands"),
    (0.658, 0.180, "Dale"), (0.660, 0.160, "Erebor"), (0.628, 0.190, "Woodland Realm"),
    (0.850, 0.380, "Rhûn"), (0.700, 0.310, "East Bight"), (0.520, 0.490, "The Wold"),
    (0.700, 0.115, "Withered Heath"), (0.832, 0.160, "Iron Hills"),
    (0.600, 0.115, "Grey Mountains"),
    # Dunland / Rohan
    (0.400, 0.520, "Dunland"), (0.490, 0.560, "Rohan"), (0.468, 0.540, "Westemnet"),
    (0.532, 0.532, "Eastemnet"),
    # Gondor
    (0.552, 0.578, "Anórien"), (0.620, 0.630, "Ithilien"), (0.520, 0.660, "Lebennin"),
    (0.452, 0.700, "Belfalas"), (0.372, 0.688, "Anfalas"), (0.480, 0.640, "Lamedon"),
    (0.580, 0.606, "Gondor"), (0.600, 0.820, "Harondor"), (0.432, 0.660, "Pinnath Gelin"),
    (0.320, 0.700, "Andrast"), (0.520, 0.582, "White Mountains"), (0.352, 0.600, "Druwaith Iaur"),
    (0.572, 0.530, "Emyn Muil"), (0.624, 0.552, "Dagorlad"), (0.620, 0.642, "Emyn Arnen"),
    (0.552, 0.585, "Druadan Forest"),
    # Mordor
    (0.692, 0.615, "Gorgoroth"), (0.722, 0.640, "Mordor"), (0.732, 0.700, "Nurn"),
    (0.645, 0.575, "Udûn"), (0.820, 0.632, "Lithlad"),
    # Harad backdrop edge
    (0.580, 0.920, "Near Harad"),
]

REGION_RADIUS_FRAC = 0.16   # land beyond this from any seed stays unlabelled
WATER = {SEA, LAKE, RIVER}


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def build_terrain() -> List[List[str]]:
    g = _blank()
    _fill_sea(g)
    _fblobs(g, SEAS, SEA)
    _fblobs(g, ISLANDS, LAND)
    for fpts, radius in MOUNTAINS:
        _fpolyline(g, fpts, MOUNTAIN, radius)
    _hill_skirts(g)  # ring each massif in hills for a legible, passable skirt
    _fblobs_where(g, HILLS_BLOBS, HILLS, only=LAND)
    _fblobs(g, FORESTS, FOREST)
    _fblobs_where(g, CLEARINGS, LAND, only=FOREST)
    _fblobs(g, MARSHES, MARSH)
    _fblobs(g, BARRENS, BARREN)
    _fblobs(g, LAKES, LAKE)
    for river in RIVERS:
        _fpolyline(g, river, RIVER)
    for road in ROADS:
        _fpolyline(g, road, ROAD)
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

    seeds = [(*P(x, y), name) for x, y, name in REGION_SEEDS]
    radius2 = R(REGION_RADIUS_FRAC) ** 2

    grid = [["." for _ in range(WIDTH)] for _ in range(HEIGHT)]
    for row in range(HEIGHT):
        for col in range(WIDTH):
            if terrain[row][col] in WATER:
                continue
            best_d = radius2 + 1
            best_name = None
            for sc, sr, name in seeds:
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
        {"col": P(x, y)[0], "row": P(x, y)[1], "kind": kind, "name": name}
        for x, y, kind, name in (*SITES, *GATEWAYS)
    ]
    return {
        "name": "arda_ta2965",
        "description": (
            "The full TA-2965 War-of-the-Ring theatre, traced in fractional "
            "coordinates over the canonical 'West of Middle-earth at the End of "
            "the Third Age' map (build ticket 04): terrain tile grid, region "
            "labels, sites, and off-map provider gateways."
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
