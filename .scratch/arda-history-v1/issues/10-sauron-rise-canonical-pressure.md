# Sauron's rise & canonical-pressure model

Type: grilling
Status: resolved
Blocked by: 06, 09

## Question

How is Sauron modeled as a rising force, and how do "canonical pressures" bend an otherwise-emergent history toward the books?

Decide:

- **Sauron as a power** — how his growing strength is represented over ticks (rebuilding Mordor, the Nazgûl, orc/troll armies, Dol Guldur/Minas Morgul), what accelerates or checks it, and his win/loss conditions.
- **His agents & goals** — the Nazgûl, allied factions, the search for the Ring (ties to ticket 09), pressure on Gondor/Rohan/the North.
- **Canonical pressures** — the mechanism that weights emergent dynamics toward canon without scripting: which forces get nudged (Sauron tends to rise, the Ring tends to stir, certain alliances tend to form) and how strongly.
- **The light canonicity parameter (v1 scope)** — a single/simple tunable (e.g. low/medium/high, or 0–1) that scales those pressures. Define what it affects in v1; deeper per-force tuning stays fog.

Consult `/domain-modeling`. This is where the emergent-with-canonical-pressures decision (map Notes) becomes concrete.

## Answer

Sauron is the **Mordor faction (06)** plus a **`sauron_strength` scalar** on a **canon-anchored baseline curve × canonicity + emergent deltas**, run in **tick phase 7**. His agents are **nine named Nazgûl** driving the Ring-search off 09's `pull`. Canon pressure is **soft weighting only** — a single global **canonicity 0–1 knob** that adds weight to canon-aligned choices in four force areas, never firing events or overriding rolls. History can still diverge; canon is just more likely.

### 1. Sauron as a power *(fork resolved — canon-anchored baseline, perturbed)*

- **Representation:** a single integer **`sauron_strength`** scalar (float-safe), computed each phase 7 as `canon_baseline(year) × canonicity + Σ emergent_deltas`.
  - **`canon_baseline(year)`** encodes the canon ramp: arming since 2951 (Barad-dûr rebuilt, Mordor repopulating), accelerating toward the War-of-the-Ring window, with **Orodruin rekindling ~3007** flipping the world flag 09 gates Ring-destruction on. Scaled by the **canonicity** knob, so at `canonicity = 0` the baseline flattens and his rise is **purely emergent**.
  - **Emergent deltas** perturb it: **gaining the Ring spikes it** (toward the reclaim-terminal), **military defeats / losing Dol Guldur or Minas Morgul slow it**, provider pacts and territory/economy gains raise it, orc/troll mustering scales with it.
- **What `sauron_strength` drives:** the size/frequency of Mordor's mustered hosts (07), provider `commitment` growth (06), Nazgûl activation (§2), and the **weighting of the `pull` rise** that 09 computes (a stronger Sauron "listens" harder).
- **Win / loss conditions** (each flips a world-level flag feeding the aftermath fog): **win** = Sauron reclaims the Ring *or* conquers the West (Free-Peoples capitals fall); **loss** = the Ring is destroyed at Orodruin (09 terminal) → Mordor catastrophically broken, then dissolved through 06's ordinary extinction machinery. Neither is reachable near seed (Ring quiescent, Doom cold).

### 2. His agents & goals — nine named Nazgûl *(fork resolved)*

