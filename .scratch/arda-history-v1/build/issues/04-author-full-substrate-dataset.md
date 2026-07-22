# 04 — Author the full TA-2965 substrate dataset

**What to build:** The complete hand-authored region/route/location dataset for the tightened War-of-the-Ring theatre, traced from a reference map of Middle-earth, so the real geography renders and everything downstream (territory, movement, war) runs on the true map. This is a content-authoring pass against the model from ticket 03.

**Blocked by:** 03

**Status:** done

> **Note (ADR-0001 pivot):** this ticket was authored in the pre-pivot
> polygon/route vocabulary. Under the tile substrate, regions are **named labels
> over tiles** (no polygons, `seat_location_id`, `base_yield`, or adjacency
> edges — ownership/borders are per-tile and *derived*), and roads/rivers are
> **terrain tiles**, not route objects. The acceptance below is met in the tile
> idiom. Authored via a deterministic generator (`tools/authoring/gen_substrate.py`)
> that bakes coordinate-traced geography into `src/arda_sim/scenarios/arda_ta2965.json`
> (100×125 = 12,500 tiles).

- [x] **56 named regions** (label areas, Voronoi-assigned from seed points) spanning Eriador → Rhovanion/Wilderland → Rohan → Gondor → Mordor; far north Forodwaith and deep Harad left as unlabelled backdrop (~14% of land).
- [x] Regions are named labels over tiles; dominant terrain, adjacency, seats and yields are **derived per-tile downstream** (retired by ADR-0001), not authored per-region.
- [x] Key locations placed at their reference-map positions — Minas Tirith, Osgiliath, Edoras, Helm's Deep, Isengard, Barad-dûr, the Morannon, Cirith Ungol, Mount Doom, Erebor, Dale, Esgaroth, Rivendell, Caras Galadhon, Thranduil's Halls, Dol Guldur, Bree, Fornost, Annúminas, Michel Delving, the Grey Havens, Carn Dûm, and more (36 sites incl. gateways).
- [x] Canonical roads & rivers authored as **terrain tiles** (Great East Road, Greenway, Anduin, Gwathló, Isen, Celduin, Entwash, Harad Road, …).
- [x] Provider gateway sites placed on map edges (Harad Road/Poros, E. Rhovanion, SE Nurn, Umbar-sea).
- [x] The full dataset loads through the engine loader and renders coherently on the tile canvas; tiles/regions/sites are inspectable via click.
- [x] A validation check (`arda_sim/validate.py`, exercised by `tests/test_substrate.py` and enforced at app startup): dimensions consistent, every region label resolves and is used, no orphan regions, every site in bounds and not in open sea, gateways on edges, no duplicate site names.
