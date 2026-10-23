"""The officer review page: the petition stays in view, and prints clean.

THE TWO DEFECTS THIS EXISTS FOR, both found by rendering the page rather
than by reading it.

ONE. The review grid put the petition preview and the assistance panel in
two columns at their own content heights. The preview ended around 1100px;
the panel ran past 1900. So an officer reading the Acts & Rules card had
scrolled the petition off the top of the screen a thousand pixels earlier —
measured at 105px ABOVE the viewport, entirely gone — and the whole point of
the layout is that the two are read against each other. Below the preview
sat a screen and a half of empty page.

TWO. The officer print used `@page{margin:12mm}`, which is exactly the room
Chrome needs to draw its own header and footer: the date, the page title and
the URL across the top of a government document. That had already been
reported and removed on the citizen side; the officer side still had it.

WHAT THESE TESTS ARE. Assertions about CSS text, which cannot prove a layout
renders — `scripts/officer_scroll_check.py` drives a real browser and
measures it, and that is the one that proves it. These hold the rules so a
later edit cannot quietly drop them: both defects were silent in every other
test in this suite.
"""

from __future__ import annotations

import pathlib
import re

import pytest

CSS = pathlib.Path("app/static/officer.css")


def stylesheet() -> str:
    return CSS.read_text(encoding="utf-8")


def without_comments() -> str:
    return re.sub(r"/\*.*?\*/", "", stylesheet(), flags=re.S)


