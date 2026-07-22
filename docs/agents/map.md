# Module map

Where things live, so a task can jump straight to the right file instead of
searching. One line per module. Domain *terms* are in `CONTEXT.md`; lasting
*decisions* are in `docs/adr/`; this is the *"which file"* index.

Package root: `src/arda_sim/`. The UI (`src/arda_sim/ui/`) imports PySide6; the
sim core never does, so core and its tests stay Qt-free.

## The spine

- **`world.py`** — `World`, the single authoritative state container (id-keyed
  entities, current year, the run's one seeded RNG, monotonic id counter, event log).
- **`entities.py`** — the `Entity` base and `Event` dataclasses; all cross-refs are
  integer ids, so state is a cycle-free tree that serializes straight to JSON.
- **`pipeline.py`** — `run_tick` / `run_years`; the fixed, ordered `PIPELINE` of
  systems. **The order is the reproducibility contract — edit with care.**
- **`rng.py`** — the one `random.Random` per run, seeded from a shareable string;
  `getstate`/`setstate` are the exact-resume contract.
- **`driver.py`** — headless "seed → advance K years → dump events"; the top
  testing seam the whole sim is exercised through.

## The tick, in phase order (see `pipeline.py::PIPELINE`)

1. **`characters.py`** — `aging_births_deaths`: named people live, are born, die.
2. **`succession.py`** — heirs take vacant seats; heirless lines fail (absorbed or fragment).
3. **`factions.py`** — `faction_decisions`: powers' per-tick intent (muster / attack / hold). Also *owns* the `Faction` record and territory.
4. **`diplomacy.py`** — evolves per-pair disposition, derives `stance`, forms treaties/marriages/vassalage, sets & clears the at-war flag.
5. **`armies.py`** — `movement`: raised `Army` hosts march tile→tile deterministically.
6. **`sauron.py`** — `nazgul_hunt`: the Nine ride (after armies march).
6½. **`journeys.py`** — `character_journeys`: named travellers advance tile→tile on
   their own journeys (ADR-0015 mover), before the Ring phase so an arrival is on
   the tile when it looks. Isolated per-tick RNG; inert until motives are wired.
7. **`war.py`** — resolves field battles, sieges, conquest, razing at current positions.
8. **`economy.py`** — `construction_economy`: yearly treasury income, settlement building (peacetime foil to war).
9. **`ring.py`** — the One Ring; runs after war so it can read the field. XOR invariant: exactly one of `bearer_id` / `location_id` set.
10. **`sauron.py`** — `sauron_rise`: recompute `sauron_strength` and canonical pressure (phase 7).
11. `salience_bookkeeping` (in `pipeline.py`) — final per-event `importance` scoring via `chronicle.finalize_event`.

## Cross-cutting core

- **`chronicle.py`** — turns the raw event stream into readable history: salience/importance scoring and the chronicle sentence. Headless, no Qt, no RNG.
- **`metrics.py`** — read-only fold over the event stream → the war-tuning scalars / regression guard.
- **`naming.py`** — culture-authentic character names; a pure function of `(culture, sex, seed, taken)`, draws no RNG (never perturbs the stream).
- **`tiles.py`** — the tile grid that *is* the world; per-tile `owner_faction_id` is the only mutable substrate state, borders are derived.
- **`validate.py`** — substrate integrity checks (site in sea, empty region, bad gateway) as reusable data-returning invariants.

## Persistence & time-travel

- **`persistence.py`** — canonical-JSON save/load (state + event log + RNG state) behind a storage-backend seam; load is a rehydrate, never a replay.
- **`snapshot.py`** — immutable per-tick view the UI renders from (never the live `World`).
- **`playback.py`** — forward-only sim with a snapshot-per-tick cache; scrubbing back restores a snapshot, seeking forward fast-forwards.

## Scenarios (authored content, not run state)

- **`scenarios/__init__.py`** — loader for bundled scenario JSON (tile grid, terrain/region legends, sites, `miles_per_tile`).
- `scenarios/arda_ta2965.json` — the shipped starting theatre. `names.json` — name pools.

## UI (`src/arda_sim/ui/`, PySide6)

- **`app.py`** — entry point `arda-sim-ui`: build run → `Playback` → show window → Qt loop.
- **`mainwindow.py`** — the shell (~440 lines): map canvas, timeline toolbar, annals strip, Codex pane; owns the sim thread and turns its `(snapshot, events)` stream into UI updates. Construction is `_build_toolbar` + `_build_docks`; the rest is worker→UI wiring (`_on_tick_advanced`, pulses/battle-markers, the ring-trend accumulator), the annals/scrub/click handlers, and `_render_page` as a one-line delegate to `CodexPages`.
- **`codex_pages.py`** — the headless Codex page-render library: `CodexPages`, extracted whole from `MainWindow` (#39). Every non-map surface is here — the `describe_*` dossiers (faction, dynasty, ring, army, site, tile, event), the `_*_page` wrappers, the `_*_index` rolls (`_armies_index`, `_factions_index`, `_wars_index`), and `_search_page`. No Qt widgets, no window reference: it reads a small context (`update(...)` each tick) and returns HTML strings, so it renders without a window. Jump to the method you need rather than reading it whole.
- **`sim_worker.py`** — drives `Playback` on a `QThread`; play/pause/step/seek slots, publishes `tickAdvanced`.
- **`map_view.py`** — the pannable/zoomable tile canvas (tile-pixel coords, stacked layers).
- **`tile_render.py`** — tile theme: terrain sprites (Kenney CC0), faction tints, per-tile painting.
- **`codex.py`** — the Codex browser pane; every non-map surface is a `codex://<kind>/<id>` page (ADR-0014).
- **`annals_model.py`** — virtualized `QListView` model for the dated event feed.
- **`annals_style.py`** — category buckets + the styled row delegate (the one type→bucket mapping).
- **`event_dossier.py`** — deep reading of a single annals event (handcrafted war narratives + fallback).
- **`dossier_html.py`** — shared HTML dossier primitives (faction/host/site/tile/event render the same way).
- **`assets.py`** — locating bundled reference tilesets under `references/`.
