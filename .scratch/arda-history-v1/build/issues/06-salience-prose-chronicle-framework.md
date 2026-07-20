# 06 — Salience + prose chronicle framework

**What to build:** The mechanism that turns the raw event stream into a readable chronicle. Every event gets a deterministic absolute importance score at emission; the annals render events as prose via per-type templates and a seeded phrase-grammar; the feed defaults to important-only with filters and fires transient on-map pulses for high-salience events. This establishes the framework; each later system ticket contributes its own event templates + salience weights.

**Blocked by:** 02, 05

**Status:** ready-for-agent

- [ ] Salience scorer assigns `importance` (0–100) at emission = `type base-weight × subject prominence × scale × canon-bump`, deterministic (no RNG), immutable once written.
- [ ] Character prominence (from ticket 05) feeds the score; a faction-prominence input is honoured when factions exist (ticket 07).
- [ ] A phrase-grammar/template engine renders `Event.text` from `subject_ids`/`location_id`/`payload`, deterministic and offline (no external dependency); templates authored for the event types that exist so far.
- [ ] Annals feed filters on the four indices (subject, faction, year, type) + an importance threshold; defaults to **important-only** with one-click "show all".
- [ ] Above-threshold events fire a transient on-map pulse at their `location_id`.
- [ ] The `Event.text` field is the swappable seam (a future LLM backend could replace the renderer without touching sim code).
- [ ] Tests: identical importance scores under a fixed run; prose renders deterministically; feed filtering returns the right subsets.
