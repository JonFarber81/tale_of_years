"""Locating bundled reference assets (the v7 map image).

The reference images live in ``references/`` at the repo root, outside the
package. For the v1 editable install that directory is a fixed number of parents
above this file; a real bundle (Briefcase, ticket 16) would ship them as package
data and this is the one place to change.
"""

from __future__ import annotations

from pathlib import Path

V7_MAP_FILENAME = "Middle Earth v7.jpg"


def references_dir() -> Path:
    """The repo-root ``references/`` directory (editable-install layout)."""
    # this file: src/arda_sim/ui/assets.py -> parents[3] is the repo root.
    return Path(__file__).resolve().parents[3] / "references"


def v7_map_path() -> Path:
    """Absolute path to the v7 Middle-earth map image.

    Raises ``FileNotFoundError`` with a clear message if the asset is missing,
    so a mis-packaged build fails loudly rather than rendering a blank canvas.
    """
    path = references_dir() / V7_MAP_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"v7 map image not found at {path}")
    return path
