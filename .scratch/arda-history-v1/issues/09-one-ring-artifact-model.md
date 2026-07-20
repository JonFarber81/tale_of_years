# The One Ring artifact model

Type: grilling
Status: resolved
Blocked by: 02, 05

## Question

How is the One Ring modeled as a real, tracked object on the map — the gravitational center of the game?

Decide:

- **The Ring as an entity** — its location on the map at all times, and who (if anyone) bears it. Starts with Bilbo in the Shire at TA 2965.
- **Movement & possession** — how it changes hands: inheritance, theft, loss, being found, capture in war, deliberate carrying (a Fellowship-like errand). How it moves across the substrate.
- **Effect on the bearer** — corruption/temptation over time, life-prolonging, invisibility/being hunted; how it modifies a character's behavior and draws danger.
- **Sauron's pull** — how the Ring's presence/movement feeds Sauron's awareness and search (coordinate with ticket 10), and what happens if it nears Mordor or is destroyed (Mount Doom) or claimed by Sauron.
- **Terminal outcomes** — destruction, Sauron reclaiming it, or it lying lost — and how each reshapes the world (ties into the aftermath fog).

Is v1 a single unique artifact with bespoke rules (recommended), or the first instance of a general artifact system (the rest of which is fog)? Consult `/domain-modeling`.

## Answer

The Ring is a **single bespoke `Artifact` record** honouring the `bearer_id` XOR `location_id` invariant, a **passenger** that moves only with its bearer, tracked by **two scalars — `corruption` (per-bearer, attenuating) and `pull` (global, Sauron-facing)**. Possession changes via a fixed set of **canon-weighted transfer events**; **09 owns and computes `pull`, ticket 10 consumes it**; three terminal states feed the aftermath fog. At TA 2965 it is quiescent with Bilbo, both scalars low.

### 0. Bespoke, not a general system *(pre-locked in 02)*

One hand-coded Ring record with bespoke rules and its two tick hooks — no artifact registry, no polymorphism. The Elven Rings, palantíri, etc. stay in the magic/metaphysics fog.

### 1. The Ring as an entity

- One `Artifact` record with **`bearer_id` XOR `location_id`** (exactly one non-null, always). **Seed:** `bearer_id = Bilbo`, `location_id = None`. When dropped/lost/hidden, flip to `bearer_id = None`, `location_id =` where it lies.
- **Rendering (01/11):** when borne, the Ring's displayed position is derived from the bearer's position/route-progress; when unborne it renders at its own `location_id`. It never free-roams — always at a node or carried.

### 2. Movement & possession *(fork resolved — passive passenger + probability modifier)*

