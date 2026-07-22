"""Culture-authentic names for generated characters (issue #34).

Turns a naming register plus a stable integer identity into an authentic personal
name. The selection is a **pure function** of ``(culture, sex, seed, taken)`` — it
draws no RNG, so wiring it into the movement phase never perturbs the shared stream
and a run stays byte-stable (the hard determinism contract, ``armies.py``).

The name pools live in ``scenarios/names.json`` (data, not code) and are loaded
once and cached. The layered collision policy (Decision 5 on the issue) is: index a
given name from the pool; if that full name is already borne by a living member of
the same faction, widen it with a patronymic (Rohirric/Dwarvish) or an
epithet/place-of-origin; if a namesake still stands, append a deterministic ordinal.
"""

from __future__ import annotations

from typing import AbstractSet, Dict, Optional

from .factions import NamingCulture
from .scenarios import load_name_pools_data

# The registers that may field a (rare, deterministic) woman captain — cultures with
# canonical martial women. The rest stay male for now (Decision 3). Revisitable.
_FEMALE_CULTURES = frozenset(
    {
        NamingCulture.ROHIRRIC,
        NamingCulture.DUNEDAIN,
        NamingCulture.ELVISH,
        NamingCulture.GONDORIAN,
    }
)

# 1-in-N of an eligible culture's captains are women: low, but present. Deterministic
# — keyed off the same integer identity as the name, so it never draws RNG.
_FEMALE_DIVISOR = 8

# Deterministic index offsets, kept coprime-ish with pool sizes so the surname,
# patronymic-father and epithet sub-choices decorrelate from the given name.
_SURNAME_STRIDE = 7
_FATHER_STRIDE = 13
_EPITHET_STRIDE = 11

# Ordinal suffixes appended when a widened name still collides with a living
# namesake — "the Younger" first (a fresh captain is junior to the standing one),
# then Roman numerals for any further clashes.
_ORDINALS = ("the Younger", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


_POOLS: Optional[Dict[str, dict]] = None


def load_name_pools() -> Dict[str, dict]:
    """The per-culture name pools, loaded once from ``names.json`` and cached."""
    global _POOLS
    if _POOLS is None:
        _POOLS = load_name_pools_data()
    return _POOLS


def choose_sex(culture: NamingCulture, seed: int) -> str:
    """Deterministically pick a captain's sex: ``"F"`` (rarely) only for cultures
    with canonical martial women, else always ``"M"`` (Decision 3). RNG-free."""
    if culture not in _FEMALE_CULTURES:
        return "M"
    return "F" if seed % _FEMALE_DIVISOR == 0 else "M"


def generate_name(
    culture: NamingCulture, sex: str, seed: int, taken: AbstractSet[str]
) -> str:
    """An authentic full name for a generated character of this register.

    Pure and RNG-free: ``seed`` is a stable integer identity (see
    ``armies.generate_captain``). ``taken`` is the set of full names borne by living
    members of the same faction — the base name is widened (patronymic/epithet) and
    then ordinal-suffixed as needed until it is unused, so a century of one realm's
    captains stay recognisably distinct.
    """
    pool = load_name_pools()[culture.value]
    given = _given(pool, sex, seed)
    base = _with_surname(pool, given, seed)
    if base not in taken:
        return base

    widened = _widen(pool, given, base, sex, seed)
    if widened not in taken:
        return widened

    return _ordinalize(widened, taken)


# -- internals ------------------------------------------------------------

_POOL_KEY = {"M": "male", "F": "female"}


def _given(pool: dict, sex: str, seed: int) -> str:
    """A given name indexed from the sex-appropriate pool (male if female is empty)."""
    names = pool["given"].get(_POOL_KEY.get(sex, "male")) or pool["given"]["male"]
    return names[seed % len(names)]


def _with_surname(pool: dict, given: str, seed: int) -> str:
    """``given`` plus a pool surname where the register uses them (Hobbits)."""
    surnames = pool.get("surnames") or []
    if not surnames:
        return given
    surname = surnames[(seed // _SURNAME_STRIDE) % len(surnames)]
    return f"{given} {surname}"


def _widen(pool: dict, given: str, base: str, sex: str, seed: int) -> str:
    """Widen a colliding name: a patronymic (Rohirric/Dwarvish), else an epithet,
    else the base unchanged (the ordinal layer then guarantees uniqueness). Note the
    epithet pools carry place-of-origin forms too (e.g. Gondor's ``of Minas Tirith``),
    so the register's data — not a code branch — decides its widening flavour."""
    construction = pool.get("construction") or {}
    if construction.get("patronymic"):
        father = _patronymic_father(pool, given, seed)
        kin = "daughter" if sex == "F" else "son"
        return f"{given} {kin} of {father}"
    epithets = construction.get("epithets") or []
    if epithets:
        epithet = epithets[(seed // _EPITHET_STRIDE) % len(epithets)]
        return f"{base} {epithet}"
    return base


def _patronymic_father(pool: dict, given: str, seed: int) -> str:
    """A father's given name for a patronymic — never the bearer's own name."""
    males = pool["given"]["male"]
    idx = (seed // _FATHER_STRIDE) % len(males)
    if males[idx] == given:
        idx = (idx + 1) % len(males)
    return males[idx]


def _ordinalize(name: str, taken: AbstractSet[str]) -> str:
    """Append the first ordinal suffix that makes ``name`` unused in ``taken``."""
    for suffix in _ORDINALS:
        candidate = f"{name} {suffix}"
        if candidate not in taken:
            return candidate
    # Beyond ten living namesakes of one widened name (never seen in practice), fall
    # back to a numeric tail so the result is still guaranteed unique.
    n = len(_ORDINALS)
    while True:
        candidate = f"{name} ({n})"
        if candidate not in taken:
            return candidate
        n += 1
