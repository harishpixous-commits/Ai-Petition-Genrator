"""The panel a citizen watches while they dictate a complaint.

WHAT A TEST OVER SOURCE TEXT CAN AND CANNOT PROVE. It cannot prove the
panel renders, that the bars move, or that any of it is legible at a
counter — only a browser does that, and the report says so. What it can do
is hold the rules that are silent when they break:

  * every string the panel shows exists in BOTH languages
  * the level bars are driven by measurement, never by a timer
  * the "noise reduction active" tick is shown only when the track said yes
  * the buttons send the same messages the voice path triggers

The third is the one worth having a test for. A tick that is always on
looks identical to a tick that is honest, and it is the single claim on
this page a citizen cannot check for themselves.
"""

from __future__ import annotations

import pathlib
import re

import pytest

STATIC = pathlib.Path("app/static")


def page() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def script() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")


def styles() -> str:
    return (STATIC / "app.css").read_text(encoding="utf-8")


def without_comments(text: str) -> str:
    """Comments say what the code should do. Tests must read what it does."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


def strings(language: str) -> dict[str, str]:
    """The `en` or `ta` block of the page's own table."""
    js = script()
    start = js.index(f"  {language}: {{")
    end = js.index("  ta: {") if language == "en" else js.index("\n};", start)
    block = js[start:end]
    return dict(re.findall(r'\b([A-Za-z0-9_]+):\s*"((?:[^"\\]|\\.)*)"', block))


# ---------------------------------------------------------------------------
# It is all there, in both languages
# ---------------------------------------------------------------------------

PANEL_IDS = [
    "dictation", "dictationWave", "dictationTitle", "dictationTime",
    "dictationSub", "dictationText", "dictationNoise", "dictationCount",
    "dictationFinish", "dictationPause", "dictationRestart",
    "grievanceDone", "grievanceDoneTitle", "grievanceDoneText",
    "answerEdit",
]


@pytest.mark.parametrize("element_id", PANEL_IDS)
def test_the_panel_has_its_parts(element_id):
    assert f'id="{element_id}"' in page(), element_id


NEW_STRINGS = [
    "dictationTitle", "dictationPaused", "dictationHeld", "dictationSub",
    "dictationSubHeld", "dictationSubDone", "dictationFinish",
    "dictationPause", "dictationResume", "dictationRestart",
    "answerEdit", "answerGrievanceHeading", "answerGrievanceAsk",
    "grievanceDoneTitle", "grievanceDoneText", "noiseOn",
]


@pytest.mark.parametrize("key", NEW_STRINGS)
def test_every_word_exists_in_both_languages(key):
    for language in ("en", "ta"):
        assert strings(language).get(key, "").strip(), f"{key} ({language})"


@pytest.mark.parametrize("key", NEW_STRINGS)
def test_and_the_tamil_is_not_the_english(key):
    """A copied line looks translated in a diff and is not translated on the
    page. Every one of these is a full phrase, so identity is a mistake."""
    assert strings("ta")[key] != strings("en")[key], key


@pytest.mark.parametrize("state", ["long_paused", "long_editing", "long_confirmed"])
def test_the_new_states_have_labels_in_both_languages(state):
    """A state the server can send with no label leaves the status line
    blank — the citizen is told nothing at all about what is happening."""
    for language in ("en", "ta"):
        table = script()
        start = table.index(f"  {language}: {{")
        end = (table.index("  ta: {") if language == "en"
               else table.index("\n};", start))
        assert f"{state}:" in table[start:end], f"{state} ({language})"


# ---------------------------------------------------------------------------
# What it shows is what is happening
# ---------------------------------------------------------------------------

