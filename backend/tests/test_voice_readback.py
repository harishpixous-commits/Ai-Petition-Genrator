"""Reading each answer back before it is used, over a real WebSocket.

WHAT THIS IS FOR. A citizen dictating into a government form finds out that
"12 Kumar Street" was heard as "20 Kumar Street" at the counter, weeks later,
when the letter is handed back. The loop under test puts that discovery
thirty seconds after they said it: the assistant quotes what it captured, and
nothing reaches the petition until they agree with the quotation.

THE PROPERTY EVERY TEST HERE IS REALLY CHECKING is the same one, stated a
dozen ways: **the workflow does not see an answer the citizen has not
confirmed.** The stand-in workflow records every `invoke`, so "was it saved?"
is a fact in these tests rather than an inference.

WHY TYPED TURNS. `{"type":"text"}` on the voice socket is part of the
documented protocol and takes the identical path — same intent reading, same
pending answer, same confirm. It exercises the loop without a microphone.
What it cannot exercise is the audio gate in front of it, which has its own
tests next door and is deliberately untouched here.

NOT PROVEN HERE, and not claimed: that a real microphone in a real room
reaches this code with the right words in it. These tests start after the
transcript exists.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import Iterator

import anyio
import pytest
from fastapi.testclient import TestClient

from app.api.ws import Phase
from app.main import app
from app.services import asr, tts

FIELDS = {"applicant_name": "Harish"}


class Recording:
    """A workflow that stays on one question and remembers what it was told.

    Staying on `collecting` is what keeps the read-back gate open turn after
    turn, so a test can walk a whole answer — offered, corrected, confirmed —
    without the graph moving the goalposts underneath it.
    """

    status = "collecting"

    def __init__(self, language: str = "en") -> None:
        self.language = language
        self.invoked: list[str] = []

    def _state(self) -> dict:
        return {"language": self.language, "status": self.status, "fields": dict(FIELDS)}

    async def snapshot(self, session_id: str) -> dict:
        return self._state()

    async def peek(self, session_id: str) -> dict:
        return self._state()

    async def invoke(self, session_id: str, payload: dict) -> dict:
        self.invoked.append(payload["utterance"])
        # A reply, because the real graph always has one — it asks the next
        # question. A stand-in that answers with silence would exercise a
        # path the citizen never reaches.
        return {**self._state(), "reply": "And what is your address?"}


class AtReview(Recording):
    """The same workflow, at the step where the assistant has already asked a
    yes/no question of its own."""

    status = "confirming"


@pytest.fixture
def dictation_available(monkeypatch):
    """Let `voice.start` be accepted with no credentials installed."""
    monkeypatch.setattr(asr, "status", lambda settings=None: {"ok": True, "provider": "test"})


@pytest.fixture
def spoken(monkeypatch):
    """A voice, so the read-back is actually uttered and can be read.

    Without this the service has no TTS configured, takes the silent path and
    never emits `tts.start` — which is a supported deployment, and has its own
    test below, but hides the sentence this loop exists to say.
    """
    async def _stream(text, language, settings):
        yield b"RIFF"

    monkeypatch.setattr(tts, "configured", lambda settings=None: True)
    monkeypatch.setattr(tts, "stream", _stream)


class Session:
    """One live voice socket, with everything the browser received so far."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.seen: list[dict] = []
        self.clips = 0

    # Long enough for a slow machine, short enough that a broken loop is a
    # failure rather than a hung suite. A test that never returns is worse
    # than one that fails: the first break tried against these tests made
    # them block, and a blocked test reports nothing at all.
    DEADLINE_S = 15.0

    def _receive(self) -> dict:
        """One frame, or a readable failure.

        Reaches past `receive()` for the underlying stream so a deadline can
        be attached — the public call blocks forever by design. If starlette
        moves it, this falls back to blocking, which is what it did before.
        """
        stream = getattr(self.ws, "_send_rx", None)
        if stream is None:  # pragma: no cover - starlette internals moved
            return self.ws.receive()

        async def _before_the_deadline():
            with anyio.fail_after(self.DEADLINE_S):
                return await stream.receive()

        try:
            return self.ws.portal.call(_before_the_deadline)
        except TimeoutError:
            raise AssertionError(
                f"nothing arrived within {self.DEADLINE_S}s. "
                f"Received so far: {[m.get('type') for m in self.seen]}"
            ) from None

    def _next(self) -> dict:
        """The next JSON message, stepping over the audio.

        Spoken replies arrive as a `tts.audio` announcement followed by a
        BINARY frame, and `receive_json` raises on the binary one. Skipping
        it here rather than in each test keeps the audio path real: the
        clips are still sent and still counted, they are simply not what
        these tests are reading.
        """
        while True:
            frame = self._receive()
            if frame.get("text") is not None:
                message = json.loads(frame["text"])
                self.seen.append(message)
                return message
            if frame.get("bytes") is not None:
                self.clips += 1
                continue
            raise AssertionError(f"the socket closed: {frame}")

    def _drain(self, *, expect: str, cap: int = 60) -> dict:
        """Read until the message this turn was waiting for arrives."""
        for _ in range(cap):
            message = self._next()
            if message.get("type") == expect:
                return message
        raise AssertionError(
            f"no {expect!r} arrived; got {[m.get('type') for m in self.seen]}")

    def says(self, text: str) -> dict:
        """One utterance, as a transcript would arrive.

        Reads on past the answer card until the session has settled into
        waiting for agreement, so a test can assert on the phases without
        racing the read-back: the card is sent BEFORE the assistant starts
        speaking, and stopping at it would leave READING_BACK unread in the
        socket buffer and the test asserting it never happened.
        """
        self.ws.send_json({"type": "text", "text": text})
        self.settle(Phase.WAITING_CONFIRMATION)
        cards = [m for m in self.seen if m.get("type") == "voice.answer"]
        assert cards, f"no answer card; got {[m.get('type') for m in self.seen]}"
        return cards[-1]

    def settle(self, phase: Phase, *, cap: int = 60) -> None:
        for _ in range(cap):
            message = self._next()
            if message.get("type") == "voice.state" and message["state"] == phase.value:
                return
        raise AssertionError(
            f"never reached {phase.value}; saw {self.phases()}")

    def send(self, message: dict, *, expect: str) -> dict:
        self.ws.send_json(message)
        return self._drain(expect=expect)

    def phases(self) -> list[str]:
        return [m["state"] for m in self.seen if m.get("type") == "voice.state"]

    def spoken_lines(self) -> list[str]:
        return [m.get("text", "") for m in self.seen if m.get("type") == "tts.start"]


