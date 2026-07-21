# Context — Arda History (ubiquitous language)

A glossary of the domain terms this simulation uses. Implementation lives in
`src/arda_sim/`; decisions with lasting consequence live in `docs/adr/`. This file
is *only* the shared vocabulary.

## Factions & relations

**Faction** — a power on the map, switched by `kind ∈ realm | culture | provider`.
Realms own territory and muster hosts; cultures hold ground but project little
force; providers are off-map peoples reached through a gateway.

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
