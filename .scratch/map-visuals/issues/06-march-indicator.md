# 06 — March direction indicator

**What to build:** A marching host currently teleports disc-to-tile each
tick. Show motion: a small direction indicator on any host that is mid-march,
honoring the v1 spec's "armies shown moving along roads and rivers"
(.scratch/arda-history-v1/spec.md:37).

**Blocked by:** —

**Status:** done

- [x] In `MapView.refresh_armies` (`src/arda_sim/ui/map_view.py:121-146`),
      when a host has a march path with a next tile, draw a direction cue
      pointing from its tile toward the next path tile. Implementer's pick:
      a small arrowhead/chevron at the marker's leading edge, or a short
      fading trail behind it. Keep it subtle — the marker itself (ticket 03)
      stays the dominant element.
- [x] Idle/garrisoned hosts (no active march) show no indicator.
- [x] The cue reads at mid zoom but does not clutter full-map zoom — either
      scale-gated like labels or small enough not to matter (tune by eye).
- [x] Data source: the host's march path already lives on the army record
      (CONTEXT.md "March"); read the next waypoint from state — no new sim
      fields, this is render-only.
- [x] Rebuilt wholesale with the rest of the army items each
      `refresh_armies` call — no stale indicators after a host halts or dies.
- [x] Verify by running a war scenario: a host marching along a road shows a
      consistent forward cue each tick; it disappears on arrival.
