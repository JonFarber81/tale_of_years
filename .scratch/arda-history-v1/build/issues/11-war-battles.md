# 11 — War & battles (phase 5)

**What to build:** Armed conflict that changes the world. When hostile hosts meet, phase 5 resolves a battle by strength-ratio plus a bounded seeded roll; fortified seats are besieged over multiple years; taking a region's seat flips its ownership and the conqueror may raze it to a ruin; named generals occasionally fall (even in victory) and trigger succession; committed provider hosts (mûmakil, corsairs) fight. The viewer watches wars reshape the map and reads them in the annals.

**Blocked by:** 08, 09, 10

**Status:** ready-for-agent

- [ ] Battle triggers when enemy hosts share a location or a border route segment, or a host sits on an enemy-owned settlement (→ siege); resolution order deterministic by location id; only pairs flagged at-war (ticket 09) fight.
- [ ] Resolution: `effective_strength = size × leader_factor × terrain/posture × provider-unit modifiers`, one bounded seeded roll → outcome tier → integer casualties; winner holds the field, loser retreats or is destroyed; emits `battle`. Upsets are possible; canonicity never touches the dice.
- [ ] Sieges persist across ticks (`besieging` state + accumulating progress; fortification bonus); on fall the attacker holds the `seat_location_id` → ownership flips (`conquest`) with an optional **raze** (→ `ruin`, `razing`) by posture.
- [ ] Named-character death = rare post-battle scaled roll (higher on the losing side, lowered by `martial`); on death → tombstone + `death (killed_in_battle)` + trigger ticket 08 succession.
- [ ] Provider hosts fight as ordinary armies with unit-type modifiers; Corsairs resolve as coastal raids on coast regions (no seat seizure).
- [ ] Battle/siege/conquest/razing events carry prose + salience weights; casualties, victor, and territory changes are inspectable.
- [ ] Tests: strength dominates on average but upsets occur; sieges span multiple ticks; conquest flips ownership; named death triggers succession; all outcome-deciding math is integer/fixed-point.
