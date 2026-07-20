# 07 — Factions & territory (phase 2 + ownership)

**What to build:** The powers of Middle-earth and their grip on the map. The canon faction roster is seeded; regions are coloured by their owning faction; each year factions make decisions via weighted-utility scoring (phase 2); off-map peoples exist as abstract provider gateway nodes. A faction is inspectable, and the map reads as a political map.

**Blocked by:** 04, 05

**Status:** ready-for-agent

- [ ] `Faction` record tagged `kind ∈ realm | culture | provider`, with `leader_id`, `capital_location_id`, derived `military_strength`, `treasury`, `aggression`/`posture`, sparse asymmetric `disposition` map, `goals`, `overlord_faction_id?`, and derived `prominence`.
- [ ] The TA 2965 roster seeded per the spec (Gondor, Rohan, landless Rangers with an "unclaimed North" claim, Isengard, Mordor, distinct Dol Guldur, unified Durin's Folk, Dale, four Elf realms, Shire/Bree/Dunland/Havens cultures; providers Haradrim/Easterlings/Variags/Corsairs at gateways); wilderness = `owner_faction_id = None`.
- [ ] Regions render coloured by `owner_faction_id`; borders/contested state derived (not stored) and shown.
- [ ] Phase 2: each faction scores a fixed intent menu (muster/attack/fortify/seek-pact/build) via weighted utility + RNG jitter, writing intents for later phases; Elf realms hold `withdrawing` posture.
- [ ] Provider record exposes `gateway_location_id`, `allegiance_faction_id?`, `commitment`, `output`; providers never own regions.
- [ ] A faction is inspectable (state + its events); salience uses faction prominence.
- [ ] Tests: seed roster correct; ownership rendering matches state; intent scoring deterministic under seed.
