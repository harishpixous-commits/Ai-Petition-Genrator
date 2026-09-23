"""The grievance, from "tell me" to "confirmed", entirely by voice.

WHAT IS NEW HERE and why it needed its own file. `test_voice_long_dictation`
proves the complaint is captured whole. This proves what the citizen can do
with it once they have heard it: agree, reject, pause, or CHANGE ONE THING
IN IT without losing the rest.

That last one is what was missing, and its absence was destructive rather
than merely incomplete. "Change five days to three days", said of a
two-minute complaint, went to `answer_intent.read`, which found content in
it and returned REPLACE — so the complaint was discarded and those six words
became the whole of the petition.

WHAT THESE TESTS ARE, AND ARE NOT. They drive the real WebSocket handler
with real messages and assert on what the workflow was finally given, so
"did the right text reach the petition?" is a fact here, not an inference.
They begin after a transcript exists. Whether a real microphone in a real
room produces that transcript is not a thing any of this can prove — see the
audio-gate tests for the half in front, and a browser for the rest.
"""

from __future__ import annotations

import time

import pytest

from app.api.ws import Phase
from app.services import asr, tts
from tests.test_voice_long_dictation import BRISK, AtGrievance, talking

# Declared here rather than imported. Importing a fixture by name and then
# naming it again in a test signature is a redefinition, and every one of
# the hundred-odd parameters below counts as another — which buries a real
# shadowing bug in noise. Every other voice test file declares its own.


@pytest.fixture
def dictation_available(monkeypatch):
    monkeypatch.setattr(asr, "status", lambda settings=None: {"ok": True, "provider": "test"})


@pytest.fixture
def brisk():
    return BRISK


@pytest.fixture
def spoken(monkeypatch):
    async def _stream(text, language, settings):
        yield b"RIFF"

    monkeypatch.setattr(tts, "configured", lambda settings=None: True)
    monkeypatch.setattr(tts, "stream", _stream)

COMPLAINT = ("Water has not been supplied to our street for five days. "
             "We informed the local office but nobody came.")


def captured(session) -> str:
    """The grievance as the page was last told it stands."""
    latest = session.dictation()
    return latest["text"] if latest else ""


def offered(session) -> str:
    """The text sitting on the confirmation card."""
    card = session.card()
    return card["answer"] if card else ""


def dictate(session, text: str = COMPLAINT):
    """Say a complaint and get to the confirmation."""
    session.says(text)
    session.says("finished", expect="voice.answer")
    session.settle(Phase.WAITING_CONFIRMATION)


# ---------------------------------------------------------------------------
# Confirming
# ---------------------------------------------------------------------------

