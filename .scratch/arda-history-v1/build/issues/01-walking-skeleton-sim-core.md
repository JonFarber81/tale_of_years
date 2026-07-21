# 01 — Walking skeleton: seeded sim core, tick loop, event log, save/load

**What to build:** The headless, framework-agnostic simulation core with nothing but the spine — no game systems yet. You can start a run from a string seed, advance it year by year from TA 2965, have it emit at least one placeholder event per tick, save the run to disk, reload it, and prove the reloaded run continues bit-identically to one that never stopped. This is the prefactor + walking skeleton every other ticket builds on.

> **Update (ADR-0003):** the tick is now a **month** (`TICKS_PER_YEAR = 12`), not a year. `World` stores an absolute `tick` clock; `current_year`/`month` are derived. Persistence stores `tick` (schema v2, with a v1→v2 migration). The `Event.year` stamp and the driver's `--years N` (now `N * TICKS_PER_YEAR` ticks) are unchanged in spirit.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A `World` holds id-keyed typed record collections + run-level fields (`current_year` starting TA 2965, RNG state, `id_counter`, `config`, append-only `events`).
- [ ] Entity base fields exist: `id`, `kind`, `name`, `created_year`, `status` (`active` + tombstone enum `dead`/`departed`/`destroyed`); ids are monotonic and never reused.
- [ ] All cross-references are integer ids; state serializes as a plain tree with no pointer cycles.
- [ ] A fixed 8-phase tick pipeline scaffold runs each `system(world, rng) -> events` in order (phases registered but empty of game logic); advancing a tick increments the year and appends events.
- [ ] One seeded `random.Random`, seeded via `sha256(seed_str)` → int, threaded through the pipeline; `seed_str` stored verbatim.
- [ ] `Event` record (`id`, `year`, `type`, `subject_ids`, `location_id?`, `importance`, `payload`, `text?`) is appended to the log; a placeholder event type is emitted per tick to exercise the stream.
- [ ] Save = canonical JSON (`sort_keys`, never pickle/`hash()`) of state + event log + `rng.getstate()` + provenance header (`schema_version, code_version, python_version, rng_family, scenario_id, scenario_version, seed_str`); load = direct rehydrate.
- [ ] A headless driver advances K ticks and dumps the event stream.
- [ ] Determinism tests: same (seed, config) → byte-identical run twice and across processes; save→load→continue equals never-stopping (bit-identical).
