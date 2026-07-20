"""Seeded RNG: one ``random.Random`` per run, derived deterministically from a
human-shareable seed string, plus JSON-safe (de)serialization of its state.

The RNG family is locked to ``random.Random`` for v1; ``getstate()``/``setstate()``
are the exact-resume contract, so a reloaded run continues bit-identically.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any, List


def seed_int_from_str(seed_str: str) -> int:
    """Derive the integer RNG seed from a seed string via SHA-256.

    Uses the first 8 bytes of the digest, big-endian — stable across processes,
    platforms, and Python versions (unlike ``hash()``, which must never be used).
    """
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def make_rng(seed_str: str) -> random.Random:
    """Build the seeded ``random.Random`` for a run from its seed string."""
    return random.Random(seed_int_from_str(seed_str))


def state_to_jsonable(state: tuple) -> List[Any]:
    """Convert ``random.Random.getstate()`` into a JSON-serializable list.

    ``getstate()`` returns ``(version, internal_tuple, gauss_next)``; JSON has no
    tuples, so nest it as lists. ``state_from_jsonable`` is the exact inverse.
    """
    version, internal, gauss_next = state
    return [version, list(internal), gauss_next]


def state_from_jsonable(data: List[Any]) -> tuple:
    """Rebuild a ``setstate``-ready tuple from ``state_to_jsonable`` output.

    ``setstate`` requires exact types: an int version, a tuple of ints, and the
    gauss-next float-or-None. JSON round-trips these as lists/ints, so re-tuple.
    """
    version, internal, gauss_next = data
    return (int(version), tuple(int(x) for x in internal), gauss_next)
