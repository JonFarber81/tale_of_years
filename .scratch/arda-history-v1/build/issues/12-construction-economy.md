# 12 — Construction & economy (phase 6)

**What to build:** The built world changing in peacetime. Each faction has a treasury that accrues from its regions; phase 6 prices build intents against it to found or grow settlements and fortresses and open roads, favouring borders/passes for fortresses; a settlement razed in war can be rebuilt later once there is peace. The viewer watches the map's settlements grow and ruins return.

**Blocked by:** 07, 11

**Status:** done

- [ ] Single `treasury`/economy scalar per faction; yearly income = sum of owned-region `base_yield`; population is a derived aggregate only.
- [ ] Phase 6 consumes `build` intents, priced against treasury: found a settlement/fortress at an eligible un-settled owned location (fortresses favour border/pass locations), grow a settlement tier, or open a road route; founding flips a Location to a settlement type (no new entity) and emits `founding`.
- [ ] Phase-6 construction skips contested regions (an enemy host present); "08 builds where there is peace, 07 destroys where there is war".
- [ ] A razed `ruin` (from ticket 11) is eligible for peacetime rebuild in a later tick.
- [ ] Canonicity weight biases toward canonical builds; scarcity from the treasury makes razing meaningful.
- [ ] Founding/growth/rebuild events carry prose + salience weights; settlement tiers are inspectable.
- [ ] Tests: treasury gates building; a razed ruin can be rebuilt; income + build costs deterministic and integer/fixed-point.
