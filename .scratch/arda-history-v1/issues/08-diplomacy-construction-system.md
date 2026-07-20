# Diplomacy & construction system

Type: grilling
Status: resolved
Blocked by: 06

## Question

How do factions relate peacefully, and how does the built world change outside of war?

Decide:

- **Diplomacy** — relationship state between factions (alliance, hostility, neutrality, vassalage), how it changes over ticks, and the events that move it (marriages from ticket 05, treaties, betrayals, provider-pacts with off-map peoples siding with Sauron).
- **Construction** — settlements/castles/roads founded and grown in peacetime; population/economy growth; what drives a faction to build and where.
- **Interaction with war** — how diplomacy triggers or ends wars (ticket 07), and how construction interacts with siege/razing.

Consult `/domain-modeling`. Note the overlap with ticket 07 on construction/destruction — this ticket owns *peacetime* construction and *all* diplomacy; resolve the seam between them here.

## Answer

Diplomacy is a **continuous per-faction `disposition` scalar (asymmetric) + a derived discrete stance** run in **phase 3**; construction is **build intents priced against a lean single treasury scalar** in **phase 6**. Wars **formally start and end in phase 3** (07 only executes); vassalage is an explicit directional bond that also models provider-pacts. 08 owns all diplomacy and peacetime construction; 07 owns wartime destruction.

### 1. Diplomacy relationship model *(both scalar + derived stance; asymmetric)*

- **Authoritative state:** the shared per-faction `disposition` map (06), a directional scalar (e.g. −100..+100) — **asymmetric** (Gondor→Dunland may differ from Dunland→Gondor), stored as a **sparse dict** keyed by faction id (absent = seeded baseline), matching 05's sparse-edge philosophy and avoiding an O(n²) matrix.
- **Derived stance:** a thin band over the scalar — `alliance | neutrality | hostility | vassalage` — plus a few **explicit pinned flags** (a signed treaty, an at-war boolean, a vassalage bond) that override drift. Gives 07 a clean boolean handshake without a second authoritative store.
- **Evolution (phase 3):** each tick the scalar decays toward a seeded baseline and takes event-driven jumps from marriages (05), treaties, betrayals, shared/opposed wars, and border friction; a ruler-to-ruler `oath`/`rivalry` sentiment edge (05) feeds in as one term. Then stance is recomputed. All arithmetic + bounded `rng` jitter, integer/fixed-point where a comparison fires an outcome (float-determinism).

### 2. Economy & construction *(fork resolved — lean single treasury scalar)*

- **One `economy`/`treasury` scalar per faction** (stubbed in 06). **Yearly income** = sum over owned regions of a config `base_yield` (terrain/settlement-weighted). No per-settlement resource ledger, no commodities, no trade flows in v1.
- **Population is a derived aggregate only** (per 05): at most a per-settlement `size`/`tier` integer that grows slowly when the region is at peace and the faction has surplus, feeding `military_strength` — not a simulation subsystem.
- **Construction (phase 6):** 06's phase-2 AI emits a `build` intent; 08 defines its **cost and effect** — spend treasury to (a) **found** a settlement/fortress at an eligible un-settled location in an owned region (fortresses favoured on border/pass locations), (b) **grow** an existing settlement's tier, or (c) **open a road route** between two owned settlements. Founding = flip a Location to a settlement type + attach `settlement_id` (no new entity, per 01); emits `founding`. Canonicity weight biases toward canonical builds. Scarcity from the treasury is what makes **razing meaningful** (rebuilding costs).
- (A no-economy model was rejected — free building carpets the map and guts razing; a multi-resource economy was deferred to fog as over-scoped for a watch-only yearly sim.)

### 3. Interaction with war — the 07↔08 handshake *(wars start/end in phase 3)*

- **Declaration:** phase-2 emits a war intent; **phase 3 flips the pair's stance to at-war** (the pinned boolean) and emits the declaration event. **Phase 5 (07) only acts on pairs already marked at-war** — it fights, it does not decide to start a war.
- **Termination:** 07 produces the military facts (a faction crushed, a seat taken, a host routed); those move `disposition`, and the **next tick's phase 3 emits the peace `treaty` and clears the at-war flag** — white-peace, tribute, or vassalage (§4). So wars *start and formally end in diplomacy (phase 3)* and are *fought in war (phase 5)*, preserving the locked phase order (3 → 5 → 6).
- **Construction seam (ownership-flag-gated):** 08's phase-6 construction **skips contested regions** (06: a region with an enemy host in it). 08 builds where there is peace; 07 destroys/captures where there is war; re-founding a razed `ruin` in peacetime is 08's.

### 4. Vassalage & provider-pacts *(fork resolved — vassalage bond)*

- **Vassalage = an explicit directional bond** (an `overlord_faction_id?` on Faction) that pins stance to `vassalage` regardless of scalar drift. A vassal **musters for its overlord** (07 reads it), does not war the overlord's allies, keeps its own succession and dormant claim (05/06), and **can break free**.
- **Reunited Kingdom / Arnor-restoration arc** binds via this bond — a restored Arnor and Gondor, or the northern Dúnedain accepting a high king, formalized as a vassalage bond in phase 3 under 06's canon-weighted restoration arc. **No faction merge** — both realms survive, the sub-realm keeps its identity and can rebel. (Faction-merge was rejected as harder to reverse and identity-destroying; "bond then optional merge" was rejected as extra machinery for v1.)
- **Provider-pacts are vassalage-lite:** a provider siding with Sauron is subordination without territory — expressed through 06's existing `allegiance_faction_id`/`commitment` surface; 08 raises/lowers `commitment` via the provider-pact intent under canon weighting (Sauron the default suitor). One mental model for "peoples subordinate to a power."

### 5. Marriage as diplomacy (05↔08 seam)

08 **decides whether a marriage happens** (phase 3): a dynastic-alliance utility read off `disposition` + the presence of eligible unwed heirs on both sides, weighted by canonicity. 05 **defines what the marriage does** (creates kinship edges, enables succession). 08 never touches kinship structure; 05 never initiates.

### Seams & fog surfaced

- **08↔07:** at-war boolean owned by 08's stance; wars execute in 07. Settled above.
- **War-as-entity (deferred, joint with 07):** a first-class conflict record (belligerents, war-goal, start/end) vs. the per-pair at-war flag used here — left as fog for v1.
- **Reunited-Kingdom = bond, not merge** (settled) — so 05/06 need no united-crown merge machinery in v1.
- **Content-authoring fog (data):** per-region `base_yield`; settlement tiers/costs; the **treaty taxonomy** (non-aggression, alliance, peace/white-peace, tribute, vassalage, provider-pact) with each type's disposition effect + event payload; disposition baselines/decay rates; marriage-eligibility params.
- **Float-determinism:** disposition decay, income accrual, and every threshold that fires a treaty/war must be integer/fixed-point (per 12).
- **Deferred fog:** tribute economics and procedural rebellion mechanics beyond "a vassal can break free."
