# Characters journey: a general movement layer, and the Ring is found physically

## Context

The world seeded almost empty of characters — most realms held a single ruler,
four held none, and the Shire held only Bilbo. So when the Ring was dropped (on
Bilbo's heirless death, or a slip), it lay at Michel Delving with **no character
ever on its tile**: no finder, no thief, no captor. The one actor that could
travel to it — the Nazgûl hunt — was pull-gated and a lost Ring emits no pull. The
Ring was structurally marooned and **every run ended `lying_lost`** (30/30 seeds,
diagnosed via the playtest harness). Abstract inheritance (`inheritance_heir`
teleporting the Ring to any eligible kin) hid the emptiness until movement made
location matter.

## Decision

Introduce a **general character-movement layer** rather than a Ring-special patch.
Named characters undertake purposeful **journeys** for a closed set of **motives**
(ring-seeking, kin-&-court, homecoming, ranging), reusing the existing
tile-movement primitive (`find_path` / `step_along_path`). The world is populated
by seeded **retinues** and sustained by throttled **notable generation**; the
freely-mobile class is the non-dynastic **notable**, with rulers kept at their
seats, heirs roaming readily, and campaigning generals locked to their host.

The Ring is re-acquired **physically**: it is taken up only by a character standing
on its tile — a resident finder, an arriving **seeker** (the free-peoples
counterpart to the hunt; a bounded few race for a given Ring), or a ranging
**warden** — never by abstract take-up at a distance. The sole exception is an
eligible heir already present at a bearer's death.

## Considered options

- **A Ring-special fix** (spawn a bespoke Ring-mover, keep characters static) —
  rejected: it fixes the symptom but leaves the world a map of lone rulers, and
  the requested "characters moving around doing non-war things" would still be
  absent. The general capability delivers both and the Ring mobility falls out of
  it.
- **Keep abstract acquisition** (an eligible character teleports the Ring into
  hand) — rejected: it produces no movement and reproduces the flatness we are
  removing.

## Consequences

- A **new movement phase** is ordered with the other movers (armies, hunt) before
  the Ring phase, so an arriving seeker/warden is on the tile when the Ring phase
  looks. This edits the pipeline order — the reproducibility contract — deliberately.
- Journey decisions draw from an **isolated per-tick RNG** (the ADR-0008 pattern),
  so the character layer does not perturb the shared war/diplomacy stream: existing
  histories are not silently rewritten by adding characters.
- **No new terminal logic.** Putting a bearer back in play is enough — the existing
  corruption / errand / quest / thrall rolls now finally run, so *destroyed* and
  *Sauron reclaims* become reachable again. The fix is measured on the playtest
  harness (`ring_outcome` no longer ~100% `lying_lost`).
- Eligibility rules (rulers seated, generals locked) keep the war and succession
  machinery from being destabilised by the new mobility.
