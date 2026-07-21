# War-layer tuning baseline (issue #13)

Captured **before** any tuning, so the re-balanced war layer is calibrated against
reality rather than vibes (issue #13, first implementation step). Produced with:

```
arda-sim --seed <seed> --years 100 --summary
```

against the pre-#13 code (annual per-faction levy, adjacency battles, flat
destroy floor). One century, four seeds:

| seed            | musters | battles | decisive | destroyed | median size | led |
|-----------------|--------:|--------:|---------:|----------:|------------:|----:|
| fellowship      |     596 |      53 |       40 |       587 |         500 |  0% |
| war-of-the-ring |     590 |      27 |       19 |       580 |         500 |  0% |
| third-age       |     579 |      15 |       10 |       571 |         500 |  0% |
| great-war       |     581 |      13 |        9 |       572 |         500 |  0% |

**What it shows (the busy-map problem):**

- **~580–600 musters a century** — a host raised almost every year by almost every
  realm; the map is never quiet.
- **median host size 500** — exactly `MUSTER_BASE`, i.e. the median mustering realm
  contributes ~0 strength; hosts are small and uniform.
- **0% led** — the seeded roster is rulers + heirs with almost no *field-eligible*
  third character, so nearly every host marches leaderless. This is the clearest
  motive for the **leader ladder** (fall back to the heir, then a generated
  captain) — not merely a nicety.
- battles/decisive swing widely by seed but there are **dozens** of small clashes,
  not a few great ones.

**Directional targets after #13** (calibrated, not hard thresholds): decisive
battles into the low single digits per century, median host size up several-fold,
~all hosts led, few concurrent standing hosts.

## After #13 (tuned)

Same command and seeds, against the shipped retuning (coalition Gathering, muster
cadence, shared-tile-only + proportional-destruction battles, can-fail evasion,
leader ladder). One century:

| seed            | musters | battles | decisive | conquests | destroyed | median size | led |
|-----------------|--------:|--------:|---------:|----------:|----------:|------------:|----:|
| fellowship      |      10 |       1 |        0 |         2 |         6 |        8540 | 100%|
| war-of-the-ring |      10 |       0 |        0 |         2 |         6 |        8540 | 100%|
| third-age       |      10 |       1 |        0 |         2 |         6 |        8540 | 100%|
| great-war       |      10 |       1 |        1 |         2 |         7 |        8540 | 100%|

**What changed vs. baseline:**

- **Musters ~580 → ~10 a century.** Hosts are episodic, not annual: the at-war gate
  plus a size-scaled cooldown keep realms out of the field between campaigns.
- **Median host size 500 → ~8540 (≈17×).** Coalition summing plus the tuned levy
  constants make each host a heavy war-effort.
- **0% → 100% led.** The leader ladder (non-heir → heir → generated captain, and a
  captain for provider hosts too) means no host marches leaderless.
- **Decisive engagements are now a handful, not dozens.** Field battles are rare
  (shared-tile-only) — most war resolves as **~2 decisive conquests a century** via
  siege; when a pitched battle does fire, proportional destruction can shatter a host
  and end a war in one stroke.
- **Evasion** is built and tested but rarely *fires* in canon runs: field encounters
  are scarce and most clashes are at seats (where a defender is besieged and cannot
  flee), so it triggers only when an outmatched host is caught in the open. It
  remains a real, deterministic, can-fail mechanism (see the war tests).
