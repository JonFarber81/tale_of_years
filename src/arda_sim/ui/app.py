"""Entry point for the desktop app: ``arda-sim-ui``.

Builds a seeded run, wraps it in :class:`Playback`, shows the main window, and
enters the Qt event loop. Watch-only — the sim advances on its own thread.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from PySide6.QtWidgets import QApplication

from ..characters import new_seeded_run
from ..factions import factions, seed_factions
from ..playback import Playback
from ..scenarios import load_scenario
from ..validate import check_grid
from ..world import World
from .mainwindow import MainWindow

# The full War-of-the-Ring theatre (ADR-0001 / build ticket 04). The Gondor
# slice (gondor_stub) remains on file as the substrate's first proving ground.
_SCENARIO = "arda_ta2965"


def build_window(
    seed: str, canonicity: float = 1.0, *, seed_characters: bool = True
) -> MainWindow:
    """Construct (but do not show) the main window for a fresh run.

    Split out from ``main`` so it can be exercised headlessly (offscreen) in
    tests without entering the event loop.

    The run is seeded with the canon TA 2965 roster (ticket 05) and the canon
    faction roster (ticket 07), so there is life *and* a political map to
    chronicle from year one: births/deaths and yearly faction decisions stream
    into the Annals as prose and pulse on the map (ticket 06), and regions render
    coloured by their owning faction. ``seed_characters=False`` starts an empty
    world (no roster, no factions), which wiring smoke tests use so their per-year
    event counts don't hinge on the roster's lifecycle RNG.
    """
    grid = load_scenario(_SCENARIO)
    check_grid(grid)  # fail loudly if the authored substrate is malformed
    if seed_characters:
        world = new_seeded_run(seed, canonicity=canonicity)
        faction_names = seed_factions(world, grid)
        # faction id -> people, so host markers draw their folk's sprite (03).
        faction_people = {f.id: f.people for f in factions(world)}
    else:
        world = World.new_run(seed, canonicity=canonicity)
        faction_names = {}
        faction_people = {}
    # Attach the map as the live handle every territory-touching phase reaches
    # through (ADR-0004) — without it movement (phase 4) and war (phase 5) are
    # inert no-ops, so the political map would never move. Mirrors seed_world().
    world.grid = grid
    playback = Playback(world)
    return MainWindow(playback, grid, faction_names, faction_people)


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