class TestConfirming:

    def test_the_whole_complaint_reaches_the_petition(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == [COMPLAINT]

    @pytest.mark.parametrize("agreement", [
        "yes", "yeah", "correct", "that's right", "okay", "continue",
        "proceed", "go ahead",
    ])
    def test_the_ordinary_ways_of_saying_yes(
            self, agreement, dictation_available, brisk, spoken):
        """Listed in the brief, and each one is how somebody actually
        answers a machine that has just read their complaint back."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says(agreement, expect="voice.answer")

        assert workflow.invoked == [COMPLAINT], agreement

    @pytest.mark.parametrize("agreement", [
        "ஆம்", "ஆமாம்", "சரி", "சரிதான்", "தொடரலாம்", "ஓகே", "அதுதான்",
        # Mixed, which is how people here actually speak.
        "sari continue", "yes சரிதான்",
    ])
    def test_the_tamil_and_mixed_ways(
            self, agreement, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says(agreement, expect="voice.answer")

        assert workflow.invoked == [COMPLAINT], agreement

    def test_the_page_is_told_the_grievance_is_settled(
            self, dictation_available, brisk, spoken):
        """So it can show the success card. A citizen who has spent two
        minutes on this should see it accepted, not infer it from the next
        question arriving."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("yes", expect="voice.grievance")

            assert Phase.LONG_CONFIRMED.value in session.phases()

    def test_and_then_the_next_question_is_asked_without_a_click(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("yes", expect="voice.grievance")
            session.drain("tts.start")
            said = session.spoken_lines()[-1]

        # The acknowledgement and the next question, in ONE utterance: two
        # would put a silence between them that reads as the assistant
        # having finished.
        assert "confirmed" in said.lower(), said
        assert "Thank you." in said, said

    def test_nothing_reaches_the_petition_before_the_yes(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)

            assert workflow.invoked == []


# ---------------------------------------------------------------------------
# Rejecting
# ---------------------------------------------------------------------------

class TestRetry:

    @pytest.mark.parametrize("rejection", [
        "retry", "again", "start again", "that's wrong",
        "மீண்டும்", "மறுபடியும்", "தவறு",
    ])
    def test_the_draft_is_thrown_away_and_the_step_stays(
            self, rejection, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says(rejection, expect="voice.dictation")

            assert captured(session) == "", rejection
            assert workflow.invoked == [], rejection

    def test_the_citizen_is_told_the_whole_thing_is_being_redone(
            self, dictation_available, brisk, spoken):
        """"Please tell me again", said of a two-minute complaint, does not
        make clear that all of it has gone."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("retry", expect="voice.dictation")
            session.drain("tts.start")
            said = " ".join(session.spoken_lines()).lower()

        assert "grievance again" in said, said

    def test_and_the_new_complaint_is_the_one_that_is_filed(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("retry", expect="voice.dictation")
            session.says("The street light has not worked for a month.")
            session.says("finished", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == ["The street light has not worked for a month."]


# ---------------------------------------------------------------------------
# Editing by voice — the part that was missing
# ---------------------------------------------------------------------------

class TestEditingByVoice:

    def test_changing_a_number_keeps_the_rest_of_the_complaint(
            self, dictation_available, brisk, spoken):
        """THE BUG. Before this, those six words became the whole petition."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change five days to three days", expect="voice.answer")

            assert "for three days" in offered(session)
            assert "We informed the local office but nobody came." in offered(session)
            assert offered(session) != "Change five days to three days"

    def test_the_edit_is_not_an_approval(
            self, dictation_available, brisk, spoken):
        """The brief: "Do NOT immediately approve after edit." The petition
        must not have moved on."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change five days to three days", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)

            assert workflow.invoked == []

    def test_it_says_what_it_changed_and_asks_again(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change five days to three days", expect="voice.answer")
            session.drain("tts.start")
            said = session.spoken_lines()[-1].lower()

        assert "five days" in said and "three days" in said, said
        assert "correct now" in said, said

    def test_and_confirming_afterwards_files_the_edited_text(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change five days to three days", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == [
            "Water has not been supplied to our street for three days. "
            "We informed the local office but nobody came."]

    def test_removing_the_last_sentence(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Remove the last sentence", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == [
            "Water has not been supplied to our street for five days."]

    def test_adding_a_detail(self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Add that I already complained last week",
                         expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == [
            f"{COMPLAINT} I already complained last week"]

    def test_two_edits_in_a_row(self, dictation_available, brisk, spoken):
        """Each one is applied to the result of the last, and neither is
        approved on its own."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change five days to three days", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("Remove the last sentence", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == [
            "Water has not been supplied to our street for three days."]

    def test_the_screen_is_updated_as_well_as_the_card(
            self, dictation_available, brisk, spoken):
        """The panel showing the complaint and the card asking about it must
        not disagree — a citizen reading one and hearing about the other is
        being asked to approve two different things."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change five days to three days", expect="voice.answer")

            assert captured(session) == offered(session)


# ---------------------------------------------------------------------------
# No guessing
# ---------------------------------------------------------------------------

class TestAnUnclearEditIsAskedAbout:

    def test_change_that_asks_which_part(
            self, dictation_available, brisk, spoken):
        """The brief, word for word: Citizen "Change that." -> AI "Which
        part would you like to change?" -> Do not guess."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change that", expect="tts.start")
            said = session.spoken_lines()[-1].lower()

        assert "which part" in said, said

    def test_and_the_complaint_is_untouched_while_it_asks(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change that", expect="tts.start")

            assert offered(session) == COMPLAINT
            assert workflow.invoked == []

    def test_naming_the_words_then_the_replacement(
            self, dictation_available, brisk, spoken):
        """Two steps, because naming the words does not say what to put
        there. "The five days part" is half an instruction and acting on
        half is the guessing this avoids."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change that", expect="tts.start")
            session.says("five days", expect="tts.start")

            assert "instead" in session.spoken_lines()[-1].lower()

            session.says("three days", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == [
            "Water has not been supplied to our street for three days. "
            "We informed the local office but nobody came."]

    def test_words_that_are_not_in_the_complaint_are_asked_about_again(
            self, dictation_available, brisk, spoken):
        """Never approximated. A near-miss substitution into a document
        somebody signs is worse than a second question."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change the drainage to the sewer", expect="tts.start")
            said = session.spoken_lines()[-1].lower()

            assert "could not find" in said, said
            assert offered(session) == COMPLAINT

    def test_an_outstanding_question_does_not_trap_the_citizen(
            self, dictation_available, brisk, spoken):
        """They asked to change something, then decided it was fine. Saying
        yes has to still mean yes."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change that", expect="tts.start")
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == [COMPLAINT]

    def test_removing_the_only_sentence_is_refused(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("The street light does not work.")
            session.says("finished", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("Remove the last sentence", expect="tts.start")

            assert offered(session) == "The street light does not work."
            assert workflow.invoked == []


# ---------------------------------------------------------------------------
# An edit is not a continuation, and a continuation is not an edit
# ---------------------------------------------------------------------------

class TestTheTwoAreKeptApart:

    def test_also_reopens_the_microphone(
            self, dictation_available, brisk, spoken):
        """Unchanged behaviour, pinned because the edit check now runs in
        front of it."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Also the drain is blocked", expect="voice.dictation")

            assert "Also the drain is blocked" in captured(session)
            assert COMPLAINT in captured(session)

    def test_add_one_more_point_reopens_rather_than_appending_those_words(
            self, dictation_available, brisk, spoken):
        """It announces more; it is not the more. Appending it literally
        would print "one more point" in somebody's complaint."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("I want to add one more thing", expect="voice.dictation")

            assert "one more thing" not in captured(session)
            assert captured(session) == COMPLAINT

    def test_an_edit_wins_over_a_continuation_cue_inside_it(
            self, dictation_available, brisk, spoken):
        """Both readings are available for one sentence. Read as a
        continuation, the instruction to change the complaint is appended to
        it instead of carried out."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Also change five days to three days",
                         expect="voice.answer")

            assert "three days" in offered(session)
            assert "Also change" not in offered(session)


# ---------------------------------------------------------------------------
# Pausing
# ---------------------------------------------------------------------------

class TestPausing:

    def test_pausing_stops_the_recording_without_losing_it(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says(COMPLAINT)
            session.send({"type": "dictation.pause"}, expect="voice.dictation")

            assert session.dictation()["paused"] is True
            assert captured(session) == COMPLAINT
            session.settle(Phase.LONG_PAUSED)

    def test_a_pause_is_not_an_ending(
            self, dictation_available, brisk, spoken):
        """The finish timer must not decide the citizen has stopped for good
        while they are deliberately thinking."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says(COMPLAINT)
            session.send({"type": "dictation.pause"}, expect="voice.dictation")
            session.settle(Phase.LONG_PAUSED)

            assert session.card() is None, "it was offered for confirmation"
            assert workflow.invoked == []

    def test_resuming_carries_on_from_where_it_stopped(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says(COMPLAINT)
            session.send({"type": "dictation.pause"}, expect="voice.dictation")
            session.send({"type": "dictation.resume"}, expect="voice.dictation")
            session.says("The tank is also empty.")

            assert session.dictation()["paused"] is False
            assert captured(session) == f"{COMPLAINT} The tank is also empty."

    def test_finish_works_from_a_pause(
            self, dictation_available, brisk, spoken):
        """Somebody who paused to think and then decided they were done
        should not have to resume in order to stop."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says(COMPLAINT)
            session.send({"type": "dictation.pause"}, expect="voice.dictation")
            session.send({"type": "dictation.finish"}, expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)

            assert offered(session) == COMPLAINT


# ---------------------------------------------------------------------------
# The buttons and the voice do the same thing
# ---------------------------------------------------------------------------

class TestTheButtonsAgreeWithTheVoice:

    def test_the_edit_button_asks_the_same_question(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.send({"type": "answer.edit"}, expect="tts.start")

            assert "which part" in session.spoken_lines()[-1].lower()

    def test_and_lands_in_the_same_place_as_saying_it(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.send({"type": "answer.edit"}, expect="tts.start")
            session.says("five days", expect="tts.start")
            session.says("three days", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("yes", expect="voice.answer")

        assert "three days" in workflow.invoked[0]

    def test_the_confirm_button_files_the_edited_text(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change five days to three days", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.send({"type": "answer.confirm"}, expect="voice.answer")

        assert "three days" in workflow.invoked[0]


# ---------------------------------------------------------------------------
# Tamil, end to end
# ---------------------------------------------------------------------------

TAMIL_COMPLAINT = ("எங்கள் தெருவில் ஐந்து நாட்களாக தண்ணீர் வரவில்லை. "
                   "அலுவலகத்தில் தெரிவித்தோம்.")


class TestTamil:

    def test_a_tamil_grievance_is_captured_and_confirmed(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance(language="ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says(TAMIL_COMPLAINT)
            session.says("முடிந்தது", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("ஆம்", expect="voice.answer")

        assert workflow.invoked == [TAMIL_COMPLAINT]

    def test_a_tamil_edit_changes_only_what_was_named(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance(language="ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says(TAMIL_COMPLAINT)
            session.says("முடிந்தது", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("ஐந்து நாட்கள் என்பதை மூன்று நாட்கள் என்று மாற்றவும்",
                         expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("ஆம்", expect="voice.answer")

        assert workflow.invoked == [
            "எங்கள் தெருவில் மூன்று நாட்களாக தண்ணீர் வரவில்லை. "
            "அலுவலகத்தில் தெரிவித்தோம்."]

    def test_the_tamil_removal(self, dictation_available, brisk, spoken):
        workflow = AtGrievance(language="ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says(TAMIL_COMPLAINT)
            session.says("முடிந்தது", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("கடைசி வரியை நீக்கவும்", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("ஆம்", expect="voice.answer")

        assert workflow.invoked == [
            "எங்கள் தெருவில் ஐந்து நாட்களாக தண்ணீர் வரவில்லை."]


# ---------------------------------------------------------------------------
# Two phrases that meant the wrong thing here
# ---------------------------------------------------------------------------

class TestThePhrasesThatCollided:
    """Both were found by this flow, and both had the same shape: a pattern
    written for the FINISHED petition ("shall I read it out?") was also
    consulted at the grievance read-back, where the same words mean
    something else.

    Neither failed anything before. The citizen was simply read their own
    complaint instead of being taken at their word, and the session went
    round again.
    """

    def test_go_ahead_at_a_read_back_means_yes(
            self, dictation_available, brisk, spoken):
        """It was listed literally as a request to read aloud."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("go ahead", expect="voice.answer")

        assert workflow.invoked == [COMPLAINT]

    def test_marupadiyum_means_again_not_read_it(
            self, dictation_available, brisk, spoken):
        """\u0bae\u0bb1\u0bc1\u0baa\u0b9f\u0bbf\u0baf\u0bc1\u0bae\u0bcd contains \u0baa\u0b9f\u0bbf, which was matched as a substring
        because Tamil has no word boundaries. One of the two commonest ways
        to reject an answer was read as a request to recite it."""
        workflow = AtGrievance(language="ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says(TAMIL_COMPLAINT)
            session.says("\u0bae\u0bc1\u0b9f\u0bbf\u0ba8\u0bcd\u0ba4\u0ba4\u0bc1", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("\u0bae\u0bb1\u0bc1\u0baa\u0b9f\u0bbf\u0baf\u0bc1\u0bae\u0bcd", expect="voice.dictation")

            assert captured(session) == ""
            assert workflow.invoked == []

    def test_reading_it_out_still_works(
            self, dictation_available, brisk, spoken):
        """The narrowing must not have taken the feature with it. A citizen
        who cannot read the screen has only this."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("read it to me", expect="tts.start")
            said = " ".join(session.spoken_lines())

        assert COMPLAINT in said, said
        assert workflow.invoked == []

    def test_and_in_tamil(self, dictation_available, brisk, spoken):
        workflow = AtGrievance(language="ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says(TAMIL_COMPLAINT)
            session.says("\u0bae\u0bc1\u0b9f\u0bbf\u0ba8\u0bcd\u0ba4\u0ba4\u0bc1", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            session.says("\u0baa\u0b9f\u0bbf\u0b95\u0bcd\u0b95\u0bb5\u0bc1\u0bae\u0bcd", expect="tts.start")
            said = " ".join(session.spoken_lines())

        assert TAMIL_COMPLAINT in said, said
        assert workflow.invoked == []


class TestAPauseIsNotASilence:
    """`last_voice_at` is refreshed by audio arriving, and a pause discards
    audio before anything touches it. So the idle clock kept running: a
    citizen who asked for a minute to think had the session ended at the end
    of it, with their half-told complaint on screen."""

    def test_the_watchdog_leaves_a_paused_session_alone(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, voice_idle_timeout_s=1.0, **BRISK) as session:
            session.says(COMPLAINT)
            session.send({"type": "dictation.pause"}, expect="voice.dictation")
            session.settle(Phase.LONG_PAUSED)
            # Long enough that an unpaused session would have been ended.
            time.sleep(3.0)
            session.send({"type": "dictation.resume"}, expect="voice.dictation")

            assert captured(session) == COMPLAINT
            assert "idle" not in [m.get("reason") for m in session.seen]

    def test_and_still_ends_one_that_is_merely_quiet(
            self, dictation_available, brisk, spoken):
        """The guard must not have turned the idle timeout off altogether."""
        workflow = AtGrievance()
        with talking(workflow, voice_idle_timeout_s=1.0, **BRISK) as session:
            session.says(COMPLAINT)
            ended = session.drain("voice.ended", cap=200)

        assert ended["reason"] == "idle"


class TestTheClarificationDoesNotTrapAnyone:
    """The assistant has asked WHICH PART to change, and is waiting to be
    told. Every reply that is not a phrase from the complaint has to lead
    somewhere, or the citizen is in a loop with a two-minute complaint they
    cannot get out of."""

    def test_deciding_it_was_fine_after_all(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change that", expect="tts.start")
            session.says("yes", expect="voice.answer")

        assert workflow.invoked == [COMPLAINT]

    def test_giving_up_and_starting_over(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change that", expect="tts.start")
            session.says("start again", expect="voice.dictation")

            assert captured(session) == ""
            assert workflow.invoked == []

    def test_a_phrase_that_was_misheard_does_not_discard_the_complaint(
            self, dictation_available, brisk, spoken):
        """The reason the escape is tested on explicit refusal words rather
        than on the "retry" reading: that reading is ALSO what an utterance
        too thin to act on returns, and escaping on it would throw a
        complaint away every time a word was not found."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            dictate(session)
            session.says("Change that", expect="tts.start")
            session.says("the thing about the pipes", expect="tts.start")

            assert offered(session) == COMPLAINT
            assert "could not find" in session.spoken_lines()[-1].lower()
