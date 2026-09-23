"""Kiosk mode: the same petition flow, on a terminal with a printer.

WHAT A KIOSK IS HERE. A machine standing in a government office. A citizen
walks up, answers the questions, and the finished petition comes out of the
printer — nobody is asked to find a Print button, and nobody needs an
account, an email address or a way to get the file home.

THE DESIGN DECISION THESE TESTS PROTECT is that it is the SAME flow, not a
copy of it. Kiosk is a flag on the page that already exists: the same graph,
the same questions, the same document, the same voice. A second
implementation would be two things to fix every time one of them changed,
and the copy is always the one nobody remembers to change.

WHAT CANNOT BE TESTED HERE. Whether a printer prints. `window.print()` and
Chrome's `--kiosk-printing` are the browser's, and proving they work needs a
terminal with paper in it. What these tests hold is everything up to that
call: that it happens automatically, that it happens once, and that the
screen is cleared afterwards.
"""

from __future__ import annotations

import pathlib
import re

import pytest

STATIC = pathlib.Path("app/static")


def js() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")


def without_comments(source: str) -> str:
    """Code only.

    A test that searches the raw text finds the comment EXPLAINING why
    something is not done and reports it as being done — which is exactly
    what happened to the `window.open` check below.
    """
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def nav() -> str:
    return (STATIC / "navigation.js").read_text(encoding="utf-8")


def html() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def css() -> str:
    return re.sub(r"/\*.*?\*/", " ",
                  (STATIC / "app.css").read_text(encoding="utf-8"), flags=re.S)


class TestItIsTheSameFlowNotACopy:
    """The one that matters. Everything else here is detail."""

    def test_the_kiosk_route_runs_the_ordinary_create_flow(self):
        source = nav()
        branch = source[source.index('if (route === "kiosk"'):]
        branch = branch[:branch.index("}")]

        assert "await start()" in branch, branch
        assert 'route === "create"' in branch, "the two share one branch"

    def test_there_is_no_second_generator_page(self):
        """A kiosk page of its own would be a copy of the form, the document
        panel and the voice layer, drifting from the original from the day it
        was written."""
        assert html().count('id="generatorPage"') == 1
        assert "kioskPage" not in html()

    def test_the_flag_is_the_only_difference(self):
        """`setKioskMode` toggles a class and nothing else. If it started
        rewiring the flow, this is where that would show."""
        source = js()
        fn = source[source.index("function setKioskMode"):]
        fn = fn[:fn.index("\n}") + 2]

        assert "classList.toggle(\"kiosk\"" in fn
        for forbidden in ("api(", "fetch(", "session", "workflow"):
            assert forbidden not in fn, (forbidden, fn)


class TestThePetitionReachesThePrinterOnItsOwn:

    def test_printing_is_triggered_by_the_document_being_ready(self):
        source = js()
        fn = source[source.index("function kioskMaybePrint"):]
        fn = fn[:fn.index("function showKioskDone")]

        assert 'v.status !== "ready"' in fn
        assert "window.print()" in fn

    def test_it_prints_the_page_rather_than_opening_a_window(self):
        """`window.open` from a timer rather than a click is blocked by
        default, and a kiosk has nobody to click "allow". The print
        stylesheet already reduces this page to the letter alone."""
        source = js()
        fn = source[source.index("function kioskMaybePrint"):]
        fn = without_comments(fn[:fn.index("function showKioskDone")])

        assert "window.open" not in fn, fn
        assert "window.print()" in fn

    def test_it_prints_once_for_a_petition(self):
        """`render` runs on every state change, and several arrive after the
        document is ready — an edit, a version, a reconnect. Each would be
        another sheet of paper."""
        source = js()
        fn = source[source.index("function kioskMaybePrint"):]
        fn = fn[:fn.index("function showKioskDone")]

        assert "kioskPrintedFor === v.session_id" in fn
        assert "kioskPrintedFor = v.session_id" in fn

    def test_nothing_prints_outside_a_kiosk(self):
        source = js()
        fn = source[source.index("function kioskMaybePrint"):]
        fn = fn[:fn.index("function showKioskDone")]

        assert re.search(r"if \(!kiosk\b", fn), fn

    def test_it_is_called_from_the_one_place_state_arrives(self):
        source = js()
        render = source[source.index("function render(v)"):]
        render = render[:render.index("clearTimeout(generationPoll)")]

        assert "kioskMaybePrint(v)" in render


class TestTheNextCitizenSeesNothingOfTheLast:
    """A terminal showing the previous person's name, address and grievance
    to whoever walks up next is a privacy failure, not an inconvenience."""

    def test_the_screen_clears_itself(self):
        source = js()

        assert "KIOSK_CLEAR_SECONDS" in source
        assert "startKioskCountdown" in source
        assert "kioskRestart" in source

    def test_clearing_forgets_the_session(self):
        source = js()
        fn = source[source.index("async function kioskRestart"):]
        fn = fn[:fn.index("\n}") + 2]

        assert "forgetSession()" in fn, "the id would come back on reload"
        assert "await start()" in fn

    def test_the_countdown_is_visible_and_can_be_stopped(self):
        """A screen that wipes itself without warning loses somebody's work,
        and the person reading it may simply be slow."""
        source = js()

        assert "kioskClearing" in source
        assert 'kioskStay").onclick' in source
        assert 'id="kioskStay"' in html()

    def test_it_is_a_clear_count_not_a_silent_timer(self):
        source = js()
        fn = source[source.index("function startKioskCountdown"):]
        fn = fn[:fn.index("function stopKioskCountdown")]

        assert "kioskDoneText" in fn
        assert "setInterval" in fn


class TestTheWaysOffThePageAreGone:

    @pytest.mark.parametrize("selector", [
        "body.kiosk .main-nav",
        'body.kiosk [data-route="petitions"]',
    ])
    def test_a_queue_cannot_browse_other_peoples_petitions(self, selector):
        assert selector in css(), selector

    def test_the_language_switch_stays(self):
        """The one control a kiosk must keep. A Tamil speaker at a Tamil Nadu
        counter needs it more than anyone."""
        hidden = css()[css().index("body.kiosk .main-nav"):]
        hidden = hidden[:hidden.index("}")]

        assert "#lang" not in hidden
        assert "lang" not in hidden.replace("body.kiosk", "")


class TestTheButtonThatOpensIt:

    def test_it_sits_next_to_new_petition(self):
        markup = html()

        assert 'id="kiosk"' in markup
        assert markup.index('id="kiosk"') < markup.index('id="new"')

    def test_it_is_named_in_both_languages(self):
        source = nav()

        assert 'kiosk: "Kiosk"' in source
        assert 'kiosk: "கியாஸ்க்"' in source

    def test_the_label_is_painted(self):
        assert "kioskText: n.kiosk" in nav()


class TestTheOperatorIsToldHowToMakeItSilent:
    """`window.print()` opens a dialog unless the browser was launched to
    skip it. That is a deployment step, and a feature whose deployment step
    is undocumented is a feature that gets reported as broken."""

    def test_the_launch_command_is_written_down_where_it_is_implemented(self):
        source = js()
        note = source[source.index("/* ------------------------------------------------------------------ kiosk"):]
        note = note[:note.index("*/")]

        assert "--kiosk-printing" in note
        assert "#kiosk" in note
