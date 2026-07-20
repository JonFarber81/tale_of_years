# Python Rendering & Architecture Stack for a "Watch-It-Unfold" Middle-earth Map App

**Ticket:** arda_history — survey realistic options for a 2D graphical map application in Python and recommend a stack.
**Date:** 2026-07-20
**Scope:** Desktop (macOS primary), distributable to non-developers. Large static base map + faction territory overlay + moving icons + timeline playback + clickable inspection panels + event log, driven by a headless, deterministic, seedable simulation core.

---

## TL;DR — Recommendation

- **Primary recommendation: PySide6 (Qt) with a `QGraphicsView` / `QGraphicsScene` for the map, and native Qt widgets for the panels/timeline.** This project is really a *data-visualization / inspector application that happens to animate*, not a twitch game. Qt gives you pan/zoom, scene-graph hit-testing, docking inspection panels, and a proper timeline widget essentially for free, plus first-class macOS `.app` bundling. ([Qt QGraphicsView docs](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html), [pythonguis QGraphics tutorial](https://www.pythonguis.com/tutorials/pyside6-qgraphics-vector-graphics/))
- **Backup recommendation: pygame-ce + pygame_gui** (or arcade if you want GPU-accelerated sprites). Lighter, game-loop-native, better if you later want lots of animated sprites or particle-heavy effects — but you hand-build the panels/timeline and lean harder on a UI add-on. ([pygame-ce releases](https://github.com/pygame-community/pygame-ce/releases), [pygame_gui](https://github.com/MyreMylar/pygame_gui))
- **Architecture (independent of the above):** keep a pure-Python, framework-agnostic **sim core** that advances by discrete ticks (years), owns all randomness through a single seeded RNG, and emits **immutable snapshots + an event stream**. The renderer only ever *reads* snapshots. This separation is the single most important design decision and is what makes both save/load and reproducibility fall out naturally.

The key trade-off: **Qt gives you the app shell (panels, docking, timeline, hit-testing, packaging) at the cost of a heavier dependency and a widget-oriented mental model; the game frameworks give you a simpler animation loop at the cost of building the entire UI layer yourself.** For an app dominated by inspection panels and an annals feed rather than fast action, Qt wins.

---

## 1. Rendering / game frameworks

| Framework | Latest (2026) | Maintained? | Rendering model | Large map + many sprites | Learning curve | Notes for this project |
|---|---|---|---|---|---|---|
| **pygame-ce** (Community Edition) | 2.5.x, SDL3 migration underway toward a 3.0 | **Yes — the actively maintained fork; use this, not upstream `pygame`** | CPU raster blitting (SDL). Rotation/scale is CPU-bound. | Fine for a static base image + moderate sprite counts; heavy rotation/scaling of many sprites is CPU-costly | Low — simplest API | Great for a manual game loop; you build all UI yourself. ([releases](https://github.com/pygame-community/pygame-ce/releases), [perf notes](https://github.com/pygame-community/pygame-ce/wiki/Performance-Comparisons-Against-Upstream-Pygame)) |
| **arcade** | 3.x (3.0 stable line, built on pyglet + OpenGL) | Yes | **GPU/OpenGL** — offloads rotation, scaling, transparency to the GPU | Best raw sprite throughput of the three; scales to thousands of moving icons cheaply | Low–moderate | Modern, batch/GPU sprite drawing; smaller community than pygame. ([PyPI](https://pypi.org/project/arcade/), [arcade vs pygame](https://api.arcade.academy/en/2.6.17/pygame_comparison.html)) |
| **pyglet** | 2.1.x (2.1.14, 2026), 3.0 in pre-release | Yes, but lower-level and thinner docs | OpenGL, windowing + media, no batteries | Capable (arcade is built on it) but you assemble more yourself | Moderate–high | You'd rarely pick raw pyglet over arcade for this. ([docs](https://pyglet.readthedocs.io/)) |
| **Textual / TUI** (contrast only) | current | Yes | Terminal cells | N/A — no true raster map | Low | Only viable as a low-fidelity ASCII/annals view. A real base-map image and pan/zoom are out of scope for a TUI. Useful at most as a headless debug view of the sim. |

**Takeaway:** All three graphical frameworks are alive in 2026. For a *game*, arcade (GPU) or pygame-ce are the natural picks. But note: **none of them provide real UI widgets** — panels, scrollable lists, sliders, docking, text input — so a game framework "alone" does *not* suffice for the inspection/timeline/annals requirements (see §2).

**Performance reality for this app:** the base map is a *single large static image*, which is cheap on any of these (draw it once, or once per pan/zoom transform). The load is a few hundred to a few thousand small moving icons — trivial for arcade (GPU batching) and manageable for pygame-ce. Territory overlay (hexes/polygons) is the main draw cost; pre-render it to a cached surface/texture and only redraw when it changes, not every frame.

---

## 2. UI / widget layer (panels, timeline, inspection, annals)

This requirement — **clickable entities opening an inspection panel, a scrollable event-log feed, and a timeline with pause/speed/step controls** — is what pushes the decision. These are *application UI*, and the quality bar differs sharply by choice.

| Option | What it gives you | Fit for panels/timeline/annals | Trade-offs |
|---|---|---|---|
| **PySide6 (Qt) widgets** | Full native toolkit: dock widgets, `QListView`/`QTableView` (model-backed, virtualized — good for a long annals feed), `QSlider`, `QToolBar`, `QLabel`, styling via QSS. Map lives in a `QGraphicsView`. | **Excellent.** Everything the ticket asks for is a stock widget. Docking inspection panels, a timeline toolbar, a virtualized event log all exist out of the box. ([Qt for Python](https://doc.qt.io/qtforpython-6/), [PySide6 tutorial](https://www.pythonguis.com/pyside6-tutorial/)) | Heavier dependency; LGPL (fine for most uses); widget/event-loop mindset rather than a game loop. |
| **Dear PyGui** | GPU-accelerated immediate-mode GUI with a built-in drawing API (draw lists, plots, even simple 2D scenes). | **Good.** Fast, modern, can host both the map (draw layer) and panels in one framework. Immediate-mode suits data that changes every tick. Actively maintained; a "Dear PyGui 2 / Pilot Light" rewrite is in progress. ([GitHub](https://github.com/hoffstadt/DearPyGui), [PyPI](https://pypi.org/project/dearpygui/)) | Immediate-mode layout is less flexible for complex docked desktop UIs; theming/native feel is weaker than Qt; large scrollable virtualized lists are less mature. |
| **pygame_gui** | Widget add-on for pygame (buttons, sliders, text boxes, HTML-ish labels, windows, theming via JSON). Actively maintained (0.6.14, mid-2025). | **Adequate.** Covers buttons/sliders/windows for a game-style overlay UI, but you'll fight it for a polished desktop inspector with lots of dense data. ([GitHub](https://github.com/MyreMylar/pygame_gui), [PyPI](https://pypi.org/project/pygame-gui/)) | Least powerful of the three for rich panels; best when you've *already* committed to pygame for rendering. |

**Verdict:** A game framework alone is **not** warranted here — the app is panel-heavy. Either (a) use a real UI toolkit (**Qt/PySide6**) that also renders the map via `QGraphicsView`, or (b) use **Dear PyGui** which unifies GPU drawing + GUI, or (c) accept pygame-ce + pygame_gui as a lighter but more DIY combo. Given the emphasis on inspection panels and an annals feed, **Qt is the strongest fit**.

---

## 3. Architecture — separating a deterministic sim from the renderer

This is framework-independent and should be built first.

```
+-------------------+        snapshots + events        +--------------------+
|   SIM CORE        | --------------------------------> |   RENDERER / VIEW  |
| (pure Python,     |                                   | (Qt / pygame / DPG)|
|  no rendering)    | <-- commands (pause/step/seek) -- |                    |
+-------------------+                                   +--------------------+
   owns: World state, single seeded RNG, tick(year)        owns: camera, sprites,
   emits: immutable WorldSnapshot, list[Event] per tick    panels, playback clock
```

**Principles**
- **Two independent clocks.** The **sim** advances in discrete ticks (one game *year* per step). The **renderer** runs at display FPS and *interpolates/animates* between the two most recent snapshots. Never tie simulation outcomes to frame rate or wall-clock time — determinism requires the sim to be a pure function of `(previous_state, seed)`.
- **One-way data flow.** The sim never imports or calls the renderer. The renderer holds a reference to (a copy of) the latest `WorldSnapshot` and only reads it. UI controls send *commands* back (pause, set speed, step one year, seek/scrub), which the driver loop translates into "advance N ticks" or "reload snapshot at year T".
- **State delivery = snapshots + events.**
  - *Snapshot*: the complete world at year T (positions, faction ownership, Ring location, army/settlement records). Cheap to diff and to serialize (§4). The renderer resolves entity positions from snapshots.
  - *Event stream*: the discrete things that happened this tick ("Battle of X", "Ring changed hands"). These feed the **annals/event-log panel** directly and can trigger transient animations. Events are a log, snapshots are the truth.
- **Single RNG, threaded explicitly.** Instantiate one `random.Random(seed)` (or a NumPy `Generator`) inside the sim and pass it everywhere; forbid any module-level `random.random()` or reliance on `hash()`/set iteration order. Every stochastic decision draws from this one generator so a seed fully determines history. ([Python random reproducibility](https://pynative.com/python-random-seed/))
- **Threading option:** run the sim in a worker thread/process and hand finished snapshots to the UI thread via a queue (Qt: `QThread` + signals). This keeps a heavy tick from stuttering the UI. Because the sim is pure and communicates only via immutable snapshots, this is safe.

**Why this matters for the ticket:** save/load, scrubbing the timeline, and seed-reproducibility are all *the same feature* once the sim is a deterministic state machine — you can always re-derive year T from `(seed, T)`, or fast-forward by replaying ticks.

---

## 4. World-state storage — save/load + string-seed determinism

**Recommended baseline: in-memory dataclasses → JSON snapshots**, with a documented canonical serialization. Move to SQLite only if world state grows too large to hold/serialize comfortably or you need querying over long histories.

| Approach | Pros | Cons | When |
|---|---|---|---|
| **dataclasses + JSON snapshot** | Human-readable, diffable, trivial to version, git-friendly; easy `asdict`/`from_dict` | Whole-world rewrites; must enforce canonical form for reproducible hashes | **Default.** Best for save files and reproducibility auditing |
| **SQLite** | Handles large/long histories, incremental writes, query annals by year/faction | More ceremony; still must serialize custom objects | If state or history outgrows memory |
| **pickle** | Zero-effort | **Avoid for saves** — version-fragile, insecure, non-canonical, poor cross-version reproducibility | Never for durable/shared saves |

**String seed → deterministic sim.** Accept a user-facing *string* seed and hash it to an integer with a **stable, cross-run algorithm** — e.g. `int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")`. **Do not use the built-in `hash()`** for this: Python randomizes string hashing per process (`PYTHONHASHSEED`), so `hash("Mordor")` differs run to run. ([deterministic hashing of Python objects](https://death.andgravity.com/stable-hashing))

**Serialization gotchas for reproducibility** ([death and gravity](https://death.andgravity.com/stable-hashing), [random seeds](https://medium.com/data-science/random-seeds-and-reproducibility-933da79446e3)):
- **Sort keys / fix order.** Serialize with `json.dumps(..., sort_keys=True)` and iterate collections in a defined order. Never let `set` iteration or dict insertion order leak into sim decisions.
- **`dataclasses.asdict()` is recursive** and copies nested dataclasses wholesale — fine for plain data, but it won't handle custom types (enums, tuples-as-keys, `Path`, `datetime`); provide explicit `to_dict`/`from_dict` for those.
- **Floats are a determinism hazard.** Prefer integers / fixed-point for anything the sim branches on (positions on a grid, resource counts). If you must use floats, be aware results can differ across platforms; avoid comparing floats for equality in sim logic.
- **Record provenance in the save.** Store `{seed, tick, schema_version, code_version}` in every snapshot so a save can be validated and replayed. ([reproducible experiment tracking](https://agentbus.sh/posts/how-to-build-reproducible-ai-experiments-with-seeds/))
- **Pin the RNG.** `random.Random` (Mersenne Twister) is stable across CPython versions; if you use NumPy, pin to the explicit `Generator(PCG64)` API (not the legacy global) and record the bit generator.

**Reproducibility contract:** *same string seed + same code version ⇒ identical event history.* Snapshots are then an optimization (fast load/scrub), and the seed is the source of truth.

---

## 5. Map handling — big image, territory overlay, hit-testing

**Displaying the large base map**
- **Qt path:** add the map as a `QGraphicsPixmapItem` in a `QGraphicsScene`; pan via scrollbars/drag and zoom by applying `view.scale()` — pan/zoom and coordinate transforms are built in. For a very large image, tile it or use `QPixmap` with level-of-detail so you're not uploading the full-res image at every zoom. ([QGraphicsView docs](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html), [pythonguis tutorial](https://www.pythonguis.com/tutorials/pyside6-qgraphics-vector-graphics/))
- **Game-framework path:** draw the map as one large texture/surface, maintain your own `camera = (offset, zoom)`, and convert screen↔world coordinates yourself. Cache the scaled map so you don't rescale every frame.

**Territory overlay (hex grid or region polygons)**
- **Hex grid:** use the **Red Blob Games** hex algorithms as your canonical reference — axial/cube coordinates, hex↔pixel conversion, and `pixel_to_hex` rounding for click hit-testing. It publishes adaptable Python recipes (not a package); several thin third-party libraries wrap it if you prefer. Store the third cube coordinate as a field (Python attribute access is slow). ([Red Blob hex implementation](https://www.redblobgames.com/grids/hexagons/implementation.html))
- **Region polygons:** keep each region as a polygon in *map/world* coordinates; color-fill by current owning faction from the snapshot. Pre-render the whole overlay to a cached layer and only rebuild it when ownership changes.

**Hit-testing clicks back to entities**
- **Qt does this for you:** every `QGraphicsItem` (army icon, settlement, region polygon) receives its own click events, and `scene.itemAt(pos)` resolves a point to an item — no manual math. This is a major reason Qt suits this app. ([QGraphicsView docs](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html))
- **Game frameworks:** you implement hit-testing. For hexes, convert the click to world coords then `pixel_to_hex` → look up the entity in that cell ([Red Blob](https://www.redblobgames.com/grids/hexagons/implementation.html)). For polygons, point-in-polygon test (e.g. `shapely` for robust geometry, or a small ray-cast). For sprite icons, a distance/AABB check or arcade's built-in sprite collision helpers.

---

## 6. Packaging / distribution & Python version

| Tool | Strengths | Weaknesses | macOS specifics |
|---|---|---|---|
| **Briefcase** (BeeWare) | Produces *native* `.app` bundles; manages **signing & notarization**; bundles interpreter + bytecode; best "native install experience"; also targets Windows/Linux/mobile | Build-on-target only (no cross-compile); some AV false positives remain; extra learning | **Strongest for a distributable macOS `.app`** — handles codesign/notarytool workflow. ([InfoWorld guide](https://www.infoworld.com/article/2259512/how-to-package-python-apps-with-beeware-briefcase.html), [pydevtools](https://pydevtools.com/handbook/reference/briefcase/)) |
| **PyInstaller** | Mature, ubiquitous, one-folder/one-file freezes; interpreter + all deps bundled | AV false-positive reputation; you wire up codesign/notarize yourself; build machine arch must match target | Works on macOS but you drive `codesign` + `notarytool` with an Apple Developer ID manually. ([pydevtools](https://pydevtools.com/handbook/reference/pyinstaller/)) |

**Recommendation:** For shipping to **non-developers on macOS**, **Briefcase** is the better default because it produces a proper signed/notarized `.app` (Gatekeeper won't block it) and pairs naturally with a Qt GUI. If you hit a tricky dependency Briefcase mishandles, **PyInstaller** is the fallback. Either way, **budget time for Apple Developer ID signing + notarization** — an unsigned app triggers Gatekeeper warnings for end users. ([Briefcase vs PyInstaller discussion](https://github.com/beeware/briefcase/issues/145))

**Python version:** target **CPython 3.12 or 3.13** (stable, widely supported by PySide6/pygame-ce/arcade/Briefcase in 2026). Pin the exact interpreter version in the build and record it in save metadata (§4), since the RNG-stability guarantee is per interpreter family. Avoid the newest x.0 release for a distributed app until your key deps publish wheels for it.

---

## Final recommendation, tied to this project

1. **Build the sim core first**, framework-agnostic: pure dataclasses, one seeded RNG, `tick(year)` advancing discrete state, emitting immutable `WorldSnapshot` + `list[Event]`. Establish the string-seed → SHA-256 → int rule and the canonical `to_dict`/`from_dict` + JSON save format on day one. This unlocks save/load, timeline scrubbing, and reproducibility simultaneously.
2. **Render with PySide6 + `QGraphicsView`** (primary). Map = `QGraphicsPixmapItem`; territory = polygon/hex `QGraphicsItem`s colored per snapshot; army/settlement/Ring = movable pixmap items; clicks resolve via built-in item hit-testing into an **inspection dock panel**; the **annals feed** is a model-backed `QListView`; the **timeline** is a `QToolBar` (play/pause/step) + `QSlider` (scrub) + speed control. Run the sim on a `QThread`, deliver snapshots via signals.
3. **Backup: pygame-ce + pygame_gui** (or arcade if you expect many animated sprites). Same sim core; you hand-build camera transforms, hex/polygon hit-testing (Red Blob recipes), and the panel UI. Lighter and more "game-like," but more UI work.
4. **Package with Briefcase** into a signed/notarized macOS `.app` on **Python 3.12/3.13**; PyInstaller as fallback.

**The decisive trade-off:** this is an inspector/visualization app with playback, not an action game. Qt's `QGraphicsView` supplies pan/zoom, scene-graph click hit-testing, docking inspection panels, a virtualized event log, and native macOS packaging almost for free — worth its heavier dependency. The game frameworks are simpler loops but would force you to reimplement the entire panel/UI layer, which is exactly where this project's requirements concentrate.

---

## Sources
- pygame-ce releases & SDL3 status — https://github.com/pygame-community/pygame-ce/releases ; performance notes — https://github.com/pygame-community/pygame-ce/wiki/Performance-Comparisons-Against-Upstream-Pygame
- arcade (GPU/OpenGL) — https://pypi.org/project/arcade/ ; arcade vs pygame — https://api.arcade.academy/en/2.6.17/pygame_comparison.html
- pyglet 2.1.x docs — https://pyglet.readthedocs.io/
- Python game engines overview 2025 — https://gamefromscratch.com/python-game-engines-in-2025/
- PySide6 `QGraphicsView` docs — https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html ; Qt for Python — https://doc.qt.io/qtforpython-6/
- PySide6 QGraphics vector-graphics tutorial — https://www.pythonguis.com/tutorials/pyside6-qgraphics-vector-graphics/ ; PySide6 tutorial — https://www.pythonguis.com/pyside6-tutorial/
- Dear PyGui — https://github.com/hoffstadt/DearPyGui ; https://pypi.org/project/dearpygui/
- pygame_gui — https://github.com/MyreMylar/pygame_gui ; https://pypi.org/project/pygame-gui/
- Red Blob Games hex grid implementation — https://www.redblobgames.com/grids/hexagons/implementation.html
- Deterministic hashing / serialization gotchas — https://death.andgravity.com/stable-hashing
- Random seeds & reproducibility — https://pynative.com/python-random-seed/ ; https://medium.com/data-science/random-seeds-and-reproducibility-933da79446e3 ; https://agentbus.sh/posts/how-to-build-reproducible-ai-experiments-with-seeds/
- Briefcase — https://www.infoworld.com/article/2259512/how-to-package-python-apps-with-beeware-briefcase.html ; https://pydevtools.com/handbook/reference/briefcase/ ; Briefcase vs PyInstaller — https://github.com/beeware/briefcase/issues/145
- PyInstaller — https://pydevtools.com/handbook/reference/pyinstaller/
