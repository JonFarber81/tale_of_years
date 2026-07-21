# 06 — Salience + prose chronicle framework

**What to build:** The mechanism that turns the raw event stream into a readable chronicle. Every event gets a deterministic absolute importance score at emission; the annals render events as prose via per-type templates and a seeded phrase-grammar; the feed defaults to important-only with filters and fires transient on-map pulses for high-salience events. This establishes the framework; each later system ticket contributes its own event templates + salience weights.

**Blocked by:** 02, 05

**Status:** done

- [x] Salience scorer assigns `importance` (0–100) at emission = `type base-weight × subject prominence × scale × canon-bump`, deterministic (no RNG), immutable once written.
- [x] Character prominence (from ticket 05) feeds the score; a faction-prominence input is honoured when factions exist (ticket 07).
- [x] A phrase-grammar/template engine renders `Event.text` from `subject_ids`/`location_id`/`payload`, deterministic and offline (no external dependency); templates authored for the event types that exist so far.
- [x] Annals feed filters on the four indices (subject, faction, year, type) + an importance threshold; defaults to **important-only** with one-click "show all".
- [x] Above-threshold events fire a transient on-map pulse at their `location_id`.
- [x] The `Event.text` field is the swappable seam (a future LLM backend could replace the renderer without touching sim code).
- [x] Tests: identical importance scores under a fixed run; prose renders deterministically; feed filtering returns the right subsets.

## Implementation notes

- New headless module `src/arda_sim/chronicle.py` owns salience scoring (integer-only, float-determinism-safe), the seeded phrase-grammar prose renderer, `AnnalsFilter` (four indices + threshold), and `pulse_events`. `finalize_event` is the single seam the pipeline calls per event at emission; systems now emit *structured-only* events (importance/text stripped from `characters.py`).
- `scale` and `canon-bump` factors and the `site_names`/`faction_of` inputs are wired as documented ×1.0 / empty seams — the formula shape is fixed now; later tickets (07 factions, 11 war) register their base-weights, scaled magnitudes, canon-aligned types, and per-index UI filters into it.
- UI: `AnnalsModel` filters (default important-only) with a "Show all" toolbar toggle; above-threshold located events fire a self-cleaning ring pulse via `MapView.pulse`.
