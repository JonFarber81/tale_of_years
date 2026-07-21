# Context — Arda History (ubiquitous language)

A glossary of the domain terms this simulation uses. Implementation lives in
`src/arda_sim/`; decisions with lasting consequence live in `docs/adr/`. This file
is *only* the shared vocabulary.

## Factions & relations

**Faction** — a power on the map, switched by `kind ∈ realm | culture | provider`.
Realms own territory and muster hosts; cultures hold ground but project little
force; providers are off-map peoples reached through a gateway.

**People** — the broad folk a faction belongs to
(`men | elves | dwarves | orcs | hobbits`). World-truth about the faction itself,
not its army's composition, and independent of `kind` (Isengard in TA 2965 is
*men*: Saruman's holding, no Uruk-hai yet). Authored at seed on every faction,
providers included.

**Disposition** — an *asymmetric* per-ordered-pair scalar (−100..+100) recording
how one faction regards another. Sparse: an absent entry means "no special
feeling", read as the pair's baseline temper. Evolved by the diplomacy phase.

**Baseline temper** — the authored, canon disposition a pair *returns to* over
time (Gondor↔Rohan warm, Gondor↔Mordor hostile). Frozen at seed and immutable;
the live disposition decays toward it each year, so canon allegiances are lasting
attractors rather than mere starting conditions.

**Stance** — the *derived* discrete relation between two factions
(`alliance | neutrality | hostility | vassalage`), read as a pure function of the
disposition scalar plus the pinned flags. Never stored (like a border, it is
computed on demand).

**Pinned flags** — sticky discrete relational facts that are *not* mere
thresholds on disposition: a **signed treaty**, the **at-war** boolean, and the
**vassalage bond**. Stored, because each is a decision that persists until
explicitly undone.

**Treaty** — a symmetric signed pact of amity/alliance between two factions.

**At-war** — the symmetric formal state of war between two factions. Declared and
ended by the diplomacy phase; the *fighting* is executed by the war phase.

**Vassalage** — a *directional* overlord→vassal bond. A vassal musters for its
overlord yet keeps its own succession and dormant claim and can break free. This
is the mechanism for the Reunited Kingdom (a bond, never a faction merge) and for
provider-pacts.

**Provider-pact** — a realm's diplomatic tie to an off-map provider people,
raising or lowering that provider's `allegiance` and `commitment`.

**Marriage** — a dynastic union the diplomacy phase *decides* (does it happen?)
and the kinship layer *enacts* (the symmetric spouse bond and its succession/
fertility consequences). The junior partner weds *into* the senior house: the
lower-standing spouse adopts the other's faction, so the couple's children belong
unambiguously to the senior realm.

**Border friction** — the slow souring of disposition between two factions whose
territory touches and who are not bound by treaty/vassalage; the standing
downward pressure that rubbing borders exert.

**Betrayal** — declaring war on a faction one currently holds a treaty (or
vassalage bond) with; it tears up the pact and sours disposition far harder than
an ordinary declaration.

## Armies & movement

**Host (Army)** — a body of troops raised by a **coalition** (a lead faction and any
co-belligerents who Gather with it). It stands on a single map *tile* and carries an
integer `size` (summed across its contributors), a general, and (while marching) the
remaining tile path to its objective. A coalition fields one host; each contributor
lends at most one levy at a time.

**Muster** — raising a host as a rare, heavy **war-effort**, not an annual levy. A
faction musters only while genuinely **at war** (the at-war flag, not mere hostility)
and only past a **cooldown** since its last host left play — a size-scaled rest, so a
great hosting depletes the realm's manpower for longer. A host's `size` is a
deterministic (no-RNG) function of its contributors' `military_strength`; its general
comes down the **leader ladder** (the ruler stays home).

**Coalition host** — the single combined host a **Gathering** produces: owned by the
lead faction, summing the strength-derived levy of every contributor (the lead plus
its treaty-allies, vassals, or overlord that share the *same* war), led by the ablest
eligible leader across the whole coalition, and marching at the lead's **pace**.

