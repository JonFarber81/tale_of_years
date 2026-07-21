# ADR-0003 — The tick is a month; the clock counts ticks and derives the calendar

Status: **Accepted** (2026-07-20)

Amends ADR-0001 (which assumed a yearly tick). Changes the simulation's time
granularity; does not touch the tile substrate, factions, or any system's logic.

## Context

The original design (spec, ticket 02) advanced the world **one year per tick**. In
play that made history lurch: a single step could jump a war, a succession, and a
migration at once, and the map redrew in yearly leaps. The desired feel is history
*unfolding gradually* — change you can watch accrue — which means a finer time
step.

"One tick = one year" was baked into four places: the clock (`current_year += 1`
per tick); the per-*year* lifecycle rates in `characters.py`; the
snapshot/playback cache, keyed by year; and the UI scrub/label. A naive "tick
faster" would silently misbehave — twelve yearly death/fertility rolls per year —
and collide snapshot-cache keys.

## Decision

**A tick is one month. `TICKS_PER_YEAR = 12`. An absolute `tick` count is the
authoritative clock, and the calendar (year, month) is derived from it.**

- **`World.tick`** (an int, 0 at the start month of `START_YEAR`) replaces the
  stored `current_year`. `current_year` and `month` become **derived
  properties** (`year_of_tick` / `month_of_tick`), so nothing stores a year
  independently of the tick. `run_tick` advances one tick; `run_years(n)` is the
  convenience for `n * TICKS_PER_YEAR` ticks.
- **Per-year rates apply against the monthly scale, in integer math.** The
  death/fertility tables stay authored as *annual* basis points; each monthly
  roll uses the wider `BP_SCALE * TICKS_PER_YEAR` denominator, so twelve rolls a
  year reproduce the same annual probability with no float (ADR-0001's
  float-determinism rule holds). Elf weariness accrues per tick against a
  threshold scaled by `TICKS_PER_YEAR`, preserving the "departures over centuries"
  timescale at any tick rate.
- **Playback and snapshots key on the absolute tick,** not the year. The frontier,
  restore, fast-forward, and the scrub slider all work in ticks; a `Snapshot`
  carries both its `tick` (the cache key) and its derived `year` (for labels). The
  date label reads year + month (Shire-calendar month names — cosmetic).
- **The annals stay year-grained.** Events keep their `year` stamp; the map/state
  scrub monthly while the chronicle groups by year. Scrubbing to a mid-year tick
  shows that whole year's annals — a deliberate seam, not a defect (a chronicle is
  naturally year-grained; the fine detail lives on the map).
- **Persistence stores `tick`;** schema bumps to **v2** with a v1→v2 migration
  (`tick = (current_year - START_YEAR) * TICKS_PER_YEAR`), so old yearly saves keep
  loading.
- **The driver's `--years N`** advances `N` whole years (`N * TICKS_PER_YEAR`
  ticks); `run_tick`/`run_ticks` count months.

## Consequences

- **Every run re-baselines.** The RNG stream now depends on `TICKS_PER_YEAR` (more
  rolls per year, wider `randrange` denominators), so a given seed produces
  different history than under the yearly clock. Determinism is preserved
  (run-vs-reload is still bit-identical); only saves made *before* this change
  won't reproduce identically — the migration loads them but does not reproduce
  their old RNG trajectory.
- **Performance pressure rises ~12×** — snapshots, the event log, and RNG work all
  scale with tick count. This sharpens the spec's #1 risk; ticket 15's
  performance spike and ticket 12's keyframe/replay-and-SQLite fallbacks become
  more likely to be needed. Snapshots deep-copy every entity per tick, so a
  monthly sim over centuries is the case to profile first.
- **Later systems inherit the finer clock for free.** Movement (ticket 10) is a
  per-tick tile budget = miles/year ÷ `TICKS_PER_YEAR`; sieges/wars that "persist
  across ticks" now persist across months. No system reads the calendar to decide
  outcomes, so none needed changing.
- **`TICKS_PER_YEAR` is the single knob.** Quarterly (4) or back to yearly (1) is a
  one-constant change; the rate-scaling and tick-keyed playback already generalise.

## Alternatives considered

- **Keep the yearly tick; only slow playback.** The speed control already reaches
  0.25 ticks/s, but that changes wall-clock pace, not how much history happens per
  step — it doesn't deliver gradual change. Rejected.
- **Run the lifecycle only on the year-boundary tick** (keeping annual rates
  literally annual). Simpler math, but births/deaths would still batch once a year
  — defeating the point. Rejected for scaling the rates to per-tick.
- **Quarterly (`TICKS_PER_YEAR = 4`).** A third of the performance cost for most of
  the "gradual" feel. A reasonable default, but the user asked for monthly;
  quarterly remains a one-line change if the cost bites.
