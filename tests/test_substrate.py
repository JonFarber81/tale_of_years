"""The full TA-2965 substrate (build ticket 04): it loads, renders coherently,
and satisfies the substrate invariants.

These tests guard the *authored content* against regressions in the generator or
an accidental hand-edit of the JSON — they load the shipped scenario, never the
generator, since the JSON is the artifact the engine consumes.
"""

import pytest

from arda_sim.scenarios import load_scenario, load_scenario_data
from arda_sim.tiles import Terrain, load_grid
from arda_sim.validate import GATEWAY_KIND, check_grid, validate_grid

SCENARIO = "arda_ta2965"


@pytest.fixture(scope="module")
def grid():
    return load_scenario(SCENARIO)


def test_theatre_dimensions(grid):
    # ~100x130 ≈ 13k tiles at 15 mi/tile (ADR-0001).
    assert (grid.width, grid.height) == (100, 125)
    assert len(grid.terrain) == grid.width * grid.height
    assert grid.miles_per_tile == 15


def test_spans_the_theatre_regions(grid):
    # A handful of anchor regions from west to east must be present as labels.
    names = {r.name for r in grid.regions.values()}
    for expected in ["Lindon", "The Shire", "Rohan", "Gondor", "Mordor", "Mirkwood", "Rhûn"]:
        assert any(expected in n or n == expected for n in names), expected
    # The ticket asks for ~50–100 named regions.
    assert 50 <= len(grid.regions) <= 100


def test_key_sites_present_and_placed(grid):
    by_name = {s.name: s for s in grid.sites}
    for expected in [
        "Minas Tirith", "Osgiliath", "Edoras", "Helm's Deep", "Isengard",
        "Barad-dûr", "The Morannon", "Erebor", "Dale", "Rivendell",
        "Caras Galadhon", "Thranduil's Halls", "Dol Guldur", "Bree", "Grey Havens",
    ]:
        assert expected in by_name, expected
        s = by_name[expected]
        assert grid.in_bounds(s.col, s.row)


def test_has_provider_gateways_on_edges(grid):
    gateways = [s for s in grid.sites if s.kind == GATEWAY_KIND]
    assert len(gateways) >= 3
    for g in gateways:
        assert g.col in (0, grid.width - 1) or g.row in (0, grid.height - 1)


def test_terrain_is_varied(grid):
    kinds = {t for t in grid.terrain}
    # A real map, not a monoculture: land, water, relief, and routes all appear.
    for t in [Terrain.PLAINS, Terrain.SEA, Terrain.MOUNTAIN, Terrain.FOREST,
              Terrain.RIVER, Terrain.ROAD]:
        assert t in kinds, t


def test_substrate_passes_validation(grid):
    assert validate_grid(grid) == []
    check_grid(grid)  # does not raise


def test_loader_is_deterministic():
    data = load_scenario_data(SCENARIO)
    a, b = load_grid(data), load_grid(data)
    assert a.terrain == b.terrain
    assert a.region_of == b.region_of
    assert a.regions == b.regions
