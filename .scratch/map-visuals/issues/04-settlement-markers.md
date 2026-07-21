# 04 — Settlement markers by kind and tier

**What to build:** The renderer currently draws every site as the same cream
disc, ignoring `Site.kind`/`tier` (`src/arda_sim/tiles.py:92-97`). Make the
marker say what stands there: city, town, fort, or ruin.

**Blocked by:** —

**Status:** ready-for-agent

- [ ] Distinct marker treatment per site kind/tier in
      `MapView._add_sites` (`src/arda_sim/ui/map_view.py:148-167`),
      preferring building sprites from the bundled Kenney sheet (castle /
      tower / house cells — implementer picks; the sheet-blitting machinery
      from `tile_render.py` applies). Procedural-vector fallback is
      acceptable where no sprite fits, matching the terrain precedent.
      Minimum legible distinctions:
      - **city** (tier 2) — largest / most elaborate marker;
      - **town** (tier 1) — modest marker;
      - **fort** — martial silhouette (tower/keep), distinct from
        settlements;
      - **ruin** — visibly diminished (broken/greyed marker).
- [ ] Sites change kind/tier over a run (found/rebuild, grow — see
      CONTEXT.md "Construction & economy"). Markers must refresh when that
      happens: find where the sim mutates a site's kind/tier and make the
      view re-render its marker (mirroring how `refresh_owners` handles
      ownership churn) rather than rendering once at construction forever.
- [ ] Site markers stay visually distinct from army markers (ticket 03).
- [ ] Click hit-testing still resolves the site (dossier-subject
      most-specific-first order unchanged).
- [ ] Verify by running the app across enough years for at least one grow /
      ruin event; the marker follows the site's state.
