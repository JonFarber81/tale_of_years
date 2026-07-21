"""The chronicle framework (build ticket 06): deterministic salience scoring,
offline prose rendering with a seeded phrase-grammar, and the annals feed filter.

All headless — the chronicle has no Qt dependency, so the whole framework is
exercised at the same top seam the sim is (drive a run, read the event stream).
"""

from arda_sim.characters import (
    BIRTH_EVENT,
    DEATH_EVENT,
    DEPARTED_EVENT,
    Race,
    Role,
    add_character,
    new_seeded_run,
)
from arda_sim.chronicle import (
    BASE_WEIGHT,
    IMPORTANT_THRESHOLD,
    MAX_IMPORTANCE,
    AnnalsFilter,
    finalize_event,
    pulse_events,
    render_text,
    score_importance,
    show_all_filter,
    subject_prominence,
)
from arda_sim.entities import Event
from arda_sim.pipeline import run_ticks
from arda_sim.world import World


# -- salience scoring ----------------------------------------------------

def _ev(type_, subject_ids=(), importance=0, location_id=None, payload=None, id_=1, year=2965):
    return Event(
        id=id_, year=year, type=type_, subject_ids=list(subject_ids),
        importance=importance, location_id=location_id, payload=payload or {},
    )


def test_importance_is_bounded_0_to_100():
    # A vastly prominent subject on a heavy event type still clamps at 100.
    imp = score_importance(_ev(DEPARTED_EVENT), prominence=10_000, canonicity=1.0)
    assert imp == MAX_IMPORTANCE
    # A zero-weight type (the heartbeat) always scores 0, whatever the subject.
    assert score_importance(_ev("tick"), prominence=10_000, canonicity=1.0) == 0


def test_more_prominent_subject_scores_higher_on_same_type():
    low = score_importance(_ev(DEATH_EVENT), prominence=40, canonicity=1.0)
    high = score_importance(_ev(DEATH_EVENT), prominence=200, canonicity=1.0)
    assert 0 < low < high <= MAX_IMPORTANCE


def test_heavier_type_scores_higher_at_equal_prominence():
    birth = score_importance(_ev(BIRTH_EVENT), prominence=80, canonicity=1.0)
    death = score_importance(_ev(DEATH_EVENT), prominence=80, canonicity=1.0)
    assert birth < death
    assert BASE_WEIGHT[BIRTH_EVENT] < BASE_WEIGHT[DEATH_EVENT]


def test_scoring_is_deterministic_and_rng_free():
    a = score_importance(_ev(DEATH_EVENT), prominence=123, canonicity=0.5)
    b = score_importance(_ev(DEATH_EVENT), prominence=123, canonicity=0.5)
    assert a == b


def test_subject_prominence_reads_the_most_prominent_subject():
    w = World.new_run("seed")
    king = add_character(w, "King", Race.MAN, 2900, role=Role.RULER,
                         title="King", traits={"leadership": 90})
    peasant = add_character(w, "Peasant", Race.MAN, 2940, role=Role.NONE)
    ev = _ev(DEATH_EVENT, subject_ids=[peasant.id, king.id])
    assert subject_prominence(w, ev) == king.prominence
    # An event whose subject ids resolve to nothing contributes no prominence.
    assert subject_prominence(w, _ev(DEATH_EVENT, subject_ids=[9999])) == 0


# -- prose rendering (seeded phrase-grammar) ------------------------------

def test_render_uses_subject_names_and_is_deterministic():
    w = World.new_run("seed")
    c = add_character(w, "Théoden", Race.MAN, 2948)
    ev = _ev(DEATH_EVENT, subject_ids=[c.id], id_=7)
    text = render_text(w, ev)
    assert text is not None and "Théoden" in text
    assert render_text(w, ev) == text  # same event -> same prose, always


def test_birth_prose_names_child_and_parents():
    w = World.new_run("seed")
    mother = add_character(w, "Morwen", Race.MAN, 2922, sex="F")
    father = add_character(w, "Thengel", Race.MAN, 2905)
    child = add_character(w, "Théoden", Race.MAN, 2948)
    ev = _ev(BIRTH_EVENT, subject_ids=[child.id, mother.id, father.id])
    text = render_text(w, ev)
    assert "Théoden" in text and "Morwen" in text and "Thengel" in text


def test_phrase_grammar_varies_by_event_but_stays_offline():
    w = World.new_run("seed")
    c = add_character(w, "Elf", Race.ELF, 500)
    # Two different event ids over the same fact can pick different phrasings;
    # each is a pure function of the id, so the choice is stable and offline.
    texts = {render_text(w, _ev(DEPARTED_EVENT, subject_ids=[c.id], id_=i)) for i in range(6)}
    assert len(texts) > 1
    assert all(t and "Elf" in t for t in texts)


