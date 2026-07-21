# ADR-0002 — One faction record switched by `kind`; territory is atomic region ownership on the tile substrate

Status: **Accepted** (2026-07-20)

Realizes the faction & territory design resolved in `.scratch/arda-history-v1/issues/06-faction-territory-system.md` and built in build ticket `07-factions-territory`. Builds on ADR-0001 (tiles are the substrate).

## Context

Build ticket 07 needed to model the powers of Middle-earth and their grip on the
map: a canon TA 2965 roster, a political map coloured by ownership, a yearly
faction turn, and the off-map peoples (Harad, Rhûn, Khand, Umbar). Three design
forks had to be settled before code:

1. **What a faction is** — one record type, or separate Realm / Culture / Provider
   classes?
2. **How territory is held** — per-tile, per-region, or fractional influence?
3. **How providers fit** — fully simulated peoples, or an abstract interface?

The tick pipeline constrains the answer: a system is `system(world, rng) -> events`
and is handed only the `World` and the seeded RNG — **not** the `TileGrid`. So
whatever a faction needs to *decide* each year must be readable from the `World`
alone.

## Decision

**One `Faction` record, tagged `kind ∈ realm | culture | provider`, behaviour
switched by the tag. Territory is atomic region ownership realized as per-tile
`owner_faction_id` on the ADR-0001 substrate.**

- **One record type, not three.** `Faction` is an ordinary id-keyed `Entity`
  subtype (`src/arda_sim/factions.py`), so it persists and snapshots with no
  schema change and every cross-reference stays an integer id. A single record
  keeps `owner_faction_id` one foreign key everywhere and lets territory / war /
  diplomacy treat every holder uniformly. `kind` switches behaviour:
  - **realm** — owns regions, musters, has a capital + leader (Gondor, Mordor…).
  - **culture** — holds ground and identity but projects little force and has no
    seeded leader (Shire, Bree-land, Dunland, Grey Havens).
  - **provider** — an abstract off-map people reached through a map-edge *gateway*;
    owns no region, is never a conquest target, takes no faction turn.
- **Territory is atomic region ownership on tiles.** Ownership lives where
  ADR-0001 put it — per-tile `owner_faction_id`, the only authoritative mutable
  tile state. Seeding paints *every tile of an owned region* with its faction, so
  region ownership is atomic (a region is wholly owned or unowned); **borders and
  "contested" are derived** from neighbouring tiles' owners, never stored.
  Wilderness is `owner = None` — no sentinel faction inflates the map.
- **Faction-level scalars are cached on the record.** Because phase 2 can't see
  the grid, each faction caches the derived `military_strength` and `prominence`
  computed from its territory at seed time. Ownership only changes by conquest
  (war, ticket 11), which will recompute the cache — so the cache is a
  correct-by-construction read model for the whole run until then, and the map is
  a pure function of the seed (no separate territory persistence yet).
- **The faction turn is weighted utility + jitter, canonicity as a weight.** Phase
  2 (`faction_decisions`) scores a fixed intent menu (muster / attack / fortify /
  seek-pact / build) from the faction's own cached scalars and disposition map,
  adds seeded-RNG jitter drawn in fixed menu order, and records the winning intent
  for later phases. **Canonicity is a global scalar weight** nudging each
  faction's authored canon move — never a scripted timeline, no learning AI, no
  lookahead. Deterministic under seed.
- **Providers are a gateway interface, not a simulation.** A provider exposes only
  `gateway_location_id`, `allegiance_faction_id`, `commitment`, and an `output`
  unit profile. It never owns ground, appears on the ownership map, or takes a
  turn; it is a diplomacy pact target (ticket 8) and, once war lands (ticket 11),
  spawns a real allied host at its gateway.
- **Integer-only, JSON-clean.** Per ADR-0001's float-determinism policy, every
  outcome-deciding comparison is integer: utility scores and `commitment` are
  `0..100` ints (not the design sketch's `0–1` fraction). All maps
  (`disposition`, `output`, `current_intent`) use **string keys** so the record
  round-trips through canonical JSON without int-key coercion.

## Consequences

- **Persistence/snapshots are unchanged.** `Faction` rides the existing entity
  list and `register_entity_type`; a save round-trips and continues
  bit-identically, exercised by a phase-2 RNG-resume test.
- **Salience is unified.** A faction carries the same derived `prominence` field a
  character does, so `chronicle.subject_prominence` scores faction events with no
  special case. Yearly intent events are deliberately low base-weight — below the
  important-only cutoff, so they stay out of the default annals but remain visible
  under "show all" and on a faction's inspection timeline.
- **Seams opened for later tickets:** conquest flips `owner_faction_id` and
  recomputes the strength/prominence cache (11); disposition mechanics and the
  provider pact surface (8); the canonicity scalar co-defined with Sauron's rise
  (14). "Contested" is *derived* but not yet *shown* — nothing occupies a region
  until hosts exist (11).
- **Substrate limitation surfaced.** Isengard and Bree-land have no matching
  region label in the `arda_ta2965` grid, so they seed with a capital but no
  painted territory (invisible on the political map). A future substrate-authoring
  pass could add `Nan Curunír` / `Bree-land` labels; Rivendell holds `Trollshaws`
  as its nominal ground meanwhile.

## Alternatives considered

- **Separate Realm / Culture / Provider classes.** More type-honest per kind, but
  it forks `owner_faction_id` into three foreign-key targets and forces war /
  diplomacy / territory to branch on concrete type everywhere. Rejected for one
  record with a `kind` tag.
- **Per-region ownership as first-class state** (a `region -> owner` map beside
  the grid). A second source of truth for who-owns-what, contradicting ADR-0001's
  "per-tile owner is the only authoritative territory state." Rejected; atomic
  region ownership is *realized* on tiles instead.
- **Fractional / influence-based territory.** Richer contested modelling, but not
  needed at this tick cadence and expensive to render legibly. Deferred (fog).
- **Fully simulating Harad / Rhûn / Khand** (internal territory, dynasties).
  Enormous scope for peoples that only ever appear as allied hosts. Rejected for
  the abstract gateway-provider interface.
