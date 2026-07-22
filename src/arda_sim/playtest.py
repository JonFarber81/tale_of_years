"""Playtest harness — an end-of-run *chronicle* and a batch comparator.

Two read-only folds over a finished run, layered on the same event stream the
annals read (:mod:`chronicle`) and the war gauge folds (:mod:`metrics`):

* :func:`run_chronicle` reduces one finished ``(world, grid)`` to a
  :class:`RunChronicle` — the run's terminal facts (the Ring's fate and its
  year, the conquest and decisive-battle tally, who stood at the end) plus the
  handful of turning-point event lists. It renders either as a narrative report
  (:meth:`RunChronicle.as_text`, reusing :func:`chronicle.render_text` so the
  prose matches the annals) or as a flat facts dict (:meth:`RunChronicle.as_facts`).

* :func:`playtest_batch` runs many seeds to the same span and collects their
  facts, and :func:`aggregate` folds those facts into a distribution — the real
  balance gauge, turning single anecdotes into "the Ring is destroyed 1 run in 5".

Pure reporting, exactly like :mod:`metrics`: it reads a finished world and its
events, never a live tick, and touches no world state. Everything it needs is
already emitted — this module only folds and formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .chronicle import render_text
from .entities import Event
from .factions import Faction, factions, seed_world
from .metrics import WarSummary, war_summary
from .pipeline import run_years
from .ring import (
    RING_DESTROYED_FLAG,
    RING_LYING_LOST_FLAG,
    SAURON_RECLAIMED_FLAG,
)
from .tiles import TileGrid
from .war import CONQUEST_EVENT
from .world import World

# The terminal Ring fates, in resolution order, each read off a ``World.flags``
# entry the ring phase raises (issue #5). The first flag set wins; an
# unresolved run (no flag) is reported as ``"unresolved"``.
_RING_OUTCOMES: Tuple[Tuple[str, str], ...] = (
    (RING_DESTROYED_FLAG, "destroyed"),
    (SAURON_RECLAIMED_FLAG, "sauron_reclaims"),
    (RING_LYING_LOST_FLAG, "lying_lost"),
)

# The event types whose *first* occurrence marks a Ring terminal, so the
# chronicle can date the outcome. Mirrors the flags above.
_RING_TERMINAL_EVENTS: Mapping[str, str] = {
    "ring_destroyed": "destroyed",
    "ring_claimed": "sauron_reclaims",  # terminal claim only; see ``_ring_outcome``
    "ring_lost": "lying_lost",
}

# The turning-point event types the chronicle sections gather, keyed by section.
_CONQUEST_TYPES = (CONQUEST_EVENT,)


@dataclass(frozen=True)
class RunChronicle:
    """One finished run reduced to its terminal facts and turning-point events.

    ``war`` is the existing :class:`WarSummary` gauge, carried whole so a
    chronicle is a strict superset of the numeric summary. The event lists are
    slices of the run's stream (already scored), kept for the narrative render;
    the scalar fields are the flat facts the batch table compares on.
    """

    seed: str
    span_years: int
    ring_outcome: str
    ring_outcome_year: Optional[int]
    survivors: Tuple[str, ...]
    extinguished: Tuple[str, ...]
    war: WarSummary
    conquests: Tuple[Event, ...] = field(default_factory=tuple)
    decisive_battles: Tuple[Event, ...] = field(default_factory=tuple)
    ring_journey: Tuple[Event, ...] = field(default_factory=tuple)
    _world: Optional[World] = None
    _site_names: Mapping[int, str] = field(default_factory=dict)

    def as_facts(self) -> Dict[str, object]:
        """The flat, JSON-able facts the batch table and :func:`aggregate` read."""
        return {
            "seed": self.seed,
            "span_years": self.span_years,
            "ring_outcome": self.ring_outcome,
            "ring_outcome_year": self.ring_outcome_year,
            "survivors": list(self.survivors),
            "extinguished": list(self.extinguished),
            "conquests": self.war.conquests,
            "decisive_battles": self.war.decisive_battles,
            "battles": self.war.battles,
            "musters": self.war.musters,
        }

    def _sentence(self, event: Event) -> str:
        """The annals prose for ``event`` (or a bare type tag if none is templated)."""
        if self._world is None:
            return event.type
        text = render_text(self._world, event, self._site_names)
        return text if text is not None else event.type

    def as_text(self) -> str:
        """A sectioned narrative report — the human read of how the run played out."""
        lines: List[str] = []
        lines.append(f"=== Chronicle of run {self.seed!r} ({self.span_years} years) ===")

        lines.append("")
        lines.append("-- The Fate of the Ring --")
        year = f"TA {self.ring_outcome_year}" if self.ring_outcome_year else "unresolved"
        lines.append(f"Outcome: {self.ring_outcome} ({year})")
        for ev in self.ring_journey:
            lines.append(f"  TA {ev.year}: {self._sentence(ev)}")

        lines.append("")
        lines.append("-- Rise & Fall of Realms --")
        if self.conquests:
            for ev in self.conquests:
                lines.append(f"  TA {ev.year}: {self._sentence(ev)}")
        else:
            lines.append("  No seat changed hands.")

        lines.append("")
        lines.append("-- The Great Battles --")
        if self.decisive_battles:
            for ev in self.decisive_battles:
                lines.append(f"  TA {ev.year}: {self._sentence(ev)}")
        else:
            lines.append("  No decisive battle was fought.")

        lines.append("")
        lines.append("-- Standing at the End --")
        lines.append(f"  Survivors ({len(self.survivors)}): {', '.join(self.survivors) or '—'}")
        lines.append(
            f"  Extinguished ({len(self.extinguished)}): "
            f"{', '.join(self.extinguished) or '—'}"
        )

        lines.append("")
        lines.append("-- War Gauge --")
        lines.extend(f"  {line}" for line in self.war.as_lines())
        return "\n".join(lines)


def _ring_outcome(world: World, events: Sequence[Event]) -> Tuple[str, Optional[int]]:
    """The Ring's terminal fate and the year it fell, read off flags + the stream.

    The flag says *which* terminal (authoritative), the stream dates it. A
    ``ring_claimed`` event only counts as the ``sauron_reclaims`` terminal when
    its payload marks it ``terminal`` — a mortal's transient claim is not an end.
    """
    outcome = "unresolved"
    for flag, name in _RING_OUTCOMES:
        if world.flags.get(flag):
            outcome = name
            break
    if outcome == "unresolved":
        return outcome, None
    year: Optional[int] = None
    for ev in events:
        mapped = _RING_TERMINAL_EVENTS.get(ev.type)
        if mapped != outcome:
            continue
        if ev.type == "ring_claimed" and not ev.payload.get("terminal"):
            continue
        year = ev.year
        break
    return outcome, year


def _ring_journey(events: Sequence[Event]) -> Tuple[Event, ...]:
    """The Ring's hand-to-hand story: every transfer/claim and its terminal."""
    kinds = {"ring_transferred", "ring_claimed", "ring_destroyed", "ring_lost", "nazgul_unmade"}
    return tuple(ev for ev in events if ev.type in kinds)


