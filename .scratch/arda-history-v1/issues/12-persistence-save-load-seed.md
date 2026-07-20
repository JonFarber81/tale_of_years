# World-state persistence: save/load + string seed

Type: grilling
Status: resolved
Blocked by: 02

## Question

How is a run saved, reloaded, and reproduced?

Decide:

- **Save/load** — serializing the full world state (all entities, territory, relationships, the Ring, event history) to disk and restoring it exactly; format (JSON snapshot vs. SQLite vs. other, informed by ticket 04); when saves happen (manual, autosave per N years).
- **String seed** — a human-shareable **random string seed** that, combined with the starting configuration, deterministically reproduces a run. Requires the sim to be fully deterministic given (seed + config): a single seeded RNG threaded through every stochastic system, no reliance on wall-clock/hash-ordering.
- **Config vs. seed** — separate the fixed starting scenario (TA 2965 canon seed, the canonicity parameter) from the run seed, so "same seed, different canonicity" and "different seed, same start" both make sense.
- **Versioning** — how saves survive later changes to the entity model (at least a version stamp).

Depends on the core entity model (02). Consult `/codebase-design` for the serialization seam.

## Answer

A run is saved as a **canonical-JSON snapshot** (state + event log) behind a **storage-backend seam**, reproduced from a **SHA-256 string seed** with the **live RNG state** captured for exact resume, and identified by a **(scenario+version, canonicity, seed, code) tuple** with a **versioned migration chain**.

### A. Save format — JSON-first, storage seam *(fork resolved)*

- One **canonical-JSON snapshot** per save: `json.dumps(sort_keys=True)` over `World.to_dict()`. The id-only-refs decision (02) already makes `World` a plain serializable tree (no pointer cycles), so this is a near-mechanical dump — human-diffable, git-friendly, **never pickle/`hash()`** (per research 04).
- Load is a **direct rehydrate** (`from_dict`), not a replay — state is authoritative.
- **Saving is wrapped behind a `to_dict`/`from_dict` + storage-backend boundary**, so if the append-only event log balloons over centuries (the map's performance-at-scale fog), the event log can move to a **JSONL/SQLite sidecar** — or the whole thing to SQLite — **without touching sim code**. JSON is the v1 default; the seam is the hedge.

### B. When saves happen

- **Autosave every N years** (config, e.g. 25) at **tick phase 8** (the pipeline already reserves the "autosave check" slot — the only quiescent point, no system mid-mutation), **plus manual save any time**. Optional ring-buffer of the last K autosaves is a cheap future rewind affordance (fog).

### C. String seed → RNG

- `seed_int = int.from_bytes(hashlib.sha256(seed_str.encode("utf-8")).digest()[:8], "big")`, feeding **one `random.Random(seed_int)`** created at world init and threaded through every system (the 02 single-RNG contract). SHA-256 is stable cross-process, unlike `hash()` (which `PYTHONHASHSEED` randomizes) — research 04 names this explicitly.
- The raw `seed_str` is stored **verbatim** so it stays human-shareable.
- **RNG family is locked to `random.Random`** for v1 (no vectorized draws needed); if that ever changes, the version stamp (§F) must record the family, since the state format differs.

### D. Capturing RNG state for exact resume

- On save, serialize the **live RNG internal state** — `rng.getstate()` (a tuple → JSON list of ints) — and restore with `setstate()` on load, so a resumed run is bit-identical to one that never stopped (ticks have already consumed draws, so the *current* position, not the original seed, is what matters). `seed_str` is still stored for from-scratch reproduction.
- **Constraint this imposes (cross-cutting):** exact determinism requires the sim to avoid float branch-points across platforms — a policy every system ticket (05–10) must honour (integer/fixed-point where a comparison decides an outcome). Surfaced as fog (see below), not resolved here.

### E. Config vs seed vs canonicity — three independent inputs

Every save records three separable things so both experiment axes work:
1. **Scenario config** — the fixed TA-2965 canon dataset + geometry (regions/locations/routes), referenced by a stable **`scenario_id` + `scenario_version`**, *not* re-serialized inline (it's a deterministically id-assigned build asset per 02).
2. **Canonicity parameter(s)** — the tunable canon-pressure knob(s); part of `World.config` but recorded **separately** from the scenario id, so it can vary while scenario is held fixed.
3. **Run seed** — the `seed_str`.

A run is fully identified by `(scenario_id+version, canonicity_params, seed_str, code_version)`. This directly yields "same seed+scenario, vary canonicity" **and** "same scenario+canonicity, vary seed."

### F. Versioning & migration

- A **provenance header** on every save: `{schema_version, code_version, python_version, rng_family, scenario_id, scenario_version, seed_str}` (matches research 04's provenance list; pins the RNG-stability caveat to an interpreter family).
- `schema_version` is an integer bumped on any breaking record-shape change, with a small **ordered migration-function chain** (`migrate_v1_to_v2`, …) run on load to upgrade old saves. The id-keyed-record shape keeps field migrations local and mechanical. A tolerant reader (ignore-unknown / default-missing) may complement numbered migrations for additive changes but does not replace them.

### Seams & fog surfaced

- **Float-determinism policy** — 12's resume guarantee requires system tickets 05–10 to avoid cross-platform float branch-points. Cross-cutting constraint; recorded as fog and noted on each system ticket as they're worked.
- **Event-log growth at scale** — quantifying log size over centuries drives whether/when to exercise the storage seam (JSON → sidecar/SQLite); overlaps the map's performance-at-scale fog. Likely a small research/prototype spike later.
- **Scenario-dataset versioning** — if the hand-authored region/route dataset changes after saves exist, does a `scenario_version` bump migrate or invalidate old runs? Couples to §E's reference-not-inline choice; deferred.
- **12↔11** — on-disk persistence and retention of the per-year snapshot cache (11's playback) is budgeted here when it's exercised.
