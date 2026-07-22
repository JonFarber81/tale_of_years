# ADR-0014 — The Codex: one browser pane where everything is a page

Status: **Accepted** (2026-07-21)

Settles the interface architecture for the nine open UI issues #17–#25.
Realized incrementally: the shell is issue #36; each view lands as its own
issue on top of it.

## Context

Issues #17–#25 read together are not nine features but one demand: everything
the sim models — characters, regions, wars, coalitions, the Ring's history —
becomes an inspectable dossier, and every entity name anywhere links to one.
They cluster into global browse tables (#17 armies, #19 factions, #20 wars),
search (#18), new or enriched dossier kinds (#18 character, #23 ring, #24 host,
#25 region), navigation (#21 dynasty tree, #22 annals links), and map overlays
(march paths, region tint, ring path).

The current shell cannot absorb that: a central map, a timeline toolbar, and
two fixed right docks (Annals, Inspection), with dossiers reachable only by
clicking map markers and no history, search, or cross-links. The real design
question is *where dossiers live and how you move between them*.

Three directions were prototyped as HTML mockups (branch `prototype/codex-ui`,
`src/arda_sim/ui/prototype_codex_options.html`; rendered at
<https://claude.ai/code/artifact/2049a9be-2b84-4535-ac85-9e6ab2c3b4a6>):

- **A — The Registers**: keep the shell, add a third (left) tabbed dock holding
  the three tables. Cheapest, everything visible at once; but three columns
  squeeze the map, and link-hopping has no way back.
- **B — The Codex**: replace both right docks with a single wiki-style browser
  pane — back/forward history, an omnibox over every entity, index pages that
  are just pages, dossiers with internal tabs; Annals becomes a bottom strip.
- **C — The Command Deck**: full-bleed map, one bottom tabbed Ledger for feed +
  tables, floating dossier cards beside markers, special views as map overlays.
  Most atmospheric; most custom widgetry, least side-by-side density.

## Decision

**Option B. The Codex is the one place non-map information lives, and
everything in it is a page.**

- The Annals and Inspection docks are **replaced** by a single **Codex pane**
  on the right. The Annals feed moves to a **bottom strip dock** spanning the
  window.
- **Everything is a page**, addressed by an internal scheme
  (`codex://<kind>/<id>`): the existing dossier kinds (faction, host, site,
  tile, event), the new ones (character, region, ring), and the **index pages**
  (Armies, Factions, Wars), which are ordinary pages that happen to render
  tables of links.
- The Codex header carries **back/forward** over a history stack of addresses,
  an **omnibox** that searches entities by name, and static links to the index
  pages.
- Large dossiers use **internal tabs** rather than new panes — e.g. a faction
  page carries Overview / Diplomacy / Dynasty / Regions tabs.
- Map and Codex stay linked both ways: selecting on the map opens a page;
  activating a page entity centres/highlights the map and may add overlays
  (march path, region tint, ring path).
- The pane renders through the existing dossier anatomy
  (`dossier_html.py`: banner, stat grid, sections) and reads only from
  immutable `Snapshot`s, like the rest of the UI.

### Where each issue lands

| Issue | Home in the Codex |
| --- | --- |
| #36 | The shell itself: pane, routing, history, omnibox plumbing, Annals strip |
| #17 | **Armies index page**; rows link to host pages, row click also highlights the marker |
| #18 | **Omnibox character search** + the **character dossier page** |
| #19 | **Factions index page** |
| #20 | **Wars index page** + a **Diplomacy tab** on the faction page |
| #21 | **Dynasty tab** on faction and character pages (tree of linked nodes) |
| #22 | Annals-strip entries and event pages render entity names as `codex://` links |
| #23 | **Ring page**: bearer timeline, corruption sparkline, errand link; ring-path map overlay |
| #24 | Enriched **host page** (mustered vs current, coalition, supply, ETA); march-path map overlay |
| #25 | **Region dossier page** + a Regions tab on the faction page; region-tint map overlay |

## Consequences

- #36 blocks all of #17–#25 (native GitHub dependencies). Every view issue is
  "add a page/tab/overlay", never "add a dock" — new dossier kinds cost a
  renderer registration, which is why B beat A: it scales to unlimited kinds
  without new chrome.
- Link-hopping is safe (back button), so #22's everything-is-a-link becomes the
  primary navigation and the map stops being the only entry point.
- Accepted trade-off: only one Codex page is visible at a time — no
  table-beside-dossier comparison (A's strength). If that bites later, the
  escape hatch is a "pin page to second pane" affordance, not a return to
  fixed docks.
- The old `QDockWidget` pair and the Inspection dock's direct
  `QTextBrowser.setHtml` calls give way to the address/registry indirection;
  existing dossier builders are reused as the first registered renderers.
- The mockups are throwaway; the prototype branch is history, not a base to
  merge.
