# 07 — Factions & territory (phase 2 + ownership)

**What to build:** The powers of Middle-earth and their grip on the map. The canon faction roster is seeded; regions are coloured by their owning faction; each year factions make decisions via weighted-utility scoring (phase 2); off-map peoples exist as abstract provider gateway nodes. A faction is inspectable, and the map reads as a political map.

**Blocked by:** 04, 05

**Status:** done

- [x] `Faction` record tagged `kind ∈ realm | culture | provider`, with `leader_id`, `capital_location_id`, derived `military_strength`, `treasury`, `aggression`/`posture`, sparse asymmetric `disposition` map, `goals`, `overlord_faction_id?`, and derived `prominence`.
- [x] The TA 2965 roster seeded per the spec (Gondor, Rohan, landless Rangers with an "unclaimed North" claim, Isengard, Mordor, distinct Dol Guldur, unified Durin's Folk, Dale, four Elf realms, Shire/Bree/Dunland/Havens cultures; providers Haradrim/Easterlings/Variags/Corsairs at gateways); wilderness = `owner_faction_id = None`.
- [x] Regions render coloured by `owner_faction_id`; borders derived (not stored) and shown. *(Contested state is deferred to war/ticket 11 — nothing occupies a region until hosts exist.)*
- [x] Phase 2: each faction scores a fixed intent menu (muster/attack/fortify/seek-pact/build) via weighted utility + RNG jitter, writing intents for later phases; Elf realms hold `withdrawing` posture; canonicity is a global scalar weight on each faction's canon move.
- [x] Provider record exposes `gateway_location_id`, `allegiance_faction_id?`, `commitment` (0–100 int, per the no-float-in-outcome-math rule), `output`; providers never own regions and take no phase-2 turn.
- [x] A faction is inspectable (state + its events); salience uses faction prominence.
- [x] Tests: seed roster correct; ownership rendering matches state; intent scoring deterministic under seed.

## Notes

- `Faction` is an ordinary id-keyed `Entity` subtype (`src/arda_sim/factions.py`), so persistence/snapshots pick it up with no schema change. All maps use string keys to stay JSON-clean.
- **Substrate limitation:** Isengard and Bree-land have no matching region label in the `arda_ta2965` substrate, so they seed with a capital but no painted territory (invisible on the political map). A follow-up substrate authoring pass could add `Nan Curunír` / `Bree-land` region labels. Rivendell holds `Trollshaws` as its nominal ground.
- **Commitment units** are `0..100` (int), not the design's `0–1`, to keep outcome math integer-only per ADR-0001; anything later reading `commitment × output` must treat it as a percentage.