**Gathering / muster point** — the act of a coalition's belligerents combining their
levies into one host at the lead faction's seat (the muster point). Each contributor
is still gated by its own at-war state and cooldown; an unbound third party at war
with the same enemy fields its own host rather than joining.

**Leader ladder** — how a host is always given a general: the ablest field-eligible
**non-heir** across the coalition → failing that, the **heir** (who may then die in
battle, seating the next heir) → failing even that, a **generated captain**. A
leaderless host does not occur.

**Generated captain** — a named field officer synthesised to lead a host when no
existing character is eligible: a non-dynastic character (no kin, outside the
succession line) with generated `martial`/`leadership`, seated as a general. Over a
long history this grows a distinct sub-population of captains.

**March pace** — a faction's marching speed in **miles/year**, authored per faction
and otherwise defaulting by **people** (mounted realms fastest, Elves lithe, Men the
mid reference, Orc-hosts their own profile, Dwarves slower). Replaces the single
global rate; a coalition marches at its lead's pace.

**March** — a host advancing tile→tile along a deterministic least-cost path
(Dijkstra over terrain move-cost; roads cheap, rough ground dear), spending an
integer per-tick movement budget derived from its **miles/year** pace. Position is
tile coords, not a route — the two-layer route model was superseded (ADR-0001).

**Attrition** — the integer strength a marching host loses each tick to harsh
ground (barren/marsh/mountain) and to being off friendly soil (its own, an ally's,
its liege's, or a vassal's). The off-friendly toll *deepens with distance from a
friendly seat*, tracked as the run of ticks since the host last stood on home
ground (**supply lag**, capped) — a host driven deep bleeds harder. A host bled to
nothing **disbands**. Supply is this lightweight decay, not a logistics model, and
is never applied to a host in garrison.

**Objective** — the seat a mustered host marches on: a **war enemy** (providers,
holding no ground, are never objectives; mere hostility no longer raises a host). On
arrival the host garrisons; the fighting itself is the war phase's (ticket 11).

## War & battles

