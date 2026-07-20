# Faction & territory system

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

How are the powers of Middle-earth and their control of the map modeled?

Decide:

- **What a faction is** — realm vs. culture vs. people; the roster for TA 2965 (Gondor, Rohan, Arnor's Dúnedain, the Shire, Rivendell, Lórien, Mirkwood, Erebor/Dale, Isengard, Mordor, Dunland, etc.).
- **Territory** — how factions hold and contest space on the chosen substrate (ticket 01): ownership of hexes/regions, borders, contested zones, how territory changes hands.
- **Faction attributes & AI** — what drives a faction's behavior over a tick (military strength, resources/economy, aggression, goals). How much "AI" vs. simple weighted rules.
- **Off-map providers** — Harad, Rhûn, Khand modeled as **abstract allies/providers only**: they can side with a power (chiefly Sauron), contribute troops/resources/effects, but are never fully simulated (no internal territory/dynasties). Define exactly what interface they expose to war (ticket 07) and diplomacy (ticket 08).

Consult `/domain-modeling`. Blocks war, diplomacy/construction, and Sauron's rise.

## Answer

A faction is one **id-keyed record with a `kind` tag** (`realm | culture | provider`); territory is **atomic region ownership** that flips by conquest of a region's controlling seat; faction behaviour is **weighted-utility rules** (no learning AI) in tick phase 2; off-map providers are **abstract gateway nodes that spawn real allied hosts**.

### 1. What a faction is

One `Faction` dataclass, behaviour switched by `kind`:
- **realm** — owns regions, musters hosts, has a capital + succession-bearing leader (Gondor, Rohan, Mordor…).
- **culture** — holds territory and identity but has weak/absent central military and procedural leadership (Shire, Bree-land, Dunland). Conquerable (Saruman *does* seize the Shire) but rarely projects force.
- **provider** — the abstract off-map node (§5); no interior, never a conquest target.

One record type keeps `owner_faction_id` a single foreign key everywhere and lets territory/war/diplomacy treat all holders uniformly. No separate Realm/Culture classes.

### 2. The TA 2965 roster *(fork resolved — canon-distinct package)*

Every leader → a seeded 05 character id; every capital → a seeded 01 location id.

| Faction | kind | Leader (2965) | Capital |
|---|---|---|---|
| Gondor | realm | Steward Ecthelion II | Minas Tirith |
| Rohan | realm | King Thengel | Edoras |
| Dúnedain of the North (Rangers) | realm | Chieftain Aragorn II | — (landless; see below) |
| Isengard | realm | Saruman | Orthanc |
| Mordor | realm | Sauron (Witch-king at Minas Morgul) | Barad-dûr |
| Dol Guldur | realm | (Nazgûl) | Dol Guldur — **distinct Mordor-allied realm** |
| Durin's Folk (Erebor **+** Iron Hills) | realm | King Dáin II Ironfoot | Erebor — **one faction** |
| Dale | realm | King Bard I | Dale |
| Rivendell | realm | Elrond | Imladris |
| Lothlórien | realm | Galadriel & Celeborn | Caras Galadhon |
| Woodland Realm (N. Mirkwood) | realm | Thranduil | Thranduil's Halls |
| Grey Havens (Mithlond) | culture | Círdan | Mithlond |
| The Shire | culture | Thain Ferumbras III (proc. Mayor) | Michel Delving |
| Bree-land | culture | — | Bree |
| Dunland | culture | (procedural chief) | — |
| Haradrim · Easterlings of Rhûn · Variags of Khand · Corsairs of Umbar | provider | — | gateway locations |

Roster edge cases (as chosen):
- **Rangers / Dúnedain of the North** are a **landless realm** holding a thin **"unclaimed North" nominal claim** (empty North Downs / Eriador wilds) — so the Arnor-restoration arc is emergently reachable. Their host wanders like an army; they own no populated region at seed.
- **Durin's Folk = one faction** spanning Erebor + Iron Hills.
- **Dol Guldur = a distinct Mordor-allied realm**, so the southern-Mirkwood front vs Lórien/Thranduil is its own theatre.
- **Elf realms kept separate** (Rivendell, Lórien, Woodland Realm, Grey Havens), each with a **`withdrawing` posture** flag (per 05's fading model) rather than a distinct kind.
- **Wilderness** = `owner_faction_id = None` (no sentinel faction), so region count isn't inflated by fake owners.

### 3. Territory — atomic region ownership, seat-based conquest *(binary, fork resolved)*

- **Region ownership is binary/atomic** (`owner_faction_id`, the only mutable region state). No fractional influence in v1 (that's fog).
- **"Contested" is derived, not stored:** a region is contested when an enemy host occupies a location inside it or sits on a border route segment. **Borders** = region-adjacency edges whose two regions differ in owner — computed, never stored.
- **Ownership flips by discrete conquest in phase 5 (war):** each region names a **`seat_location_id`** (its controlling settlement/fortress); holding the seat with no contesting defender flips `owner_faction_id` and emits a `conquest`/`razing` event. → **New Region config field `seat_location_id`** for the 01 dataset (noted as content-authoring fog).

### 4. Faction attributes & AI — weighted-utility rules, no learning AI

- Per-faction state: `military_strength` (derived/cached from hosts + settlements), `treasury/economy` (08), `aggression` & `posture` scalars (seeded, canon-flavoured: Mordor high, Elves withdrawing), a `disposition` map (relation scalar per other faction, shared with 08), and a small ordered `goals` list. A **derived `prominence`** (from territory + kind + leader stature) is also exposed here — the faction-side input to 11's salience scoring (the character side is 05's).
- **Phase 2** scores a fixed menu of candidate intents (muster / attack region X / fortify / seek-pact / build) via a weighted utility function + **seeded-RNG jitter**, picks top intent(s), and writes them as intents consumed by later phases. Pure `system(world, rng) -> events`, deterministic under seed.
- The **canonicity parameter** enters here as a **global scalar weight** nudging scores toward canon moves (per-faction canon "gravity" stays fog). This is where "emergent with canonical pressures" becomes concrete on the faction side (coordinated with ticket 10).
- No goal-planner / lookahead AI and no scripted canon timeline — canonicity is a weight, not a script.

### 5. Provider interface *(fork resolved — distinct allied hosts)*

Provider record (fills 02's stub): `id`, `kind=provider`, `name`, `gateway_location_id` (Poros/Harad Road, E. Rhovanion, SE Nurn, Umbar-sea), `allegiance_faction_id?` (whom it backs — chiefly Mordor; `None` = uncommitted), `commitment` 0–1 (rises with Sauron's strength / canon pressure), and a config `output` profile (Haradrim → heavy infantry + mûmakil; Rhûn → infantry/cavalry; Khand → auxiliaries; Umbar → naval/coastal-raid).

- **To diplomacy (08):** a provider is a valid **pact target** — 08 can raise/lower `allegiance_faction_id`/`commitment` via a provider-pact intent (Sauron the default suitor under canon-weighting). Exposes `is_available_to(faction)`.
- **To war (07):** when its patron musters, the provider **spawns a real `Army` at its gateway location**, **provider-flagged** (distinct allied host, `faction_id` = patron), sized by `commitment × output`, that then moves/fights on the ordinary route layer — **can be intercepted, routed, or defect** ("the Haradrim were broken at the Poros"). Corsairs emit **coastal raids** on Gondor's coast regions (Belfalas/Anfalas) via the sea gateway rather than an overland march.
- **Never** exposes: owned regions, internal characters/dynasties, economy, succession. Never appears on the ownership map.

Because provider output is a standard `Army` on the locked location/route layer, ticket 07 needs zero special-casing after spawn.

### 6. Faction lifecycle — birth, conquest, extinction

- A faction reduced to its last region + seat is **tombstoned** (`active=False`), history intact; its **dormant claim persists** (ties to 05's failed-line handling).
- **New factions** in v1 arise only via a small set of **canon-weighted restoration arcs** (chiefly Arnor / a Reunited Kingdom), spawned as normal `Faction` records with fresh ids. Full procedural genesis (rebellions, breakaway succession splits) is **fog**.

### Seams & fog surfaced

- **06→07 (war):** conquest = "hold the seat"; provider spawns a host at gateway. 07 owns battle/siege resolution and casualty/size math.
- **06↔08 (diplomacy):** 06 fixes the provider *pact surface* and the shared `disposition` map; 08 owns disposition mechanics, treaty types, and who initiates.
- **06↔10 (canon pressure):** the global canonicity scalar weighting phase-2 utilities is defined jointly with ticket 10.
- **New content-authoring fog:** Region `seat_location_id`; per-faction seed values for aggression/posture/disposition; provider `output` unit profiles (the *interface* is decided; the *numbers* are authoring data).
- **Deferred fog:** fractional/contested-influence territory; procedural faction genesis beyond the canon restoration arc.
