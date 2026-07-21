# 07 — Transient battle markers

**What to build:** Battles resolve invisibly — you only learn of them from
the annals feed. Put a transient marker (crossed-swords motif or a sharp
flash distinct from the salience pulse) on the tile where a battle resolved,
so wars are legible from the map alone.

**Blocked by:** —

**Status:** done

- [x] When the war phase resolves a battle in a tick, the map shows a
      battle marker on that tile for a limited time (a few ticks or a timed
      fade — implementer tunes; the existing salience-pulse machinery in
      `map_view.py` z=5 is the pattern to follow, but the battle marker must
      be visually distinct from a salience pulse).
- [x] Data source: battle events already flow to the annals — hook the same
      event stream the annals/pulse path consumes rather than adding sim
      state. Find where `mainwindow.py` routes events to `focus_tile`/pulse
      and extend that routing.
- [x] Sieges (if the war phase distinguishes them) may share the same marker
      for now — a distinct siege treatment is out of scope.
- [x] Markers clean themselves up (timer or tick-count), never accumulate,
      and survive a `refresh_armies`/`refresh_owners` rebuild untouched
      (they live on their own z-layer).
- [x] Multiple battles in one tick each get a marker; a battle on a
      currently-pulsing tile still reads (offset, layering, or the pulse
      simply yields).
- [x] Verify by running a war scenario tick-by-tick: each battle from the
      annals has a visible marker on the right tile, gone a few ticks later.
