# Research: Python 2D game / rendering stack

Type: research
Status: resolved

## Question

Survey the realistic options for building a **watch-it-unfold 2D graphical map** app in **Python**, and recommend a stack.

Compare, with trade-offs relevant to *this* project (a large static map, faction-colored territory, moving icons for armies/settlements/the Ring, a timeline/speed control, clickable entities for inspection, an event feed):

- **Rendering / game frameworks** — pygame / pygame-ce, arcade, pyglet, and whether a UI toolkit (e.g. Dear PyGui, pygame-gui) is needed for panels/controls. Note Textual/TUI only as a fallback contrast.
- **Architecture** — separating the simulation (headless, deterministic, seedable) from rendering; running the sim loop vs. render loop; how state flows to the view.
- **World-state storage** — in-memory + JSON snapshots vs. SQLite vs. other, in light of the save/load + string-seed requirement (ticket 12).
- **Map handling** — displaying a large static image, overlaying a hex grid or region polygons, hit-testing clicks to entities.
- **Packaging/distribution** and Python-version considerations.

Deliverable: a cited markdown file at `.scratch/arda-history-v1/research/python-rendering-stack.md` with a clear primary recommendation and one backup. Feeds the chronicle/UI ticket and the eventual architecture in the spec.

## Answer

Resolved. Findings written to [`research/python-rendering-stack.md`](../research/python-rendering-stack.md).

- **Primary recommendation: PySide6 (Qt)** — a `QGraphicsView` for the pan/zoom map (scene-graph click hit-testing, polygon/hex overlays) plus native Qt docking widgets for the inspection panels, timeline, and a virtualized annals list. Rationale: this is an *inspection-and-playback* app, not an action game, and that's exactly where Qt is strong; the game frameworks would force hand-building the entire panel/UI layer.
- **Backup: pygame-ce + pygame_gui** (or arcade for GPU sprite throughput). All three graphical frameworks (pygame-ce/SDL3, arcade 3.x, pyglet 2.1.x) confirmed actively maintained in 2026.
- **Architecture (framework-agnostic core):** a pure-Python, seeded simulation emitting **immutable snapshots + an event stream**; the renderer is a consumer. Reproducibility rules: **SHA-256 of the string seed** for the RNG, **canonical JSON** saves, **never `hash()` or pickle**. Directly supports ticket 12 (save/load + string seed).
- **Distribution:** Briefcase for a signed/notarized macOS `.app` on Python 3.12/3.13; PyInstaller as fallback.

Note: this is a **recommendation**, not a final decision — the stack is locked when the spec is written. Feeds ticket 11 (chronicle/UI) and the spec's architecture section.
