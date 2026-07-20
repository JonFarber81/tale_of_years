"""Core-model behaviour: id space, entity base, the tick loop, the heartbeat."""

from arda_sim import START_YEAR
from arda_sim.entities import EntityStatus, Event
from arda_sim.pipeline import HEARTBEAT_EVENT_TYPE, PIPELINE, run_tick, run_ticks
from arda_sim.world import World


def test_new_run_starts_at_canonical_year():
    world = World.new_run("seed")
    assert world.current_year == START_YEAR  # TA 2965
    assert world.config.seed_str == "seed"
    assert world.events == []


def test_ids_are_monotonic_and_never_reused():
    world = World.new_run("seed")
    a = world.add_entity("character", "Aragorn")
    b = world.add_entity("faction", "Gondor")
    ev = world.new_event("test")
    assert [a.id, b.id, ev.id] == [1, 2, 3]
    assert world.id_counter == 4


def test_entity_base_fields_and_default_status():
    world = World.new_run("seed")
    e = world.add_entity("character", "Bilbo")
    assert e.kind == "character"
    assert e.name == "Bilbo"
    assert e.created_year == START_YEAR
    assert e.status == EntityStatus.ACTIVE.value == "active"


def test_pipeline_has_eight_phases_in_fixed_order():
    names = [name for name, _ in PIPELINE]
    assert names == [
        "aging_births_deaths",
        "faction_decisions",
        "diplomacy",
        "movement",
        "war",
        "construction_economy",
        "sauron_rise",
        "salience_bookkeeping",
    ]


def test_tick_increments_year_and_emits_placeholder():
    world = World.new_run("seed")
    events = run_tick(world)
    assert world.current_year == START_YEAR + 1
    assert len(events) == 1
    (heartbeat,) = events
    assert isinstance(heartbeat, Event)
    assert heartbeat.type == HEARTBEAT_EVENT_TYPE
    assert heartbeat.year == START_YEAR  # stamped with the year it simulated
    assert world.events == events


def test_run_ticks_produces_one_event_per_year():
    world = World.new_run("seed")
    events = run_ticks(world, 10)
    assert len(events) == 10
    assert [e.year for e in events] == list(range(START_YEAR, START_YEAR + 10))
    assert world.current_year == START_YEAR + 10


def test_all_events_have_resolvable_ids_and_years():
    world = World.new_run("seed")
    run_ticks(world, 5)
    ids = [e.id for e in world.events]
    assert len(ids) == len(set(ids))  # unique
    assert all(e.year >= START_YEAR for e in world.events)
