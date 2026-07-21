# 14 — Sauron's rise & canonicity

**What to build:** The rising Shadow and the canon-pressure that bends history toward the books. Sauron (the Mordor faction) grows in strength on a canon-shaped baseline that emergent events accelerate or check; the nine Nazgûl hunt the Ring when it stirs and lead his hosts; a single canonicity knob nudges four forces toward canon without ever scripting events or rigging battles; and the Ring's terminal fates resolve into world-reshaping outcomes.

**Blocked by:** 11, 13

**Status:** migrated — now tracked on GitHub as [#5](https://github.com/JonFarber81/tale_of_years/issues/5) (2026-07)

- [ ] `sauron_strength` recomputed each phase 7 as `canon_baseline(year) × canonicity + Σ emergent_deltas` (arming since 2951, ramp to the War-of-the-Ring window, Orodruin active ~3007; Ring-gain spikes it, defeats/Dol-Guldur-or-Minas-Morgul loss check it; canonicity=0 flattens to emergent). Strength scales Mordor musters, provider commitment, Nazgûl activation, and `pull`-rise weighting.
- [ ] The nine Nazgûl are named Characters (wraith-Men bound to the Nine, immortal while Sauron/the Ring endures; Witch-king at Minas Morgul, three at Dol Guldur); they hunt via the **normal phase flow** — a phase-2 Mordor intent when strength+`pull` are high, phase-4 movement with a search budget, phase-5 capture attempt. 10/14 read the Ring's `pull`+location; never mutate the Ring record.
- [ ] A single global `canonicity` knob (0–1) in `World.config`, saved separately, applied as **soft weighting only** to four forces: Sauron's rise, the Ring's stirring, Free-Peoples alliance formation, character role-seeking. Never fires events; never overrides dice.
- [ ] Terminal outcomes wired: **destroyed** (only once Orodruin active → Ring tombstoned `destroyed`, all nine Nazgûl unmade `destroyed`, Mordor collapses via ticket 08 extinction over subsequent ticks), **Sauron reclaims**, **lying lost**; each flips a world flag.
- [ ] Sauron/Nazgûl/terminal events carry prose + high salience weights; Sauron's strength and the Nazgûl are inspectable.
- [ ] Tests: strength follows baseline×canonicity+deltas; canonicity=0 flattens the baseline; Nazgûl hunt only when strength+pull high; Ring destruction unmakes the Nazgûl; canonicity biases intents but two identical runs differing only in canonicity diverge without ever changing a battle's dice.