@contextlib.contextmanager
def talking(workflow, *, language: str = "en") -> Iterator[Session]:
    with TestClient(app) as client:
        # After startup: the lifespan builds the real workflow and assigns it
        # to this attribute, so a stand-in installed earlier is replaced.
        previous = getattr(app.state, "workflow", None)
        app.state.workflow = workflow
        try:
            url = f"/ws/voice/{uuid.uuid4()}?language={language}"
            with client.websocket_connect(url) as ws:
                session = Session(ws)
                ws.send_json({"type": "voice.start"})
                session._drain(expect="voice.state")
                yield session
        finally:
            app.state.workflow = previous


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------

class TestNothingIsSavedUntilItIsAgreedWith:

    def test_an_answer_is_quoted_back_instead_of_being_used(self, dictation_available):
        workflow = Recording()
        with talking(workflow) as session:
            card = session.says("12 Kumar Street")

        assert card["awaiting"] is True
        assert card["answer"] == "12 Kumar Street"
        assert workflow.invoked == [], "the answer reached the petition unconfirmed"

    def test_yes_is_what_lets_it_through(self, dictation_available):
        workflow = Recording()
        with talking(workflow) as session:
            session.says("12 Kumar Street")
            session.send({"type": "text", "text": "yes"}, expect="state")

        assert workflow.invoked == ["12 Kumar Street"]

    def test_the_words_that_are_saved_are_the_citizens_own(self, dictation_available):
        """Not the normalised form, not the masked form. What they said."""
        workflow = Recording()
        said = "Water has not been supplied for five days."
        with talking(workflow) as session:
            session.says(said)
            session.send({"type": "text", "text": "that's correct"}, expect="state")

        assert workflow.invoked == [said]

    def test_a_refusal_throws_the_answer_away(self, dictation_available):
        workflow = Recording()
        with talking(workflow) as session:
            session.says("20 Kumar Street")
            card = session.send({"type": "text", "text": "no"}, expect="voice.answer")

        assert card["awaiting"] is False
        assert workflow.invoked == [], "a rejected answer was saved anyway"

    def test_a_correction_in_the_same_breath_is_not_a_retry(self, dictation_available):
        """"No, 36" already contains the new answer. Asking them to repeat it
        is asking a third time for something they have now said twice."""
        workflow = Recording()
        with talking(workflow) as session:
            session.says("35")
            card = session.send({"type": "text", "text": "No, 36."}, expect="voice.answer")

        assert card["awaiting"] is True
        assert card["answer"] == "36", "the correction was lost"
        assert workflow.invoked == []

    def test_and_the_correction_is_confirmed_in_its_turn(self, dictation_available):
        """A replacement is a candidate like any other. It does not skip the
        read-back just because it arrived as a correction."""
        workflow = Recording()
        with talking(workflow) as session:
            session.says("35")
            session.send({"type": "text", "text": "No, 36."}, expect="voice.answer")
            session.send({"type": "text", "text": "yes"}, expect="state")

        assert workflow.invoked == ["36"], "the old value was saved, or the new one was not"

    def test_a_citizen_can_change_their_mind_twice(self, dictation_available):
        workflow = Recording()
        with talking(workflow) as session:
            session.says("Chennai")
            session.send({"type": "text", "text": "no, Madurai"}, expect="voice.answer")
            card = session.send({"type": "text", "text": "actually Trichy"},
                                expect="voice.answer")
            session.send({"type": "text", "text": "ok"}, expect="state")

        assert card["answer"] == "Trichy"
        assert workflow.invoked == ["Trichy"]


