# 08 — Dynasties & succession

**What to build:** Bloodlines and the passing of crowns. Kinship (parents, marriage) forms an emergent graph; when a ruler dies or departs, the realm's succession rule chooses the heir; a failed line fragments or is absorbed by the strongest neighbour, and an extinguished faction leaves a dormant claim so realms like Arnor can be restored generations later. A dynasty is inspectable as a bloodline.

**Blocked by:** 05, 07

**Status:** ready-for-agent

- [ ] Kinship is a query over Character id-fields (`parent_ids`, `spouse_id`; siblings/descent derived); no separate Dynasty entity.
- [ ] Each faction carries a `succession_rule` enum (`agnatic_primogeniture / elective / stewardship / dwarf_line_of_durin / …`).
- [ ] On a `leader_id` holder's death/departure, a succession walk resolves the heir under the rule and emits `succession`.
- [ ] Failed line: try kin → elective/relative fallback → else the realm fragments or is absorbed by the strongest bordering faction (conquest-like ownership transfer); a zero-territory faction is tombstoned with a **dormant claim** that persists.
- [ ] Canon succession behaviours hold for the seeded realms (Gondor stewardship, Rohan agnatic, Durin's line, Dúnedain Chieftains).
- [ ] The chronicle can render a dynasty/bloodline view; succession and line-failure events carry prose + salience weights.
- [ ] Tests: normal succession, elective fallback, failed-line fragmentation/absorption, and dormant-claim persistence each reproduce under a fixed seed.
