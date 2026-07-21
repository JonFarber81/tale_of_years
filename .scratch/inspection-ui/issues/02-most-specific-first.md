# 02 — Most-specific-first restructure + per-type stat grids

**What to build:** A map click resolves to one **dossier subject** — host >
site > faction > bare tile — which headlines the banner with full depth;
everything else demotes to trimmed context sections. Each subject type gets
its stat grid.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Subject resolution on tile click: a living host on the tile wins;
      else a site on the tile; else the owning faction; else the bare tile.
- [ ] Per-type stat grids (per the spec):
      - **Faction**: Leader, Kind, Succession, Posture · Aggression,
        Strength, Treasury. Prominence and latest intent are dropped from
        the grid (intent still reads via faction-intent events under
        RECENT EVENTS when shown-all).
      - **Host**: Strength as the hero stat, Leader, Faction, Destination —
        plus **siege progress** ("Siege: N / fortification") whenever
        `Army.siege_progress > 0`, new content the UI never showed.
      - **Site**: rank ("City · tier 2" / "Fortress" / "Ruin"), Owner,
        Region, Terrain.
      - **Bare tile**: Terrain, Region, Owner only.
- [ ] Trimmed-context faction section: when the faction is *context* (a
      host or site headlines), it renders as leader + strength + a one-line
      stance summary — no bloodline, no recent events, no full diplomacy
      block. Full depth only when the faction is the subject.
- [ ] A host subject still shows a compact locator line for where it stands
      ("Stands in Anórien, land of Gondor").
- [ ] Clicking open owned ground (no site, no host) headlines the faction
      with today's full depth (diplomacy, bloodline, recent events), so no
      information becomes unreachable.
- [ ] Tests cover: each rung of the resolution order, the trimmed-context
      faction vs full-depth faction, the siege-progress row appearing only
      mid-siege, and the dropped prominence/intent stats.

## Comments
