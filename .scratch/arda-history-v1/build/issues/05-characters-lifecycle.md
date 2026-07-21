# 05 — Characters & lifecycle (phase 1)

**What to build:** Named people who live and die over the years. The TA 2965 canon character roster is seeded accurately; phase 1 ages everyone, rolls natural/disease deaths, and produces births; races age differently (mortal Men/Hobbits, long-lived Dúnedain/Dwarves, immortal Elves/Maiar), and Elves slowly weary and depart over the Sea. Births and deaths appear in the annals and a character's full timeline is inspectable.

> **Update (ADR-0003):** phase 1 runs every **monthly** tick. The death/fertility tables stay authored as *annual* basis points, but each roll uses the `BP_SCALE * TICKS_PER_YEAR` denominator so twelve monthly rolls reproduce the same annual behaviour (integer math intact). Elf-weariness threshold scales with `TICKS_PER_YEAR`, keeping departures on a centuries timescale.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] `Character` record: `race`, `birth_year`, `sex`, `location_id`, `faction_id?`, `role`, trait vector (`leadership, martial, ambition, loyalty`, optional `wisdom/guile`), kinship id-fields (`parent_ids`, `spouse_id`), and a derived `prominence`.
- [ ] A `race` config table (`mortality_kind ∈ mortal|long_lived|immortal`, `maturity_age`, `fertility_window`, `base_death_curve`).
- [ ] Phase 1 ages everyone, rolls natural/disease deaths (integer/fixed-point comparisons) and births on established couples, all off the seeded RNG; violent death is deferred to war (ticket 11).
- [ ] Immortals skip the natural-death roll; Elves accrue a weariness drive and can **depart** (status `departed`).
- [ ] The canon TA 2965 roster is seeded from research (correct rulers/ages/locations); the not-yet-born list stays absent at seed.
- [ ] `birth`, `death`, `departed` events emitted with the right subjects; characters are inspectable (fields + by-subject timeline), including tombstoned ones.
- [ ] Tests: deterministic births/deaths under a fixed seed; immortals never die naturally; the seed roster matches canon and excludes not-yet-born characters.
