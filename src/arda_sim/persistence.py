"""Save/load: canonical-JSON snapshot of state + event log + RNG state, behind a
storage-backend seam.

Save is ``json.dumps(..., sort_keys=True)`` of a provenance header plus the plain
state tree — never ``pickle`` or ``hash()``, both of which are non-portable and
non-deterministic. Load is a direct rehydrate (not an event replay). A reloaded
run continues bit-identically to one that never stopped.
"""

from __future__ import annotations

import json
import platform
from dataclasses import asdict
from typing import Any, Dict

from . import RNG_FAMILY, SCHEMA_VERSION, START_YEAR, TICKS_PER_YEAR, __version__
from . import characters as _characters  # noqa: F401  (registers the Character type)
from . import factions as _factions  # noqa: F401  (registers the Faction type)
from .entities import Event, entity_from_dict
from .rng import state_from_jsonable, state_to_jsonable
from .world import RunConfig, World


def canonical_json(obj: Any) -> str:
    """The single definition of "canonical JSON" for this project: sorted keys,
    UTF-8 preserved, never pickle or ``hash()``. Used for both saves and the
    driver's event dumps so the two never drift.
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)

def _migrate_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """v1 stored a yearly ``current_year``; v2 stores a monthly ``tick`` clock.

    A v1 save sat at the first month of its year, so ``tick = (year - start) *
    TICKS_PER_YEAR``. Events keep their year stamp unchanged.
    """
    state = data["state"]
    year = state.pop("current_year", START_YEAR)
    state["tick"] = (year - START_YEAR) * TICKS_PER_YEAR
    data["provenance"]["schema_version"] = 2
    return data


# Ordered chain of migration functions, indexed by the schema version they
# upgrade *from*. Grows as the schema evolves so old saves keep loading. Each
# entry: (from_version) -> callable(save_dict) -> save_dict.
_MIGRATIONS: Dict[int, Any] = {
    1: _migrate_v1_to_v2,
}


def _provenance(world: World) -> Dict[str, Any]:
    """Build the provenance header — the run's identity and environment."""
    return {
        "schema_version": SCHEMA_VERSION,
        "code_version": __version__,
        "python_version": platform.python_version(),
        "rng_family": RNG_FAMILY,
        "scenario_id": world.config.scenario_id,
        "scenario_version": world.config.scenario_version,
        "seed_str": world.config.seed_str,
        # canonicity is run config too; kept with the rest of the run identity.
        "canonicity": world.config.canonicity,
    }


def to_dict(world: World) -> Dict[str, Any]:
    """Serialize a world to a plain, JSON-ready dict.

    Entities are emitted as a list sorted by id (stable ordering; ints stay ints
    rather than being coerced to JSON string keys).
    """
    return {
        "provenance": _provenance(world),
        "state": {
            "tick": world.tick,
            "id_counter": world.id_counter,
            "entities": [asdict(e) for e in _sorted_entities(world)],
            "events": [asdict(ev) for ev in world.events],
            "rng_state": state_to_jsonable(world.rng.getstate()),
        },
    }


def _sorted_entities(world: World):
    return [world.entities[i] for i in sorted(world.entities)]


def from_dict(data: Dict[str, Any]) -> World:
    """Rehydrate a world from a ``to_dict`` payload, applying migrations first."""
    data = _migrate(data)
    prov = data["provenance"]
    state = data["state"]

    config = RunConfig(
        seed_str=prov["seed_str"],
        # canonicity was added to the header after the initial schema; default
        # for any header that predates it so old saves keep loading.
        canonicity=prov.get("canonicity", 1.0),
        scenario_id=prov["scenario_id"],
        scenario_version=prov["scenario_version"],
    )
    world = World(
        config=config,
        tick=state["tick"],
        id_counter=state["id_counter"],
    )
    for e in state["entities"]:
        entity = entity_from_dict(e)
        world.entities[entity.id] = entity
    world.events = [Event(**ev) for ev in state["events"]]
    world.rng.setstate(state_from_jsonable(state["rng_state"]))
    return world


def _migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    """Run the migration chain until the save matches the current schema version."""
    version = data["provenance"]["schema_version"]
    while version < SCHEMA_VERSION:
        migrate = _MIGRATIONS.get(version)
        if migrate is None:
            raise ValueError(
                f"No migration from schema version {version} to {SCHEMA_VERSION}"
            )
        data = migrate(data)
        version = data["provenance"]["schema_version"]
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"Save schema version {version} is newer than supported {SCHEMA_VERSION}"
        )
    return data


def dumps(world: World) -> str:
    """Canonical JSON string for a world: sorted keys, no pickle, no hash()."""
    return canonical_json(to_dict(world))


def loads(text: str) -> World:
    """Rehydrate a world from a canonical JSON string."""
    return from_dict(json.loads(text))


def save(world: World, path: str) -> None:
    """Write a world to ``path`` as canonical JSON (UTF-8)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(world))


def load(path: str) -> World:
    """Read and rehydrate a world from a canonical-JSON file at ``path``."""
    with open(path, "r", encoding="utf-8") as fh:
        return loads(fh.read())
