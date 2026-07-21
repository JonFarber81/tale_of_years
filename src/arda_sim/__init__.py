"""arda_sim — seeded, deterministic simulation core for an emergent Third Age.

v1 walking skeleton: the framework-agnostic spine (World, tick pipeline, event
log, save/load) that every game system builds on. No game logic yet.
"""

__version__ = "0.1.0"

# Fixed run constants (see .scratch/arda-history-v1/spec.md and build ticket 01).
SCHEMA_VERSION = 3  # v3: the built map (owner grid + site kinds + roads) persists.
START_YEAR = 2965  # Third Age; the scenario's canonical start.
# The tick is the unit of simulation time. A year is TICKS_PER_YEAR ticks, so the
# clock advances a *month* at a time — history unfolds gradually, not in yearly
# jumps. Per-year lifecycle rates (death/fertility/weariness) are applied against
# this scale so a monthly tick keeps the same annual behaviour. Changing this
# re-baselines every run's outcomes (the RNG stream depends on it).
TICKS_PER_YEAR = 12
RNG_FAMILY = "random.Random"
DEFAULT_SCENARIO_ID = "ta-2965-nw-middle-earth"
DEFAULT_SCENARIO_VERSION = 1
