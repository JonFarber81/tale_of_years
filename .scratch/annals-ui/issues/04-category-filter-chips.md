# 04 — Category filter chips

**What to build:** The four-bucket legend above the Annals feed doubles as a
filter: four toggle chips (War / Diplomacy / Dynasty / Construction) that
include/exclude buckets from the feed.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Four chips above the feed, one per bucket, colored to match the row
      accents (the legend teaches the color code). All on by default.
- [ ] Toggling a chip off hides that bucket's events; the chips map buckets to
      type-sets via the shared type→bucket mapping from ticket 01 and apply
      through the existing `AnnalsFilter` type index — no new filter
      machinery in the model.
- [ ] Chips AND with the existing important-only/show-all toggle (chips
      constrain *which* buckets, the toggle constrains *how important*),
      matching how `AnnalsFilter` already combines its indices.
- [ ] Events whose type maps to the neutral/unmapped bucket remain visible
      regardless of chip state (chips only subtract known buckets).
- [ ] Tests cover: single-chip exclusion, all-chips-off, chip × importance
      combination, and that re-enabling a chip restores the rows.
