# ADR-0001 — Tiles are the simulation substrate; render as a Dwarf-Fortress-style tile map

Status: **Accepted** (2026-07-20)

Supersedes the spatial-substrate decision in ticket `01-spatial-substrate` and the
"v7 image as canvas" rendering decision — see **Consequences**.

## Context

The v1 design (ticket 01, spec §"Spatial substrate") chose a **region-polygon +
location/route graph** as the world model, stored in v7 pixel coordinates, and
rendered by **blitting the v7 map image** as the canvas. Ticket 01 explicitly
rejected a grid as "overkill at a yearly tick and painful to hand-author."

Two later user decisions overturn the premises behind that choice:

1. **Rendering:** the map should be drawn *in-engine* as a **tile map in the
   Dwarf-Fortress idiom** — geography traced from Tolkien canon (v7 + other
   references) but the visuals are the engine's own tiles, not the v7 photo.
2. **Substrate:** the **tiles should be the unit of simulation**, not merely a
   skin over a region graph. The viewer wants to watch territory spread, armies
   march, and borders form *on the grid*.

The region graph was chosen for authoring cheapness and coarse yearly ticks; the
user has accepted the grid's authoring cost in exchange for emergent, legible
spatial history. That trade reverses ticket 01's rationale.

## Decision

**The world is a fixed grid of terrain tiles, and the tile is the unit of
simulation.**

- **Scale:** ~**15 miles per tile**, giving the War-of-the-Ring theatre roughly
  **~100 × 130 ≈ 13,000 tiles**. Strategic scale, not DF embark scale.
- **Per-tile state:** static `terrain` (config) + mutable `owner_faction_id`
  (the authoritative territory state) + optional occupant/feature references
  (settlement id, army positions layered on top).
- **Regions survive as *named labels* only** — a region is an aggregate tag over
  a set of tiles, used for identity and event prose ("the Shire"), not for
  ownership or movement. Ownership and borders are per-tile; "contested" and
  borders are *derived* from neighboring tiles' owners.
- **Movement is tile-to-tile** via deterministic pathfinding (fixed tie-breaking)
  with per-terrain movement cost; roads are cheaper tiles. Army/Ring/Nazgûl
  positions are tile coordinates. Movement budget is expressed in **tiles/year**
  (derived from miles/year ÷ 15).
- **Rendering** is a tile renderer (chosen style: real sprite tileset — Kenney
  roguelike pack, **CC0**, bundled in `references/tilesets/` — with **custom
  mountain and river tiles** the pack lacks). Each tile draws its terrain sprite;
  faction territory is a per-tile owner tint over the terrain.
- **Coordinates:** tile `(col, row)`; the authored terrain grid is fixed config.
  A one-time calibration maps tiles to v7 pixels for tracing only.

## Consequences

- **Ticket 01 (substrate) is rewritten** and its region/route decision retired.
  Ticket 01 stays on file as the record of the original exploration.
- **Reshaped:** 06 territory (per-tile ownership; emergent borders), 07 war &
  movement (tile pathfinding; battles/sieges on tiles), 08 construction
  (settlements/roads on tiles), 10 Ring/Nazgûl (tile movement), 11 render/UI
  (per-tile owner tint), 12 persistence (serialize a tile-owner grid, run-length
  encoded since ownership is contiguous). Ticket 04 authoring now produces a
  **terrain tile grid** — the main new one-time cost.
- **Largely unaffected:** 05 characters/dynasties and 09 the One-Ring object
  model — spatial only through the armies/bearers that stand on tiles.
- **Performance** (already the spec's #1 risk) becomes central but is bounded by
  the tile scale: ~13k tiles is cheap for per-tile state, deterministic A*, and
  RLE-compressed per-year owner snapshots. Finer scales remain a future option.
- **Determinism** is preserved: pathfinding and any tile iteration must use fixed
  ordering and integer/fixed-point comparisons, consistent with the existing
  float-determinism policy.

## Alternatives considered

- **Region graph simulates, tiles only render** (the "skin" model). Cheaper and
  closer to the original spec, but territory snaps to pre-drawn regions and armies
  hop city-to-city — it doesn't deliver the emergent, watch-it-spread map the
  user wants. Rejected.
- **Keep the v7 image as canvas.** Rejected per user decision (in-engine tiles).
