"""Entry point for the desktop app: ``arda-sim-ui``.

Builds a seeded run, wraps it in :class:`Playback`, shows the main window, and
enters the Qt event loop. Watch-only — the sim advances on its own thread.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from PySide6.QtWidgets import QApplication

from ..playback import Playback
from ..scenarios import load_scenario
from ..tiles import TileGrid
from ..world import World
from .mainwindow import MainWindow

# The stub scenario the tile substrate is proven against (ADR-0001 / ticket 03).
_STUB_SCENARIO = "gondor_stub"


def _seed_demo_territory(grid: TileGrid) -> Dict[int, str]:
    """Tint a couple of faction-owned blocks over the stub so the renderer has
    territory (and a derived frontier) to draw before ticket 06 lands real
    factions. Ownership is assigned from region labels: Gondor+Ithilien held by
    faction 1, Mordor by faction 2 — leaving a Gondor/Mordor border.
    """
    by_name = {r.name: r.id for r in grid.regions.values()}
    region_owner = {
        by_name.get("Gondor"): 1,
        by_name.get("Ithilien"): 1,
        by_name.get("Mordor"): 2,
    }
    for row in range(grid.height):
        for col in range(grid.width):
            rid = grid.region_of[grid.index(col, row)]
            owner = region_owner.get(rid)
            if owner:
                grid.set_owner(col, row, owner)
    return {1: "Gondor", 2: "Mordor"}


def build_window(seed: str, canonicity: float = 1.0) -> MainWindow:
    """Construct (but do not show) the main window for a fresh run.

    Split out from ``main`` so it can be exercised headlessly (offscreen) in
    tests without entering the event loop.
    """
    playback = Playback(World.new_run(seed, canonicity=canonicity))
    grid = load_scenario(_STUB_SCENARIO)
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