# ---------------------------------------------------------------------------
# What the room hears
# ---------------------------------------------------------------------------

class TestTheReadBackDoesNotAnnounceIdentifiers:
    """A screen is read by the person standing at it. A speaker is heard by
    the queue behind them."""

    def test_an_aadhaar_is_read_back_by_its_last_four_digits(
            self, dictation_available, spoken):
        workflow = Recording()
        with talking(workflow) as session:
            card = session.says("2345 6789 0124")
            said = " ".join(session.spoken_lines())

        assert "0124" in card["answer"], "the citizen cannot tell which card it was"
        assert "2345" not in card["answer"]
        assert "6789" not in said
        assert "0124" in said

    def test_a_mobile_number_keeps_only_its_last_four(self, dictation_available, spoken):
        workflow = Recording()
        with talking(workflow) as session:
            card = session.says("9876543210")
            said = " ".join(session.spoken_lines())

        assert card["answer"].endswith("3210")
        assert "98765" not in card["answer"]
        assert "98765" not in said

    def test_but_the_petition_gets_the_real_number(self, dictation_available, spoken):
        """Masking is for the read-back. A masked Aadhaar on the form would be
        a far worse bug than a spoken one."""
        workflow = Recording()
        with talking(workflow) as session:
            session.says("2345 6789 0124")
            session.send({"type": "text", "text": "yes"}, expect="state")

        assert workflow.invoked == ["2345 6789 0124"]

    def test_the_question_is_actually_asked_out_loud(self, dictation_available, spoken):
        workflow = Recording()
        with talking(workflow) as session:
            session.says("Harish Kumar")
            said = " ".join(session.spoken_lines())

        assert "Harish Kumar" in said
        assert "correct" in said.lower(), said


# ---------------------------------------------------------------------------
# Tamil
# ---------------------------------------------------------------------------

