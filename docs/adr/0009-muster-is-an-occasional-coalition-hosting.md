# Muster is an occasional coalition hosting, not an annual per-faction levy

Status: accepted — implemented by issue #13.

We are shifting the army model from *each faction re-raising a host whenever it
holds none* (an effectively annual levy) to **mustering as a rare, heavy
war-effort**: a faction may field a host only while **at war**, and only after a
**cooldown that scales with the size of the host it last raised** (a great hosting
depletes the realm's manpower for longer). Allied and vassal belligerents sharing
the *same* war **combine their levies into a single coalition host** at the lead
belligerent's muster point. We chose this so the history reads as a few great
campaigns punctuated by decisive battles rather than a churn of small annual
hosts on the map — the "fewer but larger armies and very key battles" goal.

## Considered options

- **Keep annual per-faction mustering, only inflate the size and decisiveness
  constants.** Rejected: bigger numbers still leave the map busy with many
  concurrent hosts — the exact thing we set out to cut.
- **Muster frequency as the master lever, plus coalition combining.** Chosen: the
  one change that simultaneously yields fewer hosts, lets each be larger, and
  concentrates named leaders into the few hosts that exist.

## Consequences

- **"A faction fields at most one standing host" becomes "a *coalition* fields one
  host."** A combined host is owned by the lead faction; its size is the sum of
  contributors' strength-derived contributions; its **general is the ablest
  eligible leader across the whole coalition**. Each contributor still only
  contributes if its own at-war + cooldown gate allows.
- **Hosts are led by a fallback ladder,** so a leaderless host becomes vestigial:
  ablest field-eligible non-heir → else the **heir** (who may then die in battle,
  with succession seating the next) → else a **generated named captain** (a
  non-dynastic character outside the succession/kinship line). This deliberately
  introduces a new, generated character sub-population.
- **Battle destruction becomes proportional to a host's own mustered strength,**
  not a flat absolute floor (which is meaningless once hosts are large), so a
  single key battle can shatter a coalition host and effectively decide a war.
- **An outmatched host may refuse battle** — a seeded, can-fail evasion — so a
  decisive-battle world is not a deterministic execution of the weaker side.
- **March pace is per-faction** (defaulting by people), replacing the single
  global miles/year, which also gives the evasion/pursuit contest real texture.
- **v1 simplifications, deferred for later realism:** coalitions combine
  regardless of distance and march at the *lead* faction's pace; distance-gating
  the coalition (within X miles) and marching at the *slowest* contributor's pace
  are later enhancements. Troop composition (unit-types) is issue #14; a named
  skills layer beyond the six traits is issue #9.
