"""The tick: a fixed, ordered pipeline of systems.

A year advances by running a fixed list of ``system(world, rng) -> events`` in a
deterministic order, each mutating authoritative state and returning the events
it emitted. The single seeded RNG threaded through every system is the
reproducibility contract.

In the walking skeleton the eight game phases are registered but empty; a single
placeholder ``tick`` heartbeat event is emitted per year to exercise the event
stream and the RNG-resume path until real systems land.
"""

from __future__ import annotations

import random
from typing import Callable, List, Tuple

from .entities import Event
from .world import World

System = Callable[[World, random.Random], List[Event]]

# Placeholder event type emitted once per tick until systems produce real events.
HEARTBEAT_EVENT_TYPE = "tick"


def _aging_births_deaths(world: World, rng: random.Random) -> List[Event]:  # phase 1
    return []


def _faction_decisions(world: World, rng: random.Random) -> List[Event]:  # phase 2
    return []


def _diplomacy(world: World, rng: random.Random) -> List[Event]:  # phase 3
    return []


def _movement(world: World, rng: random.Random) -> List[Event]:  # phase 4
    return []


def _war(world: World, rng: random.Random) -> List[Event]:  # phase 5
    return []


def _construction_economy(world: World, rng: random.Random) -> List[Event]:  # phase 6
    return []


def _sauron_rise(world: World, rng: random.Random) -> List[Event]:  # phase 7
    return []


def _salience_bookkeeping(world: World, rng: random.Random) -> List[Event]:  # phase 8
    return []


# The fixed phase order. Each entry is (phase name, system). Order is the
# reproducibility contract and must not change casually — see spec phase-flow.
PIPELINE: Tuple[Tuple[str, System], ...] = (
    ("aging_births_deaths", _aging_births_deaths),
    ("faction_decisions", _faction_decisions),
    ("diplomacy", _diplomacy),
    ("movement", _movement),
    ("war", _war),
    ("construction_economy", _construction_economy),
    ("sauron_rise", _sauron_rise),
    ("salience_bookkeeping", _salience_bookkeeping),
)


def run_tick(world: World) -> List[Event]:
    """Advance the world by exactly one year and return the events emitted.

    Runs every phase in order (appending each system's events as it goes), emits
    the placeholder heartbeat, then increments the year. The heartbeat draws from
    the RNG so the resume path is genuinely exercised.
    """
    emitted: List[Event] = []
    rng = world.rng

    for _name, system in PIPELINE:
        events = system(world, rng)
        for event in events:
            world.append_event(event)
            emitted.append(event)

    # Placeholder heartbeat: proves the stream flows and advances the RNG so that
    # save->load->continue is a real test of exact RNG resume. Removed once
    # systems emit real events.
    heartbeat = world.new_event(
        type=HEARTBEAT_EVENT_TYPE,
        importance=0,
        payload={"year": world.current_year, "roll": rng.getrandbits(32)},
    )
    world.append_event(heartbeat)
    emitted.append(heartbeat)

    world.current_year += 1
    return emitted


def run_ticks(world: World, n: int) -> List[Event]:
    """Advance the world by ``n`` years, returning all events emitted across them."""
    emitted: List[Event] = []
    for _ in range(n):
        emitted.extend(run_tick(world))
    return emitted