class TestTamil:

    def test_sari_confirms(self, dictation_available):
        workflow = Recording("ta")
        with talking(workflow, language="ta") as session:
            session.says("மதுரை")
            session.send({"type": "text", "text": "சரி"}, expect="state")

        assert workflow.invoked == ["மதுரை"]

    def test_meendum_asks_again(self, dictation_available):
        workflow = Recording("ta")
        with talking(workflow, language="ta") as session:
            session.says("மதுரை")
            card = session.send({"type": "text", "text": "மீண்டும்"}, expect="voice.answer")

        assert card["awaiting"] is False
        assert workflow.invoked == []

    def test_illai_with_the_answer_in_it_replaces(self, dictation_available):
        workflow = Recording("ta")
        with talking(workflow, language="ta") as session:
            session.says("சென்னை")
            card = session.send({"type": "text", "text": "இல்லை, மதுரை"},
                                expect="voice.answer")

        assert card["awaiting"] is True
        assert "மதுரை" in card["answer"]
        assert workflow.invoked == []

    def test_the_read_back_is_asked_in_tamil(self, dictation_available, spoken):
        workflow = Recording("ta")
        with talking(workflow, language="ta") as session:
            session.says("மதுரை")
            said = " ".join(session.spoken_lines())

        assert "சரியா" in said, said


# ---------------------------------------------------------------------------
# The buttons
# ---------------------------------------------------------------------------

class TestTheButtonsAndTheVoiceDoTheSameThing:
    """Not similar things. The same call — which is why a citizen can start an
    answer by speaking and finish it by tapping."""

    def test_confirm_saves_exactly_what_yes_saves(self, dictation_available):
        by_voice, by_button = Recording(), Recording()
        with talking(by_voice) as session:
            session.says("12 Kumar Street")
            session.send({"type": "text", "text": "yes"}, expect="state")
        with talking(by_button) as session:
            session.says("12 Kumar Street")
            session.send({"type": "answer.confirm"}, expect="state")

        assert by_button.invoked == by_voice.invoked == ["12 Kumar Street"]

    def test_retry_discards_exactly_what_no_discards(self, dictation_available):
        workflow = Recording()
        with talking(workflow) as session:
            session.says("12 Kumar Street")
            card = session.send({"type": "answer.retry"}, expect="voice.answer")

        assert card["awaiting"] is False
        assert workflow.invoked == []

    def test_a_button_press_with_nothing_outstanding_does_nothing(self, dictation_available):
        """The page can be a moment behind the server. A stray confirm must
        not commit the next thing that comes along."""
        workflow = Recording()
        with talking(workflow) as session:
            session.ws.send_json({"type": "answer.confirm"})
            session.says("12 Kumar Street")

        assert workflow.invoked == []


# ---------------------------------------------------------------------------
# Where the loop must NOT apply
# ---------------------------------------------------------------------------

class TestTheReviewStepIsNotReadBack:
    """The assistant has just asked "shall I prepare your petition?". Reading
    "yes" back to ask whether "yes" is correct is a loop with no exit."""

    def test_a_yes_at_review_goes_straight_to_the_workflow(self, dictation_available):
        workflow = AtReview()
        with talking(workflow) as session:
            session.send({"type": "text", "text": "yes"}, expect="state")

        assert workflow.invoked == ["yes"]

    def test_no_answer_card_is_offered_there(self, dictation_available):
        workflow = AtReview()
        with talking(workflow) as session:
            session.send({"type": "text", "text": "yes"}, expect="state")

        assert not [m for m in session.seen if m.get("type") == "voice.answer"]


