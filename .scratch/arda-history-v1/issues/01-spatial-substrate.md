# Spatial substrate: how the map becomes a simulatable space

Type: prototype
Status: resolved

> **⚠ Superseded by [ADR-0001](../../../docs/adr/0001-tile-substrate-and-render.md) (2026-07-20).**
> The region/route hybrid below was retired: the world is now a **tile grid, and the
> tile is the unit of simulation**, rendered as a DF-style tile map. Kept as the record
> of the original exploration.

## Question

What spatial model does the simulation run on, and how do we derive it from the reference maps?

Decide:

- **Representation:** a **hex grid** over a reference map of Middle-earth, a **region/province graph** (named territories with adjacency), or a **hybrid** (regions for politics, hexes/points for movement & battles). A higher-detail hex reference for Eriador *is* hexed; the reference map of Middle-earth is pictorial at a different projection — reconcile them.
- **Coordinate system & scale** — the reference map has a miles scale bar; how do map distance, tick length (1 year), and army/Ring movement relate?
- **Terrain model** — which terrain types matter to the sim (mountains/impassable, forest, plains, rivers, roads, sea) and where they come from (hand-authored vs traced).
- **Boundary** — what's the edge of the fully-simulated world, and where do off-map providers (Harad/Rhûn/Khand) attach.

Deliverable: a decision on the substrate, ideally backed by a rough `/prototype` that renders the chosen representation over the reference map so we can react to it. This choice blocks rendering, factions/territory, war, and world-state persistence.

## Answer

The substrate is a **two-layer hybrid**, stored in **reference-map pixel coordinates** with a miles calibration, over a **tightened War-of-the-Ring theatre**, with off-map peoples as abstract edge nodes.

### 1. Representation — region/point hybrid

Two coupled layers, not a uniform grid:

- **Region layer (politics & territory).** A graph of ~50–100 **named regions** (polygons), each with a dominant terrain, a current owning faction, and adjacency edges. This is the canonical spine: the Shire, Bree-land, Cardolan, Rhudaur, Eregion, Enedwaith, Rohan's marches, Anórien, Ithilien, Gorgoroth, etc. Ownership, borders, and contested zones live here (ticket 06). Regions are the unit rendered as coloured overlays and the unit most events attach to.
- **Location + route layer (movement & battle siting).** A graph of **key locations** (settlements, fortresses, fords, passes, gates — Bree, Fornost, Rivendell, Isengard, Minas Tirith, the Morannon…) connected by **routes** that follow canonical roads and rivers (Greenway, Great East Road, Anduin, Harad Road…). Armies and the Ring move **node→node along routes**, not free-roaming. Battles are sited at a location or a region-border route segment.

Rationale: a full hex grid is overkill at a **yearly** tick and painful to hand-author over a pictorial map at its own projection (a higher-detail hex reference for Eriador only covers Eriador). The region graph is canon-native and cheap to author; the route layer restores enough spatial fidelity for multi-year troop movement and siege siting without tactical hexes.

### 2. Coordinates & scale — pixel-native + miles calibration

- Author and store all geometry (region polygons, location points, route polylines) directly in **reference-map pixel coordinates**. The reference map is the single source of truth for position; rendering is a straight pixel blit in `QGraphicsView` with no image↔world transform to maintain.
- Calibrate a single **pixels-per-mile** factor once from the map's scale bar (`0 · 40 · 80 · 120 miles`, bottom-centre). Any route's length in miles = pixel length ÷ px_per_mile.
- **Movement budget** is expressed in **miles/year** per mover type (host on foot/horse, the Ring's bearer, a Nazgûl search). At a yearly tick, distance chiefly governs **how many ticks a journey takes** (e.g. a host crossing Eriador is a multi-year march), not per-tick tactics. Route `kind` (road/river/pass/open/forest) modifies effective speed and risk.

### 3. Terrain — hand-authored per region and per route

Small, fully-controlled canonical dataset, no raster tracing:

- `region.terrain ∈ {plains, forest, mountain, marsh, hills, barren, sea}` — one dominant type per region.
- `route.kind ∈ {road, river, pass, open, forest}` — drives speed and hazard along that edge; passes through mountain regions are the only way hosts cross otherwise-impassable ranges.
- Impassability (high mountains, open sea) is a property of region terrain + the absence of a route, so it needs no separate mask.

### 4. Boundary — tightened War-of-the-Ring theatre + abstract provider nodes

- **Fully simulated core:** Eriador, Rhovanion/Wilderland, Rohan, Gondor, and Mordor — i.e. the map from Lindon/the Shire across to Erebor/Dale and south to Gondor and Nurn.
- **Static backdrop (not simulated):** the far north (Forochel, deep Forodwaith, Angmar's empty north) and deep Harad — drawn from the reference map but carrying no regions/factions.
- **Off-map providers** (Harad, Rhûn, Khand) are **single abstract nodes** attached at edge **gateways** where their routes enter the simulated core — the Harad Road / Crossings of Poros in the south, the eastern edge of Rhovanion, and SE Mordor/Nurn. Each provider node has no interior (no territory, no dynasties); it can **side with a power (chiefly Sauron)** and **emit troops/resources/effects** through its gateway into war (ticket 07) and diplomacy (ticket 08). This honours the map Note that off-map peoples stay abstract providers.

### Consequences for downstream tickets

- **06 Faction & territory** — territory = ownership of regions; borders/contested zones are region-adjacency state; the provider-node interface is defined here.
- **07 War & battle** — armies occupy locations and traverse routes; battles resolve at a location or border segment; sieges target the settlement at a location.
- **11 Chronicle/UI & rendering (04)** — regions are coloured `QGraphicsItem` polygons over the reference map's `QGraphicsPixmapItem`; locations/armies/Ring are movable point items; clicks hit-test to region or location.
- **12 Persistence** — geometry (pixel polygons/points/polylines + calibration) is fixed **config**, not run state; only ownership, army positions, and the Ring's location are per-tick state to serialize.

### Note on the prototype

The `/prototype` step (render the region+route graph over the reference map to react to) was **not built** — the four decisions above were settled directly and confidently from the reference map, so a throwaway visualization would not change them. Building the actual region/route dataset is downstream authoring work, tracked as content-authoring fog on the map, not a decision this ticket owns.
