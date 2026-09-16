"""Turn-taking for a live voice conversation.

    frames in -> VAD -> speech/silence -> end-of-speech -> one utterance out

This module decides WHEN the citizen has finished speaking. It decides nothing
about what they said, what is asked next, or whether a value is acceptable —
all of that stays in the graph, exactly where it is for a typed conversation.
The voice path and the typed path reach `workflow.invoke` through the same
door, and this module's only job is to work out when to knock.

Two pieces:

`VoiceActivityDetector` turns a stream of PCM frames into speech/silence, with
a calibrated noise floor so a fan or a room full of people does not read as
speech, and a hangover so an ordinary pause inside a sentence does not end the
turn.

`EndOfSpeech` turns speech/silence into exactly one utterance. The hard part is
not the timer, it is making sure a timer that has already been superseded
cannot still fire — a superseded timer commits the same words twice, and on
this form that means asking the citizen for their address twice, or worse,
submitting two petitions. The generation counter below is taken from Rapida's
silence-based end-of-speech design; see docs/voice-integration-decision.md.
"""

from __future__ import annotations

import array
import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .commit_guard import SpeechEvidence

log = logging.getLogger(__name__)


class Speech(StrEnum):
    """What the last frame was."""

    SILENCE = "silence"
    STARTED = "started"      # the first frame of an utterance
    CONTINUING = "continuing"
    ENDED = "ended"          # hangover expired; the utterance is over


@dataclass
class VadSettings:
    sample_rate: int = 16000
    frame_ms: int = 32
    # How far above the measured noise floor a frame must be to count as
    # speech. A ratio rather than an absolute level, because a laptop
    # microphone in an office and a headset in a hall do not share a scale.
    threshold: float = 3.2
    # A floor under the floor. Below this a frame is silence whatever the
    # ratio says, so a perfectly quiet room does not make its own hiss
    # significant by comparison.
    floor_rms: float = 140.0
    # Speech must last this long before the turn is considered started.
    #
    # 120 ms was too short and is why a keyboard click became "Okay": a click
    # is loud for about 150 ms, which cleared the old threshold, and what came
    # back from transcribing 150 ms of click was a filler word. A spoken
    # syllable is around 200 ms and no useful answer is shorter than two of
    # them.
    onset_ms: int = 280
    # A frame has to LOOK like speech, not merely be loud. Below `zcr_min` is a
    # fan, a hum or a hard disk; above `zcr_max` is a click, a scrape or a pop.
    # Speech lives between, and a real utterance visits both ends of the range.
    zcr_min: float = 0.02
    zcr_max: float = 0.42
    # And silence must last this long before it is considered finished. Long
    # enough to think mid-sentence, short enough not to feel like waiting.
    hangover_ms: int = 700
    # Listen to the room before judging it. Nothing is reported as speech
    # during this window; the floor is seeded from the QUIETEST frame in it,
    # so a citizen who is already talking when the session opens does not
    # teach the detector that speech is background.
    calibration_ms: int = 256


