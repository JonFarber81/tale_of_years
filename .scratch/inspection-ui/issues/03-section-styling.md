# 03 — Section styling: colored stances, bucket-dotted events

**What to build:** Style the two densest faction-dossier sections using the
color vocabulary the app already has.

**Blocked by:** 01

**Status:** ready-for-human

- [x] DIPLOMACY: the stance word is colored — `at war` / `hostility` in the
      war red, `alliance` / `treaty` in the construction-adjacent green,
      `vassalage` in the dynasty purple — with the raw disposition number
      kept after it, dimmed. Neutral stances remain unlisted (as today).
- [x] RECENT EVENTS: each line carries a small bucket-colored dot/stripe
      reusing the `annals_style` type→bucket mapping and colors, so the
      mini-history reads consistently with the annals feed. Still capped at
      the 5 most recent, newest first.
- [x] No clickable lines — cross-linking stays on the annals-ui wishlist.
- [x] Colors legible on light and dark palettes (same hues as the feed).
- [x] Tests cover: stance→color mapping (including at-war vs mere
      hostility), the dimmed disposition number surviving, and event lines
      carrying the right bucket color.

## Comments

**2026-07-21 (agent):** Implemented alongside ticket 02.
`_describe_diplomacy` emits HTML lines: the stance word colored via
`_stance_html` — **at war** (pinned flag, not mere disposition) bold in the
war red, hostility red, alliance green, vassalage purple — with the raw
disposition dimmed after; overlord/vassal names wear the fealty purple.
Colors are the annals bucket hues (`BUCKET_COLORS`), so the dock and the
feed share one vocabulary. RECENT EVENTS lines lead with a bucket-colored
● dot (`_event_line`), neutral gray for unmapped types, still capped at 5
newest-first. No clickable lines. Tested at the unit level
(`_stance_html`, `_event_line`) and through a real seeded run.