class TestTheStatesThePageIsTold:

    def test_it_settles_on_waiting_rather_than_listening(self, dictation_available):
        """"Listening" after a read-back invites the citizen to carry on with
        the next detail, which is the one thing that must not happen until
        this answer is settled."""
        with talking(Recording()) as session:
            session.says("12 Kumar Street")

        assert session.phases()[-1] == Phase.WAITING_CONFIRMATION.value, session.phases()

    def test_reading_back_is_named_while_it_is_being_said(
            self, dictation_available, spoken):
        with talking(Recording()) as session:
            session.says("12 Kumar Street")
            order = session.phases()

        assert Phase.READING_BACK.value in order, order
        assert (order.index(Phase.READING_BACK.value)
                < order.index(Phase.WAITING_CONFIRMATION.value)), order

    def test_it_returns_to_listening_once_the_answer_is_confirmed(self, dictation_available):
        with talking(Recording()) as session:
            session.says("12 Kumar Street")
            session.send({"type": "text", "text": "yes"}, expect="state")
            session.settle(Phase.LISTENING)

        assert session.phases()[-1] == Phase.LISTENING.value, session.phases()

    def test_a_deployment_with_no_voice_still_gets_the_whole_loop(self, dictation_available):
        """No TTS configured. The read-back cannot be spoken, so the card and
        its buttons are all there is — and they are enough."""
        workflow = Recording()
        with talking(workflow) as session:
            card = session.says("12 Kumar Street")
            assert not session.spoken_lines(), "TTS was configured after all"
            session.send({"type": "answer.confirm"}, expect="state")

        assert card["awaiting"] is True
        assert workflow.invoked == ["12 Kumar Street"]


class TestEndingTheSession:

    def test_ending_voice_drops_the_candidate(self, dictation_available):
        """It was never on the petition. Leaving the card up would offer an
        action with no socket behind it."""
        workflow = Recording()
        with talking(workflow) as session:
            session.says("12 Kumar Street")
            card = session.send({"type": "voice.end"}, expect="voice.answer")

        assert card["awaiting"] is False
        assert workflow.invoked == []


# ---------------------------------------------------------------------------
# When the machine, not the citizen, is the one that failed
# ---------------------------------------------------------------------------

class TestAnEmptyTranscriptionSaysSo:
    """The audio cleared every evidence test — somebody spoke — and the
    transcription came back with nothing in it. That is the machine failing,
    and it reads differently from a noise that produced a filler word."""

    def test_there_is_a_sentence_for_it_in_both_languages(self):
        from app.services.speech_text import phrase

        assert phrase("not_understood", "en") == (
            "I couldn't understand that. Please say it again.")
        assert phrase("not_understood", "ta") == (
            "எனக்கு தெளிவாக புரியவில்லை. மீண்டும் சொல்லுங்கள்.")

    def test_it_is_not_the_same_sentence_as_a_rejected_noise(self):
        """Two situations, two sentences. Collapsing them would tell a
        citizen whose microphone works that they mumbled."""
        from app.services.speech_text import phrase

        for language in ("en", "ta"):
            assert phrase("not_understood", language) != phrase("not_caught", language)

    def test_the_socket_reaches_for_it_on_an_empty_result(self):
        import pathlib

        socket = pathlib.Path("app/api/ws.py").read_text(encoding="utf-8")
        body = socket[socket.index("if not decision.ok:"):]
        body = body[:body.index("guard.begin_turn()")]

        assert "Verdict.EMPTY" in body
        assert 'phrase("not_understood"' in body


# ---------------------------------------------------------------------------
# The spoken path, driven with actual audio
# ---------------------------------------------------------------------------
#
# Everything above sends transcripts. That exercises the read-back loop but
# NOT the branch in front of it: `on_utterance` reaches the loop through its
# own code, and removing that branch left every typed test passing while a
# spoken answer went straight onto the petition unconfirmed. Found by
# deleting it and watching nothing fail.
#
# So this pushes PCM through the real detector — calibration, onset, the
# zero-crossing test, the hangover, the commit guard — and only stubs the
# transcription, which is the one part that needs a network. The audio is
# synthetic but it has to satisfy every gate that a fan and a keyboard click
# fail, which is the point: if these protections were weakened to make the
# read-back work, this test would still pass and the ones in
# test_commit_guard.py would not.

