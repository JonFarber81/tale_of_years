# 02 — Event click → map pan + highlight

**What to build:** Clicking an event row in the Annals feed centers the map on
the event's location with a transient highlight. Space-only: the timeline is
never scrubbed.

**Blocked by:** 01

**Status:** done

- [x] Clicking a placed event (one with a `location_id`) resolves the Site's
      `col`/`row` and pans/centers the map view on that tile.
- [x] A transient highlight marker (e.g. a pulse/ring that fades or expires
      after a short interval) marks the tile so the eye lands in the right
      place; it must not persist as permanent map state.
- [x] Clicking an unplaced event does not move the map (no error, no jump to
      origin). The dossier half of the click is ticket 03.
- [x] Year-divider header rows are not clickable events.
- [x] Panning does not disturb the timeline, the scrub cap, or the annals
      filter — clicking an old event must not truncate or rebuild the feed.
- [x] Tests cover: placed click pans to the right tile, unplaced click is a
      no-op for the map, and the marker expires.

## Comments

**2026-07-21 (agent):** Implemented. `MapView.focus_tile(col, row)` centers
the view on the tile and reuses the existing salience-pulse ring as the
transient marker (self-cleaning, nothing persists). The window connects the
annals view's `clicked` signal to `_on_annals_event_clicked`, which reads the
`Event` via `EventRole` — header rows and unplaced events return early, so
only placed events move the map, and nothing touches the timeline, cap, or
filter. Note: `centerOn` clamps at scene edges, so a site within half a
viewport of the map border sits as near center as the scene allows (verified
visually on Minas Tirith). Tests cover routing (header/unplaced no-ops,
placed pan), real centering geometry, and pulse expiry.