class TestTheIndicatorsAreHonest:

    def test_the_bars_are_driven_by_the_measured_level(self):
        """NOT by a timer. This panel is what a citizen uses to decide
        whether they are being heard, so bars that keep dancing at a muted,
        unplugged or denied microphone are the most misleading thing on the
        page."""
        js = without_comments(script())
        fn = js[js.index("function paintDictationBars"):]
        fn = fn[:fn.index("\n}") + 2]

        assert "voice.rms" in fn, fn
        assert "Math.random" not in fn, "a random height is not a level"

    def test_and_they_stop_when_the_microphone_does(self):
        js = without_comments(script())
        fn = js[js.index("function paintDictationBars"):]
        fn = fn[:fn.index("\n}") + 2]

        assert 'dataset.live !== "on"' in fn

    def test_the_noise_tick_needs_the_track_to_have_said_yes(self):
        """Asked for is not the same as got: Firefox applies some of these
        constraints, Safari applies them differently, and a conference
        microphone may refuse — none of which fails `getUserMedia`."""
        js = without_comments(script())
        fn = js[js.index("function showDictation"):]
        fn = fn[:fn.index("\nfunction ")]

        assert "voice.processing.noise !== true" in fn, fn

    def test_the_constraints_are_actually_requested(self):
        js = script()

        for wanted in ("echoCancellation: true", "noiseSuppression: true",
                       "autoGainControl: true"):
            assert wanted in js, wanted

    def test_a_pause_is_shown_as_a_pause_not_as_a_capture(self):
        """Three states, not two. "Grievance captured" over a pause tells
        the citizen it has been taken when it has not."""
        js = without_comments(script())
        fn = js[js.index("function showDictation"):]
        fn = fn[:fn.index("\nfunction ")]

        assert "dictationHeld" in fn
        assert "dictationPaused" in fn
        assert "m.paused" in fn

    def test_the_clock_stops_while_paused(self):
        js = without_comments(script())
        fn = js[js.index("function showDictation"):]
        fn = fn[:fn.index("\nfunction ")]

        assert "if (live) startDictationClock(); else stopDictationClock();" in fn


# ---------------------------------------------------------------------------
# The buttons and the voice do the same thing
# ---------------------------------------------------------------------------

class TestTheButtonsSendTheRightMessages:

    @pytest.mark.parametrize("message", [
        "dictation.finish", "dictation.restart", "dictation.pause",
        "dictation.resume", "answer.edit", "answer.confirm", "answer.retry",
    ])
    def test_the_page_can_send_it(self, message):
        assert f'"{message}"' in without_comments(script()), message

    def test_one_button_covers_both_directions_of_the_pause(self):
        """Two buttons would need the page to decide which is live, and the
        page is not the authority on that."""
        js = without_comments(script())
        handler = js[js.index('$("dictationPause").onclick'):]
        handler = handler[:handler.index("};") + 2]

        assert "dictation.resume" in handler
        assert "dictation.pause" in handler
        assert "dictationPaused" in handler

    def test_the_edit_button_is_offered_only_for_a_grievance(self):
        """Retrying a name IS the edit. An Edit button on a three-word
        answer offers a two-step flow where one step would do."""
        js = without_comments(script())
        fn = js[js.index("function showAnswer"):]
        fn = fn[:fn.index("\n}") + 2]

        assert '$("answerEdit").hidden = !grievance' in fn

    def test_and_the_server_is_what_says_which_it_is(self):
        js = without_comments(script())

        assert "grievance: Boolean(m.grievance)" in js


# ---------------------------------------------------------------------------
# The confirmed card
# ---------------------------------------------------------------------------

class TestTheConfirmedCard:

    def test_it_is_shown_only_when_the_server_says_confirmed(self):
        js = without_comments(script())
        fn = js[js.index("function showGrievanceDone"):]
        fn = fn[:fn.index("\n}") + 2]

        assert "if (!confirmed)" in fn

    def test_it_goes_away_on_its_own(self):
        """It acknowledges; it is not a step. Leaving it up would sit over
        the next question the assistant is already asking."""
        js = without_comments(script())
        fn = js[js.index("function showGrievanceDone"):]
        fn = fn[:fn.index("\n}") + 2]

        assert "setTimeout" in fn
        assert "hidden = true" in fn

    def test_the_server_message_reaches_it(self):
        js = without_comments(script())

        assert 'case "voice.grievance":' in js
        assert "showGrievanceDone" in js


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

class TestTheStyles:

    def test_the_stylesheet_is_still_balanced(self):
        css = re.sub(r"/\*.*?\*/", "", styles(), flags=re.S)

        assert css.count("{") == css.count("}")

    def test_the_bars_have_a_flat_state(self):
        css = re.sub(r"/\*.*?\*/", "", styles(), flags=re.S)

        assert '.dictation[data-live="off"] .dc-wave i' in css

    def test_the_pulse_stops_for_anyone_who_asked_it_to(self):
        """A pulsing dot and a moving row of bars are exactly what
        `prefers-reduced-motion` is for."""
        css = re.sub(r"/\*.*?\*/", "", styles(), flags=re.S)
        start = css.index("prefers-reduced-motion")
        block = css[start:css.index("}\n}", start) + 3]

        assert ".dc-wave i" in block
        assert "animation: none" in block

    def test_the_panel_survives_a_phone(self):
        """Three buttons where there were two. Without a basis they sit on
        one line at 90px each and overflow the panel."""
        css = re.sub(r"/\*.*?\*/", "", styles(), flags=re.S)

        assert ".dictation .dc-acts .btn{flex:1 1 90px" in css
        assert "flex-wrap: wrap" in css
