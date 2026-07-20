# 10 — Armies & movement (phase 4)

**What to build:** Hosts that muster and march. A faction's muster intent raises an army led by its ablest character; phase 4 advances armies node→node along routes by a miles/year budget, bleeding strength to attrition on bad terrain or far from friendly seats. The viewer watches armies move across the map.

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] `Army` record: `faction_id`, `leader_id`, `position` (a location id or `(route_id, progress)`), integer `size`.
- [ ] A muster intent (from phase 2) instantiates an Army at the faction's capital/seat, sized from a region-derived manpower pool; leader = highest `martial`+`leadership` eligible character, assigned `role=general`.
- [ ] Phase 4 advances each army along routes by its miles/year budget (route `kind`/terrain modulates speed); integer attrition applied for hostile/barren distance from friendly seats.
- [ ] Armies render on the map moving between locations/along routes; an army is inspectable (leader, size, destination).
- [ ] `muster`/movement-related events emitted with prose + salience weights.
- [ ] Tests: muster sizing deterministic; movement advances the right number of nodes per year under a fixed seed; attrition is integer and reproducible.
