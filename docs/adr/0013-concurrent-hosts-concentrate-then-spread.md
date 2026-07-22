# A realm fields several hosts at once, concentrating before it spreads

Status: accepted — implemented by issue #33.

ADR-0009 gave each faction (really each coalition) **one standing host at a time**,
gated by a size-scaled muster cooldown. That kept the map from churning with small
annual levies, but it also meant Mordor — the one power that should be able to wage
war on several fronts at the height of its strength — could only ever field a single
host. We are lifting the one-host cap to a **strength-scaled ceiling on concurrent
hosts**, and giving a realm with several hosts a **concentrate-then-spread** doctrine:
it masses on its strongest enemy first and only fans *surplus* hosts out to weaker
fronts. A host also now **stands down the moment its war ends**, so raising more of
them cannot silently pin a realm at its ceiling.

We chose this because "Sauron fields multiple armies across multiple fronts" is part
of the War-of-the-Ring shape we want the history to read as — but it collides head-on
with ADR-0012's invariant that Mordor must remain **conquerable**. The whole of this
ADR is about where those two forces balance.

## Considered options

- **Raise the ceiling but keep a single front (all hosts on the lowest-id enemy).**
  Rejected: it fields multiple armies but they dogpile one target, so it does not
  give the multi-front war we set out to model.
- **Full, even multi-front spread — a fresh host always opens the least-covered
  front.** Rejected empirically. On the `epoch` seed it made Mordor *unkillable*:
  every host it spread to a secondary front intercepted a West host marching on
  Barad-dûr, so the coalition that must storm the seat was broken up piecemeal and
  the Black Land never fell (violating ADR-0012). Verified by sweep — see below.
- **Concentrate-then-spread with a strong ceiling (cap 5).** Rejected: even
  concentrating three hosts on its primary foe, a fifth roaming host still let
  Mordor shatter the coalition. No head-start setting at cap 5 both spread *and*
  fell.
- **Accept a stronger Mordor and re-point the two-sided test** — let real multi-front
  stand and prove "conquerable" only at *low* canonicity / adversarial seeds.
  Considered seriously (it aligns with ADR-0012's letter — "durable, not
  invincible"), but rejected for now: it weakens the high-canonicity guarantee the
  `epoch` test was built to hold, and we found a setting that keeps both.
- **Strength-scaled concurrent hosts, cap 4, concentrate-then-spread with a two-host
  primary head-start.** Chosen. It is the setting where Mordor both wages a genuine
  two-front war *and* still falls late (TA 2997 on `epoch`), the two-sided outcome
  ADR-0012 demands.

## The tension, quantified

The `epoch` seed was swept over (host ceiling × primary-front head-start), asking
only "does Mordor still fall?":

| ceiling | head-start | Mordor's split at the pile-on | outcome |
| --- | --- | --- | --- |
| 5 | 1–2 | 3 on primary, 1+1 elsewhere | **survives forever** |
| 4 | 1 | 3 on primary, 1+1 elsewhere | survives forever |
| **4** | **2** | **3 on primary, 1 peeled off** | **falls TA 2997** |
| 3 | 1 | 2 on primary, 1 peeled off | falls TA 2997 |
| any | ≥3 | effectively single-front | falls, but no real spread |

The lesson is that **Mordor's fall depends on it *not* intercepting the coalition**.
Concentration is therefore load-bearing, not cosmetic: the feasible multi-front
envelope is narrow, and `ceiling = 4, head-start = 2` sits on its edge — the most
spread that still leaves the West enough clear approaches to Barad-dûr.

## Consequences

- **The one-host rule of ADR-0009 is relaxed to a ceiling.** `max_concurrent_hosts`
  is `1 + military_strength // 40 + sauron_strength // 40`, capped at
  `MAX_CONCURRENT_HOSTS = 4`. A weak realm or culture still fields a single host; a
  strong realm two or three; peak Mordor four. The size-scaled muster cooldown of
  ADR-0009 is unchanged and still paces *re-raising* a host once one leaves play —
  the ceiling raises the peak, the cooldown paces the refill.
- **Fewer hosts never means smaller hosts.** Muster size scales with the same
  strength that raises the ceiling, so a realm that fields more hosts fields
  *bigger* ones — the tiny-army swarm ADR-0009 guarded against does not return.
- **Concentrate-then-spread.** `_march_target` ranks a realm's war enemies by threat
  (`military_strength + sauron_strength`) and gives the strongest a
  `PRIMARY_FRONT_HEAD_START = 2` head-start, so the primary front takes the opening
  hosts before a second opens and surplus hosts fan out to weaker foes. Ties break
  toward the greater threat, then the lower id (deterministic).
- **Multi-front is, in practice, a Mordor-scale phenomenon.** ADR-0012's readiness
  gate lets a faction *declare* only one war at a time, so a realm gains several
  war-enemies only when it is **piled onto** — and Mordor is the pile-on target. A
  cap-2 or cap-3 realm with a single enemy still fields one front; the spread shows
  up when the whole West declares on the Shadow at once.
- **A host stands down when its war ends** (`_stand_down_ended_wars`, run at the top
  of the movement phase). Previously `make_peace` cleared the war flag but left any
  marching host in play; it would arrive, garrison a former enemy's seat, and never
  disband — a zombie that, under the raised ceiling, permanently pinned a realm at
  its host count once its wars resolved. This was a latent bug the one-host cap had
  masked; the ceiling made it load-bearing, so it is fixed here.
- **`epoch` still falls, later.** Mordor lives through its buildup and falls at
  TA 2997 (was TA 2992 under the one-host model) — still comfortably inside the
  War-of-the-Ring window and after a real rising-Shadow arc, so the two-sided
  ADR-0012 guarantee holds.
- **Knife-edge, watch it.** `ceiling = 4, head-start = 2` is one step past the
  survives/falls boundary. A future change to battle resolution, march pace, or
  muster sizing could flip `epoch` back to surviving. The `epoch` fall test is the
  tripwire; if it ever goes red on an unrelated change, this balance — not the other
  change — is likely what moved.
- **Deferred.** Distance- and posture-aware fronts (a realm defending its own seat
  when besieged rather than marching out), and true per-front coalition combining so
  the West massed on one approach can overwhelm a spreading Mordor, would loosen this
  knife-edge and are left as future work. So is revisiting whether "conquerable"
  should be proved at low canonicity instead — the alternative weighed and set aside
  above.
