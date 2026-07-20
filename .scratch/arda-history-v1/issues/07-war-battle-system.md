# War & battle system

Type: grilling
Status: resolved
Blocked by: 05, 06

## Question

How do armed conflicts arise, play out, and change the world?

Decide:

- **Armies** — how forces are raised, sized, moved across the substrate, and supplied; who leads them (characters from ticket 05).
- **Campaigns & battles** — how a battle is triggered, resolved (deterministic + seeded RNG), and what outcomes it produces: casualties (including named-character death), territory shifts, sieges of settlements.
- **Construction & destruction in war** — castles/strongholds/settlements founded, besieged, **razed** (the "castles built, razed" the user wants); coordinate with ticket 08.
- **Off-map providers in war** — how Harad/Rhûn/Khand contributions (troops, oliphaunts, corsairs) enter a battle without being fully simulated (see ticket 06's provider interface).
- **Scale** — battles at yearly tick granularity: abstract to a resolution model, not tactical.

Consult `/domain-modeling`. Feeds the chronicle and Sauron's rise.

## Answer

War runs in **tick phase 5** on the existing `Army` records: hosts are mustered (phase 2) from a region-derived manpower pool, move as passengers on the location/route layer (phase 4), and fight via a **strength-ratio + bounded seeded-RNG** model. Conquest = holding a region's `seat_location_id`; sieges persist across ticks; named death is a **post-battle scaled roll**; providers fight as ordinary hosts with unit modifiers. **07 is destruction-and-capture only** — peacetime founding/rebuilding is 08's.

### 1. Armies — raising, sizing, moving, supply

- A host is the `Army` record (02): `faction_id`, `leader_id`, `position`, `size` (integer). **Raising** is a phase-2 muster intent (06) that instantiates an Army at the faction's capital/seat, sized from a **manpower pool derived from owned regions + settlements** (a fraction of `military_strength`).
- **Leader** = the highest `martial`+`leadership` eligible character (05), assigned `role=general`; leaderless hosts are allowed but penalized.
- **Supply = lightweight attrition**, not a logistics sim: a per-tick `size` decay applied during phase-4 movement, scaled by route `kind`/terrain and distance from friendly seats (a host deep in hostile/barren land bleeds). Integer decay, so it stays float-safe. A full provisioning economy is out of scope (fog).

### 2. Battle trigger & resolution *(fork resolved — strength-ratio + bounded RNG, in-tick)*

- **Trigger (phase 5):** after phase-4 movement, a battle fires when two enemy hosts share a **location** or opposite ends of a **border route segment**, or a host sits on an enemy-owned settlement location (→ siege, §3). Resolution order is deterministic (by location id) so simultaneous battles never race.
- **Resolution:** each side's **effective strength** = `size × leader_factor(martial,leadership) × terrain/posture modifiers × provider-unit bonuses`. **One bounded seeded-RNG roll** perturbs the ratio within an integer/fixed-point band → outcome tier (decisive / marginal / stalemate); **casualties on both sides derive from the ratio** (loser loses more; integer floor). Winner holds the field; loser retreats to the nearest friendly location, or is destroyed if casualties exceed a threshold. Emits a `battle` event with structured payload (participants, casualties, victor).
- **Battles resolve within the tick**; multi-year grind is expressed through **sieges** (§3) and repeated yearly engagements, not multi-tick field battles. (Lanchester/quadratic attrition was rejected for float-divergence risk and multi-tick bookkeeping; a no-dice threshold was rejected for killing upsets.)
- **Canonicity does *not* touch battle dice *(fork resolved)*:** canon pressure only weights **phase-2 intents** (who musters, who attacks). Battles are honest — outcomes follow strength + RNG alone. Canon shapes *who fights*, not *who wins*. (07↔10 seam.)

### 3. Sieges & razing *(sieges persist across ticks)*

- A **siege** begins when an enemy host holds a location with a defended settlement/seat it can't take outright. Modeled as a **multi-tick state** (`besieging` flag + accumulating siege progress); the settlement adds a **fortification defense bonus** to the ratio math. Each tick the besieger rolls; the seat falls when the defender is broken or progress completes.
- On fall, the attacker **holds the seat** → 06's rule flips `owner_faction_id` (emit `conquest`). **Razing is a discrete post-capture choice** driven by attacker posture/aggression (06) + canon flavour (Orcs raze; restorers hold): raze → settlement destroyed (`razing` event, location becomes `ruin` type); else captured intact (enabling Saruman-seizes-the-Shire and Arnor-restoration arcs).

### 4. Named-general death *(fork resolved — post-battle scaled roll)*

- After a battle/siege resolves, roll a **rare seeded death check per named character present**, probability scaled by outcome tier (much higher on the losing/routed side) and lowered by the character's `martial`. A leader can fall even in a battle their side wins (Théoden-style). On death: tombstone (05 `alive=False`), emit a `death` event flagged `killed_in_battle`, and **trigger 05's succession walk** if they held `faction.leader_id`. This is the "violent death happens in phase 5" contract from 02/05.

### 5. Off-map providers in war

- Per 06, a committed provider **spawns a real provider-flagged `Army` at its gateway** (`commitment × output`), moving/fighting as any host — **interceptable, routable, can defect** ("broken at the Poros"). The only 07-side addition is reading the provider's `output` profile as **unit-type combat modifiers**: mûmakil = shock bonus (+ a rout-vulnerability term), Easterling cavalry = open-terrain mobility bonus, Variags = flat auxiliary bonus.
- **Corsairs are the exception:** they don't march overland — they emit **coastal raids**, a lightweight strike against a coast region's settlement (Belfalas/Anfalas) that damages/pillages but **does not seize the seat** (providers hold no territory). This naval/coastal-raid path lives in 07 (not a separate naval ticket in v1).

### 6. The 07↔08 construction seam *(fork resolved — 07 destructive-only)*

- **07 owns only combat-caused change:** siege → capture → optional raze (phase 5). It **does not found peacetime settlements** and does not build garrisons/field-forts in v1 — a conqueror simply holds the captured seat.
- **08 owns all founding, growth, rebuilding** (phase 6), including whether/when a razed `ruin` is later rebuilt. Rule of thumb: **"08 builds where there is peace; 07 destroys/captures where there is war."** Both mutate the same Location/settlement state and emit `founding`/`razing` events; neither crosses into the other's phase.

### Seams & fog surfaced

- **07↔10:** canon pressure stays in phase-2 intents, never battle dice (settled above).
- **07↔08:** destructive-only seam settled above; razed ruin → 08's rebuild eligibility next tick.
- **Float-determinism constraint:** battle roll, casualty math, attrition, and siege progress must be integer/fixed-point at every outcome-deciding comparison (per 12).
- **Content-authoring fog (data, not decisions):** provider `output` → combat-modifier tables; per-race/unit battle modifiers; settlement fortification values; casualty/attrition curves; siege-progress rates.
- **War-as-entity (deferred):** whether a conflict is a first-class record (belligerents, war-goal, start/end year) vs. the per-pair at-war flag 08 uses — flagged jointly with 08; left as fog for v1.