class Tone:
    """PCM that the detector accepts as somebody speaking.

    An 800 Hz tone crosses zero about a tenth of the time, which sits inside
    the speech band — a hum crosses too rarely and a click too often. The
    amplitude alternates frame by frame so the utterance MODULATES; a steady
    level is what a fan looks like and is rejected on purpose.
    """

    RATE = 16000
    FRAME = 512          # 32 ms, the detector's own frame

    @classmethod
    def _frame(cls, amplitude: int, phase: int) -> bytes:
        import math
        import struct

        return struct.pack(
            f"<{cls.FRAME}h",
            *(int(amplitude * math.sin(2 * math.pi * 800 * (phase + i) / cls.RATE))
              for i in range(cls.FRAME)),
        )

    @classmethod
    def _run(cls, frames: int, amplitudes: tuple[int, ...]) -> bytes:
        out = bytearray()
        for i in range(frames):
            out += cls._frame(amplitudes[i % len(amplitudes)], i * cls.FRAME)
        return bytes(out)

    @classmethod
    def room(cls, ms: int) -> bytes:
        """A quiet room. Not digital silence — a real one never is."""
        return cls._run(ms // 32, (18,))

    @classmethod
    def speech(cls, ms: int) -> bytes:
        return cls._run(ms // 32, (9000, 3200, 7000, 4200))


@pytest.fixture
def transcribes(monkeypatch):
    """A transcription service that returns whatever the test set."""
    said = {"text": "12 Kumar Street", "confidence": 0.95}

    async def _transcribe(wav, language, settings):
        return said["text"], said["confidence"]

    monkeypatch.setattr(asr, "transcribe_with_confidence", _transcribe)
    return said


def speak(session: Session, audio: bytes, *, chunk: int = 4096) -> None:
    """Send audio the way a browser does: in buffers, not frames."""
    for start in range(0, len(audio), chunk):
        session.ws.send_bytes(audio[start:start + chunk])


class TestTheSpokenPathIsGatedToo:

    def test_a_spoken_answer_is_read_back_before_it_is_used(
            self, dictation_available, transcribes):
        workflow = Recording()
        with talking(workflow) as session:
            # Let the detector measure the room first, exactly as it does on
            # a real session: nothing said during calibration is heard.
            speak(session, Tone.room(320))
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.WAITING_CONFIRMATION)

        cards = [m for m in session.seen if m.get("type") == "voice.answer"]
        assert cards and cards[-1]["answer"] == "12 Kumar Street"
        assert workflow.invoked == [], "a spoken answer was saved unconfirmed"

    def test_and_the_audio_really_went_through_the_detector(
            self, dictation_available, transcribes):
        """Proof that the gates above ran rather than being bypassed: the
        detector reported the citizen speaking, and the transcript settled."""
        with talking(Recording()) as session:
            speak(session, Tone.room(320))
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.WAITING_CONFIRMATION)

        assert Phase.USER_SPEAKING.value in session.phases(), session.phases()
        assert [m for m in session.seen if m.get("type") == "stt.final"]

    def test_saying_yes_out_loud_is_what_saves_it(
            self, dictation_available, transcribes):
        workflow = Recording()
        with talking(workflow) as session:
            speak(session, Tone.room(320))
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.WAITING_CONFIRMATION)

            transcribes["text"] = "yes"
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.LISTENING)

        assert workflow.invoked == ["12 Kumar Street"]

    def test_and_saying_no_out_loud_throws_it_away(
            self, dictation_available, transcribes):
        workflow = Recording()
        with talking(workflow) as session:
            speak(session, Tone.room(320))
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.WAITING_CONFIRMATION)

            transcribes["text"] = "no"
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.LISTENING)

        cards = [m for m in session.seen if m.get("type") == "voice.answer"]
        assert cards[-1]["awaiting"] is False
        assert workflow.invoked == []

    def test_the_same_answer_can_be_repeated_after_a_refusal(
            self, dictation_available, transcribes):
        """Duplicate protection must not trap a citizen who was just asked to
        say it again. This is the whole reason the guard learnt to forget."""
        workflow = Recording()
        with talking(workflow) as session:
            speak(session, Tone.room(320))
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.WAITING_CONFIRMATION)

            transcribes["text"] = "no"
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.LISTENING)

            # The very same words, on purpose.
            transcribes["text"] = "12 Kumar Street"
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.WAITING_CONFIRMATION)

        cards = [m for m in session.seen if m.get("type") == "voice.answer"]
        assert cards[-1]["awaiting"] is True, "the repetition was discarded"
        assert cards[-1]["answer"] == "12 Kumar Street"


