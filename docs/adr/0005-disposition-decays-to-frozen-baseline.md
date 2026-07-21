# ADR-0005 — Disposition decays toward a frozen canon baseline, not toward zero

Status: **Accepted** (2026-07-20)

Motivated by build ticket 09 (diplomacy & vassalage), the first system that
*evolves* the `Faction.disposition` map rather than only reading its seeded
values. Establishes what "yearly decay toward a baseline" (the ticket's phrase)
actually targets.

## Context

`Faction.disposition` is a sparse, asymmetric `-100..100` map authored at seed:
Gondor→Rohan `+80`, Gondor→Mordor `-100`, and so on. These authored values *are*
the canon temper of Middle-earth — who is whose ally and whose ancient enemy.

Ticket 09 makes phase 3 evolve this map: event-driven jumps (marriages, treaties,
betrayals, war) push it around, and between shocks it **decays back toward a
baseline**. The question is what the baseline is. Two readings:

- **Zero.** Every relation drifts toward indifference; the authored values are a
  starting condition only. Over decades Gondor and Rohan forget they are allies
  unless fresh events keep topping the disposition up. One map, simplest code.
- **The authored seed value.** Each pair returns to the temper it was authored
  with; the canon allegiances are lasting *attractors*, not just an opening
  position. Requires remembering the seed value separately from the live,
  evolving one — a second, immutable map.

Decay-to-zero is cheaper but corrosive to the setting: the single most important
thing the disposition map encodes (Gondor and Mordor are irreconcilable; Gondor
and Rohan are sworn friends) would erode on its own. A border-friction nudge or a
stray war would, given enough quiet years, leave every faction equally indifferent
to every other — the opposite of a legendarium that *remembers*.

## Decision

**At seed, snapshot the authored dispositions into an immutable
`baseline_disposition` map on each faction. The live `disposition` map evolves
under events and decays each year toward `baseline_disposition`, never toward
zero.**

- **`Faction.baseline_disposition: Dict[str, int]`** — same shape and string keys
  as `disposition`, written once at seed (a copy of the authored values) and never
  mutated thereafter. An absent pair has baseline `0` (true indifference is a
  valid, stable attractor for factions with no authored feeling).
- **Yearly decay** (gated on the year boundary, `world.month == 1`, since the
  clock is monthly per ADR-0003): each live entry steps a small fixed integer
  amount toward its baseline, clamped, and stops once it reaches it. Integer math
  only, so the walk is bit-reproducible.
- **Blood-enemies never reconcile on their own.** Gondor↔Mordor decays *toward*
  `-100`; only a (currently near-impossible) sustained run of positive events
  could lift it, and quiet years pull it back down. Incidental hostility between
  two factions with a neutral baseline *does* cool off. This falls out of the
  model for free — no special-casing of "permanent" wars.

## Consequences

- **Two maps per faction.** `baseline_disposition` (frozen) and `disposition`
  (live). Both serialize as ordinary dataclass fields; persistence and snapshots
  carry them with no special handling, and `entity_from_dict`'s field-filtering
  keeps old saves loadable.
- **The baseline is authored exactly once**, in the seed roster, alongside the
  opening dispositions it copies — there is no separate baseline authoring surface
  to keep in sync.
- **Peace between sworn enemies is unreachable by decay alone** — intentional. It
  is the correct default for the setting, and ticket 11 (war) will add exhaustion
  as the external force that can end even a baseline-hostile war.
- **Retuning is safe.** The decay step is one isolated integer constant; the
  baseline values live with the roster. Neither is load-bearing on structure.

## Alternatives considered

- **Decay toward zero (one map).** Simpler and cheaper, but washes out the canon
  temper the disposition map exists to encode; makes "Gondor and Rohan are allies"
  a fact with a half-life. Rejected — the model should remember the legendarium,
  not forget it.
- **A computed baseline (from posture/canonicity) instead of a stored one.** Would
  avoid the second map, but reintroduces authoring the temper indirectly through
  knobs that were not chosen to express pairwise relations, and couples decay to
  fields that move for other reasons. Heavier and less legible than storing the
  authored value verbatim.
