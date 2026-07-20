import os
import subprocess
import sys
from pathlib import Path


def test_package_is_importable_without_pytest_pythonpath():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-c", "import arda_sim; print(arda_sim.__file__)"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "arda_sim" in result.stdout
