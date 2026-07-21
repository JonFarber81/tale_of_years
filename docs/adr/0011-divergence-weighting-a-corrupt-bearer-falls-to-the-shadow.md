# Divergence-weighting: a corrupt bearer's fall to the Shadow runs inverse to canon

ADR-0010 fixed canonicity as **soft weighting only**, on four **canon-ward**
forces — the knob nudges history *toward* canon, and turning it to zero flattens
those forces to their purely emergent floor. The **thrall** fall (issue #28)
breaks that one-directional framing: a bearer fallen deep into corruption may
abandon flight or quest and carry the Ring to the Dark Lord's seat, giving it
over into the *Sauron reclaims* terminal. In **canon this never happens** — the
quest resists to the end — so weighting it canon-ward would make the faithful
world the one that betrays the Ring, exactly backwards.

We therefore weight the fall by **divergence**, the inverse of `_canon_weighted`:
`_divergence_weighted(base_bp) = base_bp × (1000 − ⌊canonicity × 1000⌋) // 1000`.
At `canonicity = 1` the fall is ~impossible (the faithful world quests and
destroys); as a run diverges it climbs to its base rate (a divergent world is
where the bearer falls). Same integer permille contract as its canon-ward twin,
same derived RNG (`make_rng(f"{seed}|ring|{tick}")`, ADR-0008), just mirrored.

This makes canonicity a **five**-force knob: the four canon-ward forces of
ADR-0010 (Sauron's rise, the Ring's stirring, Free-Peoples pact odds, character
role-seeking) **plus** this one divergence-ward force. It is an **amendment to
ADR-0010, not a reversal** — every invariant that ADR turns on still holds.

Consequences worth recording:

- **Still soft weighting; still no rigged die.** The fall is a bounded seeded
  roll threshold like every other Ring move — it never fires an event of its own
  and never scales or overrides a battle die. ADR-0010's core guarantee ("soft
  weighting only, never overrides a die") is preserved; only its *count* and its
  *all-canon-ward* directionality are amended.

- **Direction is a property of the move, not the knob.** Canonicity stays a
  single 0–1 scalar. Whether a given force reads it canon-ward or divergence-ward
  is chosen per force by which helper it calls (`_canon_weighted` vs.
  `_divergence_weighted`) — the canon-ward default, the inverse the deliberate
  exception a move must opt into. Future "what if the world had fallen" behaviours
  reuse `_divergence_weighted` rather than inventing a second knob.

- **Gated on the Shadow standing, not on the year.** The fall fires only once a
  dark realm exists with a living Dark Lord and a capital to walk to
  (`_dark_realm_seat`, duck-typed off the faction record so `ring.py` keeps no
  Sauron import — the ADR-0010 dependency direction is unchanged). Before the
  rise, deep corruption clutches and claims as before; there is simply no master
  to carry it to.

- **The mortal echo of the wraith's ride.** Delivery reuses the existing
  errand + transfer machinery: a thrall bearer walks on its own race pace and,
  arriving at the seat, hands the Ring to the master via an ordinary
  `transfer_ring`, tipping into the same *Sauron reclaims* terminal a Nazgûl
  delivery reaches. No new terminal, no new writer on the Ring record — the
  single-writer discipline (ADR-0008) is intact.

- **Feeds a canon-ward force in turn.** A run diverse enough to drop the Ring
  into Sauron's hand lifts his strength through the ordinary reclaimed terminal,
  which is itself canon-baseline-weighted (ADR-0010). Divergence flowing into a
  canon-ward consequence is expected — the weighting directions describe *odds of
  a choice*, not a sign on the whole history.
