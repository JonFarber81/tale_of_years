# 03 — Section styling: colored stances, bucket-dotted events

**What to build:** Style the two densest faction-dossier sections using the
color vocabulary the app already has.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] DIPLOMACY: the stance word is colored — `at war` / `hostility` in the
      war red, `alliance` / `treaty` in the construction-adjacent green,
      `vassalage` in the dynasty purple — with the raw disposition number
      kept after it, dimmed. Neutral stances remain unlisted (as today).
- [ ] RECENT EVENTS: each line carries a small bucket-colored dot/stripe
      reusing the `annals_style` type→bucket mapping and colors, so the
      mini-history reads consistently with the annals feed. Still capped at
      the 5 most recent, newest first.
- [ ] No clickable lines — cross-linking stays on the annals-ui wishlist.
- [ ] Colors legible on light and dark palettes (same hues as the feed).
- [ ] Tests cover: stance→color mapping (including at-war vs mere
      hostility), the dimmed disposition number surviving, and event lines
      carrying the right bucket color.

## Comments
