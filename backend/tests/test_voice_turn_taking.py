"""The assistant finishes speaking before the microphone counts for anything.

THE FAILURE THIS PREVENTS. The microphone is open during playback so that a
citizen can interrupt. On a counter PC with speakers a foot from the
microphone, what it hears is the assistant. Sarvam transcribes that perfectly
well — it is clean, close-miked speech — and the result is a fabricated
answer in a citizen's petition: the assistant asks "is that correct?" about a
sentence it said itself, and a confirmation is a confirmation.

Echo rejection catches most of it. Most is not enough for a document somebody
signs, so the default is sequential: the assistant speaks, the assistant
stops, then the microphone counts. `voice_half_duplex=false` gives
interruption back to a deployment using headsets, and the last test here
proves that switch still works.

THE CONTROL that makes these tests mean something is
`test_the_same_audio_is_heard_once_the_assistant_has_stopped`. Without it,
"no turn was created" would be equally satisfied by audio that never worked
at all.
"""

from __future__ import annotations

import contextlib
import json
import math
import struct
import uuid

import anyio
import pytest
from fastapi.testclient import TestClient

from app.api.ws import Phase, wav_byte_rate
from app.config import get_settings
from app.main import app
from app.services import asr, tts

RATE = 16000
FRAME = 512


def pcm(ms: int, amplitudes: tuple[int, ...]) -> bytes:
    """Audio the detector accepts as speech: 800 Hz, and modulated.

    A hum crosses zero too rarely and a click too often; 800 Hz sits inside
    the speech band. The amplitude changes frame to frame because a steady
    level is what a fan looks like and is rejected on purpose.
    """
    out = bytearray()
    for i in range(ms // 32):
        amp = amplitudes[i % len(amplitudes)]
        out += struct.pack(
            f"<{FRAME}h",
            *(int(amp * math.sin(2 * math.pi * 800 * (i * FRAME + n) / RATE))
              for n in range(FRAME)))
    return bytes(out)


def room(ms: int) -> bytes:
    return pcm(ms, (18,))


def speech(ms: int) -> bytes:
    return pcm(ms, (9000, 3200, 7000, 4200))


def wav(seconds: float) -> bytes:
    """A real WAV, so its length can be read from its own header."""
    return asr._wav(b"\x00\x00" * int(RATE * seconds), RATE)


class Asking:
    """A workflow with a question outstanding, so the assistant speaks."""

    def __init__(self) -> None:
        self.invoked: list[str] = []

    def _state(self) -> dict:
        return {"language": "en", "status": "collecting", "fields": {},
                "reply": "Please tell me your name."}

    async def snapshot(self, session_id: str) -> dict:
        return self._state()

    async def peek(self, session_id: str) -> dict:
        return self._state()

    async def invoke(self, session_id: str, payload: dict) -> dict:
        self.invoked.append(payload["utterance"])
        return self._state()


@pytest.fixture
def dictation_available(monkeypatch):
    monkeypatch.setattr(asr, "status", lambda settings=None: {"ok": True, "provider": "test"})


@pytest.fixture
def transcribes(monkeypatch):
    """A transcription service that always succeeds.

    Deliberately unconditional: if any audio reaches it during playback, a
    turn WILL be created. That is what makes "no turn was created" evidence
    that the audio never got that far, rather than evidence that the
    transcriber happened to decline it.
    """
    heard = {"text": "Harish Kumar", "calls": 0}

    async def _transcribe(data, language, settings):
        heard["calls"] += 1
        # A DIFFERENT sentence every time. A stub that repeated itself was
        # rejected by duplicate protection on the second utterance — working
        # exactly as intended, and hiding the endpointing behaviour a test
        # two utterances long is trying to measure. Duplicate protection has
        # its own tests in test_commit_guard.py.
        return f"{heard['text']} {heard['calls']}", 0.95

    monkeypatch.setattr(asr, "transcribe_with_confidence", _transcribe)
    return heard


@pytest.fixture
def speaks(monkeypatch):
    """A voice whose clip is a real, measurable second and a half."""
    clip = wav(1.5)

    async def _stream(text, language, settings):
        yield clip

    monkeypatch.setattr(tts, "configured", lambda settings=None: True)
    monkeypatch.setattr(tts, "stream", _stream)
    return clip


class Session:
    DEADLINE_S = 20.0

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

    def drain(self, expect: str, *, cap: int = 60) -> dict:
        for _ in range(cap):
            message = self._next()
            if message.get("type") == expect:
                return message
        raise AssertionError(f"no {expect!r}; got {self.kinds()}")

    def settle(self, phase: Phase, *, cap: int = 60) -> None:
        for _ in range(cap):
            message = self._next()
            if message.get("type") == "voice.state" and message["state"] == phase.value:
                return
        raise AssertionError(f"never reached {phase.value}; saw {self.phases()}")

    def speak(self, audio: bytes, *, chunk: int = 4096) -> None:
        for start in range(0, len(audio), chunk):
            self.ws.send_bytes(audio[start:start + chunk])

    def kinds(self) -> list[str]:
        return [m.get("type") for m in self.seen]

    def phases(self) -> list[str]:
        return [m["state"] for m in self.seen if m.get("type") == "voice.state"]


@contextlib.contextmanager
def talking(workflow, *, reports_playback: bool = False, **overrides):
    """One live voice socket, with any settings overridden AFTER startup.

    After, not before, and that is not a detail. The application's own
    startup calls `provider_store.apply()`, which ends with
    `get_settings.cache_clear()` — so the settings object a test patched
    before connecting is thrown away and rebuilt from the environment, and
    the test runs against the defaults while reporting that it patched them.
    A test that silently does not test what it says is worse than no test.
    """
    with TestClient(app) as client:
        previous = getattr(app.state, "workflow", None)
        app.state.workflow = workflow
        settings = get_settings()
        restore = {name: getattr(settings, name) for name in overrides}
        for name, value in overrides.items():
            setattr(settings, name, value)
        try:
            with client.websocket_connect(f"/ws/voice/{uuid.uuid4()}") as ws:
                session = Session(ws)
                ws.send_json({"type": "voice.start",
                              "reports_playback": reports_playback})
                yield session
        finally:
            for name, value in restore.items():
                setattr(settings, name, value)
            app.state.workflow = previous


# ---------------------------------------------------------------------------

class TestTheAssistantIsNotHeardByItself:

    def test_speech_during_playback_creates_no_turn(
            self, dictation_available, transcribes, speaks):
        """The whole point. What the microphone picks up while the assistant
        is talking is the assistant."""
        workflow = Asking()
        with talking(workflow) as session:
            session.drain("tts.start")
            # The speaker, coming back in through the microphone.
            #
            # The trailing silence is LONGER than the detector's hangover on
            # purpose. With 320 ms of it the utterance never settles and no
            # turn is created whatever the gate does — so the test passed
            # with the gate deleted, which is a test that proves nothing.
            session.speak(room(320))
            session.speak(speech(1280))
            session.speak(room(960))
            session.settle(Phase.LISTENING)

        assert "stt.final" not in session.kinds(), session.kinds()
        assert transcribes["calls"] == 0, "the assistant's own voice was transcribed"
        assert workflow.invoked == [], "a fabricated answer reached the petition"

    def test_the_same_audio_is_heard_once_the_assistant_has_stopped(
            self, dictation_available, transcribes, speaks):
        """The control. Without this, the test above would pass just as well
        if the audio were incapable of producing a turn at all."""
        workflow = Asking()
        with talking(workflow) as session:
            session.drain("tts.start")
            session.settle(Phase.LISTENING)
            session.speak(room(320))
            session.speak(speech(1280))
            session.speak(room(960))
            session.drain("stt.final")

        assert transcribes["calls"] == 1
        assert session.kinds().count("stt.final") == 1, "one utterance, one turn"

    def test_listening_is_not_announced_until_the_audio_has_finished(
            self, dictation_available, transcribes, speaks):
        """A page that says "Listening" while the speaker is still talking is
        inviting the citizen to speak over the question."""
        workflow = Asking()
        with talking(workflow) as session:
            session.drain("tts.end")
            before = session.phases()

        assert Phase.LISTENING.value not in before[1:], before


class TestThePageReportsTheRealEnd:

    def test_the_microphone_waits_for_the_pages_own_event(
            self, dictation_available, transcribes, speaks):
        """Not a timer. The server holds until the page says the speaker has
        gone quiet, because only the page knows."""
        workflow = Asking()
        with talking(workflow, reports_playback=True) as session:
            end = session.drain("tts.end")
            # Nothing has been reported yet, so nothing may open.
            assert Phase.LISTENING.value not in session.phases()[1:]
            session.ws.send_json({"type": "tts.played", "id": end["id"]})
            session.settle(Phase.LISTENING)

        assert session.phases()[-1] == Phase.LISTENING.value

    def test_a_report_for_an_older_reply_does_not_open_it_early(
            self, dictation_available, transcribes, speaks):
        """A stale report is a message that overtook an interruption. Acting
        on it would open the microphone into the middle of a sentence."""
        workflow = Asking()
        with talking(workflow, reports_playback=True) as session:
            end = session.drain("tts.end")
            session.ws.send_json({"type": "tts.played", "id": end["id"] + 99})
            assert Phase.LISTENING.value not in session.phases()[1:]
            session.ws.send_json({"type": "tts.played", "id": end["id"]})
            session.settle(Phase.LISTENING)

    def test_the_end_carries_an_id_to_answer(self, dictation_available, speaks):
        workflow = Asking()
        with talking(workflow) as session:
            end = session.drain("tts.end")

        assert isinstance(end.get("id"), int) and end["id"] > 0


class TestTheDurationIsMeasuredNotGuessed:

    def test_the_clip_reports_its_own_length(self, speaks):
        """The backstop for a page that cannot report is the REAL length of
        the audio, read from its header — not a fixed guess that is too short
        for a long sentence and too long for a short one."""
        rate = wav_byte_rate(speaks)

        assert rate == RATE * 2, rate
        assert abs(len(speaks) / rate - 1.5) < 0.05

    def test_something_that_is_not_a_wav_is_reported_as_unknown(self):
        assert wav_byte_rate(b"not audio") == 0
        assert wav_byte_rate(b"") == 0


class TestBargeInIsStillThereForThoseWhoWantIt:

    def test_turning_half_duplex_off_lets_the_citizen_interrupt(
            self, dictation_available, transcribes, speaks):
        """A deployment with headsets has no echo path and can have
        interruption back. The switch is what makes the default a choice
        rather than a limitation."""
        workflow = Asking()
        with talking(workflow, voice_half_duplex=False) as session:
            session.drain("tts.start")
            session.speak(room(320))
            session.speak(speech(1280))
            session.speak(room(960))
            session.drain("voice.interrupted")

        assert transcribes["calls"] >= 1, "nothing was heard over the assistant"


class AtGrievance(Asking):
    """Parked on the narrative field, so long-form endpointing applies."""

    def _state(self) -> dict:
        return {"language": "en", "status": "collecting",
                "fields": {"applicant_name": "Ravi Kumar", "age": 45,
                           "mobile": "9344174752",
                           "address": "12 Gandhi Street, Coimbatore",
                           "aadhaar": "234567890124"},
                "reply": "Now please tell me your grievance."}


class Quiet(Asking):
    """A short field whose turns produce no spoken reply.

    Needed for the control below: any reply would be spoken, and the
    half-duplex gate would then discard the second utterance for the right
    reason, hiding the endpointing difference the control exists to show.
    """

    def _state(self) -> dict:
        return {"language": "en", "status": "collecting", "fields": {}, "reply": ""}


class TestAThinkingPauseIsNotAnEnding:
    """Measured in audio frames, not wall-clock, so these are exact rather
    than timing-dependent.

    The pause tolerance is the ONLY thing long dictation changes about the
    detector. Every test that decides whether a sound was speech at all — the
    fan, the keyboard click, the modulation floor — is untouched and lives
    next door in test_commit_guard.py.

    800 ms is the number that matters: longer than a name's tolerance, well
    inside a grievance's. The two tests below feed exactly the same audio and
    get different answers, which is the whole point.
    """

    AUDIO = [room(320), speech(1280), room(800), speech(1280), room(1600)]

    def test_a_grievance_survives_an_eight_hundred_millisecond_pause(
            self, dictation_available, transcribes, speaks):
        workflow = AtGrievance()
        with talking(workflow, voice_long_silence_ms=1200) as session:
            session.drain("tts.start")
            # Its OWN state, not LISTENING: "Listening" over a two-minute
            # narration reads as waiting for them to finish a sentence.
            session.settle(Phase.LONG_LISTENING)
            for piece in self.AUDIO:
                session.speak(piece)
            session.drain("voice.dictation")

        assert session.kinds().count("stt.final") == 1, (
            "the pause split the sentence in two")

    def test_the_same_pause_ends_a_short_answer(
            self, dictation_available, transcribes, speaks):
        """The control. Without it, "one utterance" above would be equally
        satisfied by audio that only ever produced one."""
        workflow = Quiet()
        with talking(workflow, voice_read_back=False) as session:
            session.settle(Phase.LISTENING)
            for piece in self.AUDIO:
                session.speak(piece)
            session.drain("stt.final")
            session.drain("stt.final")

        assert session.kinds().count("stt.final") == 2, session.kinds()


class TestTheStatesTheCitizenIsShown:
    """The page's states come from the server's, so a state the server can
    reach and the page cannot name shows an empty status line."""

    def test_a_grievance_rests_in_its_own_state(
            self, dictation_available, transcribes, speaks):
        workflow = AtGrievance()
        with talking(workflow) as session:
            session.drain("tts.start")
            session.settle(Phase.LONG_LISTENING)

        assert session.phases()[-1] == Phase.LONG_LISTENING.value

    def test_a_short_field_does_not(self, dictation_available, transcribes, speaks):
        """The control: the two are genuinely different, not the same state
        with two names."""
        workflow = Asking()
        with talking(workflow) as session:
            session.drain("tts.start")
            session.settle(Phase.LISTENING)

        assert Phase.LONG_LISTENING.value not in session.phases()
