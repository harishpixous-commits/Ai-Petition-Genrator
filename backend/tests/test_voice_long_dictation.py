"""The grievance, spoken at length, over a real WebSocket.

WHAT THIS IS FOR. Name, age and Aadhaar are answers. A grievance is an
account: it runs for a minute, it has pauses in it while the citizen
remembers the date, and it ends with "…and nothing has been done since". The
short-answer rules end it at the first breath and file half a complaint, and
the half that gets filed is the half without the ask in it.

THE PROPERTY EVERY TEST HERE IS REALLY CHECKING: **no part of what the
citizen said is lost, reordered, or changed.** The stand-in workflow records
what it is finally given, so "did the whole complaint arrive?" is a fact in
these tests rather than an inference.

WHAT IS NOT PROVEN HERE. That a real microphone in a real room produces these
transcripts. These tests begin after the transcript exists — the audio gate
in front of them has its own tests, and one case below drives real PCM
through it to show the two halves meet.
"""

from __future__ import annotations

import contextlib
import json
import uuid

import anyio
import pytest
from fastapi.testclient import TestClient

from app.api.ws import Phase
from app.config import get_settings
from app.main import app
from app.services import asr, tts

# Everything except the grievance, so the grievance is the question on the
# table. Taken from the template's own order rather than assumed.
FILLED = {
    "applicant_name": "Ravi Kumar",
    "age": 45,
    "mobile": "9344174752",
    "address": "12 Gandhi Street, Coimbatore",
    "aadhaar": "234567890124",
}


class AtGrievance:
    """A workflow parked on the grievance question."""

    def __init__(self, language: str = "en") -> None:
        self.language = language
        self.invoked: list[str] = []

    def _state(self) -> dict:
        # `reply` carries the outstanding question, the way the real graph's
        # checkpoint does. Without it the assistant has nothing to say on
        # arriving at the grievance, and the pacing instruction — which is
        # appended to the question rather than replacing it — is never heard.
        return {"language": self.language, "status": "collecting",
                "fields": dict(FILLED),
                "reply": "Now please tell me your grievance, in your own words."}

    async def snapshot(self, session_id: str) -> dict:
        return self._state()

    async def peek(self, session_id: str) -> dict:
        return self._state()

    async def invoke(self, session_id: str, payload: dict) -> dict:
        self.invoked.append(payload["utterance"])
        return {**self._state(), "reply": "Thank you."}

    @staticmethod
    def question() -> str:
        return "Now please tell me your grievance, in your own words."


@pytest.fixture
def dictation_available(monkeypatch):
    monkeypatch.setattr(asr, "status", lambda settings=None: {"ok": True, "provider": "test"})


# Shorten the thinking pause so the suite does not sit through it. The VALUE
# is what is shortened, never the rule: the finish timer still has to expire,
# still has to wait for the assistant to stop talking, and still has to leave
# the segments alone until it does.
#
# Applied inside `talking`, AFTER the application has started. The startup
# calls `provider_store.apply()`, which clears the settings cache — so a
# fixture that patched the object beforehand was patching one that gets
# thrown away, and every test using it quietly ran on the real 3.5 seconds.
BRISK = {"voice_long_finish_s": 0.35}


@pytest.fixture
def brisk():
    return BRISK


@pytest.fixture
def spoken(monkeypatch):
    async def _stream(text, language, settings):
        yield b"RIFF"

    monkeypatch.setattr(tts, "configured", lambda settings=None: True)
    monkeypatch.setattr(tts, "stream", _stream)


