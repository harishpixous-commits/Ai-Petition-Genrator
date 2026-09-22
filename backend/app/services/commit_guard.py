"""Whether a transcript is allowed to become an answer on a petition.

The rule this module enforces is the one that was missing, and the reason
"Okay" and "Thirty" appeared on a form nobody had spoken to:

    A SPEECH SERVICE RETURNING TEXT IS NOT EVIDENCE THAT ANYONE SPOKE.

Measured against the providers this deployment uses, with no speech at all:

    input                 Sarvam (ta-IN)        Groq Whisper
    digital silence       ""                    "நான் பார்த்துக்கொள்ளுங்கள்."
    quiet room tone       "சரி சார்."           "சரி."
    fan / AC hum          "ஆ சரி சரி"           "சரி."
    keyboard click        "சரி"                 "செல்லுங்கள்!"

and in auto-detect mode a keyboard click came back as the English word "Okay"
with a language confidence of 0.765. These are not bugs in the providers.
Transcription models are trained to produce the most likely words for an audio
segment, and for an audio segment containing no words the most likely words are
whatever is most common in the training data. Asking them not to do it is not
an option available to us.

So the audio is gated before it is sent — see `voice.py`, which requires
sustained, modulated, speech-shaped sound — and the text is gated after it
comes back, here. Both gates are needed. The first stops most of it. The second
catches what the first lets through, because a fan does sometimes produce two
hundred milliseconds that look like speech, and what comes back from that is
always one of a small set of filler words.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

from ..domain.phrasing import Language

log = logging.getLogger(__name__)

TAMIL = re.compile(r"[஀-௿]")
LATIN = re.compile(r"[A-Za-z]")


class Verdict(StrEnum):
    """Why a transcript was or was not committed. Recorded as a metric."""

    COMMIT = "commit"
    EMPTY = "empty"
    NO_SPEECH_EVIDENCE = "no_speech_evidence"
    TOO_SHORT = "too_short"
    FILLER_ONLY = "filler_only"
    WRONG_SCRIPT = "wrong_script"
    LOW_CONFIDENCE = "low_confidence"
    DUPLICATE = "duplicate"
    STALE = "stale"
    ECHO_SUSPECTED = "echo_suspected"


# What a transcription service says when it was given no speech.
#
# Every entry was OBSERVED coming back from silence, room tone, a fan or a
# keyboard click — not imagined. They are short, common acknowledgements, which
# is exactly what a language model falls back on when the audio carries no
# words. A citizen who really does answer "okay" to a question that wanted
# their name or age gets asked again, which is the right outcome anyway.
_HALLUCINATIONS = {
    # English
    "okay", "ok", "o k", "hello", "hi", "yeah", "yes", "thank you", "thanks",
    "bye", "you", "the", "uh", "um", "hmm", "mm", "so", "and",
    "thirty", "please", "right", "alright", "sorry", "what", "go",
    # Tamil, as observed
    "சரி", "சரி சார்", "ஆ சரி சரி", "ஆ", "ஆம்", "சரி சரி",
    "ம்", "ம்ம்", "ஹலோ", "வணக்கம்", "நன்றி", "செல்லுங்கள்",
    "நான் விரும்புகிறேன்", "நான் பார்த்துக்கொள்ளுங்கள்",
    "போ", "வாங்க", "என்ன",
}


# Words from that list which ARE the answer when the question was a yes or no.
#
# "Shall I prepare your petition?" — "yes". The list above is right that these
# come back from silence; it was wrong to treat them as never meaning anything,
# because at the confirmation step they are the only short answer there is. The
# audio still has to be genuine speech: what changes is whether the WORD is
# allowed to mean something, not whether noise can become a turn.
_CONFIRMATIONS = {
    "yes", "yeah", "yep", "ok", "okay", "o k", "right", "alright", "sure",
    "no", "nope",
    "\u0b86\u0bae\u0bcd", "\u0b86\u0bae", "\u0b9a\u0bb0\u0bbf", "\u0b86",
    "\u0b87\u0bb2\u0bcd\u0bb2\u0bc8", "\u0bb5\u0bc7\u0ba3\u0bcd\u0b9f\u0bbe\u0bae\u0bcd",
}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower()).strip(" .,!?।")


@dataclass
class SpeechEvidence:
    """What the detector actually measured, before anything was transcribed."""

    voiced_ms: int = 0          # frames that looked like speech, not just loud
    total_ms: int = 0
    peak_snr: float = 0.0       # loudest frame over the measured noise floor
    modulation: float = 0.0     # how much the level varied; steady noise is flat
    during_playback_ms: int = 0  # overlapped the assistant's own voice

    @property
    def voiced_ratio(self) -> float:
        return self.voiced_ms / self.total_ms if self.total_ms else 0.0

    @property
    def echo_ratio(self) -> float:
        return self.during_playback_ms / self.voiced_ms if self.voiced_ms else 0.0


@dataclass
class Decision:
    verdict: Verdict
    text: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict is Verdict.COMMIT


@dataclass
class SpeechCommitGuard:
    """Decides, once per utterance, whether it becomes a turn.

    Holds the small amount of state that duplicate and stale protection need,
    and nothing else. It knows nothing about fields, validation or the petition
    — a transcript it passes goes to the same workflow a typed answer goes to,
    and that workflow decides whether the words are an acceptable answer.
    """

    # An utterance shorter than this carries no answer worth having. A keyboard
    # click is about 150 ms; a spoken "yes" is around 400.
    min_voiced_ms: int = 320
    # Of the audio kept, this much has to have looked like speech. A fan that
    # crosses the threshold for a moment inside two seconds of hum does not.
    min_voiced_ratio: float = 0.35
    # Level variation. Speech rises and falls between syllables; a fan, a hum
    # and a hard disk do not.
    min_modulation: float = 0.12
    # Loudest frame, relative to the room. Quiet speech still clears this.
    min_peak_snr: float = 2.2
    # Evidence strong enough that an utterance does not also have to be long,
    # or to fill its window.
    #
    # Speech that pauses is still speech: a citizen who thinks before answering
    # produces a low voiced RATIO while the audio that is there is unmistakable.
    # Speech that is brief is still speech: "yes" is a quarter of a second.
    # What separates either from a room is the level variation between
    # syllables and a clear peak above the noise floor — never the proportion
    # of the window filled, and never the duration on its own.
    #
    # The numbers come from utterances this service actually threw away: they
    # ran from 0.66 to 1.52 modulation and 8 dB upwards. A fan is below 0.12.
    clear_modulation: float = 0.40
    clear_peak_snr: float = 6.0
    # The floor for an utterance that IS clearly speech.
    #
    # Measured, not guessed: the word "yes", spoken plainly and pushed through
    # this exact pipeline, is 224 ms of voiced audio at 33.8 dB. A floor of 240
    # rejected it — which is what "I said yes and nothing happened" was.
    #
    # Below this are clicks and knocks, at 128 to 192 ms in the same logs. And
    # the cost of being wrong in this direction is one wasted transcription:
    # a click sent to the service comes back with no words and is discarded as
    # empty. The cost of being wrong in the other direction is a citizen
    # talking to something that ignores them.
    brief_voiced_ms: int = 200
    # And briefer still when the question was a yes or no.
    #
    # Measured through the real pipeline: a plainly spoken "Yes." came out at
    # 192 ms of voiced audio at 78 dB and was thrown away for being eight
    # milliseconds short of the floor. The risk of going lower is bounded
    # here in a way it is not elsewhere: the transcript must ALSO be one of a
    # dozen confirmation words, so a knock that transcribes to nothing, or to
    # anything else, still does not answer.
    #
    # A single click is one frame of audio. Sustaining 160 ms of VOICED frames
    # takes a voice.
    confirmation_voiced_ms: int = 160
    # A short transcript needs more than the minimum evidence, because short
    # transcripts are what hallucinations look like.
    short_text_chars: int = 12
    short_text_voiced_ms: int = 600
    # Most of an utterance overlapping the assistant's own voice is the
    # microphone hearing the speaker, not a citizen interrupting.
    max_echo_ratio: float = 0.75

    _recent: list[str] = field(default_factory=list)
    _turn: int = 0

    def begin_turn(self) -> int:
        self._turn += 1
        return self._turn

    @property
    def turn(self) -> int:
        return self._turn

    def judge(
        self,
        text: str,
        evidence: SpeechEvidence,
        *,
        language: Language = "en",
        turn: int | None = None,
        confidence: float | None = None,
        min_confidence: float = 0.0,
        during_playback: bool = False,
        expecting_confirmation: bool = False,
    ) -> Decision:
        cleaned = str(text or "").strip()

        # A result that belongs to a turn the citizen has already moved past
        # must not answer the question they are on now.
        if turn is not None and turn != self._turn:
            return Decision(Verdict.STALE)

        if not cleaned:
            return Decision(Verdict.EMPTY)

        # Unmistakably somebody talking, whatever the shape of the window.
        clear = (evidence.modulation >= self.clear_modulation
                 and evidence.peak_snr >= self.clear_peak_snr)

        if clear and expecting_confirmation:
            floor = self.confirmation_voiced_ms
        elif clear:
            floor = self.brief_voiced_ms
        else:
            floor = self.min_voiced_ms
        if evidence.voiced_ms < floor:
            return Decision(Verdict.TOO_SHORT)

        # A room fails these outright, and no amount of anything else saves it.
        if (evidence.modulation < self.min_modulation
                or evidence.peak_snr < self.min_peak_snr):
            return Decision(Verdict.NO_SPEECH_EVIDENCE)

        # And a thinly-filled window is only evidence of nothing when the audio
        # in it is not evidence of something.
        if evidence.voiced_ratio < self.min_voiced_ratio and not clear:
            return Decision(Verdict.NO_SPEECH_EVIDENCE)

        if during_playback and evidence.echo_ratio > self.max_echo_ratio:
            return Decision(Verdict.ECHO_SUSPECTED)

        normalised = _normalise(cleaned)
        if expecting_confirmation and normalised in _CONFIRMATIONS:
            # The answer to the question that was actually asked. It has
            # already cleared every evidence test above, so this is a citizen
            # saying yes, not a service inventing one.
            return Decision(Verdict.COMMIT, cleaned)

        if normalised in _HALLUCINATIONS:
            # Said on its own, with nothing else in the utterance. The citizen
            # who genuinely answers "okay" is asked again, which is what should
            # happen when "okay" is not an answer to the question anyway.
            return Decision(Verdict.FILLER_ONLY)

        if len(normalised) < self.short_text_chars and \
                evidence.voiced_ms < self.short_text_voiced_ms and not clear:
            # Two seconds of sound that produced four characters did not
            # contain four characters' worth of speech.
            return Decision(Verdict.FILLER_ONLY)

        if not self._script_matches(cleaned, language):
            return Decision(Verdict.WRONG_SCRIPT)

        if confidence is not None and confidence < min_confidence:
            return Decision(Verdict.LOW_CONFIDENCE)

        # Duplicate protection is about CONTENT arriving twice. A reply to
        # "is that correct?" is not content, and every field now ends with
        # one: with per-answer read-back a citizen says "yes" after their
        # name and "yes" again after their address, and the second one was
        # dropped as a duplicate, leaving them confirming into silence.
        #
        # Nothing is weakened for answers. Stale-turn protection is separate
        # and still applies, and a confirmation cannot become a field value —
        # it is consumed by the read-back loop and never reaches the workflow.
        if not expecting_confirmation:
            digest = hashlib.sha1(normalised.encode("utf-8")).hexdigest()[:16]
            if digest in self._recent:
                return Decision(Verdict.DUPLICATE)
            self._recent.append(digest)
            del self._recent[:-6]

        return Decision(Verdict.COMMIT, cleaned)

    def forget(self, text: str) -> None:
        """Drop one transcript from the duplicate cache.

        Called when the citizen REJECTS an answer that was read back to them.
        They are about to say the same thing again on purpose, and refusing it
        as a duplicate would trap them: the assistant asks them to repeat it
        and then discards the repetition, silently, forever.

        This narrows duplicate protection to what it is for — the same
        transcript arriving twice without anyone intending it — rather than
        removing it.
        """
        digest = hashlib.sha1(
            _normalise(str(text or "")).encode("utf-8")).hexdigest()[:16]
        self._recent[:] = [d for d in self._recent if d != digest]

    @staticmethod
    def _script_matches(text: str, language: Language) -> bool:
        """The transcript has to be in the language the citizen chose.

        A Tamil session that produces "Okay", or the Bengali "আচ্ছা।" that a
        noise burst once produced on screen, is not a citizen switching
        language — it is a model guessing at audio with no words in it. Names
        and addresses in Latin script inside a Tamil session are ordinary and
        must still pass, so this only rejects a transcript with NO character of
        the expected script at all AND nothing that could be a name.
        """
        if language != "ta":
            # An English session accepts Latin, and accepts Tamil too: a
            # citizen answering in Tamil is answering, and the workflow keeps
            # their words verbatim either way.
            return bool(LATIN.search(text) or TAMIL.search(text) or
                        any(ch.isdigit() for ch in text))
        if TAMIL.search(text):
            return True
        # No Tamil at all. Allowed only if it is plausibly a name, an address
        # or a number said in English — not a bare filler word.
        return bool(any(ch.isdigit() for ch in text) or len(text.split()) >= 2)
