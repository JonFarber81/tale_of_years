# 13 — The One Ring

**What to build:** The Ring as a real, tracked object — the gravitational centre. It starts quietly with Bilbo at Bag End, always has a definite location (borne by someone, or lying where it fell), and changes hands by inheritance, theft, loss, being found, capture in war, or a deliberate errand. It corrupts and prolongs its bearer, marks former bearers, and its use draws danger. The viewer can always find the Ring on the map and read its journey.

**Blocked by:** 08, 10, 11

**Status:** migrated — now tracked on GitHub as [#3](https://github.com/JonFarber81/tale_of_years/issues/3) (2026-07)

- [ ] Single bespoke `Artifact` record with the invariant `bearer_id` **XOR** `location_id` (exactly one non-null), seeded borne by Bilbo at Hobbiton with low scalars.
- [ ] Movement: a passenger that advances on its bearer's miles/year budget in phase 4 (emit `ring_moved`); unborne it does not move; high `pull` raises loss/theft/betrayal odds (not autonomous locomotion).
- [ ] Transfer-mode enum, each a canonicity-weighted seeded roll fired by the owning phase: inheritance/gift (phase-1 seam, biased along ticket 08 kinship — the Bilbo→heir *tendency*, never scripted), theft, loss/drop, found, war-capture (phase-5 seam), deliberate errand toward a goal node.
- [ ] Two integer scalars: `corruption` (per-bearer, trait-modulated, grows while borne, **attenuates not resets** on transfer; low = suppresses natural death / longevity, mid = secrecy bias, high = may claim it) and `pull` (global, spikes on use).
- [ ] The Ring renders on the map (from bearer position, or at its own location) and is inspectable with its full transfer/bearer history.
- [ ] A non-Sauron claim is a transient high-corruption event (not a terminal); terminal handling stubbed for ticket 14 to complete.
- [ ] Tests: XOR invariant holds after every tick; each transfer mode reproduces under a fixed seed; corruption grows/attenuates; pull rises on use; inheritance favours a canon heir under high canonicity but can diverge at low.
