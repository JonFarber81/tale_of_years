# The Tale of Years

**Watch the Third Age of Middle-earth write its own history.**

> ### ⚠️ A note on what this really is
>
> **This project is, first and foremost, a personal playground for getting better
> at working with Claude Code.** The point is to
> push on what I can do with an AI coding agent. Learning how far to trust it, how to structure a
> codebase so it stays navigable, where it shines and where it needs a short leash
> — while building something genuinely fun to watch. 
>
> The great majority of this code was written by Claude Code, and the workflow
> leans heavily on **[Matt Pocock](https://www.aihero.dev/)'s Claude skills** —
> his packaged agent skills for TDD, code review, domain modeling, deep-module
> interface design, refactor planning, and the rest do a lot of the heavy lifting
> in how the work gets planned, built, and reviewed. Treat the code as an artifact
> of that experiment as much as an app.

`The Tale of Years` is a seeded, deterministic simulation of north-west
Middle-earth that begins at **TA 2965** and advances **one month at a time**,
open-ended. It does not replay the books — it grows an *alternate* history tick by
tick from an accurate starting roster, rendered on a tiled map: characters are
born and die, crowns pass, realms rise and are absorbed, factions warm to allies
and declare war. You watch it stream past in an annals feed and on coloured
territory; you can pause, change speed, step a month, scrub the timeline, and
click any power — or any event in the annals — to read its dossier.

It *tends* toward canon without being scripted. A single **canonicity** knob
(`0..1`) weights the dynamics — at `0` history runs free, at `1` it leans hard
toward the legendarium — but it is free to diverge: Frodo might never be born,
Gondor might fall early, Arnor might be restored a century too soon. Every run is
reproducible from a human-shareable **seed string**, so a history you love can be
replayed or handed to someone else.

<img width="1512" height="949" alt="image" src="https://github.com/user-attachments/assets/35100900-05c6-4195-a681-8daabf52a856" />


> This is a personal, non-commercial fan project. Middle-earth, its places, and
> its peoples are the creation of J.R.R. Tolkien and belong to the Tolkien Estate.

---

## How it works

The design splits cleanly into a **headless simulation core** and a **UI that is
a pure consumer** of it — the entire sim can be driven and observed without ever
starting Qt.

- **The `World`** is the single authoritative state container: id-keyed dataclass
  records (characters, factions, regions, events, …) plus a seeded RNG and an
  append-only event log. Every cross-reference is an integer id, so the whole
  world is a plain serializable tree with no pointer cycles.
- **A tick is one month** (`TICKS_PER_YEAR = 12`). It advances by running a fixed,
  ordered pipeline of systems, each a pure `system(world, rng) -> events` that
  mutates state and returns the events it emitted. A single seeded RNG threaded
  through every system in a fixed phase order is the reproducibility contract:
  same seed + scenario + canonicity ⇒ bit-identical run, every time.
- **State is the source of truth; events describe what happened.** The sim is not
  event-sourced — events never drive state. Save is a state snapshot plus the
  event log; load rehydrates directly rather than replaying.
- **The chronicle** scores every event's *salience* (0–100) and renders its prose
  at emission, in one place, so the annals read as history rather than a log. The
  prose renderer is a deliberate seam a future LLM backend can replace without
  touching a line of sim code.

### The tick pipeline

Each month runs these phases in order (the order is part of the reproducibility
contract):

| Phase | What it does | Status |
|------:|--------------|:------:|
| 1 · aging / births / deaths | per-race lifecycle; Elves accrue weariness and sail West | ✅ built |
| 2 · succession | a fallen leader's heir resolved by the realm's succession rule; failed lines fragment or are absorbed | ✅ built |
| 3 · faction decisions | each power scores a weighted-utility intent menu (muster / attack / fortify / seek-pact / build) | ✅ built |
| 4 · diplomacy & vassalage | disposition drifts toward a frozen canon baseline; treaties, marriages, vassalage, provider-pacts; the war flag | ✅ built |
| 5 · movement | armies march tile-to-tile under attrition and supply lag | ✅ built |
| 6 · the Nazgûl hunt | the Nine move toward the Ring's scent; the capture attempt resolves in the Ring phase | ✅ built |
| 7 · war & battles | field battles, sieges, conquest, razing, provider hosts, coastal raids | ✅ built |
| 8 · construction & economy | income to a treasury; founding, growing, and roads where there is peace | ✅ built |
| 9 · the One Ring | a single tracked artifact under the XOR invariant; corruption, pull, transfers, and its terminal outcomes | ✅ built |
| 10 · Sauron's rise | the shadow lengthens; a canon-pressure scalar bends musters, providers, and the Nine toward the War of the Ring | ✅ built |

The **One Ring** is a single bespoke record, seeded quietly borne by Bilbo,
always somewhere definite (the *XOR invariant*: it is carried by exactly one
character **or** lies at exactly one site, never both, never neither). It moves by
a closed set of canonicity-weighted transfer modes (inheritance, gift, theft,
loss, being found, capture in war, or a deliberate errand), carries a per-bearer
`corruption` that attenuates but never resets across hands and a global `pull`
that spikes on use and decays, and can reach its **terminal outcomes** — destroyed
in an active Orodruin (the Nine unmade, Sauron broken), reclaimed by the Dark
Lord, or left lying lost. **Sauron's rise** recomputes a `sauron_strength` scalar
each month from a canon baseline weighted by the canonicity knob plus emergent
deltas; consumed by the *next* tick, it scales Mordor's musters, provider
commitment, and the **nine named Nazgûl** who hunt while Sauron and the Ring
endure.

Also built: the **tile substrate** and the authored **TA 2965 scenario dataset**
(regions, sites, routes for NW Middle-earth), the **PySide6/Qt UI shell** (map
canvas, play/pause/step/scrub timeline, interactive annals feed, inspection
dock), and **save / load** with exact RNG resume. Still to come: packaging.

---

## Getting started

Requires **Python 3.9+** (developed on 3.13). The simulation core has **no runtime
dependencies**; the desktop UI uses PySide6.

```bash
# clone, then from the repo root:
python -m venv .venv && source .venv/bin/activate
pip install -e ".[ui]"      # sim core + Qt UI  (use ".[dev]" to also get pytest)
```

### Watch it on the map

```bash
arda-sim-ui --seed fellowship --canonicity 1.0
# or: python -m arda_sim.ui.app --seed fellowship
```

Play/pause, change speed, step a month, scrub the timeline, and click any realm's
territory to open its dossier in the **Codex** — the browser pane where every
entity is a page, with back/forward history and a name-search omnibox. A faction
dossier carries internal tabs (Overview, and a **Dynasty** tab that draws the
ruling bloodline as a linked tree — the seated ruler and presumptive heir badged,
the dead marked, spouses hung inline — each node a link to the kin's own page).

The **annals feed** reads as a chronicle, not a log: events group under year
dividers, colored by category bucket (**war** red, **diplomacy** blue,
**dynasty** purple, **construction** green) with important events bold and the
rest dimmed under *Show all*. The bucket legend doubles as a filter — uncheck a
chip to hide that category. Clicking an event opens its **dossier** in the Codex
(battles, sieges, conquests, and razings render as composed
prose from the recorded facts), and an event that happened *somewhere* — marked
with a pin — also pans the map to the spot with a transient pulse. Zoom runs
from the whole map just fitting the window down to tile level.

### Run it headless

The sim needs no display — advance a seeded run and dump its events:

```bash
arda-sim --seed fellowship --years 50
arda-sim --seed fellowship --years 200 --save run.json     # persist
arda-sim --load run.json --years 50                        # resume, bit-identically
```

### Tests

```bash
pip install -e ".[dev]"
pytest            # ~350 tests; the whole sim is exercised headless
```

Determinism is a first-class, tested property: runs are compared for
bit-identical output across processes and across a save/load boundary.

---

## Repository layout

```
src/arda_sim/
  world.py          the World spine — state, ids, clock, event log
  entities.py       the serializable record base + Event
  pipeline.py       the fixed monthly tick pipeline
  rng.py            seeded RNG (reproducibility)
  persistence.py    save / load (state snapshot + event log)
  snapshot.py       immutable per-tick views the UI renders from
  tiles.py          the tile substrate (terrain, regions, ownership, borders)
  characters.py     people & lifecycle; kinship as a query over id-fields
  factions.py       powers, territory, and the phase-2 faction turn
  succession.py     dynasties & the passing of crowns
  diplomacy.py      disposition, stance, treaties, vassalage, the war flag
  armies.py         hosts: muster, march, attrition, supply lag
  war.py            battles, sieges, conquest, razing, providers, raids
  economy.py        treasury income; founding, growing, roads
  ring.py           the One Ring — one tracked artifact, XOR invariant, transfers
  sauron.py         Sauron's rise: canon-pressure scalar + the nine Nazgûl
  chronicle.py      salience scoring + prose rendering + the annals feed
  scenarios/        the authored TA 2965 dataset
  ui/               PySide6/Qt shell (map, timeline, annals, inspection)
tests/              headless test suite
docs/adr/           architecture decision records
CONTEXT.md          the project's ubiquitous-language glossary
```

## Design docs

The reasoning behind the model lives with the code:

- **[`CONTEXT.md`](CONTEXT.md)** — the glossary / ubiquitous language (faction,
  disposition, stance, vassalage, succession, salience, …).
- **[`docs/adr/`](docs/adr/)** — architecture decision records, e.g. tiles as the
  substrate, one faction record switched by `kind`, the monthly-tick clock,
  disposition decaying toward a frozen canon baseline, the One Ring as a single
  artifact under an XOR invariant, canon pressure as soft weighting only, a
  corrupt bearer falling to the Shadow, and war gated by provocation and
  readiness rather than raised on a hostile disposition alone.
- **[`.scratch/arda-history-v1/spec.md`](.scratch/arda-history-v1/spec.md)** — the
  full v1 design blueprint and the build tickets it decomposes into.
