# War is gated by provocation and readiness, not raised on an ATTACK intent

Until now the diplomacy phase collapsed **hostility** into **at-war**: whenever a
faction's ATTACK intent won the phase-2 menu, `_maybe_declare_war` raised the
symmetric at-war flag that same tick, unconditionally. Because the TA 2965 roster
seeds nearly every power with a strongly negative disposition toward Mordor
(Gondor −100, Dúnedain −90, Rohan/Dale/Durin −60..−80), ATTACK
(`aggression + hostility`) dominated every hostile neighbour's menu at once, so a
whole ring of wars was declared in the opening year, a decisive siege stormed
Barad-dûr within a few ticks, and the v1 decapitation rule extinguished Mordor
whole by TA 2968 — on every seed (issue #26). The entire rising-Shadow arc (#5)
was dead code in practice.

We decided that **disposition is a ceiling, not a trigger**. Winning the ATTACK
menu no longer declares war by itself; the leap from stance to the pinned at-war
flag is gated by two new conditions:

- **Provocation** — a faction only grows willing to declare on a disliked power
  that is *actually threatening*: one belligerent lately, or — for the dark realm
  — whose `sauron_strength` has crossed a visibility threshold. A dormant, weak
  neighbour provokes no one however old the enmity. Declaration is a staggered
  per-year roll rather than an automatic flip.
- **Readiness** — a faction opens a *new* war only when it can prosecute one (not
  already at war on another front, past its cooldown).

## Considered alternatives

- **A static disposition threshold** (declare when disposition ≤ some floor).
  Rejected: six realms already sit past any sane floor toward Mordor, so it
  reproduces the simultaneous pile-on, merely a year or two later.
- **Softening the decapitation rule** so a stormed seat costs only its region and
  a large realm survives as a rump. Left out of scope: once the pile-on is
  defused at the *declaration* seam, general decapitation softening is no longer
  load-bearing for this bug, and reworking how every conquest carves territory is
  a far larger, riskier change. Recorded as possible future work.
- **A bespoke `sauron_strength` siege-resistance bonus** to keep Barad-dûr
  standing. Rejected because it would violate ADR-0010's invariant that
  *canonicity never touches the war dice* — `sauron_strength` is largely
  canonicity-derived. Mordor's durability is instead carried by honest channels:
  authored Black-Gate-tier `fortification` on the seat (a static defensive stat)
  plus `sauron_strength` raising Mordor's `military_strength` (the same honest
  comparison it already feeds through musters). The Black Land grows harder to
  storm as the Shadow rises without any die being rigged.

## Consequences

- **TA 2965 opens quiet.** A weak, peaceable Mordor provokes no declarations, so
  the canon ramp gets its buildup years for free; the West wakes only as
  `sauron_strength` climbs past visibility and Mordor's musters begin striking
  out. This is the intended arc, not a Mordor-only shield.
- **Durable, not invincible.** Mordor must remain *conquerable* under adversarial
  conditions (low canonicity, a determined coalition). The fix is verified
  two-sided: the Shadow arc engages at high canonicity *and* Mordor can still be
  taken — guarding against an over-fix that trades one degenerate outcome
  (always conquered) for its mirror (always victorious).
- **Deferred.** The seeded anti-Mordor hostility is *authored* static hate that
  nobody earned. Tying disposition accrual to a realm's actual deeds
  (Barad-dûr raised, orc-raids, the Nazgûl stirring) is a separate future issue;
  this ADR only stops static hostility from *triggering* war, it does not change
  how that hostility comes to be.
