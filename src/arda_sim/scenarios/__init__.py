"""Bundled scenario datasets (fixed config) and a loader for them.

A scenario JSON carries the tile grid: dimensions, terrain/region char-grids with
their legends, sites, and ``miles_per_tile``. It is authored content, not run
state — the same scenario always loads to the same grid.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Dict

from .. import DEFAULT_SCENARIO_ID
from ..tiles import TileGrid, load_grid

# Logical scenario id (carried in a run's config / save provenance) -> the bundled
# JSON file that holds its grid. Persistence uses this to reload the config grid on
# load, then re-applies the saved owner/site state onto it (build ticket 12).
_SCENARIO_FILES: Dict[str, str] = {
    DEFAULT_SCENARIO_ID: "arda_ta2965",
}


def scenario_file_for_id(scenario_id: str) -> str:
    """The bundled file name backing a logical ``scenario_id`` (itself if unmapped)."""
    return _SCENARIO_FILES.get(scenario_id, scenario_id)


def load_scenario_for_id(scenario_id: str) -> TileGrid:
    """Load the grid for a run's logical ``scenario_id`` (used when rehydrating)."""
    return load_scenario(scenario_file_for_id(scenario_id))


def load_scenario_data(name: str) -> Dict:
    """Read a bundled scenario's raw JSON dict by name (e.g. ``"gondor_stub"``)."""
    text = resources.files(__package__).joinpath(f"{name}.json").read_text(encoding="utf-8")
    return json.loads(text)


def load_scenario(name: str) -> TileGrid:
    """Load a bundled scenario into a :class:`~arda_sim.tiles.TileGrid`."""
    return load_grid(load_scenario_data(name))