class TestOneSessionWhicheverWayTheCitizenAnswers:
    """Name by voice, address by keyboard, grievance by voice again — and
    one petition at the end of it. The two paths share `handle_settled`, so
    the only thing that differs between them is where the characters came
    from."""

    def test_a_spoken_answer_and_a_typed_one_land_in_the_same_session(
            self, dictation_available, transcribes):
        workflow = Recording()
        with talking(workflow) as session:
            # Spoken.
            speak(session, Tone.room(320))
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.WAITING_CONFIRMATION)
            session.send({"type": "answer.confirm"}, expect="state")

            # Typed, on the same socket, for the next question.
            session.says("45 Gandhi Street")
            session.send({"type": "text", "text": "yes"}, expect="state")

        assert workflow.invoked == ["12 Kumar Street", "45 Gandhi Street"]

    def test_a_spoken_answer_can_be_confirmed_by_typing(
            self, dictation_available, transcribes):
        """Someone whose microphone stops being heard mid-answer must be able
        to finish with the keyboard rather than start the field again."""
        workflow = Recording()
        with talking(workflow) as session:
            speak(session, Tone.room(320))
            speak(session, Tone.speech(1280))
            speak(session, Tone.room(960))
            session.settle(Phase.WAITING_CONFIRMATION)
            session.send({"type": "text", "text": "yes that's right"}, expect="state")

        assert workflow.invoked == ["12 Kumar Street"]


class TestReadingThePetitionAloudCanStillBeStopped:
    """The assistant says "say stop at any time" before it starts reading.
    The half-duplex gate would silently withdraw that invitation — the
    microphone is shut for the several minutes the reading takes — so the
    read-aloud is the one place it stays open."""

    @staticmethod
    def _ready_workflow():
        class Ready(Recording):
            def _state(self) -> dict:
                return {"language": "en", "status": "ready", "confirmed": True,
                        "fields": dict(FIELDS),
                        "letter_text": "From,\n    Ravi Kumar\n\n"
                                       "To,\n    The District Collector\n\n"
                                       "Respected Sir / Madam,\n\n"
                                       "Subject: Water supply\n\n"
                                       "   The water has not come for five days.\n\n"
                                       "Thanking you,\n\nYours faithfully,\n\nRavi Kumar"}
        return Ready()

    def test_the_gate_lets_speech_through_while_it_reads(self):
        """Asserted on the source, because what is under test is a condition
        rather than an outcome: the gate has to name the reading explicitly,
        or the invitation is withdrawn without anything failing."""
        import pathlib

        socket = pathlib.Path("app/api/ws.py").read_text(encoding="utf-8")
        gate = socket[socket.index("if (settings.voice_half_duplex"):]
        gate = gate[:gate.index("return")]

        assert "not reading_aloud" in gate, gate

    def test_stop_is_acted_on(self, dictation_available, spoken):
        """The behavioural half. The assistant acknowledges out loud that it
        has stopped, which is the only signal the citizen gets."""
        workflow = self._ready_workflow()
        with talking(workflow) as session:
            session.ws.send_json({"type": "text", "text": "read it to me"})
            session._drain(expect="tts.start")
            session.ws.send_json({"type": "text", "text": "stop"})
            for _ in range(40):
                message = session._next()
                if (message.get("type") == "tts.start"
                        and "Stopped" in (message.get("text") or "")):
                    break
            else:  # pragma: no cover
                raise AssertionError(f"never stopped: {session.spoken_lines()}")

        assert workflow.invoked == [], "a reading command reached the workflow"

    def test_nothing_else_heard_during_the_reading_reaches_the_petition(
            self, dictation_available):
        """The assistant reciting the citizen's own grievance must not come
        back in as a request to revise the petition with it."""
        import pathlib

        socket = pathlib.Path("app/api/ws.py").read_text(encoding="utf-8")
        body = socket[socket.index("if await handle_finished_command(decision.text):"):]
        body = body[:body.index('await handle_settled(decision.text, via="voice")')]

        assert "if reading_aloud:" in body
        assert "during_reading" in body
