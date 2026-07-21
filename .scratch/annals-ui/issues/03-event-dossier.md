# 03 — Event dossier in the Inspection dock

**What to build:** The same click that pans the map (ticket 02) pushes an
**event dossier** into the existing Inspection dock — the detail view for a
single event.

**Blocked by:** 02

**Status:** done

- [x] Every event click (placed or unplaced) renders a dossier into the
      Inspection dock, replacing whatever the dock showed (same behavior as
      map-click inspection).
- [x] Dossier header: year, category bucket, importance, and the chronicle
      sentence.
- [x] Handcrafted narrative blocks for the war-phase marquee types — field
      battle, siege, conquest, razing — composed from `payload`: the sides
      and their strengths, casualties, who retreated / was destroyed, siege
      progress vs fortification, named leaders present and any named-battle
      deaths. Written as prose, not key/value pairs.
- [x] Generic fallback for every other type: the sentence plus a readable
      key/value rendering of `payload` (skipping internal ids where a name
      can be resolved from the snapshot/world lookup already available to
      the inspection dock).
- [x] Names in the dossier are plain text — cross-linking to faction/character
      dossiers is wishlist, not this ticket.
- [x] Tests cover: each war-phase template renders from a representative
      payload, the generic fallback handles an arbitrary payload, and an
      event with an empty payload still renders a sane dossier.

## Comments

**2026-07-21 (agent):** Implemented as `ui/event_dossier.py` —
`render_event_dossier(event, faction_name=…, site_name=…, region_name=…)`,
pure text over resolver callables so it tests without a window. Header line
is `── TA NNNN · <bucket> · notable|minor ──` (importance expressed as the
threshold verdict rather than the raw integer), then the chronicle sentence,
then the detail block. Battle prose folds in the decisive/marginal tier and
both sides' casualties; siege reads progress-vs-fortification; conquest
names the fallen realm, the lands taken, and the razed flag; razing lists
the lands left in ruin. The payload carries no strengths or per-leader
death list (deaths are separate `death` events), so the blocks render what
the sim actually records. Generic fallback resolves `*_faction_id` keys to
names and skips `None` values. Wired in `MainWindow.describe_event`; the
click handler now pushes the dossier for every event row and still pans
only for placed ones. Verified against a real 60-year campaign run (all
four templates plus the coastal-raid fallback render well); suite green.
