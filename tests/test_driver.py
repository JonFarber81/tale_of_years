"""Headless driver CLI: it advances a run, dumps JSONL events, saves and reloads."""

import json

from arda_sim.driver import main, run
from arda_sim.pipeline import HEARTBEAT_EVENT_TYPE


def test_run_advances_requested_years():
    world = run("fellowship", 7)
    assert len(world.events) == 7


def test_main_dumps_jsonl_event_stream(capsys):
    rc = main(["--seed", "fellowship", "--years", "4"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    assert len(lines) == 4
    first = json.loads(lines[0])
    assert first["type"] == HEARTBEAT_EVENT_TYPE
    assert set(first) >= {"id", "year", "type", "subject_ids", "importance", "payload"}


def test_main_save_then_load_continues(tmp_path, capsys):
    path = tmp_path / "cli.ardasave.json"
    main(["--seed", "moria", "--years", "10", "--save", str(path)])
    capsys.readouterr()  # discard first dump

    main(["--load", str(path), "--years", "5"])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    assert len(lines) == 15  # 10 saved + 5 continued
