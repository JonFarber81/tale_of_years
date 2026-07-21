# 01 — Rich annals rows

**What to build:** Replace the flat one-line strings in the Annals feed with a
styled rendering that gives the feed visual hierarchy. Pure presentation — no
click behavior, no model-query changes.

**Blocked by:** —

**Status:** ready-for-human

- [x] A custom `QStyledItemDelegate` paints each event row: category accent
      (color stripe or glyph) on the left edge, event sentence as the body.
- [x] The four category buckets — **war**, **diplomacy**, **dynasty**,
      **construction** — are derived from `Event.type` by a single
      type→bucket mapping that lives in one place (the chips ticket and the
      dossier ticket will reuse it). Unmapped types get a neutral bucket.
- [x] Importance drives text treatment: events at/above the important
      threshold render full-strength (bold), events below it render dimmed —
      visible when the feed is in show-all mode.
- [x] Year dividers: consecutive events of the same year group under one
      `TA NNNN` header row instead of each row repeating the prefix.
      Newest-first order is preserved (row 0 = most recent).
- [x] Placed events (those with a `location_id`) show a small pin glyph;
      unplaced events show none. (The glyph is inert in this ticket — the
      click lands in ticket 02.)
- [x] The feed stays responsive across centuries of events: the virtualized
      list must not regress (year headers must not force per-row size
      computation over the whole model — e.g. keep uniform row heights with
      headers as same-height rows, or size hints computed O(1) per row).
- [x] The model exposes the underlying `Event` (e.g. via a custom role) so
      the delegate — and later tickets — read structure, not parsed strings.
- [x] Colors respect light/dark palettes (derive from or harmonize with the
      application palette rather than hardcoding for one theme).
- [x] Tests cover the type→bucket mapping, year-divider grouping (including
      the cap/filter rebuild paths), and the placed/unplaced distinction.

## Comments

**2026-07-21 (agent):** Implemented. `AnnalsModel` now interleaves year-header
rows with event rows (newest-first, one divider per year, headers merged on
append so a year never gets two); event rows expose their `Event` via
`EventRole`, and `visible_event_count()` counts events sans headers. The
type→bucket mapping and `AnnalsDelegate` live in `ui/annals_style.py` —
bucket accent stripe (fixed mid-tone hues; the neutral bucket and all text
derive from the live palette), bold-vs-dimmed by `IMPORTANT_THRESHOLD`, drawn
pin glyph on placed rows, uniform row heights throughout. Bucket calls made:
war declarations/endings and army events read as **war**; marriage reads as
**diplomacy** (the pact, not the cradle). Verified with offscreen renders of
the real fellowship feed and a synthetic placed/unplaced mix; full suite
green (236 passed).
