# Spec: arda_history v1 — Emergent Middle-earth History Simulator

Status: ready-for-agent

<!-- Synthesized by /to-spec from the wayfinder map at .scratch/arda-history-v1/ (map.md + issues/01–12). Each Implementation Decision cites the ticket that holds its full rationale. -->

## Problem Statement

I want to watch the history of the Third Age of Middle-earth *unfold on its own* — not replay the books, but see an alternate history grow tick by tick from an accurate starting point, on a real map, with characters being born and dying, realms rising and falling, castles built and razed, wars fought, dynasties succeeding, and the One Ring moving across the land as a tracked object with Sauron rising in the background. I want it to feel like Tolkien's world and *tend* toward canon, but be free to diverge — Frodo might never be born, Gondor might fall early, Arnor might be restored a century too soon. And I want every run to be reproducible and shareable by a seed, so a history I love can be replayed or handed to someone else.

Today no such thing exists: reading the Appendices is static, strategy games are player-driven and non-canonical, and Dwarf-Fortress-style generators aren't Middle-earth and aren't seeded to a real canon starting state.

## Solution

A watch-only desktop application (Python) that runs a deterministic, seeded simulation of NW Middle-earth starting at **TA 2965**, advancing **one month per tick** (`TICKS_PER_YEAR = 12`), open-ended, rendered on a **reference map of Middle-earth**. The viewer watches history stream past — an annals feed of dated events, coloured territory shifting between factions, armies marching, the Ring moving — and can pause, change speed, step a tick, scrub the timeline, and click any entity (character, faction, settlement, army, the Ring) to inspect its current state and full history. Dynamics are **emergent but weighted toward canon** by a single tunable **canonicity** knob (0–1): at 0 history is free; at 1 it leans hard toward the books. A human-shareable **string seed** plus the fixed scenario and canonicity setting deterministically reproduces any run.

**This spec produces the v1 design only.** It is the blueprint handed to `/to-tickets` → `/implement`; it contains no game code.

## User Stories

### Watching & playback
1. As a viewer, I want to watch history advance one month per tick automatically, so that I can see an alternate Third Age unfold without acting.
2. As a viewer, I want to pause and resume the simulation, so that I can stop on an interesting moment.
3. As a viewer, I want to change the playback speed (ticks per second), so that I can skim quiet centuries and slow down for dramatic years.
4. As a viewer, I want to step forward exactly one tick (month), so that I can examine a pivotal turn carefully.
5. As a viewer, I want to scrub/seek the timeline to any already-simulated year, so that I can jump back to when a war started.
6. As a viewer, I want scrubbing to be instant (restore a stored snapshot, not re-simulate), so that navigating history feels immediate.
7. As a viewer, I want to see the current in-world year (starting TA 2965) prominently, so that I always know when I am.
8. As a viewer, I want to seek past the simulated frontier to fast-forward the sim to a future year, so that I can advance quickly to see how things turn out.

### The map
9. As a viewer, I want a reference map of Middle-earth as the canvas, so that the world looks like the Middle-earth I know.
10. As a viewer, I want to pan and zoom the map, so that I can move between the Shire and Mordor.
11. As a viewer, I want factions' territory shown as coloured region overlays, so that I can see who holds what at a glance.
12. As a viewer, I want borders and contested zones to be visible, so that I can see frontiers and where fighting is likely.
13. As a viewer, I want settlements, fortresses, fords, passes, and ruins marked at their real map locations, so that the geography is legible.
14. As a viewer, I want armies shown moving along roads and rivers between locations, so that I can follow campaigns.
15. As a viewer, I want the One Ring's position shown on the map (with its bearer, or lying where it was lost), so that I can always find the Ring.
16. As a viewer, I want a transient on-map pulse where an important event just happened, so that my eye is drawn to what matters.

### The chronicle / annals feed
17. As a viewer, I want a live annals feed of dated events streaming as years tick, so that I can read history as prose.
18. As a viewer, I want events written in readable prose ("In TA 2984, the host of Rohan broke the siege of the Hornburg"), so that it reads like a chronicle, not a log.
19. As a viewer, I want the feed to default to important events only, so that the War of the Ring reads as a story and not noise.
20. As a viewer, I want to switch the feed to show all events with one click, so that I can see the full detail when I want it.
21. As a viewer, I want to filter the feed by faction, event type, and importance, so that I can follow one thread.
22. As a viewer, I want to follow a single subject (a character, a realm, the Ring) in the feed, so that I can track its story.
23. As a viewer, I want the feed to remain responsive across centuries of accumulated events, so that a long run stays usable.

### Inspection
24. As a viewer, I want to click any entity on the map to open an inspection panel, so that I can see its details.
25. As a viewer, I want the inspection panel to show an entity's current state fields, so that I understand its condition.
26. As a viewer, I want the panel to show that entity's full personal timeline of events, so that I can read its life or history.
27. As a viewer, I want cross-references in the panel to be clickable (a king → his realm → its battles), so that I can navigate relationships.
28. As a viewer, I want to inspect long-dead or departed entities and their descendants, so that I can trace a dynasty back through history.
29. As a viewer, I want to drill into a battle to see its participants, casualties, and victor, so that I understand what happened.
30. As a viewer, I want to inspect a dynasty/bloodline, so that I can follow a line of kings.

