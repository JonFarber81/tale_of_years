# 09 — Diplomacy & vassalage (phase 3)

**What to build:** How factions relate peacefully and bind together. Phase 3 evolves an asymmetric disposition scalar per faction pair and derives a discrete stance (alliance/neutrality/hostility/vassalage); marriages, treaties, and betrayals move it; vassalage bonds let a realm serve a high king (the Reunited-Kingdom mechanism) and model provider-pacts. Relationship changes appear in the annals.

**Blocked by:** 07, 08

**Status:** ready-for-agent

- [ ] Phase 3 maintains the shared asymmetric `disposition` map (sparse; absent = seeded baseline): yearly decay toward baseline + event-driven jumps (marriages, treaties, betrayals, shared/opposed wars, border friction); derives stance + pinned flags (signed treaty, at-war boolean, vassalage bond).
- [ ] Marriage seam: phase 3 decides *whether* a marriage happens (utility off disposition + eligible unwed heirs); the kinship effect is created via ticket 08's machinery.
- [ ] Vassalage = directional `overlord_faction_id` bond: vassal musters for its overlord (read by war), keeps its own succession/dormant claim, can break free; used for the restoration arc (bond, not merge) and for provider-pacts (raise/lower `allegiance`/`commitment`).
- [ ] `treaty`, `marriage`, `provider_pact`, `war_declared`/`war_ended` events emitted with prose + salience weights; the at-war flag is set/cleared here (war executes in ticket 11).
- [ ] Diplomacy is inspectable (a faction's stances toward others).
- [ ] Tests: disposition drift + event jumps deterministic; a vassalage bond forms and can dissolve; the war-declaration flag is owned here.
