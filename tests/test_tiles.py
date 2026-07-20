"""Tile substrate: loader determinism, config/state split, borders, movement."""

import pytest

from arda_sim.scenarios import load_scenario, load_scenario_data
from arda_sim.tiles import (
    UNOWNED,
    Terrain,
    TileGrid,
    is_passable,
    load_grid,
    move_cost,
)


def test_load_gondor_stub_dimensions_and_terrain():
    grid = load_scenario("gondor_stub")
    assert (grid.width, grid.height) == (44, 28)
    assert len(grid.terrain) == 44 * 28
    assert grid.miles_per_tile == 15
    # Minas Tirith's tile was authored as plains (the settlement is a Site on top)
    assert grid.terrain_at(17, 11) == Terrain.PLAINS
    assert grid.terrain_at(0, 0) in set(Terrain)


def test_loader_is_deterministic():
    data = load_scenario_data("gondor_stub")
    a, b = load_grid(data), load_grid(data)
    assert a.terrain == b.terrain
    assert a.region_of == b.region_of
    assert a.regions == b.regions  # ids assigned in sorted-legend order


def test_region_ids_are_stable_and_labels_resolve():
    grid = load_scenario("gondor_stub")
    names = {r.name for r in grid.regions.values()}
    assert {"Gondor", "Ithilien", "Mordor"} <= names
    # ids assigned by sorted legend char: G<I<M -> 1,2,3
    by_name = {r.name: r.id for r in grid.regions.values()}
    assert by_name["Gondor"] < by_name["Ithilien"] < by_name["Mordor"]


def test_sites_anchored_to_tiles():
    grid = load_scenario("gondor_stub")
    sites = {s.name: (s.col, s.row) for s in grid.sites}
    assert sites["Minas Tirith"] == (17, 11)
    assert all(grid.in_bounds(s.col, s.row) for s in grid.sites)


def test_terrain_is_config_owner_is_state():
    grid = load_scenario("gondor_stub")
    # a freshly loaded grid is entirely unowned; terrain is populated
    assert all(o == UNOWNED for o in grid.owner)
    assert any(t == Terrain.MOUNTAIN for t in grid.terrain)


def test_movement_cost_and_passability():
    assert move_cost(Terrain.ROAD) == 1
    assert move_cost(Terrain.PLAINS) == 2
    assert move_cost(Terrain.MOUNTAIN) is None
    assert is_passable(Terrain.PLAINS) is True
    assert is_passable(Terrain.SEA) is False
    # integer costs only — no float ever decides movement
    assert all(isinstance(move_cost(t), int) for t in Terrain if is_passable(t))


def _tiny_grid():
    # 3x1: plains, mountain, plains
    return load_grid(
        {
            "width": 3,
            "height": 1,
            "terrain_legend": {".": "plains", "^": "mountain"},
            "terrain": [".^."],
            "region_legend": {},
            "regions": ["..."],
        }
    )


def test_neighbors_fixed_order_and_bounds():
    grid = _tiny_grid()
    # middle tile has only W and E neighbours (no N/S in a 1-row grid)
    assert list(grid.neighbors(1, 0)) == [(2, 0), (0, 0)]  # E then W
    assert list(grid.neighbors(0, 0)) == [(1, 0)]


def test_border_is_derived_from_owner_differences():
    grid = _tiny_grid()
    assert grid.is_border(0, 0) is False  # unowned
    grid.set_owner(0, 0, 5)
    grid.set_owner(2, 0, 7)
    # tile (0,0) neighbour is (1,0) which is unowned -> differs -> border
    assert grid.is_border(0, 0) is True
    grid.set_owner(1, 0, 5)
    grid.set_owner(2, 0, 5)
    assert grid.is_border(0, 0) is False  # now all-5 neighbourhood


def test_owner_rle_round_trip():
    grid = load_scenario("gondor_stub")
    for i in range(0, 100):
        grid.owner[i] = 3
    for i in range(100, 150):
        grid.owner[i] = 9
    runs = grid.owner_rle()
    assert runs[0] == [3, 100]
    restored = load_scenario("gondor_stub")
    restored.load_owner_rle(runs)
    assert restored.owner == grid.owner


def test_grid_rejects_mismatched_dimensions():
    with pytest.raises(ValueError):
        load_grid(
            {
                "width": 2,
                "height": 2,
                "terrain_legend": {".": "plains"},
                "terrain": [".."],  # only 1 row for height 2
                "region_legend": {},
                "regions": [".."],
            }
        )
