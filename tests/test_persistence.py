"""Persistence: canonical-JSON round-trip, provenance, migration, and the
save->load->continue == never-stopping bit-identical guarantee.
"""

import json

import pytest

from arda_sim import RNG_FAMILY, SCHEMA_VERSION, __version__
from arda_sim.driver import run
from arda_sim.persistence import dumps, from_dict, load, loads, save, to_dict
from arda_sim.pipeline import run_ticks
from arda_sim.world import World


def test_round_trip_deep_equals():
    world = run("fellowship", 20)
    restored = loads(dumps(world))
    assert to_dict(restored) == to_dict(world)
    assert restored.current_year == world.current_year
    assert restored.id_counter == world.id_counter
    assert len(restored.events) == len(world.events)


def test_provenance_header_present_and_complete():
    world = run("fellowship", 5)
    prov = to_dict(world)["provenance"]
    assert prov["schema_version"] == SCHEMA_VERSION
    assert prov["code_version"] == __version__
    assert prov["rng_family"] == RNG_FAMILY
    assert prov["seed_str"] == "fellowship"
    assert "python_version" in prov
    assert prov["scenario_id"] and prov["scenario_version"]
    assert prov["canonicity"] == 1.0


def test_canonical_json_is_sorted_and_stable():
    world = run("fellowship", 5)
    text = dumps(world)
    # sort_keys makes the serialization order-stable regardless of dict order.
    reparsed = json.loads(text)
    assert text == json.dumps(reparsed, sort_keys=True, ensure_ascii=False)


def test_save_load_continue_is_bit_identical_to_never_stopping(tmp_path):
    # Never-stopping reference run: 40 years straight.
    reference = run("hornburg", 40)
    ref_blob = dumps(reference)

    # Interrupted run: 15 years, save, load, continue 25 more.
    interrupted = run("hornburg", 15)
    path = tmp_path / "run.ardasave.json"
    save(interrupted, str(path))
    resumed = load(str(path))
    run_ticks(resumed, 25)

    assert dumps(resumed) == ref_blob


def test_rng_state_survives_round_trip_exactly():
    world = run("gollum", 12)
    restored = loads(dumps(world))
    # Both RNGs must now produce the identical next stream.
    assert [world.rng.random() for _ in range(20)] == [
        restored.rng.random() for _ in range(20)
    ]


def test_load_rejects_future_schema_version():
    world = run("fellowship", 3)
    data = to_dict(world)
    data["provenance"]["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ValueError):
        from_dict(data)


def test_load_rejects_unbridgeable_old_schema_version():
    world = run("fellowship", 3)
    data = to_dict(world)
    data["provenance"]["schema_version"] = 0  # no migration registered from 0
    with pytest.raises(ValueError):
        from_dict(data)


def test_load_defaults_canonicity_when_header_predates_it():
    world = run("fellowship", 3)
    data = to_dict(world)
    del data["provenance"]["canonicity"]  # simulate a header written before the field
    restored = from_dict(data)
    assert restored.config.canonicity == 1.0


def test_never_pickles():
    # The save is text JSON, not a pickle stream; loads() parses it as JSON.
    world = run("fellowship", 3)
    text = dumps(world)
    assert isinstance(text, str)
    json.loads(text)  # must be valid JSON, no exception
    assert isinstance(loads(text), World)
