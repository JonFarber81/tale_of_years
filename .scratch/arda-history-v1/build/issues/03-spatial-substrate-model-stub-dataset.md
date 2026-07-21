# 03 — Tile substrate model + stub dataset

> **Revised by [ADR-0001](../../../../docs/adr/0001-tile-substrate-and-render.md) (2026-07-20)** —
> tiles are now the unit of simulation (was: region-polygon + route graph). Original
> region/route checklist retired; see the SUPERSEDED note at the bottom.

**What to build:** The tile-grid data model and its loader, plus a small
hand-authored stub region (Gondor/Anduin) so it can be exercised end-to-end. The
grid renders as a Dwarf-Fortress-style **tile map** (sprite tiles + custom
mountain/river tiles) with per-tile faction tint, clickable into the inspection
dock. This proves the tile substrate before the full theatre is authored (ticket 04).

**Blocked by:** 01, 02

**Status:** done

- [x] A `TileGrid` (fixed `width`×`height` at **~15 miles/tile**) of tiles, each with static `terrain` and, layered on top, mutable `owner_faction_id` (the authoritative territory state). Grid geometry is **config**, not run state. — `tiles.TileGrid` (`miles_per_tile=15`; `test_terrain_is_config_owner_is_state`).
- [x] Terrain enum (`plains/forest/mountain/hills/marsh/barren/water(river|lake|sea)/road`) with a per-terrain **movement cost** and passability. — `tiles.Terrain` + `movement_cost`/`is_passable` (`test_movement_cost_and_passability`).
- [x] `Region` becomes a **named label**: an id + name over a set of tiles (aggregate for identity/prose), *not* an owner. Settlements/features are records anchored to a tile `(col,row)`. — `tiles.Region`/`Site` (`test_region_ids_are_stable_and_labels_resolve`).
- [x] A tile↔pixel calibration (for tracing/authoring only); movement budget expressed in **tiles/year** (miles/year ÷ 15). — `miles_per_tile` on the grid + the authoring tools under `tools/authoring/` (the movement *phase* itself is ticket 10).
- [x] A scenario loader builds the grid + labels deterministically (same dataset → same ids/layout); terrain from an authored source. — `scenarios/load_scenario` (`test_loader_is_deterministic`).
- [x] A small **stub dataset** (the Gondor/Anduin region already traced) loads and renders as tiles over the DF-style canvas, with a couple of faction-owned tile blocks tinted.
- [x] Renderer: **Kenney CC0 sprites** for grass/dirt/water/road/forest (grass base + foliage overlay) drawn from the bundled spritesheet via the `tile_render` seam; **custom mountain & hills motifs** (peak/mound over a stone/grass base — the pack has no summit sprite) and procedural marsh; per-tile owner tint; derived-border strokes; deterministic (row-major) draw order.
- [x] Clicking a tile opens it in the inspection dock (terrain, owner label, region label, any site — resolved via `MainWindow.describe_tile`).
- [x] Tests: loader is deterministic; terrain grid is config (excluded from the mutable-state save diff); only `owner_faction_id` (+ occupants) is per-tick state; movement-cost/passability lookups behave. — `tests/test_tiles.py`, `tests/test_tile_render.py`.

<!-- SUPERSEDED (ADR-0001), kept for provenance:
- Region (polygon in v7 px, terrain, adjacency, owner_faction_id, seat_location_id, base_yield), Location (point, region_id, type, owner), Route (endpoints, polyline, kind, length_miles).
- pixels-per-mile calibration; region polygons coloured + locations marked over the v7 image blitted as canvas.
-->