class VoiceActivityDetector:
    """Speech or silence, frame by frame, with an adapting noise floor."""

    def __init__(self, settings: VadSettings | None = None) -> None:
        self.s = settings or VadSettings()
        self.frame_bytes = int(self.s.sample_rate * self.s.frame_ms / 1000) * 2
        self._buffer = bytearray()
        self._noise = self.s.floor_rms
        self._seed: float | None = None
        self._calibrated_ms = 0
        self._speech_ms = 0
        self._silence_ms = 0
        self._in_speech = False
        self.last_rms = 0.0
        self.last_zcr = 0.0
        # (level, zcr, speechlike) for the frames of the current utterance, so
        # the commit guard can be told what was actually measured rather than
        # having to trust that something was.
        self._evidence_frames: list[tuple[float, float, bool]] = []

    @staticmethod
    def rms(frame: bytes) -> float:
        """Root-mean-square level of one 16-bit little-endian mono frame."""
        if len(frame) < 2:
            return 0.0
        samples = array.array("h")
        samples.frombytes(frame[: len(frame) // 2 * 2])
        if not samples:
            return 0.0
        total = 0
        for value in samples:
            total += value * value
        return math.sqrt(total / len(samples))

    @staticmethod
    def zero_crossing_rate(frame: bytes) -> float:
        """How often the waveform crosses zero, as a fraction of samples.

        This is what separates speech from the two things that were being
        mistaken for it. A fan or an air conditioner is low-frequency and
        crosses rarely — under about 0.02. A keyboard click, a chair scrape or
        a microphone pop is broadband noise and crosses constantly — over about
        0.45. Speech sits between: voiced vowels are low, fricatives are high,
        and a real utterance contains both.

        Cheap to compute, no model, and it costs a fan nothing to be quiet.
        """
        if len(frame) < 4:
            return 0.0
        samples = array.array("h")
        samples.frombytes(frame[: len(frame) // 2 * 2])
        if len(samples) < 2:
            return 0.0
        crossings = 0
        previous = samples[0]
        for value in samples[1:]:
            if (value >= 0) != (previous >= 0):
                crossings += 1
            previous = value
        return crossings / (len(samples) - 1)

    def feed(self, pcm: bytes) -> list[Speech]:
        """Add audio, get one verdict per whole frame it completed."""
        self._buffer.extend(pcm)
        out: list[Speech] = []
        while len(self._buffer) >= self.frame_bytes:
            frame = bytes(self._buffer[: self.frame_bytes])
            del self._buffer[: self.frame_bytes]
            out.append(self._classify(frame))
        return out

    def _classify(self, frame: bytes) -> Speech:
        level = self.rms(frame)
        self.last_rms = level
        ms = self.s.frame_ms

        # Calibration. A fixed starting guess cannot work for both a quiet
        # office and a hall with a fan: start too low and every frame in the
        # hall is speech, so the citizen is never heard; start too high and
        # nothing in the office is. So the room is measured first, and the
        # quietest frame of it is the seed — the minimum survives a citizen who
        # starts talking during calibration, where an average would not.
        if self._calibrated_ms < self.s.calibration_ms:
            self._calibrated_ms += ms
            self._seed = level if self._seed is None else min(self._seed, level)
            if self._calibrated_ms >= self.s.calibration_ms:
                self._noise = max(self._seed or self.s.floor_rms, 1.0)
            return Speech.SILENCE

        loud = level > max(self._noise * self.s.threshold, self.s.floor_rms)

        # Loud is not the same as spoken. A fan clears a level threshold and
        # crosses zero almost never; a keyboard click clears it and crosses
        # constantly. Requiring both tests is what stopped either becoming a
        # sentence on a petition.
        zcr = self.zero_crossing_rate(frame)
        self.last_zcr = zcr
        speechlike = loud and self.s.zcr_min <= zcr <= self.s.zcr_max

        # The floor tracks the LOWER envelope of the room: it follows a room
        # that goes quiet quickly, and a room that gets louder only slowly.
        # Asymmetry is the point — moving up as fast as it moves down would let
        # a long spoken answer raise the floor until the speaker is inaudible.
        if not self._in_speech:
            weight = 0.15 if level < self._noise else 0.005
            self._noise = (1 - weight) * self._noise + weight * max(level, 1.0)

        if self._in_speech or speechlike:
            self._evidence_frames.append((level, zcr, speechlike))

        loud = speechlike

        if loud:
            self._speech_ms += ms
            self._silence_ms = 0
            if not self._in_speech and self._speech_ms >= self.s.onset_ms:
                self._in_speech = True
                return Speech.STARTED
            return Speech.CONTINUING if self._in_speech else Speech.SILENCE

        self._speech_ms = 0
        if self._in_speech:
            self._silence_ms += ms
            if self._silence_ms >= self.s.hangover_ms:
                self._in_speech = False
                self._silence_ms = 0
                return Speech.ENDED
            # Still inside the utterance: a pause, not an ending.
            return Speech.CONTINUING
        return Speech.SILENCE

    @property
    def speaking(self) -> bool:
        return self._in_speech

    @property
    def noise_floor(self) -> float:
        return self._noise

    @property
    def speech_threshold(self) -> float:
        return max(self._noise * self.s.threshold, self.s.floor_rms)

    def evidence(self, frame_ms: int | None = None) -> SpeechEvidence:
        """What was measured during the utterance that just ended.

        Handed to the commit guard so the decision rests on the audio rather
        than on the transcription service having produced characters.
        """
        from .commit_guard import SpeechEvidence

        ms = frame_ms or self.s.frame_ms
        frames = self._evidence_frames
        if not frames:
            return SpeechEvidence()

        voiced = [f for f in frames if f[2]]
        levels = [f[0] for f in frames]
        mean = sum(levels) / len(levels)
        # Coefficient of variation. Speech swings between syllables and
        # silences; a fan holds one level, and that is the difference the
        # number captures.
        spread = math.sqrt(sum((x - mean) ** 2 for x in levels) / len(levels))
        return SpeechEvidence(
            voiced_ms=len(voiced) * ms,
            total_ms=len(frames) * ms,
            peak_snr=(max(levels) / self._noise) if self._noise > 0 else 0.0,
            modulation=(spread / mean) if mean > 0 else 0.0,
        )

    def clear_evidence(self) -> None:
        self._evidence_frames.clear()

    def reset(self) -> None:
        """Forget the current utterance, keep what was learnt about the room."""
        self._buffer.clear()
        self._speech_ms = 0
        self._silence_ms = 0
        self._in_speech = False
        self._evidence_frames.clear()


# --------------------------------------------------------------------------- #
# End of speech
# --------------------------------------------------------------------------- #


@dataclass
class Utterance:
    """One settled thing the citizen said."""

    turn: int
    audio: bytes
    started_at: float
    ended_at: float
    seconds: float


@dataclass
class EndOfSpeech:
    """Collects audio for one utterance and hands it over exactly once.

    The generation counter is the whole point. Under a live stream the silence
    timer is reset many times a second, and without it a timer scheduled three
    resets ago can still fire — committing the same words a second time. On a
    petition that is not a cosmetic bug: it answers the next question with the
    previous answer, or submits the form twice.
    """

    on_utterance: Callable[[Utterance], Awaitable[None]]
    max_seconds: float = 45.0
    min_seconds: float = 0.25
    sample_rate: int = 16000

    _chunks: list[bytes] = field(default_factory=list)
    _generation: int = 0
    _turn: int = 0
    _open: bool = False
    _started_at: float = 0.0
    _delivered: set[int] = field(default_factory=set)
    _task: asyncio.Task | None = None

    def begin(self) -> int:
        """A new utterance starts; anything pending from the last one is void."""
        self._generation += 1
        self._chunks.clear()
        self._open = True
        self._started_at = time.monotonic()
        self._cancel_pending()
        return self._generation

    def add(self, pcm: bytes) -> None:
        if self._open:
            self._chunks.append(pcm)

    @property
    def open(self) -> bool:
        return self._open

    @property
    def seconds(self) -> float:
        return time.monotonic() - self._started_at if self._open else 0.0

    def _cancel_pending(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    async def finish(self) -> Utterance | None:
        """Close the utterance and deliver it, at most once per generation."""
        if not self._open:
            return None
        generation = self._generation
        self._open = False
        audio = b"".join(self._chunks)
        self._chunks.clear()
        ended = time.monotonic()

        # Superseded while we were closing: a newer utterance has already begun
        # and this one is no longer the live one.
        if generation != self._generation:
            log.debug("eos.superseded", extra={"generation": generation})
            return None
        if generation in self._delivered:
            log.debug("eos.duplicate_suppressed", extra={"generation": generation})
            return None

        # Measured in audio, not in wall-clock. The two are the same while a
        # citizen speaks in real time and are not the same anywhere else — a
        # reconnect that replays a buffer, a test, a slow frame delivered in a
        # burst. Wall-clock threw real utterances away as misclicks.
        seconds = len(audio) / (self.sample_rate * 2)
        if seconds < self.min_seconds or len(audio) < 2:
            return None

        self._delivered.add(generation)
        self._turn += 1
        utterance = Utterance(turn=self._turn, audio=audio,
                              started_at=self._started_at, ended_at=ended,
                              seconds=seconds)
        await self.on_utterance(utterance)
        return utterance

    def abandon(self) -> None:
        """Throw the current utterance away without delivering it.

        Used when the citizen ends the session, or when a turn is cancelled:
        audio that was being collected must not arrive later as an answer to a
        question that has moved on.
        """
        self._open = False
        self._chunks.clear()
        self._generation += 1
        self._cancel_pending()

    def reset(self) -> None:
        self.abandon()
        self._delivered.clear()
        self._turn = 0
