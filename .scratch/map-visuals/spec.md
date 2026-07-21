# Map visuals — spec

Improve the visual quality and legibility of the map view
(`src/arda_sim/ui/map_view.py`, themed by `src/arda_sim/ui/tile_render.py`).
Two reported problems plus a batch of agreed polish, decided in a grilling
session (2026-07-21).

## Problems

1. **City labels overlap on zoom.** Labels are plain scene text items that
   scale with the view transform — no font, no halo (despite the docstring's
   claim), no decluttering. At far zoom every label draws and they pile up.
2. **Armies are featureless markers.** Hosts render as faction-colored discs;
   sites are cream discs — the two read alike, and neither says anything
   about *what* is there.

## Decisions

- **Labels**: screen-fixed size via `ItemIgnoresTransformations`, with
  tier-gated visibility on zoom (cities always; towns at mid-zoom; forts and
  ruins only close-up). Real `QFont` and a halo behind the text. Collision
  culling was considered and deferred — revisit only if tier gating leaves
  dense clusters unreadable.
- **Armies**: a people sprite from the bundled Kenney sheet drawn over a
  faction-colored backing disc — color says *whose*, sprite says *what folk*.
  Army markers keep scaling with the map (they are map objects, not
  annotations).
- **People is domain vocabulary** (CONTEXT.md "People"): a new
  `people ∈ men | elves | dwarves | orcs | hobbits` field on `Faction`,
  authored on every roster seed, providers included. Isengard is **men**
  (TA 2965 — no Uruk-hai yet; world-truth beats villain styling).
- **Sites**: the renderer starts consulting `Site.kind`/`tier` — city, town,
  fort, and ruin get distinct markers.
- Also ticketed: terrain polish for the three procedural-fallback terrains
  (mountain/hills/marsh), a march-direction indicator on moving hosts, and a
  transient battle marker.

## Tickets

| # | Ticket | Blocked by |
|---|--------|------------|
| 01 | people-field | — |
| 02 | label-declutter | — |
| 03 | army-sprites | 01 |
| 04 | settlement-markers | — |
| 05 | terrain-polish | — |
| 06 | march-indicator | — |
| 07 | battle-markers | — |
