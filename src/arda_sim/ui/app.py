"""Entry point for the desktop app: ``arda-sim-ui``.

Builds a seeded run, wraps it in :class:`Playback`, shows the main window, and
enters the Qt event loop. Watch-only — the sim advances on its own thread.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import QApplication

from ..characters import new_seeded_run
from ..playback import Playback
from ..scenarios import load_scenario
from ..tiles import TileGrid
from ..validate import check_grid
from ..world import World
from .mainwindow import MainWindow

# The full War-of-the-Ring theatre (ADR-0001 / build ticket 04). The Gondor
# slice (gondor_stub) remains on file as the substrate's first proving ground.
_SCENARIO = "arda_ta2965"

# Which region labels each demo faction holds, until ticket 06 lands real
# factions. Gondor and its provinces vs. Mordor and its — a long shared frontier.
_DEMO_FACTIONS: Dict[int, Tuple[str, List[str]]] = {
    1: ("Gondor", ["Gondor", "Anórien", "Ithilien", "Lebennin", "Belfalas",
                   "Lamedon", "Anfalas", "Emyn Arnen"]),
    2: ("Mordor", ["Mordor", "Gorgoroth", "Nurn", "Udûn", "Dagorlad"]),
}


def _seed_demo_territory(grid: TileGrid) -> Dict[int, str]:
    """Tint faction-owned regions over the map so the renderer has territory (and
    a derived frontier) to draw before ticket 06 lands real factions.
    """
    by_name = {r.name: r.id for r in grid.regions.values()}
    region_owner: Dict[int, int] = {}
    for faction_id, (_, region_names) in _DEMO_FACTIONS.items():
        for name in region_names:
            rid = by_name.get(name)
            if rid:
                region_owner[rid] = faction_id
    for row in range(grid.height):
        for col in range(grid.width):
            rid = grid.region_of[grid.index(col, row)]
            owner = region_owner.get(rid)
            if owner:
                grid.set_owner(col, row, owner)
    return {fid: label for fid, (label, _) in _DEMO_FACTIONS.items()}


def build_window(
    seed: str, canonicity: float = 1.0, *, seed_characters: bool = True
) -> MainWindow:
    """Construct (but do not show) the main window for a fresh run.

    Split out from ``main`` so it can be exercised headlessly (offscreen) in
    tests without entering the event loop.

    The run is seeded with the canon TA 2965 roster (ticket 05) so there is life
    to chronicle from year one — births and deaths stream into the Annals as
    prose and pulse on the map (ticket 06); without it the feed would carry only
    invisible heartbeats. ``seed_characters=False`` starts an empty world, which
    wiring smoke tests use so their per-year event counts don't hinge on the
    roster's lifecycle RNG.
    """
    world = new_seeded_run(seed, canonicity=canonicity) if seed_characters else World.new_run(
        seed, canonicity=canonicity
    )
    playback = Playback(world)
    grid = load_scenario(_SCENARIO)
    check_grid(grid)  # fail loudly if the authored substrate is malformed
    faction_names = _seed_demo_territory(grid)
    return MainWindow(playback, grid, faction_names)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arda-sim-ui", description="Watch the Third Age unfold on the tile map."
    )
    parser.add_argument("--seed", default="fellowship", help="human-shareable seed string")
    parser.add_argument("--canonicity", type=float, default=1.0, help="canon knob 0..1")
    args = parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    window = build_window(args.seed, canonicity=args.canonicity)
    window.resize(1280, 800)
    window.show()
    window.fit_map()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