def test_unknown_type_renders_no_prose():
    # The heartbeat and any not-yet-templated type render None (the annals feed
    # falls back to a structured placeholder for those).
    assert render_text(World.new_run("seed"), _ev("tick")) is None


# -- finalize (the emission seam) ----------------------------------------

def test_finalize_stamps_importance_and_text_on_a_character_event():
    w = new_seeded_run("fellowship")
    aragorn = next(e for e in w.entities.values() if getattr(e, "name", "") == "Aragorn")
    ev = w.new_event(type=DEATH_EVENT, subject_ids=[aragorn.id],
                     payload={"cause": "natural"})
    finalize_event(w, ev)
    assert ev.importance > 0
    assert ev.text and "Aragorn" in ev.text


# -- feed filtering (four indices + threshold) ---------------------------

def test_filter_defaults_to_important_only():
    f = AnnalsFilter()
    assert f.min_importance == IMPORTANT_THRESHOLD
    assert not f.matches(_ev(BIRTH_EVENT, importance=IMPORTANT_THRESHOLD - 1))
    assert f.matches(_ev(BIRTH_EVENT, importance=IMPORTANT_THRESHOLD))


def test_show_all_reveals_low_importance_events():
    f = show_all_filter()
    assert f.matches(_ev("tick", importance=0))


def test_filter_by_type_year_and_subject():
    ev = _ev(DEATH_EVENT, subject_ids=[42], importance=90, year=3019)
    assert AnnalsFilter(type=DEATH_EVENT).matches(ev)
    assert not AnnalsFilter(type=BIRTH_EVENT).matches(ev)
    assert AnnalsFilter(year=3019).matches(ev)
    assert not AnnalsFilter(year=3018).matches(ev)
    assert AnnalsFilter(subject_id=42).matches(ev)
    assert not AnnalsFilter(subject_id=7).matches(ev)


def test_filter_excluded_types_hide_named_types():
    # The UI's category chips exclude whole buckets by naming their types;
    # exclusion ANDs with the threshold like every other constraint.
    ev = _ev(DEATH_EVENT, importance=90)
    assert not AnnalsFilter(excluded_types=frozenset({DEATH_EVENT})).matches(ev)
    assert AnnalsFilter(excluded_types=frozenset({BIRTH_EVENT})).matches(ev)
    assert AnnalsFilter(excluded_types=None).matches(ev)  # None excludes nothing
    dull = _ev(DEATH_EVENT, importance=0)
    assert not AnnalsFilter(excluded_types=frozenset({BIRTH_EVENT})).matches(dull)


def test_filter_by_faction_uses_the_subject_to_faction_index():
    ev = _ev(DEATH_EVENT, subject_ids=[42], importance=90)
    faction_of = {42: 5}  # character 42 belongs to faction 5
    assert AnnalsFilter(faction_id=5).matches(ev, faction_of)
    assert not AnnalsFilter(faction_id=6).matches(ev, faction_of)
    # Without the index (no factions yet), a faction filter matches nothing.
    assert not AnnalsFilter(faction_id=5).matches(ev)


# -- on-map pulses -------------------------------------------------------

def test_pulse_events_are_above_threshold_and_located():
    events = [
        _ev(DEATH_EVENT, importance=90, location_id=3),   # pulses
        _ev(DEATH_EVENT, importance=90, location_id=None),  # no place -> no pulse
        _ev(BIRTH_EVENT, importance=5, location_id=3),    # below threshold -> no pulse
    ]
    pulsed = pulse_events(events)
    assert len(pulsed) == 1 and pulsed[0].location_id == 3


# -- integration: a real run produces a scored, prose chronicle ----------

def test_a_seeded_run_yields_scored_prose_events():
    w = new_seeded_run("fellowship")
    run_ticks(w, 60)
    lifecycle = [e for e in w.events if e.type in (BIRTH_EVENT, DEATH_EVENT, DEPARTED_EVENT)]
    assert lifecycle, "60 years of the canon roster should produce births/deaths"
    for e in lifecycle:
        assert 0 <= e.importance <= MAX_IMPORTANCE
        assert e.text  # every lifecycle event reads as prose


def test_run_chronicle_is_byte_deterministic_across_runs():
    def blob(seed):
        w = new_seeded_run(seed)
        run_ticks(w, 40)
        return [(e.id, e.type, e.importance, e.text) for e in w.events]

    assert blob("fellowship") == blob("fellowship")
