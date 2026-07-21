# 02 — Site labels: screen-fixed, tier-gated, haloed

**What to build:** Fix the overlapping-label problem in
`MapView._add_sites` / zoom handling (`src/arda_sim/ui/map_view.py:148-197`)
and deliver the typography/halo polish in the same pass — it is the same
function in the same file.

**Blocked by:** —

**Status:** done

- [x] Labels set `QGraphicsItem.ItemIgnoresTransformations` so they render at
      constant screen size regardless of zoom (markers keep scaling — they
      are map objects; labels are annotations).
- [x] Tier-gated visibility, re-evaluated whenever the zoom scale changes
      (`_apply_zoom`, `fit_map`, and initial show):
      - **cities** (tier 2): always labeled;
      - **towns / forts** (tier 1): labeled from a mid-zoom threshold;
      - **ruins / everything else**: labeled only when zoomed close.
      Thresholds live as named constants in `map_view.py`, tuned by eye.
- [x] An explicit `QFont` (pick one deliberate size/weight; stop inheriting
      the app default) and a halo behind the text — either
      `QGraphicsDropShadowEffect`, an outlined `QPainterPath`, or a
      translucent background rect — so labels stay readable over dark
      terrain. The `_add_sites` docstring already promises "haloed label";
      make it true.
- [x] Label anchor offset re-checked after `ItemIgnoresTransformations`
      (the current `(cx + TILE*0.3, cy - TILE*0.7)` offset was tuned for
      scene-scaled text and will land differently).
- [x] Collision culling is **out of scope** (deferred decision) — leave a
      brief comment noting tier gating is the chosen mechanism.
- [x] Verify by running the app: zoom from full-map to close-up over the
      Gondor cluster (Minas Tirith / Osgiliath / Minas Morgul are the
      densest) — no overlapping label text at any zoom stop.
