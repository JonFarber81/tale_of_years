"""Run-summary metrics — the war-layer tuning gauge and regression guard (issue #13).

A read-only fold over the append-only event stream that reduces a run to the
handful of scalars which say whether its history reads like a chronicle of a few
great campaigns or a churn of small hosts:

* **musters raised** — how many hosts were put in the field,
* **battles fought** and, of those, **decisive battles** — the rare turning points,
* **hosts destroyed** — shattered in the field or bled to nothing,
* **median host size** — are the hosts that *do* muster meaningfully large,
* **share led** — the percent of hosts that marched under a named general.

Each count is also offered **per century**, normalised over the run's span, so
runs of different length compare directly against the issue's directional targets
(a handful of decisive battles a century, median host size up several-fold). This
is *reporting only* — it never feeds back into an outcome-deciding comparison, so
it touches no world state and is safe to call mid-run or after. The raw counts are
integer; the per-century view divides for display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from . import TICKS_PER_YEAR
from .armies import ARMY_DISBANDED_EVENT, ARMY_MUSTERED_EVENT
from .entities import Event
from .war import BATTLE_EVENT


@dataclass(frozen=True)
class WarSummary:
    """The reduced war-layer metrics of a run over ``span_years`` whole years.

    Raw counts are exact integers; :meth:`per_century` scales any of them to the
    issue's per-century target frame. ``median_host_size`` and ``pct_led`` are
    integer summaries over the muster events seen.
    """

    span_years: int
    musters: int
    battles: int
    decisive_battles: int
    hosts_destroyed: int
    median_host_size: int
    pct_led: int

    def per_century(self, count: int) -> float:
        """``count`` normalised to a 100-year frame (0.0 for a zero-length span)."""
        if self.span_years <= 0:
            return 0.0
        return count * 100.0 / self.span_years

    def as_lines(self) -> List[str]:
        """A short human-readable block, one metric per line (driver ``--summary``)."""
        return [
            f"span: {self.span_years} years",
            f"musters raised:   {self.musters:5d}  ({self.per_century(self.musters):.1f}/century)",
            f"battles fought:   {self.battles:5d}  ({self.per_century(self.battles):.1f}/century)",
            f"  decisive:       {self.decisive_battles:5d}  "
            f"({self.per_century(self.decisive_battles):.1f}/century)",
            f"hosts destroyed:  {self.hosts_destroyed:5d}  "
            f"({self.per_century(self.hosts_destroyed):.1f}/century)",
            f"median host size: {self.median_host_size:5d}",
            f"hosts led:        {self.pct_led:5d}%",
        ]


def _median(values: Sequence[int]) -> int:
    """The integer median of ``values`` (0 if empty; the two-middle mean floored)."""
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def war_summary(events: Iterable[Event], span_years: int) -> WarSummary:
    """Reduce an event stream to its :class:`WarSummary` over a ``span_years`` run.

    Counts muster/battle/disband events, reads host sizes and the ``led`` flag off
    the muster payloads, and folds the battle ``tier`` into the decisive count.
    Pure — it reads events only, never world state.
    """
    musters = 0
    led = 0
    sizes: List[int] = []
    battles = 0
    decisive = 0
    destroyed = 0
    for ev in events:
        if ev.type == ARMY_MUSTERED_EVENT:
            musters += 1
            sizes.append(int(ev.payload.get("size", 0)))
            if ev.payload.get("led"):
                led += 1
        elif ev.type == BATTLE_EVENT:
            battles += 1
            if ev.payload.get("tier") == "decisive":
                decisive += 1
        elif ev.type == ARMY_DISBANDED_EVENT:
            destroyed += 1
    pct_led = (led * 100 // musters) if musters else 0
    return WarSummary(
        span_years=span_years,
        musters=musters,
        battles=battles,
        decisive_battles=decisive,
        hosts_destroyed=destroyed,
        median_host_size=_median(sizes),
        pct_led=pct_led,
    )
