# 11 — War & battles (phase 5)

**What to build:** Armed conflict that changes the world. When hostile hosts meet, phase 5 resolves a battle by strength-ratio plus a bounded seeded roll; fortified seats are besieged over multiple years; taking a region's seat flips its ownership and the conqueror may raze it to a ruin; named generals occasionally fall (even in victory) and trigger succession; committed provider hosts (mûmakil, corsairs) fight. The viewer watches wars reshape the map and reads them in the annals.

**Blocked by:** 08, 09, 10

**Status:** done

- [x] Battle triggers when enemy hosts share a tile or an adjacent tile, or a host sits on an at-war enemy's fortified capital seat (→ siege); hosts, sieges, and providers are all processed in a fixed id/tile order; only factions flagged at-war (ticket 09) fight (a provider fights its patron's wars). — `war._field_battles`/`_sieges`/`_hosts_engage`.
- [x] Resolution: `effective_strength = size × leader × provider × (defender) terrain/posture`, one bounded seeded roll tilting the ratio both ways → tier → integer casualties; winner holds the field, loser retreats toward home or is destroyed; emits `battle`. Upsets possible; canonicity never touches the dice. — `war._resolve_battle`/`_effective_strength`.
- [x] Sieges persist across ticks (`Army.siege_progress` accumulates against a per-site-kind fortification); on fall the attacker takes the realm → ownership flips (`conquest`), a total loss **extinguishes** the realm (tombstone + dormant claim, wars ended), with an optional **raze** (land laid waste) by posture/aggression. — `war._press_siege`/`_conquer`/`_extinguish`.
- [x] Named-character death = rare post-battle/storming integer roll (higher on the losing side, blunted by `martial`); on death → tombstone + `death (killed_in_battle)`; a slain ruler vacates `leader_id` and the next tick's succession seats the heir. — `war._maybe_slay`/`_roll_battle_deaths`.
- [x] Provider hosts fight as ordinary armies with unit-type modifiers; Corsairs never march — they resolve as occasional (once-a-year, seeded) coastal raids that pillage an enemy shore without seizing a seat. — `war._muster_providers`/`_provider_factor`/`_coastal_raids`.
- [x] Battle/siege/conquest/razing/coastal-raid events carry prose + salience base-weights; casualties, victor, and territory changes ride the payload and are inspectable. — `chronicle.BASE_WEIGHT`/`_render_battle` … `_render_coastal_raid`.
- [x] Tests: strength dominates on average but upsets occur; sieges span multiple ticks; conquest flips ownership; named death triggers succession; all outcome-deciding math is integer/fixed-point. — `tests/test_war.py` (21 tests).

**Also fixed:** `ui/app.build_window` never attached `world.grid`, so the UI ran neither movement (phase 4) nor war (phase 5) — the political map never moved. Now attaches it (ADR-0004), matching `seed_world`.

**v1 simplifications (documented, within the content-authoring fog):** conquest is by the **capital** seat only (taking it takes the whole realm) — per-region seat_location_ids are future content. Razing lays a region **waste** (owner → unowned) rather than flipping a persisted site kind to `ruin`, since site-kind state isn't persisted until later; the chronicle records the razing.
