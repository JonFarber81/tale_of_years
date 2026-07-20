# Core entity & tick model

Type: grilling
Status: resolved

## Question

What is the fundamental object model and simulation loop the whole game is built on?

Decide:

- **Entities** — the core kinds that exist (character, faction/realm, settlement, army, artifact, event, place) and the minimal fields each needs at the core level. System-specific detail (battle rules, Ring rules) belongs to their own tickets — this ticket sets the shared spine.
- **The tick** — what happens, in what order, when a year advances. How systems (aging/birth/death, faction AI, war, diplomacy, construction, Ring, Sauron) are sequenced within one yearly tick.
- **Event model** — how a thing that happens becomes a recorded, dated, queryable event (the raw material of the chronicle and the UI feed).
- **Identity & references** — how entities reference each other stably over time (needed for save/load, seeding, and the UI).

This is foundational: it blocks the character, faction, Ring, chronicle, and persistence tickets. Consult `/domain-modeling` and `/codebase-design`.

## Answer

The spine is a single **`World` of id-keyed typed records**, advanced by a **fixed ordered system pipeline** once per year, with each system mutating authoritative state and appending to an **immutable event log**. Cross-references are ids, never object pointers — the property that makes seeded save/load (ticket 12) tractable.

### 1. Entities — the shared spine

Every simulated thing is a plain **dataclass record** living in a typed collection on `World`, keyed by a stable integer id. Core kinds and their **minimal core fields** (system-specific fields are added by their own tickets and are noted as *(→ NN)*):

- **Entity base (shared by all):** `id`, `kind`, `name`, `created_year`, and a **`status`** field — `active` plus a small tombstone enum recording *how* it left play: `dead` (natural/violent), `departed` (Elves sailing West → 05), `destroyed` (the Ring at Mount Doom → 09; the Nazgûl unmade with it → 10). Tombstoned entities are **never deleted**, so references stay resolvable. (Coherence note: this replaces the earlier bare `alive` boolean, which 05/09/10 overloaded.)
- **Character** *(→ 05)*: `race`, `birth_year`, `sex`, `location_id`, `faction_id`, `role`. Traits, kinship, succession → 05.
- **Faction / realm** *(→ 06)*: `kind` (realm | culture | provider), `leader_id`, `capital_location_id`. Owned regions, disposition, goals, AI → 06.
- **Region** *(config, → 01/06)*: `terrain`, `polygon` (v7 pixel coords), `adjacency` (region ids), `owner_faction_id`. Geometry is fixed config; only `owner_faction_id` is mutable state.
- **Location** *(config point, → 01)*: `point` (pixel coords), `region_id`, `type` (city | fortress | ford | pass | gate | ruin), `owner_faction_id`, `settlement_id?`.
- **Route** *(config edge, → 01)*: `endpoints` (location ids), `polyline`, `kind` (road | river | pass | open | forest), cached `length_miles`.
- **Army / host** *(→ 07)*: `faction_id`, `leader_id`, `position` (a location id, or a `(route_id, progress)` pair), `size`. Composition, supply → 07.
- **Artifact — the One Ring** *(→ 09)*: `bearer_id?` **xor** `location_id?` (always exactly one), plus `corruption`/`pull` fields owned by 09. Modeled as a single bespoke artifact, not a general system (that stays fog).
- **Provider (abstract off-map)** *(→ 06)*: `allegiance_faction_id?`, `gateway_location_id`, `output` (troops/resources). No interior — honours the abstract-provider Note.
- **Event** *(see §3)*: the dated record of a happening.

`World` also holds run-level fields: `current_year` (starts **TA 2965**), the seeded `rng` state, the `id_counter`, `config` (canonicity parameter + scenario), and the append-only `events` log.

### 2. The tick — fixed ordered system pipeline

A tick advances **one year**. The tick is an explicit, fixed list of **systems**, each a callable `system(world, rng)` that mutates state and appends events. Deterministic order + a single seeded RNG threaded through every system (never wall-clock or `hash()`) is what makes a run reproducible from (seed + config) — the persistence contract of ticket 12.

Order within one year:

1. **Aging / births / deaths** — advance ages; resolve births, natural & disease deaths *(→ 05)*.
2. **Faction decisions** — factions set goals, muster hosts, choose war/diplomacy/build intents *(→ 06)*.
3. **Diplomacy** — relationship shifts, treaties, marriages, betrayals, provider-pacts *(→ 08)*.
4. **Movement** — armies and the Ring advance node→node along routes by their miles/year budget *(→ 01/07/09)*.
5. **War** — battles & sieges where forces meet; casualties (incl. named-character death), territory shifts, razing *(→ 07)*.
6. **Construction / economy** — settlements founded/grown/razed, population & economy *(→ 08)*.
7. **Sauron rise + canonical pressure** — Sauron's strength grows; the canonicity parameter nudges emergent dynamics toward canon *(→ 09/10)*.
8. **Salience + bookkeeping** — score event importance for the annal *(→ 11)*; increment `current_year`; autosave check *(→ 12)*.

The phase list is the one authoritative sequencing point; individual systems stay decoupled behind the `(world, rng) -> events` contract, so a later ticket can deepen a system without touching the others.

### 3. Event model — state-authoritative, append-only log

World state is the **source of truth**; systems mutate it directly and then **emit an immutable `Event`** describing what happened. Events never drive state (not event-sourced) — they are the queryable **annal** and the raw material for the chronicle UI (ticket 11).

`Event` fields: `id`, `year`, `type` (enum: birth, death, battle, siege, razing, founding, treaty, marriage, succession, ring_moved, sauron_grows, …), `subject_ids` (primary + participants), `location_id?`, `importance` (salience score assigned at emission → 11), `payload` (structured, type-specific), `text?` (optional rendered prose → 11). Events are indexed for query **by subject, by faction, by year, by type**.

Save = **state snapshot + event log** (ticket 12). Because state is authoritative, load is a direct rehydrate, not a replay.

### 4. Identity & references — stable integer ids

- A single **monotonic integer id space** for everything addressable (characters, factions, regions, locations, routes, armies, the Ring, events), allocated from `World.id_counter`. **Ids are never reused**, even after an entity dies — so an old event or a genealogy edge always resolves to the right (possibly tombstoned) record.
- **All cross-entity references are ids**, resolved by dictionary lookup on `World`. No object holds a pointer to another entity. This is what keeps state a plain serializable tree (no pointer cycles) and keeps references valid across save/reload.
- Config geometry (regions/locations/routes) is assigned ids **deterministically at scenario load** from the fixed dataset, so the same scenario always yields the same ids — a prerequisite for "same seed, same run."

### Consequences for downstream tickets

- **05 Character & dynasty** — fills Character's lifecycle/traits/kinship fields and owns tick phase 1.
- **06 Faction & territory** — fills Faction/Region ownership + provider output; owns phase 2; defines the provider interface.
- **09 One Ring** — fills the Artifact's bearer/location invariant and corruption/pull; hooks phases 4 & 7.
- **11 Chronicle/UI** — consumes the event log + salience; the `text` field and salience scoring are its to define.
- **12 Persistence** — serializes `World` (state snapshot + event log + rng state + id_counter); the id-only-refs and single-seeded-rng decisions here are its foundation.
