# 09 — Diplomacy & vassalage (phase 3)

**What to build:** How factions relate peacefully and bind together. Phase 3 evolves an asymmetric disposition scalar per faction pair and derives a discrete stance (alliance/neutrality/hostility/vassalage); marriages, treaties, and betrayals move it; vassalage bonds let a realm serve a high king (the Reunited-Kingdom mechanism) and model provider-pacts. Relationship changes appear in the annals.

**Blocked by:** 07, 08

**Status:** done

- [x] Phase 3 maintains the shared asymmetric `disposition` map (sparse; absent = seeded baseline): yearly decay toward a **frozen** baseline (ADR-0005) + event-driven jumps (marriages, treaties, betrayals, war, border friction); derives stance + pinned flags (signed treaty, at-war boolean, vassalage bond). — `diplomacy.py` (`stance`, `_decay_toward_baseline`, `_apply_border_friction`); `Faction.baseline_disposition/at_war_with/treaties`.
- [x] Marriage seam: phase 3 (09) decides *whether* a marriage happens (utility off disposition + eligible unwed heirs); the kinship effect is enacted by `characters.wed` (05, where `spouse_id` lives), and the junior spouse weds into the senior house. — `diplomacy._make_marriage` + `characters.wed`.
- [x] Vassalage = directional `overlord_faction_id` bond (overlord offers, vassal accepts): vassal keeps its own succession/dormant claim and breaks free when it sours on / outlives its overlord; the field war (11) will read to muster. Provider-pacts raise `commitment`/`allegiance` through the same shape. — `diplomacy._form_vassalage/_dissolve_stale_vassalage/_deepen_provider`.
- [x] `treaty`, `marriage`, `vassalage`, `provider_pact`, `war_declared`, `war_ended` events emitted with prose + salience weights; the at-war flag is set here. Peace (`make_peace`/`war_ended`) is built as the seam ticket 11 will trigger — phase 3 declares wars but never ends them. — `chronicle` weights/renderers; `diplomacy.make_peace`.
- [x] Diplomacy is inspectable (overlord, vassals, and every non-neutral stance). — `mainwindow._describe_diplomacy` in the inspection dock.
- [x] Tests: disposition drift + event jumps deterministic; a vassalage bond forms and can dissolve; the war-declaration flag is owned here; marriage moves the junior spouse; `make_peace` is symmetric and the only peace path. — `tests/test_diplomacy.py`.

## Notes

- **ADR-0005** records the load-bearing decision: disposition decays toward a *frozen* authored baseline (`baseline_disposition`), not toward zero, so the canon tempers (Gondor↔Rohan warm, Gondor↔Mordor hostile) are lasting attractors. Blood-enemies never reconcile by drift alone — the correct default; ticket 11 adds exhaustion as the force that ends even a baseline-hostile war.
- **Grid dependence, per ADR-0004:** border friction and vassalage-offer adjacency read `world.grid`. A *reloaded* world carries no grid until ticket 12, so those branches are inert there and it diverges from a live run — resume is bit-identical only once the painted grid is re-attached (which ticket 12 restores). Field/flag state itself round-trips.
- **Peace is a seam:** `make_peace` + `war_ended` exist and are tested, but nothing in phase 3 calls them; deciding *when* wars end is ticket 11's (exhaustion/tribute/subjugation).
