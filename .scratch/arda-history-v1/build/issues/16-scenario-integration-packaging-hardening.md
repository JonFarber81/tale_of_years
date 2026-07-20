# 16 — Scenario integration, packaging & determinism hardening

**What to build:** The capstone that turns the assembled systems into a shippable v1. The full TA 2965 scenario is verified end to end; long open-ended runs are proven deterministic and exactly resumable; saves survive version changes via a migration scaffold; and the app ships as a native, offline macOS application a non-developer can launch.

**Blocked by:** 12, 13, 14

**Status:** ready-for-agent

- [ ] Full TA 2965 seed assembled and verified: canon faction + character roster correct, not-yet-born characters absent, the Ring borne by Bilbo at Bag End with low scalars, providers at their gateways, the nine Nazgûl placed (Witch-king at Minas Morgul, three at Dol Guldur).
- [ ] End-to-end determinism hardening: a long open-ended run (e.g. through and past the canonical War-of-the-Ring window) is byte-identical across two runs and across processes; save→load→continue at an arbitrary year is bit-identical to never-stopping.
- [ ] Experiment axes verified: "same seed, different canonicity" and "different seed, same start" both behave as specified; canonicity=0 and canonicity=1 produce visibly different but each-reproducible histories.
- [ ] Save-versioning scaffold: provenance header on every save + an ordered migration chain; a `schema_version`-bumped older save loads via migration.
- [ ] Briefcase packaging produces a launchable macOS `.app`; the app runs fully offline with no network/account.
- [ ] A smoke test drives a full run in the packaged app (or a headless equivalent) and confirms the annals, map, playback, and save/load all function together.
