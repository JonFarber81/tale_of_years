# 08 — Dynasties & succession

**What to build:** Bloodlines and the passing of crowns. Kinship (parents, marriage) forms an emergent graph; when a ruler dies or departs, the realm's succession rule chooses the heir; a failed line fragments or is absorbed by the strongest neighbour, and an extinguished faction leaves a dormant claim so realms like Arnor can be restored generations later. A dynasty is inspectable as a bloodline.

**Blocked by:** 05, 07

**Status:** done

- [x] Kinship is a query over Character id-fields (`parent_ids`, `spouse_id`; siblings/descent derived); no separate Dynasty entity. — `characters.ancestors/descendants/children_of/bloodline`.
- [x] Each faction carries a `succession_rule` enum (`agnatic_primogeniture / elective / stewardship / dwarf_line_of_durin / …`). — `factions.SuccessionRule`.
- [x] On a `leader_id` holder's death/departure, a succession walk resolves the heir under the rule and emits `succession`. — `succession.py` phase, after `aging_births_deaths`.
- [x] Failed line: try kin → elective/relative fallback → else the realm fragments or is absorbed by the strongest bordering faction (conquest-like ownership transfer); a zero-territory faction is tombstoned with a **dormant claim** that persists. — via `world.grid` (ADR-0004); dormant claim in `Faction.claim_region_ids`.
- [x] Canon succession behaviours hold for the seeded realms (Gondor stewardship, Rohan agnatic, Durin's line, Dúnedain Chieftains).
- [x] The chronicle can render a dynasty/bloodline view; succession and line-failure events carry prose + salience weights. — `render_bloodline` in the inspection dock; `succession/line_failed/absorption` weights + renderers.
- [x] Tests: normal succession, elective fallback, failed-line fragmentation/absorption, and dormant-claim persistence each reproduce under a fixed seed. — `tests/test_succession.py`.

## Notes

- ADR-0004 records the one architectural decision this ticket forced: territory changes hands one ticket before war, so the `TileGrid` is now reachable through `world.grid` (a live, non-serialized handle) — the `system(world, rng)` signature is unchanged and ticket 11's conquest reuses the same seam.
- Owner-grid persistence stays ticket 12: a *reloaded* world carries no grid, so the absorption branch is skipped there (the dormant claim itself persists on the faction record). Unreachable in practice at the start year.
