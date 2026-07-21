# 04 — Category filter chips

**What to build:** The four-bucket legend above the Annals feed doubles as a
filter: four toggle chips (War / Diplomacy / Dynasty / Construction) that
include/exclude buckets from the feed.

**Blocked by:** 01

**Status:** done

- [x] Four chips above the feed, one per bucket, colored to match the row
      accents (the legend teaches the color code). All on by default.
- [x] Toggling a chip off hides that bucket's events; the chips map buckets to
      type-sets via the shared type→bucket mapping from ticket 01 and apply
      through the existing `AnnalsFilter` type index — no new filter
      machinery in the model.
- [x] Chips AND with the existing important-only/show-all toggle (chips
      constrain *which* buckets, the toggle constrains *how important*),
      matching how `AnnalsFilter` already combines its indices.
- [x] Events whose type maps to the neutral/unmapped bucket remain visible
      regardless of chip state (chips only subtract known buckets).
- [x] Tests cover: single-chip exclusion, all-chips-off, chip × importance
      combination, and that re-enabling a chip restores the rows.

## Comments

**2026-07-21 (agent):** Implemented, with one deviation from the ticket text:
`AnnalsFilter.type` is a single-type *equality*, so it cannot express "hide
these buckets" — instead of bolting a parallel predicate onto the model, the
filter itself gained a small `excluded_types: FrozenSet[str]` constraint
(ANDing in `matches` like every other index, `None` excludes nothing). The
chips are checkable buttons above the feed (`_bucket_chips`), each styled
with its bucket's accent color, dimmed when unchecked; bucket→type-sets come
from the shared `types_in_bucket` in `annals_style.py`. The window composes
one filter from both controls in `_apply_annals_filter` (show-all picks the
importance base, unchecked chips name the excluded types), so flipping
either control re-applies both. Unmapped types are never excluded. Tested at
the filter level (test_chronicle) and the UI level (single exclusion,
all-off, chip × importance, restore); chip states verified visually.
