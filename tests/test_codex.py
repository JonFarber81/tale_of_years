"""The Codex's Qt-independent core: addresses, history, search (issue #36).

Everything here is pure — parsing, the back/forward stack, name matching, and
page HTML as strings — so these run without a QApplication. The pane and the
window wiring are exercised in test_ui_shell.py, which owns the offscreen-Qt
guard.
"""

import pytest

pytest.importorskip("PySide6")  # codex.py imports Qt for the pane half

from arda_sim.ui.codex import (  # noqa: E402
    CodexAddress,
    CodexHistory,
    render_search_page,
    search_matches,
)


# -- addresses ------------------------------------------------------------


def test_address_round_trips_through_its_url():
    addr = CodexAddress("faction", "12")
    assert addr.url == "codex://faction/12"
    assert CodexAddress.parse(addr.url) == addr


def test_address_ident_may_carry_slashes_and_commas():
    # A tile address is "col,row"; a search address is the raw query, which
    # may contain anything — everything after the kind belongs to the ident.
    assert CodexAddress.parse("codex://tile/7,9") == CodexAddress("tile", "7,9")
    assert CodexAddress.parse("codex://search/minas tirith") == CodexAddress(
        "search", "minas tirith"
    )
    assert CodexAddress.parse("codex://search/a/b") == CodexAddress("search", "a/b")


def test_address_rejects_foreign_and_malformed_urls():
    assert CodexAddress.parse("https://example.com/x") is None
    assert CodexAddress.parse("codex://") is None
    assert CodexAddress.parse("codex://faction") is None  # no ident
    assert CodexAddress.parse("not a url") is None


# -- history --------------------------------------------------------------


def _addr(n):
    return CodexAddress("faction", str(n))


def test_history_starts_empty_and_visits_advance_it():
    history = CodexHistory()
    assert history.current is None
    assert not history.can_back() and not history.can_forward()
    history.visit(_addr(1))
    history.visit(_addr(2))
    assert history.current == _addr(2)
    assert history.can_back() and not history.can_forward()


def test_history_back_and_forward_walk_the_stack():
    history = CodexHistory()
    for n in (1, 2, 3):
        history.visit(_addr(n))
    assert history.back() == _addr(2)
    assert history.back() == _addr(1)
    assert history.back() is None  # at the oldest entry already
    assert history.current == _addr(1)
    assert history.forward() == _addr(2)
    assert history.forward() == _addr(3)
    assert history.forward() is None
    assert history.current == _addr(3)


def test_history_visit_truncates_the_forward_branch():
    history = CodexHistory()
    for n in (1, 2, 3):
        history.visit(_addr(n))
    history.back()  # at 2
    history.visit(_addr(9))  # branches: 3 is gone
    assert history.current == _addr(9)
    assert history.forward() is None
    assert history.back() == _addr(2)


def test_history_ignores_revisiting_the_current_page():
    # Clicking the link you are already on must not bury the back stack
    # under duplicates.
    history = CodexHistory()
    history.visit(_addr(1))
    history.visit(_addr(1))
    assert not history.can_back()


# -- search ---------------------------------------------------------------


def _candidates():
    return [
        ("Gondor", "realm", CodexAddress("faction", "1")),
        ("Minas Tirith", "city of Gondor", CodexAddress("site", "4")),
        ("Host of Gondor", "host · 4,200", CodexAddress("host", "9")),
        ("Rohan", "realm", CodexAddress("faction", "2")),
    ]


def test_search_matches_by_case_insensitive_substring():
    matches = search_matches("gond", _candidates())
    # "Minas Tirith" only says Gondor in its detail line, so it stays out.
    assert [m[0] for m in matches] == ["Gondor", "Host of Gondor"]


def test_search_matches_names_only_not_details():
    assert [m[0] for m in search_matches("city", _candidates())] == []


def test_search_ranks_prefix_hits_before_interior_hits():
    matches = search_matches("ro", _candidates())
    assert [m[0] for m in matches] == ["Rohan"]
    matches = search_matches("o", _candidates())
    # Prefix-less query: prefix hits first (none start with "o"), then
    # interior hits in given order.
    assert [m[0] for m in matches] == [
        "Gondor",
        "Host of Gondor",
        "Rohan",
    ]


def test_search_ignores_blank_queries():
    assert search_matches("   ", _candidates()) == []


# -- the search page ------------------------------------------------------


def test_search_page_lists_matches_as_codex_links():
    html = render_search_page("mi", search_matches("mi", _candidates()))
    assert "SEARCH" in html and "mi" in html
    assert 'href="codex://site/4"' in html and "Minas Tirith" in html
    assert "city of Gondor" in html  # the detail line renders too


def test_search_page_with_no_matches_says_so():
    html = render_search_page("zzz", [])
    assert "zzz" in html and "Nothing in the record" in html


def test_search_page_escapes_hostile_queries_and_names():
    html = render_search_page(
        "<b>&", [("R&D <keep>", "site", CodexAddress("site", "3"))]
    )
    assert "<b>&" not in html  # the raw query never lands unescaped
    assert "&lt;b&gt;" in html and "R&amp;D &lt;keep&gt;" in html