- **Movement:** while borne, the Ring advances node→node using its **bearer's** miles/year budget on the 01 route layer — no independent movement budget. Emits `ring_moved` when its location node changes. While unborne it does not move.
- **The Ring's "will" is a modifier, not locomotion:** high `pull` **raises the probability of loss/theft/betrayal** (it "slips off" at the worst moment — Isildur at the Gladden Fields, Gollum), but the Ring never autonomously paths toward Sauron. Easy to tune, no special phase-4 mover.
- **Possession changes — one transfer-mode enum**, each a weighted (never scripted) roll off the seeded RNG, fired by the phase owning the trigger:
  - **inheritance / gift** (phase-1 seam, on bearer death/departure): walk 05 kinship, **biased toward a nephew-heir-type by the canonicity parameter** — the Bilbo→Frodo *tendency*, not "Frodo."
  - **theft / grab** — low-probability when a covetous non-bearer is co-located (amplified by the will-modifier above).
  - **loss / drop** — rare, higher under duress (death in water/battle) → Ring becomes unborne where it fell.
  - **found** — a weighted pickup roll when a character is co-located with an unborne Ring (Déagol/Bilbo).
  - **war-capture** (phase-5 seam): if the bearer is killed/routed in battle, the Ring passes to the victor's side or drops to unborne — how it can fall to Mordor.
  - **deliberate errand** — an emergent faction/character intent to carry the Ring toward a goal node (a Council bearing it to Mount Doom; Sauron's forces to Barad-dûr), weighted by canonicity — not a scripted quest.

### 3. Effect on the bearer *(two scalars; corruption attenuates on transfer)*

- **`corruption`** (per-bearer, integer): the current bearer's thrall. Grows each tick the Ring is borne, modulated by **05 traits** (high `ambition`/low `loyalty`/`wisdom` corrupt faster; hobbits notably resistant; a "great" lord corrupts fast). Threshold effects:
  - *low:* **life-prolonging** — suppress the phase-1 natural-death roll while borne (Bilbo/Gollum's unnatural longevity);
  - *mid:* behaviour bias — decisions skew toward secrecy/possessiveness, raising the resist-weight against voluntary transfer and the loss/theft-under-duress odds;
  - *high:* the bearer may **claim** it (§5) or become wraith-drawn. **Using/wearing** it (an occasional event under threat) **spikes `pull`**.
  - **On transfer, corruption attenuates toward zero, not resets** — ex-bearers stay marked (Bilbo's longing, Gollum's centuries).
- **`pull`** (global on the Ring, integer): how loud the Ring is *now* — the Sauron-facing scalar, kept separate from corruption so a hobbit can bear it quietly (corrupting but quiet) while *using* it is loud regardless. (A single combined scalar was rejected for exactly this reason.)

### 4. Sauron's pull & the 09↔10 seam *(09 owns/computes `pull`; 10 consumes)*

- **09 owns:** the Ring record, its fields, and the **rules that raise/lower `pull`** — rises with the Ring being used/worn, corruption of a "great" bearer, proximity to Mordor/Barad-dûr on the region/route layer, and Mount Doom being active (~3007+); decays when it lies lost/quiet with a resistant bearer. Written into world state in **phase 7**; emits `ring_moved` and a pull-changed event.
- **10 owns:** Sauron's strength growth, the decision to **launch a search**, spawning/directing **Nazgûl searchers** (special movers with a search budget on the 01 layer), and resolving a found Ring into a war-capture attempt. **10 reads `pull` + Ring location as inputs; it never mutates the Ring record** (single-writer discipline for determinism).
- **At seed** `pull ≈ 0` (Bilbo, unused, deep in the Shire, Doom cold) → 10 does no hunting yet, matching "Nazgûl not yet hunting."
- **Graduates to ticket 10:** the searcher entity, the search→capture mechanic, and Sauron's strength curve. 09 supplies only the `pull` interface + Ring-location query.

### 5. Terminal outcomes *(three states; non-Sauron claim is transient)*

Each is a distinct world-transition event that flips a world-level flag the **aftermath fog** keys off; 09 emits the transition, not the centuries after.
1. **Destroyed (Mount Doom):** possible only once Orodruin is **active** (~3007+) and the Ring is borne to / dropped into it. Ring **tombstoned** (`active=False`, neither bearer nor location — the one sanctioned exit from the XOR invariant); Sauron/Mordor catastrophically broken (hand to 06/10). **Mechanically impossible near 2965** since Doom is cold — matches canon.
2. **Sauron reclaims it:** Ring reaches Sauron/Barad-dûr (war-capture or a corrupted bearer carrying it home); Sauron's strength → max; canon pressure inverts toward a dark-victory world.
3. **Lying lost / dormant:** unborne at a location with no finder — a low-`pull` holding pattern (Gladden-Fields limbo), not a hard terminal; ends if someone finds it.
- **A non-Sauron claimant** (a tempted Saruman/Denethor/Galadriel) is a **transient**, not a fourth terminal: claiming spikes `corruption`/`pull` and warps that character's behaviour, but only resolves via reaching Sauron or Mount Doom. (A fourth "new Dark Lord" terminal was considered and declined for v1 scope; the transient captures the canon "corrupted but not victorious" beat.)

### Seams & fog surfaced

- **09→10 (graduates):** searcher entity (Nazgûl with a search budget), search→capture mechanic, Sauron's strength curve — 09 hands 10 the `pull` interface + Ring-location query. This is the material that unblocks ticket 10.
- **05↔09 (confirmed):** inheritance bias reads 05 kinship × canonicity; corruption reads the 05 trait vector — no new 05 fields required.
- **Content-authoring fog (numbers):** per-race/per-trait corruption-susceptibility coefficients; pull rise/decay rates; proximity-to-Mordor pull weighting; errand-formation weighting.
- **Aftermath fog (existing):** all three terminals feed it; 09 emits only the transition flag.
- **Float-determinism:** `corruption`/`pull` and every transfer-probability comparison must be integer/fixed-point (per 12).