**War phase** — tick phase 5, run after movement. It reads where every host
stands and resolves the fighting: field battles, sieges, provider hosts, and
corsair raids. Only factions the diplomacy phase has flagged **at-war** fight
(a provider fights its patron's wars). Every outcome-deciding comparison is
integer/fixed-point, and **canonicity never touches the battle dice** — it
weights only who musters and who attacks (phase 2), never who wins.

**Field battle** — a clash between two at-war hosts **sharing a tile** (adjacency no
longer triggers a fight — battles concentrate where hosts actually meet, so the few
that fire are the decisive ones). Each side's **effective strength** = `size × leader
× provider ×` (for the defender) `terrain/posture` modifiers, all integer permille;
**one bounded seeded roll** tilts the ratio both ways at once, so the stronger host
usually wins, an even fight is a coin toss, and a moderate edge can still be
overturned. The loser takes the heavier casualties and retreats toward home, or is
**destroyed** if it is shattered — cut below a fraction of the strength it **mustered**
with (proportional, so one key battle can end a war), not a flat absolute floor.

**Giving vs. refusing battle (evasion)** — before a shared-tile clash, an outmatched
**defender** (the pursuer more than ~1.5× its effective strength) may try to slip away
rather than fight. Evasion is a **seeded, can-fail** contest — raised by the evader's
pace and its general's `leadership`+`guile`, lowered by the pursuer's strength edge:
success withdraws it a tile toward home with no battle; failure leaves it **caught**
and fighting at a disorder penalty. A host defending its own seat (besieged) or with
no path home cannot evade, and an aggressor pressing its objective never does.

**Siege** — a host standing on an at-war enemy's fortified **capital seat** invests
it. A siege is a *multi-tick* state: `Army.siege_progress` accumulates each tick
against the seat's **fortification** (by site kind — a city holds out far longer
than a town), so a great fortress resists for months.

**Conquest** — when a siege's progress tops the seat's fortification the seat
falls and the besieger takes the realm. In v1 taking the **capital** takes *all*
the realm's land (a decapitation; per-region seats are content-fog). A realm whose
last ground is lost is **extinguished** — tombstoned with a dormant claim over the
regions it held, and every war it was party to ends (`make_peace`), exactly as a
failed ruling line's extinction.

**Razing** — a ruthless conqueror (aggressive posture, or a high war-drive) lays
the taken land **waste** — ownership goes to *unowned* rather than being annexed —
instead of holding it. A realm that means to **rule** what it takes holds the seat
intact: the seam that lets an Isengard seize a land whole and an Orc-host leave
only ruin behind.

**Named-battle death** — after a battle or a storming, each named leader present
rolls a rare **integer death check**, far likelier on the broken side and blunted
by the character's `martial` (a hardened warrior is harder to kill, never immune).
A **ruler** who falls this way vacates `leader_id`, and the next tick's succession
phase seats the heir — the "violent death happens in phase 5" contract.

**Provider host** — a committed off-map people whose patron is at war sends a real
host to the front, fighting as any army but with **unit-type modifiers** from its
`output` profile (mûmakil = shock, cavalry = mobility, auxiliaries = flat weight).

**Coastal raid** — the Corsairs' exception: a naval provider never marches
overland but strikes an enemy **shore** in an occasional (once-a-year, seeded)
raiding season, pillaging — denting the target's strength and reading in the
annals — without ever seizing a seat.

## Construction & economy

**Construction phase** — tick phase 6, run after war: the built world changing
where there is peace. It accrues income once a year, then lets each realm that
chose the **build** intent raise exactly one affordable work. "08 builds where
there is peace, 07 destroys where there is war."

**Treasury** — a realm's single economy scalar. It accrues **income** once a year
(month 1) from every tile it holds, by terrain (`plains`/`road` rich, mountain and
marsh poor, water nothing) plus a bonus per settlement on owned ground. Lean
treasuries genuinely gate building, so razing bites. **Population** is never stored
— a *derived* aggregate of the same holdings (`faction_population`).

**Found / rebuild** — a realm turns an **un-settled** owned location (a razed
`ruin`, or an empty `pass`) into a **town**, or — at a **border or a pass** — into
a **fortress** (`fort`). Flips the `Site`'s kind/tier in place (no new entity) and
emits `founding`; a rebuilt ruin is the peacetime foil to war's razing.

**Grow** — a realm raises an owned **town** into a **city** (a settlement **tier**
up). Emits `settlement_grew`. A site's `kind`/`tier` are the inspectable rank.

**Open a road** — a realm paves the slowest owned tile next to one of its
settlements into a `ROAD` (speeding later movement). Emits `road_opened`. Terrain
is otherwise config; a paved tile is a persisted overlay (`grid.paved`).

**Built map** — the *mutable* slice of the grid that construction and war change:
per-tile `owner`, each `Site`'s `kind`/`tier`, and paved roads. It persists with a
save (schema v3) and is re-applied onto the reloaded config grid, so a resumed run
carries its rebuilt towns and roads forward (see ADR-0007).

**Canon lean (building)** — canonicity softly weights the *choice* toward
**restoration** (founding/rebuilding over mere growth), never the fixed integer
**price** of a work; the dice-free counterpart to the phase-2 intent lean.

## The One Ring

**The One Ring** — the single bespoke artifact at the world's centre. There is
exactly one in a run; it is always somewhere definite, and its journey is the
history's quiet gravity. Seeded borne by Bilbo at the Shire's seat.

**Bearer** — the character currently carrying the Ring. Exactly one, or none: the
Ring is either **borne** (a bearer holds it) or lying at a place, never both and
never nowhere. A **former bearer** is anyone who has carried it before — the Ring
keeps that roll, and the mark it leaves is lasting.

**Corruption** — the Ring's per-bearer taint, an integer that **grows** the longer
it is borne (faster on a grasping temper, resisted by a steadfast one) and
**attenuates — never resets** when it changes hands. Low corruption prolongs the
bearer's life; a middling taint bends them to secrecy; a deep one may move them to
**claim** it.

**Claim** — a bearer, deep in corruption, seizing the Ring as their own. A
non-Sauron claim is a *transient* flare, not an ending — the terminal fates (a
claimant unmade, the Dark Lord drawn to reclaim) belong to Sauron's rise.

**Pull** — the Ring's global draw on the world, an integer that **spikes on use**
and ebbs otherwise. High pull raises the odds the Ring is lost, stolen, or
betrayed away — the danger it invites — never any power to move on its own.

**Transfer mode** — the closed set of ways the Ring changes hands, each a
canonicity-weighted chance fired by the phase that owns it:
**inheritance** (a dead bearer's kin take it up, kinship-biased), **gift**,
**theft**, **loss** (it slips and lies where it fell), **found** (picked up from
where it lay), **war-capture** (seized by a host holding that ground), and
**errand** (sent deliberately toward a goal — movement, not a handover).

**Errand** — the Ring travelling with its bearer toward a goal, advancing tile by
tile on a walking pace while borne; unborne, it never moves itself.

## Sauron's rise & canonicity

**Sauron-strength** — the phase-7 scalar of the rising Shadow, recomputed each
tick as `canon_baseline(year) × canonicity + Σ emergent deltas` and cached on the
dark realm's faction record (zero everywhere else). Consumed by the *next* tick's
phases: it scales Mordor's musters, draws provider commitment upward, unlocks the
hunt, and slows the pull's ebb.

**Canon baseline** — the authored strength ramp the era bends around: arming
since 2951, climbing toward the War-of-the-Ring window, Orodruin active ~3007.
At canonicity 0 the baseline term vanishes and only emergent history remains.

**Canonicity** — the single global 0–1 knob in the run config scaling how hard
history is nudged toward canon. **Soft weighting only**, on four forces: Sauron's
rise, the Ring's stirring, Free-Peoples pact odds, and character role-seeking. It
never fires an event and never touches a battle's dice.

**Nazgûl** — the nine wraith Characters bound to the Nine (race `wraith`,
immortal while Sauron and the Ring endure; the Witch-king at Minas Morgul,
Khamûl at Dol Guldur). Elite generals of the dark realm between hunts; **unmade**
(status `destroyed`) with the Ring's destruction.

**Hunt** — the Nine on the road after the Ring: a transient tile-moving record
spawned by the dark realm's phase-2 `hunt_ring` intent (fired only on high
strength + high pull), riding on a search budget toward the Ring's tile. The hunt
only *moves* — the capture attempt is the Ring phase's own roll.

**Terminal outcome** — one of the Ring's three endings, each raising a world
flag: **destroyed** (an errand reaching active Orodruin — Ring tombstoned, the
Nine unmade, Sauron broken, Mordor collapsing to extinction), **Sauron reclaims**
(the Ring delivered to the Dark Lord's hand), and **lying lost** (a soft,
reversible holding pattern: unborne and unfelt for years on end).

## Annals & inspection

**Annals feed** — the newest-first chronicle of events the viewer reads,
capped by the scrub position and constrained by the active filter
(important-only by default).

**Category bucket** — one of the four scannable groupings an event's type
maps into: **war**, **diplomacy**, **dynasty** (succession/kinship), and
**construction** (economy/building). A presentation grouping over event
types, not a new event field.

**Placed event** — an event anchored to a site (it carries a `location_id`),
and so navigable-to on the map. An **unplaced** event (a treaty, a marriage)
has detail but no single place.

**Event dossier** — the detail view of a single event: its year, bucket,
importance, chronicle sentence, and the structured facts behind it (for a
battle: the sides, strengths, casualties, deaths). Shown in the Inspection
dock; the deep reading of what the feed states in one line.

**Dossier subject** — the one entity a map click resolves to and the
Inspection dock headlines, chosen most-specific-first: a host standing on
the tile, else a site there, else the owning faction, else the bare tile.
Whatever is not the subject renders only as trimmed *context* beneath it.
