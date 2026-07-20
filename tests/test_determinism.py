"""Determinism / reproducibility — the highest-priority contract.

Same (seed, scenario, canonicity) -> byte-identical run, in-process and across
processes. Different seed, or different canonicity, diverges.
"""

import subprocess
import sys

from arda_sim.driver import run
from arda_sim.persistence import dumps


def _run_blob(seed, years=30, canonicity=1.0):
    return dumps(run(seed, years, canonicity=canonicity))


def test_same_inputs_byte_identical_in_process():
    assert _run_blob("fellowship") == _run_blob("fellowship")


def test_different_seed_diverges():
    assert _run_blob("fellowship") != _run_blob("nazgul")


def test_different_canonicity_diverges_in_provenance():
    # v1 has no canonicity-consuming systems yet, so state is identical, but the
    # run identity (canonicity in the provenance header) must differ.
    assert _run_blob("fellowship", canonicity=1.0) != _run_blob("fellowship", canonicity=0.0)


def test_seed_string_stored_verbatim():
    world = run("A Elbereth Gilthoniel!", 3)
    assert world.config.seed_str == "A Elbereth Gilthoniel!"


_CROSS_PROCESS_SNIPPET = (
    "import sys; sys.path.insert(0, 'src');"
    "from arda_sim.driver import run;"
    "from arda_sim.persistence import dumps;"
    "sys.stdout.write(dumps(run('crossproc', 25)))"
)


def test_byte_identical_across_processes():
    outs = [
        subprocess.run(
            [sys.executable, "-c", _CROSS_PROCESS_SNIPPET],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for _ in range(2)
    ]
    assert outs[0] == outs[1]
    # And the same as an in-process run: the RNG derivation is process-independent.
    assert outs[0] == dumps(run("crossproc", 25))
