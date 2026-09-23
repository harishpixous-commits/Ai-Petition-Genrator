"""Kiosk mode: the same petition flow, on a self-service terminal.

WHAT A KIOSK IS HERE. A machine standing in a government office. A citizen
walks up, answers the questions on screen or by voice, and takes the printed
petition away — no account, no email address, no way of getting a file home
needed.

TWO DECISIONS THESE TESTS EXIST TO PROTECT.

The first is that it is the SAME flow, not a copy of it. Kiosk is a flag on
the page that already exists: the same graph, the same questions, the same
document, the same voice. A second implementation would be two things to fix
every time one of them changed, and the copy is always the one nobody
remembers to change.

The second is WHAT THE PAGE MAY CLAIM ABOUT PRINTING. A browser cannot tell
whether paper came out of a printer. `window.print()` opens a dialog somebody
confirms; on a terminal launched with `--kiosk-printing` it goes straight to
the default printer with no dialog. The page cannot detect which happened —
so the DEPLOYMENT says which it is, and the wording follows. "Printed
successfully" is a sentence this code is never allowed to say, because it is
never something it knows.

WHAT CANNOT BE TESTED HERE is whether a printer prints. That needs a terminal
with paper in it.
"""

from __future__ import annotations

import pathlib
import re

import pytest

STATIC = pathlib.Path("app/static")


def js() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")


def nav() -> str:
    return (STATIC / "navigation.js").read_text(encoding="utf-8")


def html() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def css() -> str:
    return re.sub(r"/\*.*?\*/", " ",
                  (STATIC / "app.css").read_text(encoding="utf-8"), flags=re.S)


def without_comments(source: str) -> str:
    """Code only.

    A test that searches raw text finds the comment EXPLAINING why something
    is not done and reports it as being done — which is exactly what happened
    to the `window.open` check below.
    """
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def block(name: str, until: str) -> str:
    source = js()
    start = source.index(name)
    return source[start:source.index(until, start)]


# ---------------------------------------------------------------------------

class TestItIsTheSameFlowNotACopy:
    """The one that matters most. Everything else here is detail."""

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

    def test_the_flag_changes_presentation_and_nothing_else(self):
        """`setKioskMode` toggles a class and paints a screen. If it started
        rewiring the workflow, this is where that would show."""
        fn = without_comments(block("function setKioskMode", "/* ----"))

        assert 'classList.toggle("kiosk"' in fn
        for forbidden in ("api(", "fetch(", "workflow", "/api/"):
            assert forbidden not in fn, (forbidden, fn)


class TestWhatThePageMayClaimAboutPrinting:
    """The honesty rule. A browser cannot confirm that paper exists."""

    def test_it_never_says_the_petition_was_printed(self):
        source = js()
        kiosk = source[source.index('kiosk: "Kiosk"'):]
        kiosk = kiosk[:kiosk.index("kioskStillThere")]
        # Code only. The comment above these strings states the rule, and it
        # states it by quoting the sentence that must never appear.
        lowered = without_comments(kiosk).lower()
        for claim in ("has been printed", "printed successfully",
                      "அச்சிடப்பட்டுவிட்டது", "வெற்றிகரமாக அச்சிட"):
            assert claim.lower() not in lowered, claim

    def test_dialog_mode_says_the_dialog_is_open(self):
        source = js()

        assert "kioskDialogTitle" in source
        assert "print window is open" in source

    def test_silent_mode_says_sent_not_printed(self):
        source = js()

        assert "sent to the printer" in source
        assert "அச்சுப்பொறிக்கு அனுப்பப்பட்டுள்ளது" in source

    def test_the_wording_follows_the_configured_mode(self):
        fn = without_comments(block("function kioskPrint", "function showKioskDone"))

        assert 'kioskState.print_mode === "silent"' in fn
        assert "kioskSentTitle" in fn and "kioskDialogTitle" in fn

    def test_the_mode_comes_from_the_deployment(self):
        """A browser cannot detect whether the dialog will appear. The
        machine it runs on can be told."""
        from app.config import get_settings

        assert "healthState?.kiosk" in js()
        assert '"print_mode"' in js()
        assert get_settings().kiosk_print_mode == "dialog", "dialog is the safe default"


