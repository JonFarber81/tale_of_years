# 02 — Event click → map pan + highlight

**What to build:** Clicking an event row in the Annals feed centers the map on
the event's location with a transient highlight. Space-only: the timeline is
never scrubbed.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Clicking a placed event (one with a `location_id`) resolves the Site's
      `col`/`row` and pans/centers the map view on that tile.
- [ ] A transient highlight marker (e.g. a pulse/ring that fades or expires
      after a short interval) marks the tile so the eye lands in the right
      place; it must not persist as permanent map state.
- [ ] Clicking an unplaced event does not move the map (no error, no jump to
      origin). The dossier half of the click is ticket 03.
- [ ] Year-divider header rows are not clickable events.
- [ ] Panning does not disturb the timeline, the scrub cap, or the annals
      filter — clicking an old event must not truncate or rebuild the feed.
- [ ] Tests cover: placed click pans to the right tile, unplaced click is a
      no-op for the map, and the marker expires.
