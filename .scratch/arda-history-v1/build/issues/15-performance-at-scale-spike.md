# 15 — Performance-at-scale spike

**What to build:** A time-boxed research/measurement spike to de-risk the one open concern the spec flagged: the cost of an open-ended yearly sim over centuries. Run long simulations, measure where time and memory actually go (tick cost, event-log growth, snapshot-cache size), and decide the concrete thresholds for the storage seam (JSON → SQLite for the event log) and the UI's snapshot strategy (per-year vs keyframe+replay). The deliverable is a findings note + recommended thresholds, not a full implementation.

**Blocked by:** 11

**Status:** migrated — now tracked on GitHub as [#4](https://github.com/JonFarber81/tale_of_years/issues/4) (2026-07)

- [ ] Drive multi-century headless runs (e.g. 200–500 years) with the systems available and record per-tick wall-clock, event-log size, and snapshot-cache memory growth.
- [ ] Identify the dominant cost drivers (which phase, which entity growth) and whether cost stays acceptable open-ended.
- [ ] Recommend the trigger point (log size / run length) for swapping the event log to the JSONL/SQLite sidecar behind ticket 01's storage seam.
- [ ] Recommend whether the UI keeps snapshot-per-year or falls back to keyframe-snapshots + bounded replay, and at what horizon.
- [ ] Capture findings + recommended thresholds as a note in the repo (research file), linked from this ticket; note any follow-up tickets it surfaces.
- [ ] No production behaviour change required beyond throwaway measurement harness code.
