"""Nothing becomes an answer on a petition without evidence that it was said.

Every rejected string in this file was OBSERVED coming back from a speech
service given audio with no speech in it — silence, room tone, a fan, a
keyboard click. They are not invented examples. The providers are not
misbehaving either: a transcription model asked for the most likely words in a
segment containing no words returns the most likely words in its training data,
which are short acknowledgements.

Which means the only defensible place to stop this is here.
"""

from __future__ import annotations

import pytest

from app.services.commit_guard import SpeechCommitGuard, SpeechEvidence, Verdict


def spoken(ms: int = 1200, ratio: float = 0.8, modulation: float = 0.30,
           snr: float = 8.0, playback_ms: int = 0) -> SpeechEvidence:
    """What a real answer measures like."""
    return SpeechEvidence(voiced_ms=int(ms * ratio), total_ms=ms,
                          peak_snr=snr, modulation=modulation,
                          during_playback_ms=playback_ms)


def noise(ms: int = 2000, modulation: float = 0.03) -> SpeechEvidence:
    """A fan: long, loud, and completely flat."""
    return SpeechEvidence(voiced_ms=ms, total_ms=ms, peak_snr=10.0,
                          modulation=modulation)


def blip(ms: int = 150) -> SpeechEvidence:
    """A keyboard click."""
    return SpeechEvidence(voiced_ms=ms, total_ms=ms, peak_snr=12.0, modulation=0.4)


class TestSilenceNeverBecomesAnAnswer:
    """The bug as reported: 'Okay' and 'Thirty' appearing with nobody speaking."""

    @pytest.mark.parametrize("text", [
        "Okay", "okay", "OK", "Hello", "Thank you", "Thirty", "yeah", "you",
        "சரி", "சரி.", "சரி சார்.", "ஆ சரி சரி", "நன்றி", "வணக்கம்",
        "செல்லுங்கள்!", "நான் விரும்புகிறேன்.",
    ])
    def test_the_words_a_service_invents_from_nothing_are_refused(self, text):
        """Every one of these came back from silence, room tone, a fan or a
        click during the audit that led to this module."""
        guard = SpeechCommitGuard()
        assert guard.judge(text, spoken()).verdict is Verdict.FILLER_ONLY

    def test_a_keyboard_click_never_reaches_a_transcript_at_all(self):
        """150 ms is a click. The guard refuses it on the audio alone, before
        anything is sent anywhere — so it costs nothing and cannot come back."""
        guard = SpeechCommitGuard()
        assert guard.judge("Okay", blip()).verdict is Verdict.TOO_SHORT

    def test_a_fan_is_refused_however_long_it_runs(self):
        """Loud, sustained, and flat. Duration is not evidence of speech; a
        level that rises and falls between syllables is."""
        guard = SpeechCommitGuard()
        assert guard.judge("the street light", noise()).verdict is Verdict.NO_SPEECH_EVIDENCE

    def test_a_long_quiet_hiss_is_refused(self):
        guard = SpeechCommitGuard()
        weak = SpeechEvidence(voiced_ms=1500, total_ms=2000, peak_snr=1.4, modulation=0.3)
        assert guard.judge("something", weak).verdict is Verdict.NO_SPEECH_EVIDENCE

    def test_a_burst_inside_a_long_stretch_of_nothing_is_refused(self):
        guard = SpeechCommitGuard()
        sparse = SpeechEvidence(voiced_ms=400, total_ms=4000, peak_snr=9.0, modulation=0.3)
        assert guard.judge("okay then", sparse).verdict is Verdict.NO_SPEECH_EVIDENCE

    def test_an_empty_transcript_is_refused(self):
        guard = SpeechCommitGuard()
        assert guard.judge("", spoken()).verdict is Verdict.EMPTY
        assert guard.judge("   ", spoken()).verdict is Verdict.EMPTY


class TestRealSpeechStillGetsThrough:
    """The failure mode that would be worse than the bug: a form nobody can
    answer out loud."""

    @pytest.mark.parametrize("text", [
        "My name is Harish",
        "Twenty three",
        "80 by 33 Perumal Kovil Street, Theni",
        "என் வயது இருபத்து மூன்று",
        "தெருவிளக்கு மூன்று மாதமாக எரியவில்லை",
        "எனது பெயர் ஹரிஷ்",
    ])
    def test_an_answer_is_committed(self, text):
        guard = SpeechCommitGuard()
        language = "ta" if any("஀" <= c <= "௿" for c in text) else "en"
        decision = guard.judge(text, spoken(), language=language)
        assert decision.ok, decision.verdict
        assert decision.text == text

    def test_a_quiet_speaker_is_still_heard(self):
        """Softly spoken, close to the room's level but modulated like speech."""
        guard = SpeechCommitGuard()
        quiet = SpeechEvidence(voiced_ms=900, total_ms=1200, peak_snr=2.6, modulation=0.22)
        assert guard.judge("My name is Harish", quiet).ok

    def test_a_short_but_real_answer_is_committed(self):
        """"Ravi Kumar" is short. It is also a name, and the evidence says it
        was spoken for most of a second."""
        guard = SpeechCommitGuard()
        assert guard.judge("Ravi Kumar", spoken(ms=1100)).ok


