"""Entry point for the desktop app: ``arda-sim-ui``.

Builds a seeded run, wraps it in :class:`Playback`, shows the main window, and
enters the Qt event loop. Watch-only — the sim advances on its own thread.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from PySide6.QtWidgets import QApplication

from ..playback import Playback
from ..world import World
from .mainwindow import MainWindow


def build_window(seed: str, canonicity: float = 1.0) -> MainWindow:
    """Construct (but do not show) the main window for a fresh run.

    Split out from ``main`` so it can be exercised headlessly (offscreen) in
    tests without entering the event loop.
    """
    playback = Playback(World.new_run(seed, canonicity=canonicity))
    return MainWindow(playback)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arda-sim-ui", description="Watch the Third Age unfold on the v7 map."
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