def _standing(world: World) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """The land-holding realms/cultures still in play vs. those extinguished.

    Providers are off-map peoples that never hold ground, so they are neither a
    survivor nor an extinguished realm — they are left out of the standing.
    """
    survivors: List[str] = []
    extinguished: List[str] = []
    for fac in factions(world):
        if fac.is_provider:
            continue
        (survivors if fac.alive else extinguished).append(fac.name)
    return tuple(sorted(survivors)), tuple(sorted(extinguished))


def run_chronicle(
    world: World, grid: TileGrid, span_years: int, seed: str = ""
) -> RunChronicle:
    """Reduce a finished ``(world, grid)`` to its :class:`RunChronicle`.

    Reads the world's event stream and end state only — call it after the run
    has been advanced ``span_years`` whole years. Pure: no tick, no mutation.
    """
    events = world.events
    site_names = {site.id: site.name for site in grid.sites}
    outcome, outcome_year = _ring_outcome(world, events)
    survivors, extinguished = _standing(world)
    conquests = tuple(ev for ev in events if ev.type in _CONQUEST_TYPES)
    decisive = tuple(
        ev for ev in events if ev.type == "battle" and ev.payload.get("tier") == "decisive"
    )
    return RunChronicle(
        seed=seed,
        span_years=span_years,
        ring_outcome=outcome,
        ring_outcome_year=outcome_year,
        survivors=survivors,
        extinguished=extinguished,
        war=war_summary(events, span_years),
        conquests=conquests,
        decisive_battles=decisive,
        ring_journey=_ring_journey(events),
        _world=world,
        _site_names=site_names,
    )


def play_one(seed: str, years: int, canonicity: float = 1.0) -> RunChronicle:
    """Seed a fresh populated run, advance ``years``, and chronicle it.

    The one call a playtest needs: it seeds the canon roster and territory (the
    war layer only means anything on a populated world), runs, and folds.
    """
    world, grid, _names = seed_world(seed, canonicity=canonicity)
    run_years(world, years)
    return run_chronicle(world, grid, years, seed=seed)


