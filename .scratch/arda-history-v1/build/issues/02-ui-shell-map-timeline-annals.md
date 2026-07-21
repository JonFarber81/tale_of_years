# 02 — UI shell: map canvas, timeline, annals feed, snapshot playback

**What to build:** The PySide6/Qt desktop shell that lets a viewer watch the skeleton sim run on the v7 map. The v7 image is the canvas with pan/zoom; a timeline toolbar gives play / pause / step-a-year / speed / scrub; an annals dock shows the event stream as it arrives; an inspection dock exists (stub content for now). The sim runs on a background thread and delivers a snapshot + events per year, cached so scrubbing restores a stored snapshot instantly rather than re-simulating.

> **Update (ADR-0003):** a tick is now a **month**. Step advances one tick; the scrub slider and the snapshot cache key on the absolute **tick**, not the year; the date label shows year + month. The annals stay year-grained (events keep a `year` stamp), so a mid-year scrub shows that whole year's annals while the map reflects the exact month.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `QGraphicsView`/`QGraphicsScene` renders `references/Middle Earth v7.jpg` as the canvas with pan and zoom.
- [ ] Timeline toolbar: play, pause, step-forward-one-year, speed (ticks/sec) control, and a scrub `QSlider`; current TA year shown prominently.
- [ ] Sim runs on a `QThread`, delivering `(snapshot, events)` per year to the UI via signals; the UI never blocks on the sim.
- [ ] Snapshot-per-year cache: scrub/seek to year T **restores snapshot[T]** (no replay); seeking past the simulated frontier fast-forwards the sim; you can only scrub within simulated years.
- [ ] Virtualized `QListView` "Annals" dock streams events and stays responsive across many years.
- [ ] An inspection dock exists and updates on selection (stub fields acceptable until real entities land).
- [ ] Manual verification: launch the app, watch years advance, pause/step/scrub, confirm scrub is instant.