class TestThePetitionReachesThePrinterOnItsOwn:

    def test_printing_waits_for_a_verified_document(self):
        """Not merely "generated". A document that failed verification is not
        one to put on paper and hand to a government office."""
        fn = without_comments(block("function kioskMaybePrint", "function kioskPrint"))

        assert 'v.status !== "ready"' in fn
        assert "verification" in fn

    def test_it_prints_the_page_rather_than_opening_a_window(self):
        """`window.open` from a timer rather than a click is blocked by
        default, and a kiosk has nobody to press "allow"."""
        fn = without_comments(block("function kioskPrint", "function showKioskDone"))

        assert "window.open" not in fn, fn
        assert "window.print()" in fn

    def test_one_document_version_prints_once(self):
        """`render` runs on every state change and several arrive after the
        document exists — an edit, a reconnect, a duplicate response. Each
        would be another sheet of paper."""
        fn = without_comments(block("function kioskMaybePrint", "function kioskPrint"))

        assert "document?.version" in fn, "a re-render must not reprint"
        assert "kioskState.printedKey === key" in fn
        assert "kioskState.printedKey = key" in fn

    def test_a_second_copy_is_something_the_citizen_asks_for(self):
        """An explicit second copy is a different thing from an accidental
        one."""
        source = js()

        assert 'kioskPrintAgain").onclick' in source

    def test_nothing_prints_outside_a_kiosk_or_when_switched_off(self):
        fn = without_comments(block("function kioskMaybePrint", "function kioskPrint"))

        assert "!kioskState.on" in fn
        assert "!kioskState.auto_print" in fn

    def test_it_is_called_from_the_one_place_state_arrives(self):
        render = block("function render(v)", "clearTimeout(generationPoll)")

        assert "kioskMaybePrint(v)" in render


class TestAFailedPrintKeepsThePetition:

    def test_the_screen_is_not_cleared_on_a_failure(self):
        """Wiping a citizen's petition because a printer is out of paper
        loses the only thing they came for."""
        fn = without_comments(block("function showKioskFailed",
                                    "function startKioskCountdown"))

        assert "stopKioskCountdown()" in fn
        assert "startKioskCountdown(" not in fn

    def test_they_are_told_it_is_safe_and_offered_a_retry(self):
        source = js()

        assert "kioskFailedTitle" in source and "kioskRetryPrint" in source
        assert "still on the screen" in source
        assert "பாதுகாப்பாக திரையில் உள்ளது" in source

    def test_a_failure_does_not_look_like_success(self):
        assert ".kiosk-done.failed" in css()


class TestTheNextCitizenSeesNothingOfTheLast:
    """A terminal showing the previous person's name, address and grievance
    to whoever walks up next is a privacy failure, not an inconvenience."""

    def test_finishing_clears_everything_the_citizen_left(self):
        fn = without_comments(block("async function kioskRestart", "/* ------"))

        for cleared in ("forgetSession()", "resetInterface()", "stopVoice(",
                        "view = null", "sid = null"):
            assert cleared in fn, cleared

    def test_it_returns_to_the_welcome_screen(self):
        fn = without_comments(block("async function kioskRestart", "/* ------"))

        assert 'kioskWelcome").hidden = false' in fn

    def test_the_countdown_is_visible_and_configurable(self):
        source = js()

        assert "kioskClearing" in source
        assert "reset_after_finish" in source

    def test_a_terminal_somebody_walked_away_from_clears_itself(self):
        """Asked first, because a citizen thinking about what to write is not
        the same as a citizen who has left."""
        fn = without_comments(block("function kioskTouch", "function stopKioskIdle"))

        assert "kioskStillThere" in fn
        assert "idle_timeout_seconds" in fn
        assert "kioskRestart" in fn

    def test_using_the_terminal_resets_the_idle_clock(self):
        source = js()

        assert "pointerdown" in source and "keydown" in source
        assert "kioskTouch()" in source


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


