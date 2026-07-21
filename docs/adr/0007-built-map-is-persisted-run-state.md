# ADR-0007 — The built map is persisted run state (site kind, tier, roads)

Status: **Accepted** (2026-07-21)

Records the state-model decision the construction & economy phase (build ticket
12) makes: a `Site`'s **kind** and **tier**, and the tiles a realm **paves into
roads**, become authoritative *mutable* run state that persists across save/load —
resolving the deferral ADR-0006 left open ("when site kind becomes persisted run
state, `_conquer` additionally stamps the seat `ruin`").

## Context

Through ticket 11 the only authoritative mutable tile state was `grid.owner`
(per-tile ownership, RLE-persisted). Everything else on the `TileGrid` —
terrain, regions, and `Site` records — was **frozen config**, reproduced by
re-loading the scenario and never serialized (ADR-0001/0004). ADR-0006 leaned on
that: razing laid land waste by sending tiles to `UNOWNED`, and the "settlement
becomes a ruin" flavour lived only in the chronicle event, not in state.

Ticket 12 needs the built world to *change and stick*:

- **Found / rebuild** turns an un-settled owned location (a `ruin` or a `pass`)
  into a `town` or a `fort`; **grow** turns a `town` into a `city`. These are
  `Site.kind`/`tier` changes.
- A **razed** seat must actually become a `ruin` so peacetime construction can
  raise it again — the 11 → 12 seam the razed-ruin-rebuild acceptance test walks.
- **Open a road** paves a tile, which is a *terrain* change (`ROAD`), and terrain
  was previously immutable config.

Two problems follow. Site kind/tier now diverges from config, and a paved tile's
terrain diverges from config — but a reloaded world rebuilds the grid from the
scenario, so both would silently reset on load and a resumed run would diverge
from an uninterrupted one (breaking ticket 12's exact-resume guarantee).

## Decision

**`Site.kind` and `Site.tier` are mutable run state.** `Site` is no longer a
frozen dataclass; construction and razing mutate it in place through
`TileGrid.set_site`. Its *identity* (name, col, row, id) stays config — only the
settlement slice moves.

**Roads are a persisted terrain overlay, not a config edit.** `TileGrid.pave`
sets a tile's terrain to `ROAD` **and** records the tile index in a new
`grid.paved` run-state list. Base terrain stays config; paved indices are the
only terrain that changes at runtime.

**The mutable grid slice persists with the owner grid (schema v2 → v3).** A save's
`state.grid` now carries `{owner_rle, sites, paved}`; load reloads the config grid
for the run's `scenario_id` (via a `scenario_id → file` registry), then re-applies
owner ownership, site kind/tier, and every paved tile on top. A v2 save (no grid
block) migrates to v3 as gridless, exactly as it loaded before.

## Consequences

- **Razing now marks the seat.** `_conquer` stamps a razed capital `ruin`
  (ADR-0006's deferred half), so a ruin is a real, rebuildable place — not just
  chronicle flavour.
- **Exact resume survives construction.** Because site kind/tier and paved tiles
  round-trip, a run saved mid-campaign and resumed stays bit-identical to one that
  never stopped, roads and rebuilt towns included.
- **Grid persistence is now real for every phase.** Re-attaching the built grid on
  load (not just repainting fresh territory) closes the `world.grid` reload gap
  ADR-0004 flagged; the grid-reading phases (diplomacy, movement, war, construction)
  resume against the actual mid-run map.
- **Config vs. state is now a slice, not a whole.** A `Site`/`TileGrid` is part
  config (identity, base terrain, regions) and part state (kind, tier, owner,
  paved). `site_state()`/`owner_rle()`/`paved` name exactly the persisted slice, so
  the boundary stays legible.

## Alternatives considered

- **Keep site kind cosmetic (chronicle-only), as ADR-0006 did.** A rebuildable
  ruin has to be real state — the rebuild loop reads `Site.kind` to find its
  targets — so cosmetic-only cannot express ticket 12 at all.
- **Persist full terrain (RLE) instead of a paved overlay.** Larger per-save
  payload and it reframes all terrain as state; the `paved` overlay keeps terrain
  config and records only the handful of runtime edits.
- **Spawn a new settlement *entity* on founding.** The design says founding "flips
  a Location to a settlement type (no new entity)"; a mutated `Site` keeps the
  stable config-space id that characters/events already point at.
