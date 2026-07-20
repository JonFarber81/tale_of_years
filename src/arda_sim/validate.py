"""Substrate integrity checks (build ticket 04).

A hand-authored theatre is easy to get subtly wrong — a site dropped in the sea,
a region label with no tiles, a gateway that isn't actually on the map edge. This
module states the substrate's invariants once, as data-returning checks so both
tests and any future authoring tool can reuse them.

The invariants are phrased for the *tile* substrate (ADR-0001), which reshapes
ticket 04's original polygon/route vocabulary: "adjacency is symmetric" becomes
"every region label resolves and is used", "route endpoints resolve" becomes
"every site sits on a real, sensible tile".
"""

from __future__ import annotations

from collections import Counter
from typing import List

from .tiles import Site, TileGrid

# Sites that model an off-map provider reached from a map edge (ADR-0001). They
# are exempt from the "on passable land" rule and instead must sit on an edge.
GATEWAY_KIND = "gateway"

# Terrain a normal (non-gateway) site must not stand on. Fortresses on mountains
# (Erebor, Helm's Deep), lake-towns (Esgaroth), and river-forts (Cair Andros) are
# all canonical, so only the open sea is a genuine authoring mistake.
_FORBIDDEN_SITE_TERRAIN = {"sea"}


def validate_grid(grid: TileGrid) -> List[str]:
    """Return a list of human-readable integrity problems (empty == valid)."""
    problems: List[str] = []
    n = grid.width * grid.height

    # 1. Grid dimensions are internally consistent.
    if len(grid.terrain) != n:
        problems.append(f"terrain has {len(grid.terrain)} tiles, expected {n}")
    if len(grid.region_of) != n:
        problems.append(f"region_of has {len(grid.region_of)} tiles, expected {n}")

    # 2. Every region label on a tile resolves to a real Region...
    used = set(rid for rid in grid.region_of if rid)
    for rid in sorted(used):
        if rid not in grid.regions:
            problems.append(f"tile references region id {rid} with no Region entry")
    # ...and every declared Region is actually used by at least one tile.
    for rid, region in sorted(grid.regions.items()):
        if rid not in used:
            problems.append(f"region {region.name!r} (id {rid}) labels no tiles")

    # 3. Sites: in bounds, sensibly placed, uniquely named.
    for name, count in Counter(s.name for s in grid.sites).items():
        if count > 1:
            problems.append(f"duplicate site name {name!r} ({count}x)")
    for site in grid.sites:
        problems.extend(_check_site(grid, site))

    return problems


def _check_site(grid: TileGrid, site: Site) -> List[str]:
    problems: List[str] = []
    if not grid.in_bounds(site.col, site.row):
        problems.append(f"site {site.name!r} at ({site.col},{site.row}) is out of bounds")
        return problems  # further checks would index out of range

    terrain = grid.terrain_at(site.col, site.row)
    if site.kind == GATEWAY_KIND:
        on_edge = (
            site.col in (0, grid.width - 1) or site.row in (0, grid.height - 1)
        )
        if not on_edge:
            problems.append(f"gateway {site.name!r} at ({site.col},{site.row}) is not on a map edge")
    elif terrain.value in _FORBIDDEN_SITE_TERRAIN:
        problems.append(f"site {site.name!r} stands on open {terrain.value} at ({site.col},{site.row})")
    return problems


def check_grid(grid: TileGrid) -> None:
    """Raise ``ValueError`` if the grid violates any substrate invariant."""
    problems = validate_grid(grid)
    if problems:
        raise ValueError("substrate validation failed:\n  - " + "\n  - ".join(problems))
