# Chronicle & event surfacing in the UI

Type: grilling
Status: resolved
Blocked by: 02, 04

## Question

How does the generated history become something the human reads and explores as it unfolds?

Decide:

- **The live feed** — how dated events (from ticket 02's event model) stream into the UI as the years tick: an event log/annals panel, on-map notifications, filtering by faction/importance.
- **Inspection** — clicking an entity (character, faction, settlement, army, the Ring) to see its state and history; drilling into a battle or a dynasty.
- **Playback controls** — pause, speed, step-a-year; jump/scrub the timeline.
- **The written chronicle** — whether events are also composed into readable prose annals (Dwarf-Fortress-legends style), and how narrative phrasing is generated from structured events.
- **Importance/salience** — how the system decides which events are worth surfacing amid thousands, so the War of the Ring reads as a story and not noise.

Depends on the entity/event model (02) and rendering stack (04). Consult `/domain-modeling`; a `/prototype` of the feed may help.

## Answer

The history is surfaced through a **virtualized annals feed + graphics-hit-test inspection dock + snapshot-cache playback**, ranked by a **deterministic absolute salience** scored at emission, and narrated by **template + seeded-grammar prose** written into `Event.text`. Everything rides the four locked event indices (subject / faction / year / type) and the PySide6/Qt shells from research 04.

What 02 already fixed (not reopened here): the `Event` field set including `importance` and optional `text`; salience computed in **tick phase 8**, in-sim, not in the UI; events queryable by subject/faction/year/type. This ticket defines *how* `importance` is scored and *how* `text` is produced.

### 1. Salience — deterministic absolute score *(fork resolved — absolute stored)*

- Phase 8 assigns each event a numeric **`importance` (0–100)** from factors the sim already holds: **base weight per event type** (ring_moved / realm-succession / named-death ≫ routine birth / minor treaty) × **subject prominence** (max over `subject_ids`; a King/Sauron/Ring-bearer scores high, a peasant birth ≈ 0) × **scale** (army sizes, regions changed hands, settlements razed, from `payload`) × **canon-bump** (events the phase-7 canon-pressure system nudged toward inherit a boost).
- **Fully deterministic — no RNG in scoring** — so it survives the reproducibility contract, and the stored value is **immutable**, honouring the append-only log.
- **Era-normalization is a UI view filter, not a stored value:** the feed can optionally show "the year's top-N" by ranking within a window at display time, without rescoring the log. (The rejected alternative stored a percentile, which would make importance non-local and fight the immutable log.)
- **Dependency:** subject prominence is the **character/faction prominence** field owned by tickets 05/06 — 11 consumes it, does not invent it.

### 2. Live feed

- A **model-backed virtualized `QListView` "Annals" dock** fed the per-tick `list[Event]` from the sim thread, **filtered by an importance threshold** with user filters on the locked indices (faction, type, importance floor, follow-a-subject). Virtualization (04) handles a centuries-long log without loading it all; every filter is a direct index query.
- Above the threshold, an event also fires a **transient on-map marker** (a pulse at its `location_id`, always resolvable per 01).
- **Default filter = important-only**, with one-click "show all" (avoids drowning the reader while keeping completeness reachable).
- Feed shows `Event.text` if present, else a template-rendered one-liner.

### 3. Inspection

- A **docked inspection panel** driven by `QGraphicsView` hit-testing (01/04): clicking a region/location/army/the Ring resolves to its item. The panel shows the entity's current record fields **plus its personal timeline = the by-subject event query** for that id.
- Cross-references render as **clickable ids** (King → realm → its battles), working precisely because 02's ids are stable and never reused — they resolve even for **tombstoned/dead** entities, so a long-dead King's dynasty stays inspectable. Battle/dynasty drill-down follows `subject_ids` + `payload`.
- Persistent dock (not modal dialogs), so the reader can pin the Ring while browsing and compare entities.

### 4. Playback & the snapshot model *(fork resolved — snapshot-per-year, scrub restores)*

- The sim thread runs **forward only**, emitting an immutable **`(snapshot, events)` per year** into an ordered cache. This is the direct consequence of 02's "state-authoritative, load = rehydrate not replay."
- **Scrub/seek to year T = restore snapshot[T]** to the map + show the log sliced to `year ≤ T`. **No replay — instant and deterministic.** **Step** = ±1 cached year; **speed** = ticks/sec of the forward sim; **pause** = stop advancing (scrubbing within simulated years stays live).
- You can only scrub **within already-simulated years** (the future doesn't exist until simulated); seeking past the frontier fast-forwards the sim.
- **Memory note / fog:** snapshot-every-year over centuries × whole map may be large. If it bites (the map's performance-at-scale fog), the fallback is **keyframe snapshots every N years + bounded replay to land exactly** — a swap that doesn't change the playback *contract*. Exact snapshot size/retention and whether snapshots persist to disk belongs to **ticket 12**; 11 owns the playback contract, not the storage budget.

### 5. The written chronicle — template + seeded grammar *(fork resolved)*

- Prose is **template-based per event `type`, with a seeded phrase-grammar (Tracery-style) for variety**, populated from `subject_ids`/`location_id`/`payload` and rendered into `Event.text`. **Deterministic, offline, zero external dependency** — so the prose is part of the reproducible artifact and ships inside a Briefcase `.app` with no network/key.
- The `Event.text` field is deliberately the **swappable seam**: prose is a *render* of structured events, so an alternate backend could slot in later without touching sim code.
- **LLM-generated prose was explicitly considered and deferred** (not adopted for v1). It stays fog / a possible future ticket, and *if* ever taken up it must be: an **optional post-processing enrichment**, **cached into `Event.text`** so saves stay reproducible, and **gated behind an offline default that falls back to templates**. Flagged so the seam is respected now.

### Seams & fog surfaced

- **11→05/06:** the **entity-prominence metric** that salience leans on is owned by 05 (characters) and 06 (factions); 11 only consumes it.
- **11↔12:** snapshot memory/retention and on-disk persistence of snapshots is 12's budget call.
- **Content-authoring fog:** the per-type prose templates + phrase-grammar are a build asset (like the region dataset), parked until the event-type set is frozen.
- **Deferred fog:** optional LLM prose enrichment (see §5); a two-tier raw-ticker + highlights feed (considered, not adopted).
