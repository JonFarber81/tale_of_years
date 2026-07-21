# Canon pressure is soft weighting only, computed on the dark realm's record

Sauron's rise (issue #5) is a single scalar, `sauron_strength`, recomputed each
phase 7 as `canon_baseline(year) × canonicity + Σ emergent_deltas` and cached on
the **Mordor faction record** (zero on every other faction) rather than on the
`World`. We chose the faction record because everything inspectable in this sim
is an entity — the scalar snapshots, persists, and reads in a dossier for free —
and because the spec's own framing is "Sauron = the Mordor faction + a scalar".
The emergent Σ is a bounded accumulator folded forward by an event-id watermark
scan (each battle or conquest counts exactly once, then fades yearly), plus
stateless checks read off current state (the Ring's `pull`, a fallen dark
vassal, Minas Morgul lost *after having been held*).

The canonicity knob is applied as **soft weighting only**, to exactly four
forces: the baseline term of Sauron's rise, the Ring's stirring (ring.py's
canonicity-weighted rolls), Free-Peoples pact odds (diplomacy), and character
role-seeking (phase 7). It never fires an event, never overrides a die. At
`canonicity = 0` the baseline term vanishes and the strength flattens to the
purely emergent deltas.

Consequences worth recording:

- **A derived RNG, like the Ring's.** Every stochastic choice the Sauron phase
  makes draws from `make_rng(f"{seed}|sauron|{tick}")`, never the shared stream
  (ADR-0008's pattern). Turning canonicity up or down therefore changes *which
  intents win* and *which soft rolls pass*; no battle roll is ever scaled or
  overridden by it. (Downstream, a canonicity-shifted decision — a pact that now
  forms, a hunt that now rides — legitimately changes what later phases draw:
  the divergence flows through decisions, never through a rigged die.)
- **The hunt moves; the Ring phase seizes.** The Nazgûl hunt is a `Hunt` entity
  (a transient tile-mover like an Army) advanced in its own pipeline slot between
  movement and war. It *reads* the Ring's `pull` and tile and never writes the
  Ring record — the capture attempt itself is rolled by the Ring phase (after
  war), preserving the single-writer discipline on the Ring.
- **Terminal outcomes are flags plus tombstones.** Destroyed / reclaimed /
  lying-lost each raise a key in the new `World.flags` dict (persisted, schema
  v4). The entities themselves carry the truth (the Ring `destroyed`, the Nine
  `destroyed`, Mordor extinguished through the ordinary war seam over subsequent
  ticks); the flags are the cheap world-transition switches later systems and
  the UI read without scanning the log.
- **One-tick lag by construction.** Phase 7 never musters, moves, or fights: it
  writes the strength scalar, nudges provider commitment and canon roles, and —
  after the destroyed terminal — unwinds the dark realm's territory. Phases 2–4
  consume the scalar the *next* tick (musters, hunt activation, pull decay), per
  the spec's phase-flow contract.
- **"Pull-rise weighting" is implemented as decay slowdown.** The Ring alone
  writes `pull`; Sauron's strength therefore weights how slowly it *ebbs*
  (a strong Shadow's gaze lingers) rather than adding a second writer to the
  spikes — the same net "his rise keeps the Ring loud", single-writer intact.