class Session:
    DEADLINE_S = 15.0

    def __init__(self, ws) -> None:
        self.ws = ws
        self.seen: list[dict] = []

    def _receive(self) -> dict:
        stream = getattr(self.ws, "_send_rx", None)
        if stream is None:  # pragma: no cover
            return self.ws.receive()

        async def _before_the_deadline():
            with anyio.fail_after(self.DEADLINE_S):
                return await stream.receive()

        try:
            return self.ws.portal.call(_before_the_deadline)
        except TimeoutError:
            raise AssertionError(
                f"nothing arrived within {self.DEADLINE_S}s. "
                f"Received: {[m.get('type') for m in self.seen]}") from None

    def _next(self) -> dict:
        while True:
            frame = self._receive()
            if frame.get("text") is not None:
                message = json.loads(frame["text"])
                self.seen.append(message)
                return message
            if frame.get("bytes") is not None:
                continue
            raise AssertionError(f"the socket closed: {frame}")

    def drain(self, expect: str, *, cap: int = 80) -> dict:
        for _ in range(cap):
            message = self._next()
            if message.get("type") == expect:
                return message
        raise AssertionError(
            f"no {expect!r}; got {[m.get('type') for m in self.seen]}")

    def settle(self, phase: Phase, *, cap: int = 80) -> None:
        for _ in range(cap):
            message = self._next()
            if message.get("type") == "voice.state" and message["state"] == phase.value:
                return
        raise AssertionError(f"never reached {phase.value}; saw {self.phases()}")

    def says(self, text: str, *, expect: str = "voice.dictation") -> dict:
        self.ws.send_json({"type": "text", "text": text})
        return self.drain(expect)

    def send(self, message: dict, *, expect: str) -> dict:
        self.ws.send_json(message)
        return self.drain(expect)

    def phases(self) -> list[str]:
        return [m["state"] for m in self.seen if m.get("type") == "voice.state"]

    def spoken_lines(self) -> list[str]:
        return [m.get("text", "") for m in self.seen if m.get("type") == "tts.start"]

    def dictation(self) -> dict | None:
        found = [m for m in self.seen if m.get("type") == "voice.dictation"]
        return found[-1] if found else None

    def card(self) -> dict | None:
        found = [m for m in self.seen if m.get("type") == "voice.answer"]
        return found[-1] if found else None


@contextlib.contextmanager
def talking(workflow, *, language: str = "en", **overrides):
    with TestClient(app) as client:
        previous = getattr(app.state, "workflow", None)
        app.state.workflow = workflow
        settings = get_settings()
        restore = {name: getattr(settings, name) for name in overrides}
        for name, value in overrides.items():
            setattr(settings, name, value)
        try:
            with client.websocket_connect(
                    f"/ws/voice/{uuid.uuid4()}?language={language}") as ws:
                session = Session(ws)
                ws.send_json({"type": "voice.start"})
                session.drain("voice.state")
                yield session
        finally:
            for name, value in restore.items():
                setattr(settings, name, value)
            app.state.workflow = previous


# ---------------------------------------------------------------------------
# The grievance is not a short answer
# ---------------------------------------------------------------------------