def block(opening: str) -> str:
    """One brace-balanced rule or at-rule, by its opening text."""
    css = without_comments()
    start = css.index(opening)
    depth, end = 0, start
    for i in range(start, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return css[start:end]


def test_the_stylesheet_is_balanced():
    """A media block left open takes every rule after it with it."""
    css = without_comments()

    assert css.count("{") == css.count("}")


# ---------------------------------------------------------------------------
# The petition stays where the officer can see it
# ---------------------------------------------------------------------------

class TestTheReviewLayout:

    def test_the_wide_layout_rules_exist_at_all(self):
        """A guard on the guard: renamed, everything below passes by
        finding nothing."""
        wide = block("@media (min-width: 1101px)")

        assert ".review-grid > section" in wide
        assert len(wide) > 150

    def test_the_preview_column_is_stuck_to_the_viewport(self):
        wide = block("@media (min-width: 1101px)")

        assert "position: sticky" in wide

    def test_and_clears_the_header_it_sticks_under(self):
        """The page header is `position:sticky; top:0`. A column stuck to
        the top of the viewport sits behind it."""
        wide = block("@media (min-width: 1101px)")

        assert "top: calc(var(--header-h)" in wide

    def test_it_is_given_the_height_of_the_screen(self):
        """Without a height it is taller than the viewport, and a sticky
        element taller than its slot simply scrolls like any other."""
        wide = block("@media (min-width: 1101px)")

        assert "max-height: calc(100dvh" in wide

    def test_and_the_paper_scrolls_inside_it(self):
        """A two-page petition has to be readable without the column
        growing back past the screen."""
        wide = block("@media (min-width: 1101px)")

        assert "overflow-y: auto" in wide

    def test_the_grid_still_aligns_to_the_top(self):
        """`align-items: start` is what makes a sticky grid child possible.
        Stretch it and the column is as tall as the row, and sticky has
        nowhere to stick."""
        grid = block(".officer .review-grid {")

        assert "align-items: start" in grid

    def test_the_narrow_layout_is_left_alone(self):
        """Below 1101px the columns stack and each already has the full
        width. Sticking one of them there would pin a petition over the
        cards the officer is scrolling to read."""
        narrow = block("@media (max-width: 800px)")

        assert "position: sticky" not in narrow


# ---------------------------------------------------------------------------
# What comes out of the printer
# ---------------------------------------------------------------------------

class TestOnlyThePetitionIsPrinted:

    def test_the_page_has_no_margin_of_its_own(self):
        """Which is what leaves Chrome nowhere to draw the date, the page
        title and the URL. Reported on the citizen print and fixed there;
        the officer print still had a 12mm margin."""
        printing = block("@media print")
        page_rule = re.search(r"@page\s*\{([^}]*)\}", printing)

        assert page_rule, printing
        assert re.search(r"margin:\s*0\s*;", page_rule.group(1)), page_rule.group(1)

    def test_it_is_a4(self):
        assert "size: A4" in block("@media print")

    def test_the_margins_move_onto_the_paper(self):
        """`@page{margin:0}` would otherwise print a petition with its text
        against the edge of the sheet."""
        paper = block(".officer .paper {")
        printing = block("@media print")
        printed_paper = re.search(r"\.officer \.paper \{([^}]*)\}", printing)

        assert printed_paper, printing
        assert "mm" in printed_paper.group(1), printed_paper.group(1)
        assert paper  # the screen rule is still there

    def test_every_page_gets_that_margin_not_just_the_first(self):
        """Padding opens at the top of the first page and closes at the
        bottom of the last. A repeating table part is drawn again at the top
        of every page it spans, which is what stops page two starting
        against the edge of the sheet."""
        printing = block("@media print").replace(" ", "").replace("\n", "")

        assert "display:table-header-group" in printing
        assert "display:table-footer-group" in printing

    def test_the_sticky_column_is_undone_for_print(self):
        """Left in place it clips the petition to one viewport height and
        prints a single page of a letter that runs to three."""
        printing = block("@media print").replace(" ", "").replace("\n", "")

        assert "position:static" in printing
        assert "max-height:none" in printing
        assert "overflow:visible" in printing

    @pytest.mark.parametrize("panel", [
        ".review-side", ".preview-tools", "#notice",
    ])
    def test_the_interface_is_not_printed(self, panel):
        """The assistance panel is the officer's working notes. It is not
        part of the citizen's document and must not come out of a printer
        alongside it."""
        hidden = block("@media print")
        rule = hidden[:hidden.index("display: none !important;")]

        assert panel in rule, panel


# ---------------------------------------------------------------------------
# The shell itself is gated
# ---------------------------------------------------------------------------

class TestTheOfficerPagesAreNotOpenToCitizens:
    """The API is what actually protects officer DATA — every endpoint
    checks the session, and `test_officer.py` proves it. This is about the
    PAGE: a citizen who types /officer/dashboard should land on the login
    screen, not on an officer-looking page that then fills with errors.

    Both matter. Gating only the page would be theatre; gating only the API
    would show a citizen a dashboard shell they cannot use and should not
    have seen the shape of.
    """

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as running:
            yield running

    @pytest.mark.parametrize("path", [
        "/officer/dashboard",
        "/officer/petitions/anything",
        "/officer/acknowledgements/anything",
    ])
    def test_a_signed_out_visitor_is_sent_to_the_login_screen(self, client, path):
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 303, path
        assert response.headers["location"] == "/officer/login", path

    def test_the_login_screen_itself_is_reachable(self, client):
        """Gating it would be a redirect loop."""
        response = client.get("/officer/login", follow_redirects=False)

        assert response.status_code == 200

    def test_the_shell_is_never_cached(self, client):
        """A shared counter machine must not serve the next person a page
        out of the browser cache."""
        response = client.get("/officer/login")

        assert "no-store" in response.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# What the dashboard waits for before it draws anything
# ---------------------------------------------------------------------------

class TestTheDashboardDoesNotWaitTwice:
    """The page shows neither the petition table nor the acknowledgement
    count until both have arrived, and it fetched them one after the other —
    so the slower request's time was spent twice over and the citizen-facing
    complaint was "loading long time".

    This is a source assertion and cannot measure anything. The measurement
    that matters was taken in a browser: login to first table row went from
    2.97s to 0.24s once this and the server-side selection were both fixed.
    """

    def _dashboard(self):
        source = pathlib.Path("app/static/officer.js").read_text(encoding="utf-8")
        start = source.index("async function dashboard")
        return source[start:source.index("\n  function ", start)]

    def test_both_reads_are_started_together(self):
        body = self._dashboard()

        assert "Promise.all" in body

    def test_neither_is_awaited_on_its_own_first(self):
        """`await api("/petitions")` followed by `await api("/ack…")` is the
        shape that was slow. Either one alone, awaited before the other is
        started, brings it back."""
        body = self._dashboard()

        assert 'await api("/petitions")' not in body
        assert 'await api("/acknowledgements")' not in body


class TestDashboardSortIsStoredPerTab:
    """Phase 2026-10-15 UI upgrade.

    Clicking a column header toggles its sort direction and the choice
    persists across page loads because it is written to localStorage.
    Two tabs (petitions / acknowledgements) each keep their own sort
    order — a search by "Date desc" on petitions must not spill onto
    acknowledgements."""

    def _officer_js(self):
        return pathlib.Path("app/static/officer.js").read_text(encoding="utf-8")

    def test_the_sort_state_is_persisted(self):
        js = self._officer_js()
        assert "officer:dashboard-sort" in js
        assert "writeSort" in js and "readSort" in js

    def test_the_sort_state_is_per_tab(self):
        js = self._officer_js()
        # The persisted shape is {<tab>: {key, dir}}, keyed by `tab`.
        assert "all[tab] = order" in js
        assert "[tab] || null" in js


class TestDetailPageHasPrevNext:
    def _officer_js(self):
        return pathlib.Path("app/static/officer.js").read_text(encoding="utf-8")

    def test_the_filtered_dashboard_ids_are_passed_to_the_detail_page(self):
        """Prev/Next must walk the FILTERED list, not every petition in the
        system. Written to sessionStorage from table()."""
        js = self._officer_js()
        assert "recordNeighbours(filtered.map" in js
        assert "readNeighbours" in js

    def test_prev_and_next_are_hidden_when_the_officer_arrived_from_a_bookmark(self):
        """`here` is -1 when the current petition is not in the stored
        list. Both buttons must stay hidden to avoid fake navigation."""
        js = self._officer_js()
        assert "here !== -1 && here < neighbours.length - 1" in js


class TestOfficerNotesAutosave:
    def _officer_js(self):
        return pathlib.Path("app/static/officer.js").read_text(encoding="utf-8")

    def test_notes_are_persisted_per_petition_id(self):
        """A single key per petition so one draft does not blow away
        another. Cleared only on a successful save."""
        js = self._officer_js()
        assert "officer:note-draft:" in js
        assert "store.del(noteKey(id))" in js

    def test_notes_restore_when_the_textarea_was_empty(self):
        """A restored draft must not overwrite a review the officer has
        already typed in this session."""
        js = self._officer_js()
        assert "if (draft && !noteBox.value)" in js

    def test_a_dirty_draft_shows_a_visible_indicator(self):
        js = self._officer_js()
        assert 'noteDraftTag.dataset.state = "dirty"' in js
        assert 'noteDraftTag.dataset.state = "saved"' in js


class TestSuccessAndErrorToastsAreDistinguished:
    def _officer_js(self):
        return pathlib.Path("app/static/officer.js").read_text(encoding="utf-8")

    def _officer_css(self):
        return pathlib.Path("app/static/officer.css").read_text(encoding="utf-8")

    def test_notify_takes_a_kind(self):
        js = self._officer_js()
        assert 'notify("Could not save: " +' in js
        assert '"success"' in js and '"error"' in js

    def test_the_notice_colour_differs_by_kind(self):
        css = self._officer_css()
        assert '[data-kind="success"]' in css
        assert '[data-kind="error"]' in css


class TestKeyboardShortcutsSkipInputs:
    """`/` to focus search and `j/k/n/p` to walk the detail page must NOT
    hijack keystrokes while the officer is typing into a textarea or
    input. If they did, pressing `n` inside the notes textarea would
    jump away."""

    def _officer_js(self):
        return pathlib.Path("app/static/officer.js").read_text(encoding="utf-8")

    def test_the_shortcut_handler_ignores_input_focus(self):
        js = self._officer_js()
        # The guard sits at the top of the handler.
        assert "/^(input|textarea|select)$/i.test(e.target.tagName)" in js

    def test_slash_focuses_search(self):
        js = self._officer_js()
        assert 'if (e.key === "/")' in js
        assert "search.focus()" in js
