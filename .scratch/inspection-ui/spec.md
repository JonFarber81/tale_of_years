# Inspection dock UI improvements

The Inspection dock today is one word-wrapped plain-text `QLabel` fed by four
describe paths (tile, army, faction, event). Everything renders in one uniform
weight with ASCII `──` rules; a tile click stacks tile facts + site line +
full army dossier + full faction dossier, and a long dossier overflows the
dock with no scrollbar. Nothing sticks out. UI-only effort: no sim changes.

## Decisions (from the grilling session, 2026-07-21)

1. **Rendering surface: Qt rich text in a `QTextBrowser`.** The `describe_*`
   renderers emit simple HTML (headings, bold, color spans, small tables).
   Scrollable for free; selectable text; and `<a href>` anchors are exactly
   the mechanism the wishlisted cross-linking ticket will want — styling and
   future linking land on the same surface.
2. **Shared dossier anatomy**, every selection kind: a **banner** (small
   kind-tag over the subject's name in large bold, with a colored accent
   bar), a **stat grid** (dimmed small labels, full-weight values), then
   **section headers** in small dimmed caps replacing the ASCII rules.
3. **Identity accents**: the banner accent is identity-driven, not
   kind-driven — a faction (or its host/site) wears its map color
   (`tile_render.faction_color`), an event wears its category-bucket color,
   an unowned tile stays neutral. Ties the dock to the map and the feed.
4. **Most-specific-first**: a map click resolves to one **dossier subject**
   — host > site > faction > bare tile — which headlines the banner and gets
   full depth. Everything else demotes to trimmed context sections (a
   faction as context = leader + strength + stance summary; bloodline and
   recent events only when the faction is the subject). Clicking open ground
   still headlines the faction with full depth, so nothing is unreachable.
5. **Stat grids per type**:
   - Faction: Leader, Kind, Succession, Posture · Aggression, Strength,
     Treasury. Prominence and latest intent are *dropped* (sim internals;
     intent still surfaces via faction-intent events under RECENT EVENTS).
   - Host: Strength (hero stat), Leader, Faction, Destination, and — new
     content — **siege progress** when investing a seat (invisible today).
   - Site: rank ("City · tier 2" / "Fortress" / "Ruin"), Owner, Region,
     Terrain.
   - Bare tile: Terrain, Region, Owner only — the boring case stays short.
   - Event: no grid; the banner absorbs year/bucket/importance, prose stays.
6. **Section styling**: DIPLOMACY stance words colored (war/hostility red,
   alliance/treaty green, vassalage purple) with the disposition number
   dimmed after; RECENT EVENTS lines get a small bucket-colored dot reusing
   the annals mapping. Still capped at 5 events. No clickable lines yet
   (cross-linking remains wishlist, see `../annals-ui/wishlist.md`).

## Tickets

| # | Ticket | Depends on |
|---|--------|------------|
| 01 | HTML dossier surface + shared anatomy | — |
| 02 | Most-specific-first restructure + per-type stat grids | 01 |
| 03 | Section styling (colored stances, bucket-dotted events) | 01 |
