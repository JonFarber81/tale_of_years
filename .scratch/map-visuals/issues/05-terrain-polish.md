# 05 — Terrain polish: mountain, hills, marsh

**What to build:** The three terrains with no fitting Kenney sprite render as
procedural fallbacks (`paint_terrain_tile`,
`src/arda_sim/ui/tile_render.py:114-153`): mountain is a drawn triangle,
hills an ellipse mound, marsh flat fill + horizontal lines. Make all three
pull their visual weight.

**Blocked by:** —

**Status:** done

- [x] Revisit each of mountain / hills / marsh with one of (implementer's
      judgment per terrain):
      - a better hand-picked or composited cell from the Kenney sheet
        (e.g. layering like forest's base + canopy approach);
      - a richer procedural motif (shading, variation, silhouette) than the
        current single flat shape.
- [x] Per-tile deterministic variation where it helps (e.g. hills mound
      offset, marsh tuft placement) — seeded from tile coords, never RNG at
      paint time, so renders are reproducible.
- [x] Mountains should read as ranges at full-map zoom — that is the main
      "does the map look good zoomed out" test, since the Misty Mountains
      dominate the map.
- [x] Stay inside the existing theme boundaries: all changes in
      `tile_render.py`; `map_view.py` keeps calling `paint_terrain_tile`
      unchanged. Color helpers stay headless-importable.
- [x] Verify by eye at three zoom levels (full map / region / close-up)
      against the current render — screenshot before/after for the PR.
