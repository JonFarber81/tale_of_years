"""arda_sim — seeded, deterministic simulation core for an emergent Third Age.

v1 walking skeleton: the framework-agnostic spine (World, tick pipeline, event
log, save/load) that every game system builds on. No game logic yet.
"""

__version__ = "0.1.0"

# Fixed run constants (see .scratch/arda-history-v1/spec.md and build ticket 01).
SCHEMA_VERSION = 1
START_YEAR = 2965  # Third Age; the scenario's canonical start.
RNG_FAMILY = "random.Random"
DEFAULT_SCENARIO_ID = "ta-2965-nw-middle-earth"
DEFAULT_SCENARIO_VERSION = 1
