"""Headless driver CLI: it advances a run, dumps JSONL events, saves and reloads.

``--years N`` advances N whole years; a year is ``TICKS_PER_YEAR`` monthly ticks,
each emitting one heartbeat, so a run of N years produces ``N * TICKS_PER_YEAR``
events.
"""

import json

from arda_sim import TICKS_PER_YEAR
from arda_sim.driver import main, run
from arda_sim.pipeline import HEARTBEAT_EVENT_TYPE


def test_run_advances_requested_years():
    world = run("fellowship", 7)
    assert len(world.events) == 7 * TICKS_PER_YEAR


def test_main_dumps_jsonl_event_stream(capsys):
    rc = main(["--seed", "fellowship", "--years", "4"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    assert len(lines) == 4 * TICKS_PER_YEAR
    first = json.loads(lines[0])
    assert first["type"] == HEARTBEAT_EVENT_TYPE
    assert set(first) >= {"id", "year", "type", "subject_ids", "importance", "payload"}


def test_main_save_then_load_continues(tmp_path, capsys):
    path = tmp_path / "cli.ardasave.json"
    main(["--seed", "moria", "--years", "10", "--save", str(path)])
    capsys.readouterr()  # discard first dump

    main(["--load", str(path), "--years", "5"])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    assert len(lines) == 15 * TICKS_PER_YEAR  # 10 saved + 5 continued years
