"""The event dossier: the deep reading of a single annals event.

Rendered into the Inspection dock when an annals row is clicked (annals-ui
ticket 03). The war-phase marquee types — field battle, siege, conquest,
razing — get handcrafted narrative blocks composed from the event's payload;
every other type falls back to the chronicle sentence plus a readable
key/value rendering, resolving faction ids to names where it can.

Pure HTML-string functions over resolver callables (no widgets), so it tests
without a window; the dock renders the result as rich text.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from ..chronicle import IMPORTANT_THRESHOLD
from ..entities import Event
from ..war import BATTLE_EVENT, CONQUEST_EVENT, RAZING_EVENT, SIEGE_EVENT
from .annals_style import BUCKET_COLORS, bucket_of
from .dossier_html import NEUTRAL_ACCENT, banner, esc, para

# Resolvers the window supplies: id -> display name (None where unknowable).
FactionName = Callable[[int], str]
SiteName = Callable[[Optional[int]], Optional[str]]
RegionName = Callable[[int], Optional[str]]


def render_event_dossier(
    event: Event,
    *,
    faction_name: FactionName,
    site_name: SiteName,
    region_name: RegionName,
) -> str:
    """The full dossier (HTML) for one event: banner, sentence, detail block.

    The banner absorbs the year, category bucket, and the notable/minor
    importance verdict (shared anatomy, inspection-ui ticket 01); the accent
    bar wears the bucket's feed color.
    """
    bucket = bucket_of(event.type)
    weight = "notable" if event.importance >= IMPORTANT_THRESHOLD else "minor"
    accent_color = BUCKET_COLORS.get(bucket)
    accent = accent_color.name() if accent_color is not None else NEUTRAL_ACCENT
    parts = [banner(f"Event · {bucket} · {weight}", f"TA {event.year}", accent)]
    if event.text:
        parts.append(para(f"<i>{esc(event.text)}</i>"))
    body = _detail_block(event, faction_name, site_name, region_name)
    if body:
        parts.append(para("<br>".join(esc(line) for line in body)))
    return "".join(parts)


def _detail_block(
    event: Event,
    faction_name: FactionName,
    site_name: SiteName,
    region_name: RegionName,
) -> List[str]:
    payload = event.payload or {}
    if event.type == BATTLE_EVENT:
        return _battle_block(event, payload, faction_name, site_name)
    if event.type == SIEGE_EVENT:
        return _siege_block(event, payload, faction_name, site_name)
    if event.type == CONQUEST_EVENT:
        return _conquest_block(event, payload, faction_name, site_name, region_name)
    if event.type == RAZING_EVENT:
        return _razing_block(event, payload, faction_name, site_name, region_name)
    return _generic_block(payload, faction_name)


# -- war-phase narratives -------------------------------------------------


def _battle_block(event, payload, faction_name, site_name) -> List[str]:
    winner = faction_name(payload.get("winner_faction_id"))
    loser = faction_name(payload.get("loser_faction_id"))
    site = site_name(event.location_id)
    where = f"before {site}" if site else "in the open field"
    tier = payload.get("tier", "marginal")
    verdict = (
        "the field was swept clear"
        if tier == "decisive"
        else "the day was carried, though hard-fought"
    )
    lines = [f"{winner} broke the host of {loser} {where}; {verdict}."]
    w_cas = payload.get("winner_casualties")
    l_cas = payload.get("loser_casualties")
    if w_cas is not None and l_cas is not None:
        lines.append(
            f"The beaten side left {l_cas:,} on the field; "
            f"the victors counted {w_cas:,} of their own."
        )
    return lines


def _siege_block(event, payload, faction_name, site_name) -> List[str]:
    besieger = faction_name(payload.get("besieger_faction_id"))
    besieged = faction_name(payload.get("besieged_faction_id"))
    site = site_name(event.location_id) or "the seat"
    lines = [f"{besieger} pressed the siege of {site}, seat of {besieged}."]
    progress = payload.get("progress")
    required = payload.get("required")
    if progress is not None and required is not None:
        lines.append(
            f"The investment stands at {progress} of the {required} "
            f"the walls will bear before they fall."
        )
    return lines


def _conquest_block(event, payload, faction_name, site_name, region_name) -> List[str]:
    conqueror = faction_name(payload.get("conqueror_faction_id"))
    # Emitted with subjects [the fallen realm, the conqueror].
    fallen = faction_name(event.subject_ids[0]) if event.subject_ids else "the realm"
    site = site_name(event.location_id) or "the capital"
    lines = [f"{site} fell, and with it the realm of {fallen} passed to {conqueror}."]
    regions = _region_list(payload.get("regions"), region_name)
    if regions:
        lines.append(f"Lands taken: {regions}.")
    if payload.get("razed"):
        lines.append("The conqueror did not stay to rule what was taken.")
    return lines


def _razing_block(event, payload, faction_name, site_name, region_name) -> List[str]:
    razer = faction_name(payload.get("razer_faction_id"))
    site = site_name(event.location_id) or "the seat"
    lines = [f"{razer} laid {site} and the lands about it waste."]
    regions = _region_list(payload.get("regions"), region_name)
    if regions:
        lines.append(f"Left in ruin, held by none: {regions}.")
    return lines


def _region_list(region_ids, region_name) -> Optional[str]:
    if not region_ids:
        return None
    names = [region_name(rid) or f"region {rid}" for rid in region_ids]
    return ", ".join(names)


# -- generic fallback -----------------------------------------------------


def _generic_block(payload, faction_name) -> List[str]:
    """A readable key/value listing; faction ids resolve to names in place."""
    lines: List[str] = []
    for key, value in payload.items():
        if value is None:
            continue
        label = key.replace("_", " ")
        if key.endswith("_faction_id"):
            label = label[: -len(" faction id")] or "faction"
            value = faction_name(value)
        lines.append(f"{label}: {value}")
    return lines
