# Annals Chronicle UI improvements

The Annals dock today is a bare `QListView` of flat one-line strings
(`"TA 3019: <sentence>"`) — a wall of text where nothing has visual weight and
nothing is clickable. This effort makes the feed scannable and interactive,
UI-only: no sim changes, all the data needed already rides on `Event`
(`type`, `importance`, `subject_ids`, `location_id`, `payload`).

## Decisions (from the grilling session, 2026-07-21)

1. **Click does both** — a single click on an event pans/centers the map on the
   event's Site tile *and* pushes an **event dossier** into the existing
   Inspection dock. One gesture, two payoffs; no popup windows.
2. **Row anatomy uses all three signals** — year dividers (grouping rows under
   a year header instead of repeating the `TA NNNN:` prefix), a category
   color/glyph on the left edge, and importance expressed as text
   weight/dimming.
3. **Four category buckets**: **war**, **diplomacy**, **dynasty**
   (succession/kinship), **construction** (economy/building).
4. **Dossier depth**: handcrafted narrative templates for the war-phase types
   (field battle, siege, conquest, razing), generic key/value `payload`
   rendering as the fallback for everything else.
5. **Map jump is space-only** — pan + transient highlight marker; the timeline
   is *not* scrubbed to the event's year. Events with no `location_id`
   ("unplaced") open the dossier only; **placed** events show a pin glyph so
   the affordance is visible before clicking.
6. **Category filter chips are in scope** — the four-bucket legend doubles as
   include/exclude toggles, ANDing with the existing important-only/show-all
   toggle via the existing `AnnalsFilter` machinery.

## Out of scope (wishlist — see `wishlist.md`)

- Cross-linking: names inside a dossier clickable through to faction/character
  dossiers.
- Time-jump: event click also scrubs the timeline to the event's year (hazard:
  the scrub cap would truncate the feed being clicked).

## Tickets

| # | Ticket | Depends on |
|---|--------|------------|
| 01 | Rich annals rows (delegate: dividers, category, importance, pin) | — |
| 02 | Event click → map pan + highlight | 01 |
| 03 | Event dossier in the Inspection dock | 02 |
| 04 | Category filter chips | 01 |
