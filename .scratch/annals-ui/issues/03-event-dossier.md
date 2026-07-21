# 03 — Event dossier in the Inspection dock

**What to build:** The same click that pans the map (ticket 02) pushes an
**event dossier** into the existing Inspection dock — the detail view for a
single event.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Every event click (placed or unplaced) renders a dossier into the
      Inspection dock, replacing whatever the dock showed (same behavior as
      map-click inspection).
- [ ] Dossier header: year, category bucket, importance, and the chronicle
      sentence.
- [ ] Handcrafted narrative blocks for the war-phase marquee types — field
      battle, siege, conquest, razing — composed from `payload`: the sides
      and their strengths, casualties, who retreated / was destroyed, siege
      progress vs fortification, named leaders present and any named-battle
      deaths. Written as prose, not key/value pairs.
- [ ] Generic fallback for every other type: the sentence plus a readable
      key/value rendering of `payload` (skipping internal ids where a name
      can be resolved from the snapshot/world lookup already available to
      the inspection dock).
- [ ] Names in the dossier are plain text — cross-linking to faction/character
      dossiers is wishlist, not this ticket.
- [ ] Tests cover: each war-phase template renders from a representative
      payload, the generic fallback handles an arbitrary payload, and an
      event with an empty payload still renders a sane dossier.
