"""Bundled scenario datasets (fixed config) and a loader for them.

A scenario JSON carries the tile grid: dimensions, terrain/region char-grids with
their legends, sites, and ``miles_per_tile``. It is authored content, not run
state — the same scenario always loads to the same grid.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Dict

from ..tiles import TileGrid, load_grid


def load_scenario_data(name: str) -> Dict:
    """Read a bundled scenario's raw JSON dict by name (e.g. ``"gondor_stub"``)."""
    text = resources.files(__package__).joinpath(f"{name}.json").read_text(encoding="utf-8")
    return json.loads(text)


def load_scenario(name: str) -> TileGrid:
    """Load a bundled scenario into a :class:`~arda_sim.tiles.TileGrid`."""
    return load_grid(load_scenario_data(name))