class TestAPauseIsNotAnEnding:

    def test_the_first_sentence_does_not_end_the_answer(
            self, dictation_available, brisk):
        """The bug this whole mode exists for: "My street has had no water
        for five days" is the BEGINNING of a complaint, and treating it as
        the whole of one files a petition with no ask in it."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            progress = session.says("My street has had no water for five days.")

        assert progress["capturing"] is True, "the answer was closed after one sentence"
        assert progress["segments"] == 1
        assert workflow.invoked == []

    def test_segments_join_in_the_order_they_were_spoken(
            self, dictation_available, brisk):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("My street has had no water for five days.")
            session.says("I already informed the local office.")
            progress = session.says("But no action has been taken.")

        assert progress["segments"] == 3
        assert progress["text"] == (
            "My street has had no water for five days. "
            "I already informed the local office. "
            "But no action has been taken.")

    def test_a_quiet_spell_closes_it_and_asks(self, dictation_available, brisk):
        """Nobody should have to say a magic word. Stopping is how a person
        signals they have finished."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("The drain outside my house has been blocked for a month.")
            card = session.drain("voice.answer")

        assert card["awaiting"] is True
        assert "drain" in card["answer"]
        assert workflow.invoked == [], "closing the dictation is not confirming it"

    def test_saying_finished_closes_it_immediately(self, dictation_available, brisk):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("The street light has not worked for three months.")
            card = session.says("finished", expect="voice.answer")

        assert card["awaiting"] is True
        assert "finished" not in card["answer"], "the word ended up in the complaint"
        assert card["answer"] == "The street light has not worked for three months."

    def test_that_is_all_is_not_confused_with_the_complaint(
            self, dictation_available, brisk):
        """"That's all the water we get in a week" is a sentence about water,
        not an announcement that the citizen has stopped talking."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            progress = session.says("That's all the water we get in a week.")

        assert progress["capturing"] is True
        assert progress["segments"] == 1


class TestTheWholeComplaintReachesThePetition:

    def test_confirming_sends_every_segment(self, dictation_available, brisk):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("My street has had no water for five days.")
            session.says("I already informed the local office.")
            session.says("finished", expect="voice.answer")
            session.send({"type": "answer.confirm"}, expect="state")

        assert workflow.invoked == [
            "My street has had no water for five days. "
            "I already informed the local office."]

    def test_nothing_is_shortened_on_the_way(self, dictation_available, brisk):
        """A two-minute grievance is about two thousand characters. Every one
        of them has to arrive: the sentence that gets cut is the last one,
        and the last one is where the citizen says what they want done."""
        workflow = AtGrievance()
        sentences = [f"Point number {i} about the water supply in my street."
                     for i in range(1, 31)]
        with talking(workflow, **BRISK) as session:
            for sentence in sentences:
                session.says(sentence)
            session.says("finished", expect="voice.answer")
            session.send({"type": "answer.confirm"}, expect="state")

        saved = workflow.invoked[0]
        assert saved == " ".join(sentences)
        assert saved.endswith("Point number 30 about the water supply in my street.")
        assert len(saved) > 1000

    def test_the_citizens_words_are_not_edited(self, dictation_available, brisk):
        """No summarising, no filler removal, no tidying. What is stored is
        what was said."""
        workflow = AtGrievance()
        said = "Well, the thing is, that the water, it just stopped on Tuesday."
        with talking(workflow, **BRISK) as session:
            session.says(said)
            session.says("finished", expect="voice.answer")
            session.send({"type": "answer.confirm"}, expect="state")

        assert workflow.invoked == [said]


class TestAddingMoreDoesNotReplaceWhatCameBefore:

    def test_also_appends(self, dictation_available, brisk):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("The street light has not worked for three months.")
            session.says("finished", expect="voice.answer")
            session.send({"type": "text", "text": "also the drain is blocked"},
                         expect="voice.dictation")
            session.drain("voice.answer")
            session.send({"type": "answer.confirm"}, expect="state")

        assert workflow.invoked == [
            "The street light has not worked for three months. "
            "also the drain is blocked"]

    def test_announcing_more_reopens_without_adding_anything(
            self, dictation_available, brisk):
        """"I have one more thing" is not itself a complaint. It reopens the
        answer and waits, rather than printing itself on the petition."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("The street light has not worked for three months.")
            session.says("finished", expect="voice.answer")
            progress = session.send({"type": "text", "text": "I have one more thing"},
                                    expect="voice.dictation")

        assert progress["capturing"] is True
        assert progress["text"] == "The street light has not worked for three months."

    def test_and_what_comes_next_is_appended(self, dictation_available, brisk):
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("The street light has not worked for three months.")
            session.says("finished", expect="voice.answer")
            session.send({"type": "text", "text": "I have one more thing"},
                         expect="voice.dictation")
            session.says("The pole is leaning over the road.")
            session.says("finished", expect="voice.answer")
            session.send({"type": "answer.confirm"}, expect="state")

        assert workflow.invoked == [
            "The street light has not worked for three months. "
            "The pole is leaning over the road."]

    def test_retry_throws_the_whole_narration_away(self, dictation_available, brisk):
        """"Say it again" about a grievance means the grievance, not the last
        sentence of it."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("The street light has not worked for three months.")
            session.says("And the drain is blocked.")
            session.says("finished", expect="voice.answer")
            progress = session.send({"type": "answer.retry"}, expect="voice.dictation")

        assert progress["segments"] == 0
        assert progress["text"] == ""
        assert workflow.invoked == []


class TestWhatTheAssistantSays:

    def test_the_citizen_is_told_they_may_take_their_time(
            self, dictation_available, brisk, spoken):
        """Asked for their grievance the way they were asked their age, a
        citizen answers in one sentence and stops."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.drain("tts.start")
            said = " ".join(session.spoken_lines())

        # The wording is the brief's, word for word.
        assert "take your time" in said.lower(), said
        assert "finished" in said.lower(), said
        # Appended to the workflow's own question, not instead of it.
        assert AtGrievance.question() in said, said

    def test_a_long_grievance_is_summarised_rather_than_recited(
            self, dictation_available, brisk, spoken):
        """Two minutes of speech read back is two minutes nobody listens to,
        and the whole of it is on the screen already."""
        workflow = AtGrievance()
        long_text = " ".join(
            f"Sentence {i} about the blocked drain on my street." for i in range(1, 12))
        with talking(workflow, **BRISK) as session:
            session.says(long_text)
            session.says("finished", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            said = " ".join(session.spoken_lines())

        # Not recited, and the three things the citizen may now do are
        # named — the brief's wording: "You can say Yes, Retry, or tell me
        # what you want to change."
        assert "is this correct" in said.lower(), said
        for offer in ("yes", "retry", "change"):
            assert offer in said.lower(), (offer, said)
        assert "Sentence 7" not in said, "the whole thing was read out after all"
        assert session.card()["lengthy"] is True
        # ...but the page was given every word of it.
        assert session.card()["answer"] == long_text

    def test_a_short_grievance_is_read_back_in_full(
            self, dictation_available, brisk, spoken):
        """Hearing it is the only way a citizen who cannot read the screen
        can check it."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("No water for five days.")
            session.says("finished", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            said = " ".join(session.spoken_lines())

        assert "No water for five days." in said
        assert session.card()["lengthy"] is False

    def test_it_can_be_read_out_in_full_on_request(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance()
        long_text = " ".join(
            f"Sentence {i} about the blocked drain." for i in range(1, 12))
        with talking(workflow, **BRISK) as session:
            session.says(long_text)
            session.says("finished", expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            before = len(session.spoken_lines())
            session.send({"type": "answer.read"}, expect="tts.start")
            read = session.spoken_lines()[before:]

        assert any("Sentence 7" in line for line in read), read


class TestTamil:

    def test_a_tamil_grievance_accumulates(self, dictation_available, brisk):
        workflow = AtGrievance("ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says("எங்கள் தெருவில் ஐந்து நாட்களாக தண்ணீர் வரவில்லை.")
            progress = session.says("அலுவலகத்தில் ஏற்கனவே தெரிவித்துவிட்டேன்.")

        assert progress["segments"] == 2
        assert "தண்ணீர்" in progress["text"]
        assert "அலுவலகத்தில்" in progress["text"]

    def test_mudinthathu_closes_it(self, dictation_available, brisk):
        workflow = AtGrievance("ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says("எங்கள் தெருவில் தண்ணீர் வரவில்லை.")
            card = session.says("முடிந்தது", expect="voice.answer")

        assert card["awaiting"] is True
        assert "முடிந்தது" not in card["answer"]

    def test_innum_onru_adds_rather_than_replaces(self, dictation_available, brisk):
        workflow = AtGrievance("ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says("தெருவிளக்கு எரியவில்லை.")
            session.says("முடிந்தது", expect="voice.answer")
            progress = session.send({"type": "text", "text": "இன்னும் ஒன்று இருக்கு"},
                                    expect="voice.dictation")

        assert "தெருவிளக்கு எரியவில்லை." in progress["text"]
        assert progress["capturing"] is True

    def test_the_instruction_is_given_in_tamil(
            self, dictation_available, brisk, spoken):
        workflow = AtGrievance("ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.drain("tts.start")
            said = " ".join(session.spoken_lines())

        assert "விரிவாக" in said, said


class TestMixedLanguage:

    def test_tamil_and_english_in_one_narration_are_kept_as_spoken(
            self, dictation_available, brisk):
        """Code-switching is how people actually talk here. Neither half is
        dropped and neither is translated."""
        workflow = AtGrievance("ta")
        with talking(workflow, language="ta", **BRISK) as session:
            session.says("எங்கள் தெருவில் தண்ணீர் வரவில்லை.")
            session.says("Water board office la complaint pannitten.")
            session.says("முடிந்தது", expect="voice.answer")
            session.send({"type": "answer.confirm"}, expect="state")

        assert workflow.invoked == [
            "எங்கள் தெருவில் தண்ணீர் வரவில்லை. "
            "Water board office la complaint pannitten."]


class TestTheHardLimit:
    """The one place a limit may change the outcome. The citizen is told
    BEFORE anything is lost, and everything already said is kept."""

    def test_the_citizen_is_warned_instead_of_being_truncated(
            self, dictation_available, brisk, spoken, monkeypatch):
        import app.api.ws as ws

        # The real ceiling is 6000 characters — roughly seven minutes of
        # speech. Lowered here so the case can be reached without reciting
        # for seven minutes; the BEHAVIOUR under test is unchanged.
        monkeypatch.setattr(ws, "MAX_FREE_TEXT", 120)
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("A" * 100)
            session.says("B" * 100, expect="voice.answer")
            session.settle(Phase.WAITING_CONFIRMATION)
            said = " ".join(session.spoken_lines())
            card = session.card()

        assert "as much as this form can hold" in said.lower(), said
        # Everything already captured survives, and the part that would not
        # fit was never silently dropped into a half-stored complaint.
        assert card["answer"] == "A" * 100
        assert "B" * 100 not in card["answer"]


class TestSegmentsArriveOnce:

    def test_the_same_transcript_twice_is_one_segment(
            self, dictation_available, brisk):
        """A retried or duplicated final result must not double a sentence in
        somebody's complaint."""
        workflow = AtGrievance()
        with talking(workflow, **BRISK) as session:
            session.says("The drain is blocked.")
            session.ws.send_json({"type": "text", "text": "The drain is blocked."})
            session.ws.send_json({"type": "text", "text": "And it smells."})
            progress = session.drain("voice.dictation")
            while progress["segments"] < 2:
                progress = session.drain("voice.dictation")

        assert progress["text"] == "The drain is blocked. And it smells."
        assert progress["segments"] == 2


class TestOtherFieldsAreUnaffected:

    def test_a_short_field_still_ends_at_the_first_answer(self, dictation_available):
        """Long dictation is for the narrative field only. A name that waited
        for a four-second pause would make the whole form feel broken."""
        class AtName(AtGrievance):
            def _state(self) -> dict:
                return {"language": "en", "status": "collecting", "fields": {}}

        workflow = AtName()
        with talking(workflow, **BRISK) as session:
            session.ws.send_json({"type": "text", "text": "Ravi Kumar"})
            card = session.drain("voice.answer")

        assert card["awaiting"] is True
        assert card["answer"] == "Ravi Kumar"


class TestADroppedConnectionDoesNotLoseTheComplaint:
    """A socket on a counter's wifi does not reliably last two minutes. The
    reason the citizen was talking for ninety seconds is that they had ninety
    seconds' worth to say, and asking them to start again is the worst thing
    this feature could do."""

    def test_the_segments_come_back_on_the_next_connection(
            self, dictation_available):
        workflow = AtGrievance()
        session_id = str(uuid.uuid4())

        def connect():
            return TestClient(app).__enter__(), session_id

        client = TestClient(app)
        with client:
            previous = getattr(app.state, "workflow", None)
            app.state.workflow = workflow
            try:
                with client.websocket_connect(f"/ws/voice/{session_id}") as ws:
                    first = Session(ws)
                    ws.send_json({"type": "voice.start"})
                    first.drain("voice.state")
                    first.says("My street has had no water for five days.")
                    first.says("I already informed the local office.")
                # ...and the connection is gone, mid-narration.

                with client.websocket_connect(f"/ws/voice/{session_id}") as ws:
                    second = Session(ws)
                    ws.send_json({"type": "voice.start"})
                    restored = second.drain("voice.dictation")
            finally:
                app.state.workflow = previous

        assert restored["segments"] == 2, "the narration was lost"
        assert restored["text"] == (
            "My street has had no water for five days. "
            "I already informed the local office.")
        assert workflow.invoked == [], "and it was not quietly saved either"

    def test_a_different_session_gets_nothing(self, dictation_available):
        """The draft belongs to one petition. A grievance leaking into
        somebody else's session would be far worse than losing it."""
        workflow = AtGrievance()
        client = TestClient(app)
        with client:
            previous = getattr(app.state, "workflow", None)
            app.state.workflow = workflow
            try:
                with client.websocket_connect(f"/ws/voice/{uuid.uuid4()}") as ws:
                    first = Session(ws)
                    ws.send_json({"type": "voice.start"})
                    first.drain("voice.state")
                    first.says("The drain outside my house is blocked.")

                with client.websocket_connect(f"/ws/voice/{uuid.uuid4()}") as ws:
                    second = Session(ws)
                    ws.send_json({"type": "voice.start"})
                    second.drain("voice.state")
                    progress = second.says("The street light is broken.")
            finally:
                app.state.workflow = previous

        assert progress["segments"] == 1
        assert "drain" not in progress["text"]

    def test_confirming_clears_the_draft(self, dictation_available):
        """Once it is the petition's, it stops being a draft: a later socket
        on the same session must not resurrect a grievance that was already
        filed."""
        workflow = AtGrievance()
        session_id = str(uuid.uuid4())
        client = TestClient(app)
        with client:
            previous = getattr(app.state, "workflow", None)
            app.state.workflow = workflow
            settings = get_settings()
            was = settings.voice_long_finish_s
            settings.voice_long_finish_s = 0.35
            try:
                with client.websocket_connect(f"/ws/voice/{session_id}") as ws:
                    first = Session(ws)
                    ws.send_json({"type": "voice.start"})
                    first.drain("voice.state")
                    first.says("The drain outside my house is blocked.")
                    first.says("finished", expect="voice.answer")
                    first.send({"type": "answer.confirm"}, expect="state")

                with client.websocket_connect(f"/ws/voice/{session_id}") as ws:
                    second = Session(ws)
                    ws.send_json({"type": "voice.start"})
                    second.drain("voice.state")
                    second.says("A different problem entirely.")
            finally:
                settings.voice_long_finish_s = was
                app.state.workflow = previous

        assert workflow.invoked == ["The drain outside my house is blocked."]
        last = [m for m in second.seen if m.get("type") == "voice.dictation"][-1]
        assert "drain" not in last["text"]
