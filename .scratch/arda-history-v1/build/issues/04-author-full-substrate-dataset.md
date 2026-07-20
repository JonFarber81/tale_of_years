# 04 — Author the full TA-2965 substrate dataset

**What to build:** The complete hand-authored region/route/location dataset for the tightened War-of-the-Ring theatre, traced over the v7 map, so the real geography renders and everything downstream (territory, movement, war) runs on the true map. This is a content-authoring pass against the model from ticket 03.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] ~50–100 named regions as polygons in v7 pixel coordinates, spanning Eriador → Rhovanion/Wilderland → Rohan → Gondor → Mordor; far north and deep Harad left as static backdrop (no regions).
- [ ] Each region tagged with a dominant terrain, its adjacency edges, and a `seat_location_id`; a `base_yield` value.
- [ ] Key locations placed (settlements, fortresses, fords, passes, gates, ruins) at their v7 positions — Minas Tirith, Osgiliath, Edoras, Helm's Deep, Orthanc, Barad-dûr, the Morannon, Erebor, Dale, Rivendell, Caras Galadhon, Thranduil's Halls, Dol Guldur, Bree, Fornost, Michel Delving, the Grey Havens, etc.
- [ ] Canonical roads & rivers authored as routes with the right `kind` (Great East Road, Greenway, Anduin, Harad Road, mountain passes…).
- [ ] Provider gateway locations placed (Harad Road/Poros, E. Rhovanion, SE Nurn, Umbar-sea).
- [ ] The full dataset loads and renders correctly over the v7 canvas; regions/locations are inspectable.
- [ ] A validation check: every region has a valid `seat_location_id`, adjacency is symmetric, and every route's endpoints resolve.
