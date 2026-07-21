# 03 — Armies: people sprite over a faction-colored disc

**What to build:** Replace the bare faction-colored ellipse in
`MapView.refresh_armies` (`src/arda_sim/ui/map_view.py:121-146`) with a
character sprite from the bundled Kenney sheet, chosen by the host faction's
`people`, drawn over a smaller faction-colored backing disc.

**Blocked by:** 01

**Status:** done

- [x] A people→sprite-cell mapping in `src/arda_sim/ui/tile_render.py`
      (alongside `_SPRITE_CELL`): one Kenney character cell each for
      `men | elves | dwarves | orcs | hobbits`, plus a fallback cell for any
      unknown value. Picking the exact cells is implementer's choice from
      `references/tilesets/kenney_roguelike-rpg/Spritesheet/
      roguelikeSheet_transparent.png` (16px cells, stride 17 — the existing
      `_sprite_source` machinery applies).
- [x] `refresh_armies` draws, per living host: a faction-colored backing
      disc (slightly smaller than today's 0.68·TILE, keeping the dark
      outline) with the people sprite blitted on top, centered, scaled into
      the tile like `paint_terrain_tile` does. Marker scales with the map
      (no `ItemIgnoresTransformations`).
- [x] Faction lookup: the view needs the host's faction's `people` — thread
      it the same way faction color already reaches `refresh_armies`
      (`tile_render.faction_color(army.faction_id)`), extending that
      call-path rather than inventing a parallel one.
- [x] Armies remain visually distinct from site markers at a glance
      (color + sprite vs the site marker treatment from ticket 04).
- [x] z-order preserved: armies above sites/labels, below salience pulses.
- [x] Headless-test safety: sprite lookup stays lazy like `_sheet_pixmap` —
      color/mapping helpers importable without a QGuiApplication.
- [x] Verify by running a scenario tick with hosts marching: Mordor host
      shows an orc, a Gondor host a man, over their faction colors.

## Note — sprite source

The ticket assumed the *bundled* Kenney roguelike/RPG sheet
(`roguelikeSheet_transparent.png`) carried character figures. It does not — it
is environment/buildings/items only. So a **second CC0 pack**, Kenney's
**Roguelike Characters** (`roguelikeChar_transparent.png`, same 16px/stride-17
geometry), was downloaded and bundled under
`references/tilesets/kenney_roguelike-characters/` (License.txt kept for
provenance). `tile_render` loads it via a second lazy pixmap
(`_char_sheet_pixmap`) and `assets.character_tileset_path()`. Folk cells:
men `(0,1)`, elves `(1,5)`, dwarves `(1,6)`, orcs `(1,3)`, hobbits `(0,10)`,
fallback `(0,0)` — real figures, distinguished by skin/robe/beard/size at tile
scale (user chose figures over the interim emblematic-prop stand-ins).
