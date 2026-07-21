# 10 — Armies & movement (phase 4)

**What to build:** Hosts that muster and march. A faction's muster intent raises an army led by its ablest character; phase 4 advances armies node→node along routes by a miles/year budget, bleeding strength to attrition on bad terrain or far from friendly seats. The viewer watches armies move across the map.

**Blocked by:** 07

**Status:** done

- [x] `Army` record: `faction_id`, `leader_id`, integer `size`, plus the position as a **tile** `(col, row)` with a remaining `path` of tiles, a `dest_site_id`/`target_faction_id`, and the carried `move_points`/`miles_per_year` budget (routes were superseded by the tile substrate — ADR-0001, so `position` is tile coords, not `(route_id, progress)`). — `armies.Army`.
- [x] A `MUSTER`/`ATTACK` intent (phase 2) instantiates a single host at the faction's seat, sized from a territory-derived pool (`muster_size` = base levy + a slice of `military_strength`); leader = the ablest field-eligible member by `martial`+`leadership` (the ruler stays home), assigned `role=general`. A one-host-per-faction cap keeps the monthly re-decision from spawning a fleet. — `armies._muster/_raise_army/_muster_leader/muster_size`.
- [x] Phase 4 advances each host tile→tile along a deterministic Dijkstra path by an integer per-tick budget (roads cheap, rough ground dear — terrain modulates speed via tile move-cost); integer attrition each marching tick on harsh (barren/marsh/mountain) or rough ground plus an off-friendly-soil toll that **deepens with distance from a friendly seat** (tracked as `supply_lag`, the run of ticks off home ground, capped), disbanding a host bled to nothing. — `armies.movement/_advance/find_path/tick_speed/_attrition`.
- [x] Hosts render as faction-coloured markers moving across the map (rebuilt per snapshot); a host is inspectable (leader, size, destination). — `map_view.refresh_armies`; `mainwindow.describe_army/_army_on`.
- [x] `army_mustered`, `army_arrived`, `army_disbanded` events emitted with prose + salience weights. — `chronicle` weights/renderers.
- [x] Tests: muster sizing is a pure deterministic function; movement advances a fixed number of tiles/year under the budget (one plains tile a month, quicker on roads); attrition is integer/reproducible; find_path routes around and into impassable terrain deterministically; seeded-run determinism + save/load round-trip + snapshot isolation. — `tests/test_armies.py`.

## Notes

- **Position is tile coords, not `(route_id, progress)`:** ADR-0001 superseded the two-layer region/route model with a tile substrate, so a host stands on a tile `(col, row)` and carries the *remaining* tile `path` to its objective (a fixed-order Dijkstra by terrain move-cost). Movement budget is an integer effort accrual spent against per-tile costs — on open plains one tile a month (`tick_speed(180, 15) == 2`, plains cost 2), quicker on roads.
- **Objectives are the ticket-11 seam:** a mustered host marches on a war enemy, else the most-hated seated realm (providers are never objectives); it garrisons if none is reachable. It reaches the enemy seat and **holds** — actually fighting/sieging is ticket 11. No RNG is drawn (muster and movement are pure), so the phase never perturbs the shared stream.
- **Grid dependence, per ADR-0004:** movement reads `world.grid` for terrain/ownership/pathing. A *reloaded* world carries no grid until ticket 12, so armies freeze there and it diverges from a live run — resume is bit-identical only once the painted grid is re-attached (the same-seed repaint ticket 12 restores). Army state (position, path, size, leader) itself round-trips.
