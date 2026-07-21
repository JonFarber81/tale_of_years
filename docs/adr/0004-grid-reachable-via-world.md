# ADR-0004 — A phase system may reach the tile grid through `world.grid`

Status: **Accepted** (2026-07-20)

Narrows ADR-0002's "a system is handed only `(world, rng)` — **not** the `TileGrid`."
Does not change the `system(world, rng) -> events` signature; it makes the grid
*reachable through the world* rather than passed as a parameter. Motivated by
build ticket 08 (dynasties & succession), the first system that must change who
owns territory.

## Context

ADR-0002 froze the tick signature at `system(world, rng)` and deliberately kept
the `TileGrid` out of it: everything a faction needed to *decide* each year was
readable from the `World`, and the one operation that *mutates* territory —
conquest — was deferred to ticket 11 (war), which would introduce its own grid
seam. Territory therefore lives only on the grid (`grid.owner`, per-tile), which
`seed_world()` returns as an object separate from the `World`; `run_tick(world)`
never sees it.

Ticket 08 breaks that timing. A **failed ruling line** must be *"absorbed by the
strongest bordering faction"* — a conquest-like ownership transfer — one ticket
earlier than war. Resolving it needs the grid on both sides of the operation:
**read** it (which factions border the dying realm; which is strongest) and
**write** it (flip the dead realm's tiles to the absorber). The succession phase
is a `system(world, rng)`, so under ADR-0002 it cannot reach territory at all,
yet its acceptance test requires absorption to actually happen under a fixed seed.

Two ways to give it access were weighed (see the ticket-08 plan): widen the
signature to `system(world, rng, grid)` (touches all eight phases, the driver,
and the UI worker, and reverses the ADR head-on), or make a second source of
truth for ownership on the `World` (rejected already by ADR-0002). Both are
heavier than the need.

## Decision

**The `TileGrid` is attached to the `World` as a live, non-serialized handle
(`world.grid`), exactly like the seeded `rng`. A phase system that needs
territory reads and mutates `world.grid`; the `system(world, rng)` signature is
unchanged.**

- **`world.grid: Optional[TileGrid]`** — `field(compare=False, repr=False)`, so
  it never enters world-equality (two worlds still compare on serialized state)
  and never bloats a `repr`. `None` in headless/skeleton runs that carry no map.
- **The grid stays the single authoritative territory state.** This adds *no*
  second source of truth — it only makes the existing authoritative grid
  reachable from the object every system already holds. ADR-0002's rejection of a
  first-class `region -> owner` map on the `World` still stands.
- **Set at the seeding entry point.** `factions.seed_world()` assigns
  `world.grid = grid` before returning; the returned `(world, grid, names)` tuple
  is unchanged, so every existing caller keeps working.
- **Not serialized here.** The grid carries config (terrain/regions) plus the
  mutable per-tile `owner`. Config is reproduced by re-loading the scenario;
  owner-state persistence (RLE) and re-attaching a *painted* grid on load are
  **ticket 12's** explicit scope. Until then a *reloaded* world carries
  `world.grid = None`, and the succession phase degrades gracefully to
  heir-resolution only (it never reaches the territory-transfer branch, which is
  the branch that needs the grid). No save/load test exercises that branch.
- **Determinism is unaffected.** The grid holds no RNG. The succession phase
  draws from `rng` only inside the death-triggered path (elective tie-breaks,
  absorption); on a tick where no leader-holder died it is a pure no-op and draws
  nothing, so a run and its reload stay bit-identical whether or not a grid is
  attached.

## Consequences

- **Ticket 11 (war/conquest) reuses this seam.** Capturing a seat and razing a
  region are the same `world.grid` read/write; war does not need to re-invent
  territory access or widen the signature.
- **`world.grid` may be `None`.** Any system that reaches for it must guard the
  no-map case (skeleton runs, and reloaded worlds until ticket 12). Succession
  does: no grid ⇒ heir-resolution still runs, the absorption branch is skipped.
- **A reloaded run cannot yet fragment/absorb territory.** Acceptable now (no
  seeded ruler is near death at the start year, so it is unreachable in practice)
  and closed by ticket 12 when the owner grid persists and is re-attached on load.
- **The signature promise holds.** No phase gained a parameter; the reproducibility
  contract (fixed phase order, one threaded RNG) is untouched.

## Alternatives considered

- **Widen the signature to `system(world, rng, grid)`.** The most honest about a
  phase touching territory, but edits all eight phase stubs, `run_tick`/`run_years`,
  the driver, and the UI worker, and directly reverses ADR-0002's head decision
  for a capability only two systems (08, 11) use. Rejected for the lighter live
  handle.
- **A first-class `region -> owner` map on the `World`.** Already rejected by
  ADR-0002 as a second source of truth contradicting ADR-0001's "per-tile owner
  is the only authoritative territory state." Unchanged here.
- **Persist the owner grid now (pull ticket 12 forward).** Would let a reloaded
  world absorb territory immediately, but crosses a ticket boundary and needs the
  scenario-id → file resolution that ticket 12 owns. Deferred.