class TestTheWelcomeScreen:

    def test_a_citizen_walking_up_is_greeted_before_anything_else(self):
        markup = html()

        assert 'id="kioskWelcome"' in markup
        assert 'id="kioskStart"' in markup

    def test_it_is_written_in_both_languages(self):
        source = js()

        assert "kioskWelcomeTitle" in source
        assert "வணக்கம்" in source
        assert "மனுவை தொடங்கவும்" in source

    def test_the_start_button_is_something_a_thumb_can_hit(self):
        rules = css()[css().index(".kiosk-welcome .kw-start"):]
        rules = rules[:rules.index("}")]

        assert "min-height:64px" in rules.replace(" ", "")


class TestTheLinkThatOpensIt:

    def test_it_lives_with_the_other_destinations(self):
        """In the navigation, not beside New Petition. It is a PLACE to go,
        like the three beside it; the buttons on the right are things to DO
        to the petition in front of you."""
        markup = html()
        navigation = markup[markup.index('<nav class="main-nav"'):]
        navigation = navigation[:navigation.index("</nav>")]

        assert 'id="navKiosk"' in navigation
        assert 'href="#kiosk"' in navigation

    def test_new_petition_is_still_there_and_separate(self):
        markup = html()
        actions = markup[markup.index('<div class="header-actions">'):]

        assert 'id="new"' in actions
        assert "kiosk" not in actions[:actions.index('id="new"')].lower()

    def test_it_is_named_in_both_languages(self):
        source = nav()

        assert 'kiosk: "Kiosk"' in source
        assert 'kiosk: "கியோஸ்க்"' in source

    def test_the_label_is_painted(self):
        assert "navKiosk: n.kiosk" in nav()


class TestTheDeploymentDecidesTheTerminalsBehaviour:
    """None of this is hardcoded in the workflow. A terminal is configured."""

    @pytest.mark.parametrize("name,expected", [
        ("kiosk_enabled", True),
        ("kiosk_print_mode", "dialog"),
        ("kiosk_auto_print", True),
        ("kiosk_print_package", "petition_only"),
        ("kiosk_idle_timeout_seconds", 120),
        ("kiosk_reset_after_finish", True),
    ])
    def test_the_settings_exist_with_safe_defaults(self, name, expected):
        from app.config import get_settings

        assert getattr(get_settings(), name) == expected

    def test_the_page_is_told_what_they_are(self):
        source = pathlib.Path("app/api/rest.py").read_text(encoding="utf-8")
        payload = source[source.index('"kiosk": {'):]
        payload = payload[:payload.index("},")]

        for key in ("print_mode", "auto_print", "idle_timeout_seconds",
                    "reset_after_finish"):
            assert key in payload, key

    def test_printing_dozens_of_attachment_pages_is_not_the_default(self):
        """A citizen who attached six photographs of a broken road should not
        silently receive thirty sheets of paper."""
        from app.config import get_settings

        assert get_settings().kiosk_print_package == "petition_only"


class TestTheOperatorIsToldHowToMakeItSilent:
    """`window.print()` opens a dialog unless the browser was launched to
    skip it. That is a deployment step, and a feature whose deployment step
    is undocumented is a feature that gets reported as broken."""

    def test_the_launch_command_is_written_down(self):
        doc = pathlib.Path("../docs/kiosk-setup.md").read_text(encoding="utf-8")

        assert "--kiosk-printing" in doc
        assert "#kiosk" in doc

    def test_the_code_says_what_it_cannot_know(self):
        source = js()
        note = source[:source.index("const kioskState")]
        note = note[note.index("WHAT THE PAGE IS ALLOWED TO CLAIM"):]

        assert "cannot" in note.lower()
        assert "KIOSK_PRINT_MODE" in note