class TestDuplicatesAndStaleResults:
    def test_the_same_transcript_is_committed_once(self):
        guard = SpeechCommitGuard()
        assert guard.judge("My name is Harish", spoken()).ok
        assert guard.judge("My name is Harish", spoken()).verdict is Verdict.DUPLICATE

    def test_punctuation_and_case_do_not_make_it_a_new_answer(self):
        guard = SpeechCommitGuard()
        assert guard.judge("My name is Harish", spoken()).ok
        assert guard.judge("my name is harish.", spoken()).verdict is Verdict.DUPLICATE

    def test_the_citizen_may_repeat_themselves_later(self):
        """Only the recent few are remembered. A citizen correcting a field
        back to what they first said must not be silently ignored."""
        guard = SpeechCommitGuard()
        assert guard.judge("Harish Kumar", spoken()).ok
        for filler in ["Twenty three", "Nine eight seven six", "Theni district",
                       "Water shortage here", "Perumal Kovil Street", "Yes correct"]:
            guard.judge(filler, spoken())
        assert guard.judge("Harish Kumar", spoken()).ok

    def test_a_result_from_a_previous_turn_is_refused(self):
        """The connection stalls, the citizen moves on, the old result lands.
        It must not answer the question they are on now."""
        guard = SpeechCommitGuard()
        old = guard.turn
        guard.begin_turn()
        assert guard.judge("Twenty three", spoken(), turn=old).verdict is Verdict.STALE


class TestTheAssistantIsNotHeardAsTheCitizen:
    def test_an_utterance_that_is_mostly_playback_is_refused(self):
        """The microphone hearing the speaker. Without this the assistant
        answers itself, and the loop does not stop."""
        guard = SpeechCommitGuard()
        echo = spoken(ms=1500, playback_ms=1400)
        decision = guard.judge("What is your age", echo, during_playback=True)
        assert decision.verdict is Verdict.ECHO_SUSPECTED

    def test_a_genuine_interruption_is_committed(self):
        """Barge-in has to survive the echo guard: the citizen starts talking
        over the end of a question, so a little overlap is expected."""
        guard = SpeechCommitGuard()
        interrupt = spoken(ms=1600, playback_ms=250)
        assert guard.judge("Actually my address is wrong", interrupt,
                           during_playback=True).ok


class TestLanguage:
    def test_a_bare_english_filler_in_a_tamil_session_is_refused(self):
        """What the screen showed: 'Okay' and 'Thirty' in a Tamil
        conversation, and once the Bengali 'আচ্ছা।' — none of them a citizen
        switching language, all of them a model guessing at noise."""
        guard = SpeechCommitGuard()
        assert guard.judge("Okay", spoken(), language="ta").verdict is Verdict.FILLER_ONLY
        assert guard.judge("আচ্ছা।", spoken(), language="ta").verdict is Verdict.WRONG_SCRIPT

    def test_a_latin_name_in_a_tamil_session_is_accepted(self):
        """Ordinary. Plenty of people spell their name in English on a Tamil
        form, and the record shows exactly that."""
        guard = SpeechCommitGuard()
        assert guard.judge("Harish Kumar", spoken(), language="ta").ok

    def test_a_number_in_a_tamil_session_is_accepted(self):
        guard = SpeechCommitGuard()
        assert guard.judge("9876543210", spoken(), language="ta").ok

    def test_tamil_in_an_english_session_is_accepted(self):
        """A citizen answering in Tamil is answering. Their words are kept
        verbatim either way."""
        guard = SpeechCommitGuard()
        assert guard.judge("தெருவிளக்கு எரியவில்லை", spoken(), language="en").ok


class TestConfidence:
    def test_a_low_confidence_transcript_is_refused(self):
        guard = SpeechCommitGuard()
        decision = guard.judge("My name is Harish", spoken(),
                               confidence=0.05, min_confidence=0.15)
        assert decision.verdict is Verdict.LOW_CONFIDENCE

    def test_a_provider_that_reports_nothing_does_not_fail_the_check(self):
        """Sarvam reports no per-transcript figure. Absence is not low
        confidence, and treating it as such would reject every utterance."""
        guard = SpeechCommitGuard()
        assert guard.judge("My name is Harish", spoken(),
                           confidence=None, min_confidence=0.15).ok


class TestTheGuardDecidesNothingAboutThePetition:
    def test_it_does_not_import_the_workflow_or_the_validators(self):
        import app.services.commit_guard as module

        source = open(module.__file__, encoding="utf-8").read()
        for forbidden in ("from ..graph", "workflow.invoke", "validate_field",
                          "verhoeff", "the_template(", "missing_fields("):
            assert forbidden not in source, f"commit_guard should not know about {forbidden}"

    def test_a_committed_transcript_is_returned_unchanged(self):
        """The guard admits or refuses. It never edits what the citizen said —
        the grievance is reproduced word for word."""
        guard = SpeechCommitGuard()
        text = "  The street light has not worked for three months.  "
        decision = guard.judge(text, spoken())
        assert decision.text == text.strip()