def playtest_batch(
    seeds: Sequence[str], years: int, canonicity: float = 1.0
) -> List[RunChronicle]:
    """Chronicle each seed's run to the same span — the raw batch for :func:`aggregate`."""
    return [play_one(seed, years, canonicity=canonicity) for seed in seeds]


@dataclass(frozen=True)
class BatchAggregate:
    """The distribution over a batch: the balance gauge across many runs."""

    runs: int
    span_years: int
    ring_outcomes: Dict[str, int]
    median_conquests: int
    median_decisive: int
    survival_rate: Dict[str, int]  # faction name -> % of runs it survived

    def as_lines(self) -> List[str]:
        lines = [f"runs: {self.runs}  ({self.span_years} years each)", "", "Ring outcomes:"]
        for name, count in sorted(self.ring_outcomes.items(), key=lambda kv: -kv[1]):
            pct = count * 100 // self.runs if self.runs else 0
            lines.append(f"  {name:16s} {count:4d}  ({pct:3d}%)")
        lines.append("")
        lines.append(f"median conquests/run: {self.median_conquests}")
        lines.append(f"median decisive/run:  {self.median_decisive}")
        lines.append("")
        lines.append("Survival rate (share of runs a realm stood at the end):")
        for name, pct in sorted(self.survival_rate.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {name:20s} {pct:3d}%")
        return lines


def _median_int(values: Sequence[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def aggregate(chronicles: Sequence[RunChronicle]) -> BatchAggregate:
    """Fold a batch of chronicles into its outcome distribution and survival rates."""
    runs = len(chronicles)
    span = chronicles[0].span_years if chronicles else 0
    outcomes: Dict[str, int] = {}
    survived: Dict[str, int] = {}
    for ch in chronicles:
        outcomes[ch.ring_outcome] = outcomes.get(ch.ring_outcome, 0) + 1
        for name in ch.survivors:
            survived[name] = survived.get(name, 0) + 1
    survival_rate = {
        name: (count * 100 // runs if runs else 0) for name, count in survived.items()
    }
    return BatchAggregate(
        runs=runs,
        span_years=span,
        ring_outcomes=outcomes,
        median_conquests=_median_int([ch.war.conquests for ch in chronicles]),
        median_decisive=_median_int([ch.war.decisive_battles for ch in chronicles]),
        survival_rate=survival_rate,
    )


def _outcome_table(chronicles: Sequence[RunChronicle]) -> List[str]:
    """A one-row-per-seed comparison table — the at-a-glance batch view."""
    header = f"{'seed':16s} {'ring outcome':16s} {'year':>6s} {'conq':>5s} {'decis':>6s}  survivors"
    lines = [header, "-" * len(header)]
    for ch in chronicles:
        year = str(ch.ring_outcome_year) if ch.ring_outcome_year else "—"
        survivors = ", ".join(ch.survivors) if ch.survivors else "—"
        lines.append(
            f"{ch.seed[:16]:16s} {ch.ring_outcome:16s} {year:>6s} "
            f"{ch.war.conquests:5d} {ch.war.decisive_battles:6d}  {survivors}"
        )
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: ``arda-playtest`` — batch many seeds, print the table + distribution."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="arda-playtest",
        description="Run many seeded histories and compare how each played out.",
    )
    parser.add_argument(
        "--seeds",
        default="",
        help="comma-separated seed strings; overrides --count/--prefix when given",
    )
    parser.add_argument(
        "--count", type=int, default=10, help="number of generated seeds (with --prefix)"
    )
    parser.add_argument("--prefix", default="playtest", help="stem for generated seeds")
    parser.add_argument("--years", type=int, default=60, help="whole years to advance each run")
    parser.add_argument("--canonicity", type=float, default=1.0, help="canon-leaning knob 0..1")
    parser.add_argument(
        "--chronicle",
        action="store_true",
        help="also print each run's full narrative chronicle",
    )
    args = parser.parse_args(argv)

    if args.seeds:
        seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    else:
        seeds = [f"{args.prefix}-{i:03d}" for i in range(args.count)]

    chronicles = playtest_batch(seeds, args.years, canonicity=args.canonicity)

    out = sys.stdout
    if args.chronicle:
        for ch in chronicles:
            out.write(ch.as_text() + "\n\n")

    out.write("\n".join(_outcome_table(chronicles)) + "\n\n")
    out.write("\n".join(aggregate(chronicles).as_lines()) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
