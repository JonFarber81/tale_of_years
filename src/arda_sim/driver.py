"""Headless driver: start a run from a seed, advance K years, dump the event
stream. No UI — this is the top testing seam the whole sim is exercised through.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from typing import List, Optional

from .entities import Event
from .metrics import war_summary
from .persistence import canonical_json, load, save
from .pipeline import run_years
from .world import World


def run(seed: str, years: int, canonicity: float = 1.0) -> World:
    """Build a fresh run from ``seed`` and advance it ``years`` whole years.

    A year is ``TICKS_PER_YEAR`` monthly ticks, so this advances the tick clock by
    ``years * TICKS_PER_YEAR``.
    """
    world = World.new_run(seed, canonicity=canonicity)
    run_years(world, years)
    return world


def _dump_events(events: List[Event]) -> str:
    """Render an event stream as one canonical-JSON object per line (JSONL)."""
    return "\n".join(canonical_json(asdict(ev)) for ev in events)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arda-sim",
        description="Headless arda_sim driver: advance a seeded run and dump events.",
    )
    parser.add_argument("--seed", default="fellowship", help="human-shareable seed string")
    parser.add_argument("--years", type=int, default=50, help="number of years to advance")
    parser.add_argument(
        "--canonicity", type=float, default=1.0, help="canon-leaning knob 0..1"
    )
    parser.add_argument("--load", help="load a saved run from this path instead of starting fresh")
    parser.add_argument("--save", help="save the resulting run to this path")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print the war-layer run summary instead of the event stream",
    )
    args = parser.parse_args(argv)

    if args.load:
        world = load(args.load)
        run_years(world, args.years)
    else:
        world = run(args.seed, args.years, canonicity=args.canonicity)

    if args.summary:
        # The war summary only means something on a *populated* run, so it seeds
        # the canon roster and territory (the bare-skeleton --load/default path
        # above carries no factions to fight). Fresh only — a reload keeps its own.
        if not args.load:
            from .factions import seed_world

            world, _grid, _names = seed_world(args.seed, canonicity=args.canonicity)
            run_years(world, args.years)
        summary = war_summary(world.events, args.years)
        sys.stdout.write("\n".join(summary.as_lines()) + "\n")
        if args.save:
            save(world, args.save)
        return 0

    sys.stdout.write(_dump_events(world.events))
    if world.events:
        sys.stdout.write("\n")

    if args.save:
        save(world, args.save)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
