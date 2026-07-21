# The One Ring is a single artifact record with a bearer XOR location invariant

The Ring is modelled as one bespoke `Ring` entity (there is exactly one per run),
not as a role on a character or a generic item type. Its core invariant is that
**exactly one** of `bearer_id` and `location_id` is set — it is always either
borne by someone or lying at a definite place, never both and never nowhere — and
all six ways it changes hands funnel through a single `transfer_ring` primitive
that is the one place the invariant is enforced. We chose a dedicated record over
a character flag because the Ring outlives every bearer, carries its own scalars
(`corruption`, `pull`) and journey, and must be found on the map and inspected as
a first-class thing; a bespoke single record over a general inventory system
because there is only ever one and a full item model would be speculative.

Two consequences worth recording:

- **Its own per-tick RNG.** The Ring phase draws from a `random.Random` derived
  from `(seed_str, tick)` rather than the pipeline's shared stream. This deviates
  from the "single seeded RNG threaded through every system" contract on purpose:
  it keeps the Ring's stochastic life reproducible from persisted state while
  neither perturbing nor being perturbed by how many armies happened to march that
  tick — so adding the Ring left every existing seeded run's behaviour byte-stable.
- **Runs after war, as its own phase.** The Ring phase sits after war (phase 5) so
  it can answer a bearer felled this tick — by lifecycle or violence — and read
  who now holds the ground a fallen Ring lies on (war-capture). The ticket's
  "inheritance = phase 1 / capture = phase 5" seams are satisfied by *reading* the
  state those phases leave, not by splitting the Ring's logic across them.

Terminal fates were deliberately out of scope here and left stubbed for ticket 14;
they have since landed with issue #5 (see ADR-0010): destruction at active
Orodruin, Sauron reclaiming, and the lying-lost holding pattern all resolve in
the Ring phase, keeping the record single-writer. A non-Sauron claim remains a
transient high-corruption event.
