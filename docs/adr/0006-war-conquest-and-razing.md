# ADR-0006 — v1 conquest is by the capital seat; razing lays land waste

Status: **Accepted** (2026-07-21)

Records two modelling decisions the war phase (build ticket 11) makes where the
design's ideal shape needs data the v1 substrate does not yet carry. Both stay
inside the effort's "content-authoring breadth" fog and are cleanly reversible
when that content lands.

## Context

The war/battle design (`.scratch/arda-history-v1/issues/07-war-battle-system.md`)
frames conquest as *"holding a region's `seat_location_id` flips that region's
`owner_faction_id`"* and razing as *"the captured settlement's site becomes a
`ruin` kind; the conqueror still holds the seat."* Both presume state the tile
substrate (ADR-0001) does not model yet:

- **Per-region seats.** A `Region` is only `(id, name)`; it carries no
  `seat_location_id`. The *only* seats that exist are **faction capitals**
  (`Faction.capital_location_id`), authored per realm. So "besiege a region's
  seat" has no target for the ~90% of regions that are not a capital's tile, and
  a multi-region realm could never lose its outlying regions.
- **Persisted site kind.** A `Site` is frozen config (terrain/regions/sites are
  reproduced by re-loading the scenario, never serialized — ADR-0001/0004). The
  only authoritative *mutable* tile state is `grid.owner`. Turning a stormed seat
  into a `ruin` kind would need site-kind to become persisted run state, which is
  later content/persistence work, not ticket 11's.

Ticket 11 still has to make conquest and razing *actually change the world* under
a fixed seed, using only the state that exists today.

## Decision

**Conquest is decapitation by the capital seat.** A siege targets an at-war
enemy's **capital** tile. When it falls, the besieger takes the realm's **entire**
territory in one stroke (`_transfer_faction_tiles`): every tile the fallen realm
owned flips to the conqueror. A realm that loses all its ground is **extinguished**
— tombstoned with a dormant claim over the regions it held, its hosts disbanded,
and every war it was party to ended via `make_peace` — exactly as a failed ruling
line's extinction (ticket 08).

**Razing lays the land waste rather than flipping a site kind.** A ruthless
conqueror (aggressive posture, or `aggression ≥ 80`) sends the taken tiles to
**unowned** (`UNOWNED`) instead of annexing them, and emits a `razing` event. A
realm that means to *rule* what it takes (any milder power) holds the land intact.
The "settlement becomes a ruin" flavour is carried by the chronicle event, not by
a persisted site-kind change.

## Consequences

- **Wars are decisive.** Reaching and storming a capital ends a realm — canonical
  enough for the WotR theatre (take Minas Tirith and Gondor falls) and it keeps
  the map legible. Attrition wars that nibble outlying provinces are not expressed
  in v1.
- **Razing has real, persisted teeth** through the one state that *is* persisted
  (`grid.owner`): razed land visibly goes wild and is distinguishable from a clean
  annex, giving the aggressive/holding posture split a mechanical consequence
  (Orc-hosts leave ruin; a restorer annexes intact — the Saruman-seizes-the-Shire
  / Arnor-restoration seam) without inventing new persisted state.
- **Both are forward-compatible.** When per-region `seat_location_id`s are
  authored, `_sieges` gains non-capital targets and `_conquer` flips one region at
  a time — no change to the battle/siege math. When site kind becomes persisted
  run state, `_conquer` additionally stamps the seat `ruin` and razing can keep
  (waste *and* mark) rather than only laying waste.
- **Determinism is unaffected.** Every step is integer and drawn from the threaded
  RNG in a fixed order; no float reaches an outcome-deciding comparison.

## Alternatives considered

- **Author per-region seats now.** The design's ideal, but it is a substrate
  content pass (a seat + base-yield per region) explicitly held as fog until the
  authoring pass; pulling it into ticket 11 widens the ticket well past "war".
- **Persist site kind now to make `ruin` real.** Crosses into the persistence
  ticket's scope (schema, migration) for a cosmetic state change; deferred, with
  the chronicle carrying the ruin flavour meanwhile.
- **Flip only the capital's region on conquest.** Faithful to "one region per
  seat", but with no per-region seats the other regions become unconquerable, so a
  realm could never actually fall — worse than decapitation for v1.
