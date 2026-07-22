"""Locating bundled reference assets (the sprite tilesets).

The reference assets live in ``references/`` at the repo root, outside the
package. For the v1 editable install that directory is a fixed number of parents
above this file; a real bundle (Briefcase, ticket 16) would ship them as package
data and this is the one place to change.
"""

from __future__ import annotations

from pathlib import Path

# The Kenney roguelike/RPG pack (CC0), bundled for terrain sprites (ADR-0001).
TILESET_RELPATH = (
    "tilesets/kenney_roguelike-rpg/Spritesheet/roguelikeSheet_transparent.png"
)

# The Kenney Roguelike Characters pack (CC0), bundled for the host people sprites
# (map-visuals ticket 03). Same 16px/stride-17 geometry as the terrain sheet.
CHARACTER_TILESET_RELPATH = (
    "tilesets/kenney_roguelike-characters/Spritesheet/roguelikeChar_transparent.png"
)


def references_dir() -> Path:
    """The repo-root ``references/`` directory (editable-install layout)."""
    # this file: src/arda_sim/ui/assets.py -> parents[3] is the repo root.
    return Path(__file__).resolve().parents[3] / "references"


def tileset_path() -> Path:
    """Absolute path to the Kenney roguelike spritesheet.

    Raises ``FileNotFoundError`` with a clear message if the asset is missing,
    so a mis-packaged build fails loudly rather than rendering blank tiles.
    """
    path = references_dir() / TILESET_RELPATH
    if not path.is_file():
        raise FileNotFoundError(f"tileset spritesheet not found at {path}")
    return path


def character_tileset_path() -> Path:
    """Absolute path to the Kenney Roguelike Characters spritesheet.

    Raises ``FileNotFoundError`` with a clear message if the asset is missing,
    so a mis-packaged build fails loudly rather than rendering blank hosts.
    """
    path = references_dir() / CHARACTER_TILESET_RELPATH
    if not path.is_file():
        raise FileNotFoundError(f"character spritesheet not found at {path}")
    return path