### Characters, dynasties, lifecycle
31. As a viewer, I want named characters to be born, age, and die over time, so that the population turns over and history feels alive.
32. As a viewer, I want the TA 2965 canon roster seeded accurately (Ecthelion II, Thengel, Aragorn as a young Chieftain, Dáin, Bilbo, Elrond, Galadriel, etc.), so that the run starts from the real world.
33. As a viewer, I want characters who are not yet born in 2965 (Frodo, Boromir, Éomer…) to *not* appear at seed, so that history has room to diverge before they would exist.
34. As a viewer, I want races to age differently — mortal Men and Hobbits, long-lived Dúnedain and Dwarves, immortal Elves and Maiar — so that lifespans feel canonical.
35. As a viewer, I want immortal Elves never to die of old age, so that Elrond and Galadriel persist as in canon.
36. As a viewer, I want Elves to slowly weary and depart over the Sea across the centuries, so that the Third Age visibly fades.
37. As a viewer, I want realms to have succession rules (Gondor's stewardship, Rohan's kingship, Durin's line, the Dúnedain Chieftains), so that leadership passes plausibly.
38. As a viewer, I want a failed or extinct ruling line to trigger interregnum, fragmentation, or absorption by a neighbour, so that dynastic collapse has consequences.
39. As a viewer, I want an extinguished faction's claim to persist dormant, so that a realm like Arnor can be restored generations later.
40. As a viewer, I want characters to have traits (leadership, martial skill, ambition, loyalty) that shape their behaviour, so that individuals matter.
41. As a viewer, I want traits to be mildly heritable, so that a strong line of kings can emerge as a tendency.
42. As a viewer, I want marriages, kinship, and personal rivalries/oaths to be modelled, so that history feels personal.

### Factions & territory
43. As a viewer, I want the powers of Middle-earth modelled as factions (Gondor, Rohan, the Dúnedain, Isengard, Mordor, Dol Guldur, Durin's Folk, Dale, the Elf realms, the Shire, Bree-land, Dunland), so that the political map is complete.
44. As a viewer, I want factions to hold and contest territory as regions on the map, so that conquest is visible.
45. As a viewer, I want a region to change hands when its controlling seat is taken in war, so that territory shifts follow battles.
46. As a viewer, I want factions to make decisions each year (muster, attack, fortify, seek pacts, build) driven by their attributes, so that they behave like agents.
47. As a viewer, I want the off-map peoples (Haradrim, Easterlings, Variags, Corsairs) to enter as abstract allies of Sauron, so that the East and South press on the West without being fully simulated.
48. As a viewer, I want provider forces to appear as real marching hosts (or coastal raids) that can be intercepted and defeated, so that "the Haradrim were broken at the Poros" can happen.
49. As a viewer, I want new factions to arise only through canon restoration arcs (a Reunited Kingdom), so that emergence stays bounded but the great arcs remain reachable.

### War & battles
50. As a viewer, I want factions to raise and move armies led by their notable characters, so that wars are fought by named leaders.
51. As a viewer, I want battles to occur when hostile hosts meet, resolved with a mix of strength and chance, so that outcomes are believable but not predetermined.
52. As a viewer, I want upsets to be possible (a smaller force can win), so that history surprises me.
53. As a viewer, I want sieges of fortified settlements to play out over multiple years, so that great sieges feel weighty.
54. As a viewer, I want captured settlements to be either held or razed depending on the conqueror, so that castles are built and razed over time.
55. As a viewer, I want named characters to occasionally die in battle (even in victories), so that war has real stakes and triggers succession.
56. As a viewer, I want long marches through hostile or barren land to cost an army strength, so that distance and geography matter.

### Diplomacy & construction
57. As a viewer, I want factions to have evolving relationships (alliance, hostility, neutrality, vassalage), so that the diplomatic web shifts over time.
58. As a viewer, I want relationships to move via marriages, treaties, betrayals, and shared or opposed wars, so that diplomacy has causes.
59. As a viewer, I want wars to be formally declared and later ended by peace, tribute, or vassalage, so that conflicts have a beginning and an end.
60. As a viewer, I want vassalage bonds (a realm under a high king), so that the Reunited Kingdom and Sauron's subject-peoples are expressible.
61. As a viewer, I want factions to found and grow settlements, fortresses, and roads in peacetime, funded by their economy, so that the built world changes outside war.
62. As a viewer, I want a razed settlement to potentially be rebuilt later in peacetime, so that ruins are not always permanent.

### The One Ring
63. As a viewer, I want the One Ring tracked as a real object with a definite location at all times (borne by someone, or lying where it fell), so that I can always locate it.
64. As a viewer, I want the Ring to start quietly with Bilbo at Bag End in 2965, so that the seed matches canon.
65. As a viewer, I want the Ring to change hands by inheritance, theft, loss, being found, capture in war, or a deliberate errand, so that its journey is emergent.
66. As a viewer, I want the Bilbo→heir inheritance to be a *tendency*, not a script, so that the Ring's canonical path is likely but not guaranteed.
67. As a viewer, I want the Ring to corrupt and prolong the life of its bearer over time, modulated by their nature (Hobbits resist), so that bearers change as in canon.
68. As a viewer, I want a former bearer to stay marked by lingering longing, so that the Ring leaves a trace (Bilbo, Gollum).
69. As a viewer, I want the Ring's presence and use to feed Sauron's awareness, so that carrying or using it draws danger.
70. As a viewer, I want the Ring to be destroyable only once Mount Doom is active (~3007+), so that early destruction is impossible, matching canon.
71. As a viewer, I want three terminal fates for the Ring — destroyed, reclaimed by Sauron, or lying lost — each reshaping the world, so that runs reach real climaxes.
72. As a viewer, I want a tempted non-Sauron claimant (a would-be new Dark Lord) to be a dramatic possibility short of a terminal, so that Saruman-/Denethor-like corruption can occur.

### Sauron's rise & canonicity
73. As a viewer, I want Sauron to grow in strength over the years (rebuilding Mordor, mustering orcs, the Nazgûl), so that a rising shadow drives the era.
74. As a viewer, I want Sauron's rise to follow a canon-shaped baseline that emergent events can accelerate or check, so that his arc feels canonical yet responsive.
75. As a viewer, I want the nine Nazgûl as named actors that hunt the Ring when it stirs and lead Sauron's hosts, so that the Ringwraiths are real on the map.
76. As a viewer, I want the Nazgûl unmade if the Ring is destroyed, so that the canon coupling holds.
77. As a viewer, I want a single canonicity knob (0–1) that scales how strongly history is nudged toward canon, so that I can tune "just like the books" vs "total chaos."
78. As a viewer, I want the canonicity knob to bias who acts and how the Ring stirs — never to rig battle dice or fire scripted events — so that even a canon-leaning run is genuinely emergent.

### Persistence & reproducibility
79. As a viewer, I want to save a run to disk and reload it exactly, so that I can return to a history later.
80. As a viewer, I want the run to autosave every N years, so that I don't lose a long run.
81. As a viewer, I want a human-shareable string seed that reproduces a run given the same scenario and canonicity, so that I can share a history.
82. As a viewer, I want a reloaded run to continue bit-identically to one that never stopped, so that saving/loading never changes the future.
83. As a viewer, I want to vary the seed with the same start, or vary canonicity with the same seed, so that I can run experiments.
84. As a viewer, I want old saves to keep working (or be migrated) after the app updates, so that my histories survive new versions.
85. As a developer, I want the whole simulation to be deterministic given (seed + scenario + canonicity), so that behaviour is testable and reproducible.

### Packaging
86. As a viewer, I want the app as a native macOS application I can launch normally, so that I don't need a developer setup.
87. As a viewer, I want the app to run fully offline, so that it works without a network or account.

## Implementation Decisions

### Architecture & the primary seam
- **Framework-agnostic seeded simulation core that emits an immutable snapshot + event stream per tick (month); the PySide6/Qt UI is a pure consumer.** This is the single, highest testing seam: the entire sim is exercised headless (no UI) by driving ticks and observing world state, the event log, and determinism. *(Ticket 04, 02)*
- **Language: Python. Watch-only** — no player control in v1. *(map Notes)*
- **UI stack: PySide6/Qt.** Map is a `QGraphicsView`/`QGraphicsScene` (the reference map as a pixmap item; region polygons + location/army/Ring items on top, resolved by built-in item hit-testing). Panels are native Qt docks; the annals feed is a model-backed virtualized `QListView`; the timeline is a `QToolBar` (play/pause/step) + `QSlider` (scrub) + speed control. The sim runs on a `QThread` and delivers `(snapshot, events)` to the UI via signals. Backup stack: pygame-ce + pygame_gui. *(Ticket 04)*
- **macOS packaging via Briefcase**; offline, no network dependency. *(Ticket 04)*

### Core object model — the `World` spine
- **A single `World` holds typed collections of id-keyed dataclass records** (character, faction, region, location, route, army, the One Ring artifact, provider, event), plus run-level fields: `current_year` (starts TA 2965), seeded RNG state, `id_counter`, `config` (scenario id+version, canonicity), and the append-only `events` log. *(Ticket 02)*
- **All cross-entity references are integer ids, never object pointers.** State is therefore a plain serializable tree with no pointer cycles. *(Ticket 02)*
- **Identity: one monotonic, never-reused integer id space** for everything addressable. Config geometry (regions/locations/routes) gets deterministic ids at scenario load, so the same scenario yields the same ids. *(Ticket 02)*
- **Entity base fields:** `id`, `kind`, `name`, `created_year`, and a **`status` field** — `active` plus a tombstone enum recording *how* an entity left play: `dead`, `departed` (Elves sailing West), `destroyed` (the Ring at Mount Doom; the Nazgûl unmade with it). Tombstoned entities are never deleted, so references stay resolvable. *(Ticket 02, corrected in coherence review; consumed by 05/09/10)*

### The tick — a fixed ordered system pipeline
- **A tick is one month (`TICKS_PER_YEAR = 12` ticks per year); it advances by running a fixed, explicit list of systems, each `system(world, rng) -> events`**, mutating authoritative state and appending events. Deterministic order + a single seeded RNG threaded through every system is the reproducibility contract. Per-year lifecycle rates (death/fertility/weariness) are applied against the monthly scale so behaviour over a span of years is unchanged. Phase order: *(Ticket 02; monthly clock added post-implementation — see ADR-0003)*
  1. **Aging / births / deaths** *(05)* — ages advance; natural & disease deaths; births. (Violent death is phase 5's.)
  2. **Faction decisions** *(06)* — factions score a menu of intents (muster / attack region / fortify / seek pact / build) via weighted utility + RNG jitter; canonicity weights the scores.
  3. **Diplomacy** *(08)* — disposition updates; treaties, marriages, betrayals, provider-pacts; war declarations/terminations flip stance flags.
  4. **Movement** *(01/07/09)* — armies and the Ring advance tile→tile along routes by a per-tick budget (derived from a miles/year rate ÷ `TICKS_PER_YEAR`).
  5. **War** *(07)* — battles & sieges where forces meet; casualties incl. named death; conquest; razing.
  6. **Construction / economy** *(08)* — settlements founded/grown/razed-rebuilt; economy accrual.
  7. **Sauron rise + canonical pressure** *(09/10)* — recompute `sauron_strength` and the Ring's `pull`; apply canon-pressure weighting for the *next* tick. This phase never musters, moves, or fights.
  8. **Salience + bookkeeping** *(11/12)* — score event importance; increment the `tick` clock (year/month are derived from it); autosave check.
- **Phase-flow contract (coherence-critical):** the static canonicity knob is available at every phase; the *dynamic* values computed in phase 7 (`sauron_strength`, `pull`-response weighting) are consumed by the **next** tick's phases 2–4 (a deliberate, invisible one-tick / one-month lag). *(Tickets 02/10)*

### Events — state-authoritative, append-only
- **World state is the source of truth; systems mutate it, then emit immutable dated `Event` records.** Events never drive state (not event-sourced). Save = state snapshot + event log; load = direct rehydrate, not replay. *(Ticket 02)*
- **`Event` fields:** `id`, `year`, `type`, `subject_ids` (primary + participants), `location_id?`, `importance` (salience, scored at emission), `payload` (structured, type-specific), `text?` (rendered prose). Indexed for query by **subject, faction, year, type**. *(Ticket 02/11)*
- **Canonical event-type catalog is consolidated at spec time** from the types each system introduced: `birth, death, battle, siege, conquest, razing, founding, treaty, marriage, succession, ring_moved, ring_pull_changed, war_declared, war_ended, provider_pact, departed, destroyed, sauron_grows` (extensible). Each carries a defined `payload` shape and a salience base-weight. *(map fog note; owned by 02/11)*

### Spatial substrate — **revised by [ADR-0001](../../docs/adr/0001-tile-substrate-and-render.md)**
> The two-layer region/route model was **superseded**. The world is now a **tile
> grid, and the tile is the unit of simulation** (ADR-0001).

- **Tile substrate.** A fixed grid of terrain tiles at **~15 miles/tile** (~100×130 ≈ 13k tiles over the theatre). Each tile: static `terrain` + mutable **`owner_faction_id`** (authoritative territory) + optional feature/occupant refs. **Regions become named labels** (aggregate tags over tiles) for identity/prose only — ownership and borders are **per-tile and emergent**; "contested"/borders are *derived* from neighboring owners. *(ADR-0001; reshapes 06/07/08)*
- **Movement is tile→tile** by deterministic pathfinding with per-terrain cost (roads = cheaper tiles); army/Ring/Nazgûl positions are tile coords; budget in **tiles/year** (miles/year ÷ 15). *(ADR-0001; 07/10)*
- **Terrain** per tile (`plains/forest/mountain/hills/marsh/barren/water(river|lake|sea)/road`); impassability falls out of terrain + movement cost. Grid is fixed **config**; a one-time tile↔reference-map-pixel calibration is for tracing only. *(ADR-0001)*
- **Rendering:** an in-engine **Dwarf-Fortress-style tile map** — Kenney roguelike sprites (**CC0**, in `references/tilesets/`) plus **custom mountain & river tiles**; faction territory is a per-tile owner tint over terrain. The reference map is **for tracing only**, never the canvas. *(ADR-0001; 11)*
- **World extent: the tightened War-of-the-Ring theatre** (Eriador → Erebor/Dale → Gondor → Mordor). Far north and deep Harad are static backdrop. Off-map peoples attach as **abstract providers at edge gateway tiles** (Harad Road/Poros, E. Rhovanion, SE Nurn/Mordor, Umbar-sea). *(ADR-0001/06)*

### Characters & dynasties
- **Data-tabled per-race lifecycle** in phase 1: a `race` config table gives `{mortality_kind ∈ mortal|long_lived|immortal, maturity_age, fertility_window, base_death_curve}`. Long-lived races use a stretched curve; **immortals skip the natural-death roll**. Seed characters are hand-authored from the TA 2965 canon roster; all others are generated by births; unnamed population is a faction aggregate, not individual records. *(Ticket 05)*
- **Elven fading:** immortals carry a slowly-rising weariness/sail-West drive; individuals **depart** (status `departed`), and Elf realms hold a `withdrawing` posture (defend, seldom expand). *(Ticket 05/06)*
- **No `Dynasty` entity** — bloodlines are queries over kinship id-fields (`parent_ids`, `spouse_id`). A realm's ruling line is whoever holds `faction.leader_id`. Each faction has a **`succession_rule`** enum (`agnatic_primogeniture / elective / stewardship / dwarf_line_of_durin / …`); on a leader's death/departure a succession walk resolves the heir and emits `succession`. On a **failed line**: try kin → elective fallback → else fragment or be absorbed by the strongest neighbour; a zero-territory faction is tombstoned with a **dormant claim** that keeps restoration reachable. *(Ticket 05/06)*
- **Trait vector** (`leadership, martial, ambition, loyalty`, optional `wisdom/guile`), sampled at generation with mild heritability; `role` enum (`ruler, heir, general, ring_bearer, ranger, councillor, none`). A derived **character prominence** (role + trait magnitude + title) feeds salience. *(Ticket 05)*
- **Relationships:** structural kinship as id-fields (drives succession and the Ring's inheritance tendency), plus a thin **sentiment-edge list** `(from_id, to_id, type ∈ rivalry|friendship|oath, strength)` created only by events. *(Ticket 05)*
- **Bilbo→Frodo is a tendency, never scripted:** the Baggins line is ordinary kinship + fertility; the Ring's inheritance bias (09) reads the kinship graph, scaled by canonicity. 05 must not encode "Frodo." *(Ticket 05/09)*

### Factions & territory
- **One `Faction` record tagged `kind ∈ realm | culture | provider`.** *Realm* owns regions, musters, has a capital + succession-bearing leader; *culture* holds territory/identity but weak central military (Shire, Bree-land, Dunland, Grey Havens); *provider* is the abstract off-map node. *(Ticket 06)*
- **TA 2965 roster:** Gondor (Ecthelion II), Rohan (Thengel), Dúnedain of the North / Rangers (Aragorn II — landless, holding a thin "unclaimed North" claim), Isengard (Saruman), Mordor (Sauron), **Dol Guldur** (distinct Mordor-allied realm), **Durin's Folk** (Erebor + Iron Hills as *one*, Dáin II), Dale (Bard I), Rivendell (Elrond), Lothlórien (Galadriel & Celeborn), Woodland Realm (Thranduil), Grey Havens (Círdan), the Shire, Bree-land, Dunland; providers: Haradrim, Easterlings of Rhûn, Variags of Khand, Corsairs of Umbar. Wilderness = `owner_faction_id = None`. *(Ticket 06, seeded from ticket 03 research)*
- **Territory is atomic region ownership** (`owner_faction_id`, the only mutable region state). "Contested" and borders are **derived**, never stored. Ownership flips by **conquering a region's `seat_location_id`** in phase 5. Fractional/influence control is out of scope. *(Ticket 06)*
- **Faction AI: weighted-utility rules** (no learning/planner AI) in phase 2. Per-faction state: derived `military_strength`, `treasury/economy`, `aggression` & `posture`, a `disposition` map, an ordered `goals` list, and a derived `prominence` (feeds salience). **Canonicity enters here as a global scalar weight** on intent scores. *(Ticket 06/11)*
- **Provider interface:** record = `gateway_location_id`, `allegiance_faction_id?`, `commitment` 0–1, config `output` profile. To diplomacy (08): a pact target whose allegiance/commitment 08 raises/lowers. To war (07): a committed provider **spawns a real provider-flagged `Army` at its gateway** (`commitment × output`) that fights on the route layer — interceptable, routable, can defect. **Corsairs** are the exception: coastal raids via the sea gateway, no seat seizure. Providers never own regions, have no interior, and are never conquered. *(Ticket 06/07)*

### War & battle
- **Phase-5 combat on `Army` records** (`faction_id`, `leader_id`, `position` = a location id or `(route_id, progress)`, integer `size`). Armies are mustered (phase 2) from a region-derived manpower pool, led by the highest `martial`+`leadership` character. **Supply = lightweight integer attrition** during movement (worse on bad terrain / far from friendly seats). *(Ticket 07)*
- **Battle trigger:** two enemy hosts share a location or a border route segment, or a host sits on an enemy-owned settlement (→ siege). Resolution order deterministic by location id. *(Ticket 07)*
- **Battle resolution — strength-ratio + one bounded seeded-RNG roll.** `effective_strength = size × leader_factor × terrain/posture × provider-unit modifiers`; a bounded roll perturbs the ratio → outcome tier (decisive/marginal/stalemate) → integer casualties (loser loses more); winner holds the field, loser retreats or is destroyed. Emits `battle`. Battles resolve within the tick; multi-year grind is expressed through sieges. **Canonicity never touches battle dice** — only phase-2 intents. *(Ticket 07)*
- **Sieges persist across ticks:** a `besieging` state + accumulating progress; the settlement adds a fortification bonus. On fall, the attacker holds the `seat_location_id` → 06 flips ownership (emit `conquest`); **razing** is a discrete post-capture choice by posture/canon flavour (→ `ruin`, emit `razing`) vs. capture intact. *(Ticket 07)*
- **Named-general death: a rare post-battle scaled roll** per named character present (much higher on the losing side, lowered by `martial`); a leader can fall in a battle their side wins. On death → tombstone + `death (killed_in_battle)` + trigger 05 succession. *(Ticket 07)*
- **07 is destructive/capture-only;** all peacetime founding/rebuilding is 08's. Rule: "08 builds where there is peace; 07 destroys/captures where there is war." *(Ticket 07/08)*

### Diplomacy & construction
- **Diplomacy (phase 3): an asymmetric per-faction `disposition` scalar** (sparse dict, absent = seeded baseline) + a **derived stance** (`alliance/neutrality/hostility/vassalage`) with pinned flags (signed treaty, at-war boolean, vassalage bond). The scalar decays toward a baseline and jumps on marriages/treaties/betrayals/shared or opposed wars/border friction. *(Ticket 08)*
- **Wars formally start and end in phase 3** (07 only executes): phase 3 flips the at-war flag and emits the declaration; 07 produces the military facts; the next phase 3 emits peace/tribute/vassalage and clears the flag. *(Ticket 08/07)*
- **Vassalage = a directional overlord bond** (`overlord_faction_id?`): a vassal musters for its overlord, keeps its own succession and dormant claim, and can break free. This is the **Reunited-Kingdom mechanism (a bond, not a faction merge)** and the shape of provider-pacts. *(Ticket 08/06)*
- **Construction (phase 6): a lean single `treasury` scalar per faction** (income = sum of owned-region `base_yield`); `build` intents are priced against it — found a settlement/fortress at an eligible location, grow a settlement tier, or open a road. Founding flips a Location to a settlement type (no new entity) and emits `founding`. Scarcity makes razing meaningful. Population is a derived aggregate only. Phase-6 construction **skips contested regions**. *(Ticket 08)*
- **Marriage seam:** the diplomacy phase (09) decides *whether* a marriage happens (dynastic-alliance utility off disposition + eligible unwed heirs); 05 defines *what it does* to kinship (`characters.wed` sets the symmetric spouse edge), and 09 moves the junior spouse into the senior house. *(Ticket 09/05; implemented — was provisionally scoped to 08)*

### The One Ring
- **A single bespoke `Artifact` record** (no general artifact system) with the invariant **`bearer_id` XOR `location_id`** (exactly one non-null). Seed: borne by Bilbo at Hobbiton, both scalars low. When borne it renders from the bearer's position; when unborne it renders at its own location; it never free-roams. *(Ticket 09)*
- **A passenger, not an autonomous mover:** while borne it advances on the bearer's miles/year budget (emit `ring_moved`); unborne it does not move. Its "will" is a **probability modifier** — high `pull` raises loss/theft/betrayal odds — not locomotion. *(Ticket 09)*
- **Possession changes via a fixed transfer-mode enum**, each a canonicity-weighted seeded roll fired by the owning phase: inheritance/gift (phase-1 seam, biased along 05 kinship = the Bilbo→heir tendency), theft, loss/drop, found, war-capture (phase-5 seam), deliberate errand (an emergent intent to carry it toward a goal node). *(Ticket 09)*
- **Two integer scalars:** `corruption` (per-bearer, grows while borne, trait-modulated — Hobbits resist; low = life-prolonging by suppressing the natural-death roll, mid = secrecy/possessiveness bias, high = may claim it; **attenuates, not resets, on transfer** so ex-bearers stay marked) and `pull` (global, Sauron-facing; spikes when the Ring is used). *(Ticket 09)*
- **09 owns and computes `pull` (phase 7); ticket 10 consumes it and never mutates the Ring record** (single-writer discipline). *(Ticket 09/10)*
- **Three terminal outcomes**, each a world-transition flag feeding the aftermath: **destroyed** (only once Orodruin is active ~3007+ → Ring tombstoned `destroyed`, Sauron broken), **Sauron reclaims**, **lying lost** (a low-`pull` holding pattern, not hard-terminal). A **non-Sauron claimant** (tempted Saruman/Denethor/Galadriel) is a **transient** high-corruption event, not a fourth terminal. *(Ticket 09)*

### Sauron & canonical pressure
- **Sauron = the Mordor faction + a `sauron_strength` scalar**, recomputed each phase 7 as `canon_baseline(year) × canonicity + Σ emergent_deltas`. The baseline encodes the canon ramp (arming since 2951, ramp to the War-of-the-Ring window, Orodruin active ~3007); at `canonicity = 0` it flattens to purely emergent. The Ring spikes it; defeats / loss of Dol Guldur or Minas Morgul check it. Strength scales Mordor musters, provider commitment, Nazgûl activation, and the `pull`-rise weighting. *(Ticket 10)*
- **The nine Nazgûl are named Characters** (wraith-Men bound to the Nine Rings, `mortality_kind = immortal` while Sauron/the Ring endures; Witch-king at Minas Morgul, three at Dol Guldur). They hunt via the **normal phase flow** — hunting is a phase-2 Mordor intent (triggered by high strength + high `pull`), movement is phase 4, a capture attempt resolves in phase 5. They are **unmade (`destroyed`) if the One Ring is destroyed**. Between hunts they are elite war-leaders. *(Ticket 10)*
- **Canon pressure = soft weighting only:** the canonicity knob adds weight to canon-aligned phase-2 intents and to Ring/event transfer probabilities. It **never fires an event directly and never overrides an outcome** (battle dice stay honest). History can diverge; canon is just more likely. *(Ticket 10/06/07/09)*
- **Canonicity is a single global 0–1 knob** in `World.config` (saved separately from seed and scenario), scaling four forces in v1: **Sauron's rise, the Ring's stirring, Free-Peoples alliance formation, and character role-seeking** (e.g. a Dúnedain heir tending toward the restoration claim). Per-force / per-faction tuning is out of scope. *(Ticket 10)*

### Persistence, seed & determinism
- **Save = a canonical-JSON snapshot** (state + event log) via `to_dict`/`from_dict` behind a **storage-backend seam**, so the event log can later move to a JSONL/SQLite sidecar without touching sim code. `json.dumps(sort_keys=True)`; **never pickle or `hash()`**. Load = direct rehydrate. **Autosave every N years** (phase 8) + manual. *(Ticket 12)*
- **Seed:** a human-shareable string → `seed_int = int.from_bytes(sha256(seed_str)[:8], "big")` → one `random.Random(seed_int)` threaded through every system. The `seed_str` is stored verbatim. **RNG family locked to `random.Random`** for v1. *(Ticket 12)*
- **Exact resume:** serialize the live RNG state (`rng.getstate()`) and restore with `setstate()`, so a reloaded run is bit-identical to one that never stopped. *(Ticket 12)*
- **Run identity = `(scenario_id + version, canonicity_params, seed_str, code_version)`** — scenario is *referenced*, not inlined — yielding both "same seed, vary canonicity" and "same scenario+canonicity, vary seed." *(Ticket 12)*
- **Versioning:** a provenance header (`schema_version, code_version, python_version, rng_family, scenario_id, scenario_version, seed_str`) + an ordered migration-function chain run on load. *(Ticket 12)*
- **Float-determinism policy (cross-cutting):** every comparison that decides an outcome (battles, casualties, attrition, disposition thresholds, corruption/pull, sauron_strength) must be integer/fixed-point. *(Tickets 12 + 05–10)*

### Chronicle & UI
- **Live feed:** a virtualized model-backed `QListView` "Annals" dock fed the per-tick events, filtered on the four indices with an importance threshold; default **important-only** with one-click "show all"; above-threshold events also fire a transient on-map pulse at their `location_id`. *(Ticket 11)*
- **Map labels:** site names (settlements/fortresses) and area names (region labels) render as **engine-drawn text over the tiles** — zoom-aware LOD (areas out, sites in), toggle-able/filterable, haloed for legibility. Data-driven from each site's/region's `name`, never baked into terrain, so they update as places are renamed/razed/founded. *(Ticket 11; see [ADR-0001](../../docs/adr/0001-tile-substrate-and-render.md))*
- **Inspection:** a persistent dock driven by graphics hit-testing; shows the entity's current fields + its **by-subject event timeline**; cross-references are clickable ids that resolve even for tombstoned entities. *(Ticket 11)*
- **Playback via a snapshot-per-tick cache:** the sim runs forward-only, emitting `(snapshot, events)` per tick (month); **scrub/seek restores snapshot[T] — never replays** (T is an absolute tick); step = ±1 cached tick; you may only scrub within simulated ticks (seeking past the frontier fast-forwards the sim). The date label shows year + month; the annals stay year-grained. Keyframe-snapshots + bounded replay is the documented fallback if memory at scale bites (more pressing at 12× the snapshot rate — see ADR-0003). *(Ticket 11)*
- **Salience:** a deterministic **absolute `importance` (0–100)** scored at emission = `type base-weight × subject prominence × scale × canon-bump`, immutable in the log; the UI may optionally normalize to a top-N-per-year *view*. *(Ticket 11)*
- **Prose chronicle:** per-event-type **templates + a seeded phrase-grammar** rendered into `Event.text` — deterministic, offline, no dependencies. The `text` field is the swappable seam for a future LLM backend (deferred, out of scope). *(Ticket 11)*

## Testing Decisions

- **What makes a good test here: assert on external, observable behaviour of the sim core at the top seam** — given a scenario + seed + canonicity, drive N ticks and assert on world state, the emitted event stream, and determinism. Never assert on internal helper structure. The sim is headless and framework-agnostic, so the entire behavioural surface is testable without instantiating any Qt/UI object. *(Ticket 04/02)*
- **Determinism / reproducibility tests (highest priority):** the same (seed, scenario, canonicity) produces a byte-identical run (same event log, same final snapshot) across two independent runs and across processes; save-then-load-then-continue equals never-stopping (bit-identical); "same seed, different canonicity" and "different seed, same start" both diverge as expected. These directly exercise the single-RNG contract and the `getstate()` resume path. *(Ticket 12)*
- **Seed-scenario tests:** loading the TA 2965 scenario reproduces the canon roster, the not-yet-born list stays absent at seed, the Ring is borne by Bilbo with low scalars, and providers/gateways/Nazgûl are placed correctly. *(Ticket 03/06/09/10)*
- **Per-system behavioural tests, each driving the pipeline and observing events:** lifecycle (births/deaths/aging, immortal skip, Elf departure); succession (normal, elective fallback, failed-line fragmentation/absorption, dormant-claim restoration); territory (conquest flips ownership on seat capture; razing → ruin); battle (strength dominates on average, upsets occur, casualties integer, named death triggers succession, sieges persist across ticks); diplomacy (disposition drift, war declared/ended in phase 3, marriage seam, vassalage bond); construction (treasury gates building, razed ruin rebuilt); the Ring (XOR invariant always holds; transfer modes; corruption grows/attenuates; pull rises on use; destruction gated on active Orodruin; terminals tombstone correctly); Sauron/canon (strength follows the baseline × canonicity + deltas; canonicity=0 flattens; Nazgûl hunt only when strength+pull high; Nazgûl unmade on Ring destruction; canonicity biases intents but never battle outcomes). *(Tickets 05–10)*
- **Invariant/property tests:** the `bearer_id` XOR `location_id` invariant holds after every tick; every event's `subject_ids`/`location_id` resolve; ids are never reused; tombstoned entities are never deleted; no float appears at an outcome-deciding comparison.
- **Persistence round-trip tests:** save → load → deep-equal; provenance header present; a `schema_version`-bumped old save migrates and loads.
- **UI is not covered by the sim test suite** (it's a thin consumer of snapshots/events); any UI testing is separate and minimal.
- **Prior art:** none in-repo (greenfield). The suite establishes the pattern: pytest, headless sim driver fixtures (build a `World` from a scenario+seed, run K ticks, inspect state/events), golden-run fixtures for determinism.

## Out of Scope

- **Building the game** — this is a spec only; implementation is the downstream `/implement` flow.
- **Player intervention / control** — v1 is watch-only.
- **Multiplayer.**
- **Non-War-of-the-Ring eras** — no TA 1 start, no earlier Ages.
- **Fully modelling off-map peoples** — Harad/Rhûn/Khand/Umbar stay abstract providers.
- **A general artifact system** — the Ring is bespoke; the Three, palantíri, etc. are fog.
- **Deep magic/metaphysics** beyond immortality and the Ring (Maiar powers, palantíri, "power" as a quantity).
- **Multi-resource economy, trade flows, tribute economics, procedural rebellion** — the economy is a single treasury scalar; a vassal can break free but rebellion mechanics are deferred.
- **Per-force / per-faction canonicity tuning** — v1 ships one global 0–1 knob.
- **LLM-generated prose** — templates + phrase-grammar only; the `Event.text` field is left as the seam for a future, separately-specified LLM enrichment.
- **A first-class "war" entity** (nameable "War of X") — v1 uses a per-pair at-war flag; deferred.
- **Sea/naval movement on the substrate** — Corsairs are abstract coastal strikes, not navigated hosts.
- **Special post-climax ("aftermath") modelling** — after a terminal, the open-ended systems simply continue.

## Further Notes

- **Reference assets:** a reference map of Middle-earth (the canvas; has the miles scale bar for calibration) and a higher-detail hex reference for Eriador (higher-detail terrain reference). Geography is fixed.
- **Content-authoring is a build asset, not a design decision** — a single authoring pass produces: the region/route/location dataset in reference-map pixel coordinates (with `seat_location_id` and `base_yield` per region); per-faction seed values (aggression/posture/disposition baselines); provider `output` → combat-modifier profiles; battle/siege tuning tables; the treaty taxonomy; Ring corruption/pull coefficients; the `canon_baseline(year)` curve; and per-event-type prose templates + phrase-grammar. `/to-tickets` should split this authoring from the engine work.
- **Performance at scale** is the main open risk, sharpened by the monthly clock (12× the ticks, event-log growth, and snapshots of a yearly sim — see ADR-0003): an open-ended sim over centuries across the whole map. A research/prototype spike is expected to decide when 12's storage seam swaps JSON→SQLite and whether 11 falls back to keyframe+replay.
- **Full decision provenance** lives in the wayfinder map at `.scratch/arda-history-v1/map.md` and the twelve resolved tickets in `.scratch/arda-history-v1/issues/`; each Implementation Decision above cites the ticket holding its rationale and rejected alternatives.
- **Coherence-reviewed:** cross-ticket seams (phase order, shared fields, event catalog, tombstone status, faction/character prominence) were reconciled before this spec; the Nazgûl phase-flow, their Ring-destruction coupling, and the tombstone `status` enum are the corrections folded in.
