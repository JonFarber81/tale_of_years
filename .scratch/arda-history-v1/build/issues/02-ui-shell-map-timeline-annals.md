# 02 — UI shell: map canvas, timeline, annals feed, snapshot playback

**What to build:** The PySide6/Qt desktop shell that lets a viewer watch the skeleton sim run on the v7 map. The v7 image is the canvas with pan/zoom; a timeline toolbar gives play / pause / step-a-year / speed / scrub; an annals dock shows the event stream as it arrives; an inspection dock exists (stub content for now). The sim runs on a background thread and delivers a snapshot + events per year, cached so scrubbing restores a stored snapshot instantly rather than re-simulating.

> **Update (ADR-0003):** a tick is now a **month**. Step advances one tick; the scrub slider and the snapshot cache key on the absolute **tick**, not the year; the date label shows year + month. The annals stay year-grained (events keep a `year` stamp), so a mid-year scrub shows that whole year's annals while the map reflects the exact month.

**Blocked by:** 01

**Status:** done

- [x] `QGraphicsView`/`QGraphicsScene` renders the map as the canvas with pan and zoom. — `ui/map_view.py` (the DF-style tile map per ADR-0001, in place of the v7 jpg).
- [x] Timeline toolbar: play, pause, step-forward-one-tick, speed (ticks/sec) control, and a scrub `QSlider`; current TA year + month shown prominently. — `ui/mainwindow.py`.
- [x] Sim runs on a `QThread`, delivering `(snapshot, events)` per tick to the UI via signals; the UI never blocks on the sim. — `ui/sim_worker.SimWorker` (`tickAdvanced`/`frontierChanged`).
- [x] Snapshot-per-tick cache: scrub/seek to tick T **restores snapshot[T]** (no replay); seeking past the frontier fast-forwards the sim; you can only scrub within the simulated frontier. — `playback.py` (`restore`/`fast_forward_to`/`frontier`).
- [x] Virtualized `QListView` "Annals" dock streams events and stays responsive across many years. — `ui/annals_model.py`.
- [x] An inspection dock exists and updates on selection (now populated: tile → faction dossier + bloodline + diplomacy). — `ui/mainwindow.describe_tile`.
- [x] Verification: offscreen UI smoke tests drive advance / step / scrub / show-all and confirm scrub restores without new events. — `tests/test_ui_shell.py`, `tests/test_playback.py`.