- The **Nazgûl are nine special Characters** (05: **wraith-Men bound to the Nine Rings**, not Maiar — modelled with `mortality_kind = immortal` *while Sauron/the Ring endures*), **led by the Witch-king** (already seeded at Minas Morgul; three at Dol Guldur per canon). They are inspectable, named actors in the chronicle. **Canon coupling:** they are **unmade if the One Ring is destroyed** (09's Mount-Doom terminal) or Sauron falls — the Ring-destroyed terminal tombstones all nine (`destroyed`), alongside Mordor's collapse.
- **As searchers (the 09→10 graduation) — via the normal phase flow, not phase 7 directly:** because Mordor is a faction, the decision to hunt is a **phase-2 Mordor intent** (triggered when `sauron_strength` is high enough and Ring `pull` is high) and the Nazgûl's actual **movement happens in phase 4** on the route layer with a **search budget**, biased toward the Ring's `pull`/last-known location; a searcher co-located with the Ring resolves a **capture attempt in phase 5** (07's war-capture path if the Ring is guarded). **Phase 7 does not move or fight anyone** — it recomputes `sauron_strength` and the `pull`-response weighting that the *next* tick's phase-2 intents read. 10 **reads** the Ring's `pull` + location; it **never mutates the Ring record** (09 is the single writer).
- **As war leaders:** between searches the Nazgûl are elite generals for Mordor/Dol Guldur hosts (07), applying strong leader factors.
- **Allied factions & goals:** Dol Guldur (distinct Mordor-allied realm, 06) and the four **providers** are Sauron's instruments; his phase-2 goals (06) press canon-aligned pressure on **Gondor, Rohan, and the North** as strength rises.
- **At seed** (2965): `pull ≈ 0`, strength low-but-arming → **no active hunt** (matches "Nazgûl not yet hunting"); the Witch-king holds Minas Morgul, three wraiths hold Dol Guldur.

### 3. Canonical pressures — soft weighting only *(fork resolved)*

- Canon pressure is **purely a thumb on the scale**: the canonicity knob adds weight to **canon-aligned options in the existing phase-2 faction-utility scores** and to the **Ring/event transfer probabilities (09)**. It **never directly fires a canonical event** and **never overrides an outcome** (battle dice stay honest per 07). History can diverge; canon is just more likely. This honors the "weight, not script" locks across 06/07/09 — no corrective canon-events were added.
- **Where the weight lands is a fixed, legible list** — see §4's four forces — applied as small additive score bumps / probability multipliers, all integer/fixed-point.

### 4. The canonicity parameter (v1 scope) *(four forces selected)*

- **Form:** a **single global scalar in 0–1** (the map's "light canonicity parameter"), part of `World.config` and recorded separately in saves (12) so "same seed, different canonicity" is a first-class experiment. `0` = fully emergent, no canon thumb; `1` = strong canon lean. **Per-force / per-faction tuning stays fog.**
- **In v1 the one knob scales all four forces:**
  1. **Sauron's rise rate** — scales `canon_baseline(year)` (§1) and Mordor's muster/aggression weights.
  2. **The Ring's stirring** — biases 09's transfer modes (inheritance-to-heir = the Bilbo→heir tendency, errand-forming, drift toward the canonical path).
  3. **Free-Peoples alliances** — nudges Gondor/Rohan/Elves/Dwarves/the North toward coalescing against Sauron as he rises (added weight on alliance/vassalage intents in 08).
  4. **Character role-seeking** — biases key characters toward canonical arcs (a Dúnedain heir tends toward pressing the Arnor/Gondor restoration claim), reusing 05/06 succession + restoration machinery.
- All four are **weight adjustments only** on machinery the other tickets already own — 10 contributes the *baseline curve*, the *Nazgûl searcher behaviour*, and the *one knob*, not new subsystems.

### Seams & fog surfaced

- **10↔09:** 10 reads `pull` + Ring location and runs the searcher/capture side; 09 remains the sole writer of the Ring record. Settled.
- **10↔06/07/08 (phase flow):** the **canonicity knob is static config**, so it's available at phase 2 with no lag. The **dynamic** values 10 computes in phase 7 — `sauron_strength` and the `pull`-response weighting — are consumed by the **next** tick's phases 2–4 (a deliberate one-year lag, invisible at yearly granularity). Concretely: phase 7 updates strength → next tick's phase-2 Mordor musters/provider-commitment/Nazgûl-hunt intents read it → phase-4 movement / phase-5 war execute. Phase 7 itself never musters, moves, or fights.
- **Aftermath (existing fog, now narrowed):** with war/Ring/Sauron resolved, a terminal outcome **flips a world flag and the open-ended systems simply continue** (Mordor dissolves via 06 extinction, Elves fade via 05, factions expand into the vacuum) — so v1 needs **no special post-climax subsystem**. What remains fog is only long-tail *balancing/pacing* over centuries, tied to the performance-at-scale spike.
- **Content-authoring fog (data):** the `canon_baseline(year)` curve shape; the per-force canon-weight coefficients; Nazgûl search-budget/activation thresholds. Numbers, not decisions.
- **Float-determinism:** `sauron_strength`, the baseline, and all canon-weight comparisons must be integer/fixed-point (per 12).
