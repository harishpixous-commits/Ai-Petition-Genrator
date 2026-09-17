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


class TestSpeechThatWasBeingThrownAway:
    """Every case here is a real utterance from a real session's log.

    In one day, 57 of 72 utterances were discarded. Thirty-four of them were
    the citizen speaking and being ignored, which is what "it does not hear me"
    actually was. The measurements below are theirs, not invented.
    """

    @staticmethod
    def _judge(voiced_ms, ratio, modulation, snr, text="the street light is broken",
               expecting=False):
        guard = SpeechCommitGuard()
        guard.begin_turn()
        evidence = SpeechEvidence(
            voiced_ms=voiced_ms, total_ms=int(voiced_ms / ratio),
            peak_snr=snr, modulation=modulation)
        return guard.judge(text, evidence, turn=guard.turn,
                           expecting_confirmation=expecting).verdict

    def test_speech_that_pauses_is_still_speech(self):
        """576 ms of audio at 41.8 dB with 1.5 modulation was rejected because
        30% of the window was the pause before the words rather than 35%."""
        assert self._judge(576, 0.30, 1.514, 41.8) is Verdict.COMMIT

    def test_a_long_utterance_with_a_thin_window(self):
        """1.4 seconds of voiced audio, thrown away on the ratio alone."""
        assert self._judge(1376, 0.33, 0.703, 14.4) is Verdict.COMMIT

    def test_the_word_yes_as_this_pipeline_actually_measures_it(self):
        """224 ms at 33.8 dB with 1.52 modulation.

        Not an estimate: the word was synthesised, pushed through the real
        voice socket, and this is what the detector reported. The floor was
        320 ms, so a spoken yes could never confirm a petition — and that is
        the step where the citizen is told nothing is happening.
        """
        assert self._judge(224, 0.24, 1.524, 33.8, text="Yes",
                           expecting=True) is Verdict.COMMIT

    def test_a_brief_but_unmistakable_answer(self):
        """256 ms at 15.6 dB. This is what a spoken "yes" looks like, and the
        floor was 320 ms."""
        assert self._judge(256, 0.24, 1.245, 15.6) is Verdict.COMMIT

    def test_a_quiet_thin_smear_is_still_not_speech(self):
        """The loosening is not a free pass: weak on every measure stays out."""
        assert self._judge(512, 0.23, 0.593, 5.6) is not Verdict.COMMIT


class TestWhatTheGuardStillStops:
    """The reason the guard exists. A transcription service asked to read
    digital silence returned a whole Tamil sentence; asked to read a keyboard
    click it returned "Okay". None of that may become an answer on a petition.
    """

    @staticmethod
    def _judge(voiced_ms, total_ms, snr, modulation, text="okay"):
        guard = SpeechCommitGuard()
        guard.begin_turn()
        return guard.judge(
            text,
            SpeechEvidence(voiced_ms=voiced_ms, total_ms=total_ms,
                           peak_snr=snr, modulation=modulation),
            turn=guard.turn).verdict

    @pytest.mark.parametrize("name,voiced,total,snr,modulation", [
        ("digital silence", 0, 2000, 0.0, 0.0),
        ("room tone", 900, 2000, 1.4, 0.03),
        ("a steady fan", 1800, 2000, 3.0, 0.05),
        ("a hard disk hum", 1200, 2000, 2.5, 0.08),
        ("one keyboard click", 150, 1200, 9.0, 0.9),
        ("a cough", 180, 1500, 12.0, 1.1),
        ("a distant television", 600, 4000, 2.0, 0.10),
    ])
    def test_it_never_becomes_a_turn(self, name, voiced, total, snr, modulation):
        assert self._judge(voiced, total, snr, modulation) is not Verdict.COMMIT, name

    def test_a_steady_noise_is_not_rescued_by_being_loud(self):
        """Level variation is what separates a voice from a machine. Volume is
        not, or a fan close to the microphone would answer every question."""
        assert self._judge(1800, 2000, 40.0, 0.05) is Verdict.NO_SPEECH_EVIDENCE


class TestYesMeansYesWhenYesWasTheQuestion:
    """"yes" is in the hallucination list because services return it from
    silence. It is also the only answer to "Shall I prepare your petition?" —
    so saying yes by voice could never work, and the flow stopped dead at the
    step before the document.
    """

    @staticmethod
    def _judge(text, expecting):
        guard = SpeechCommitGuard()
        guard.begin_turn()
        # Plainly spoken: 380 ms at 18 dB.
        evidence = SpeechEvidence(voiced_ms=380, total_ms=1100,
                                  peak_snr=18.0, modulation=1.1)
        return guard.judge(text, evidence, turn=guard.turn,
                           expecting_confirmation=expecting).verdict

    @pytest.mark.parametrize("word", ["yes", "Yes", "okay", "\u0b86\u0bae\u0bcd", "\u0b9a\u0bb0\u0bbf"])
    def test_it_is_an_answer_when_a_confirmation_was_asked_for(self, word):
        assert self._judge(word, expecting=True) is Verdict.COMMIT, word

    @pytest.mark.parametrize("word", ["yes", "okay", "\u0b86\u0bae\u0bcd"])
    def test_and_still_is_not_when_a_name_was_asked_for(self, word):
        """Asked for a name and handed "okay", the right move is to ask again."""
        assert self._judge(word, expecting=False) is Verdict.FILLER_ONLY, word

    def test_noise_does_not_become_a_yes_just_because_one_was_expected(self):
        """The word being allowed to mean something does not let the room
        speak: the audio still has to be a person."""
        guard = SpeechCommitGuard()
        guard.begin_turn()
        fan = SpeechEvidence(voiced_ms=1800, total_ms=2000, peak_snr=3.0, modulation=0.05)

        verdict = guard.judge("yes", fan, turn=guard.turn,
                              expecting_confirmation=True).verdict

        assert verdict is Verdict.NO_SPEECH_EVIDENCE


class TestWhichStepExpectsAConfirmation:
    @pytest.mark.parametrize("status,expected", [
        ("attachments", True),
        ("confirming", True),
        ("ready", True),
        ("collecting", False),
        ("generating", False),
        ("failed", False),
        ("", False),
    ])
    def test_read_from_the_workflow_never_guessed_from_the_words(self, status, expected):
        from app.api.ws import expects_confirmation

        assert expects_confirmation({"status": status}) is expected

    def test_a_correction_being_checked_also_expects_one(self):
        from app.api.ws import expects_confirmation

        assert expects_confirmation({"status": "collecting", "awaiting_correction": True})

    def test_no_state_at_all(self):
        from app.api.ws import expects_confirmation

        assert expects_confirmation(None) is False


class TestTheStartOfTheWordIsKept:
    """The detector needs 120 ms of speech before it will open a turn, and the
    buffer that completed that test used to be the FIRST one stored. Everything
    before it was dropped — up to a whole browser buffer, 128 ms at 16 kHz.

    Measured against the real transcription service: with 160 ms cut off the
    front, "Harish" comes back as "Breeze"; a Tamil sentence comes back as
    "Pair Harish". Never an empty result, which is why it never looked like a
    failure — just a wrong name on a petition.
    """

    @staticmethod
    async def _utterance(buffers, opened_at):
        import asyncio

        from app.services.voice import EndOfSpeech

        got = []

        async def keep(u):
            got.append(u)

        eos = EndOfSpeech(on_utterance=keep, sample_rate=16000)
        for index, buffer in enumerate(buffers):
            eos.remember(buffer)
            if index == opened_at:
                eos.begin()
            if index >= opened_at:
                eos.add(buffer)
        await eos.finish()
        await asyncio.sleep(0)
        return got[0].audio if got else b""

    async def test_audio_from_before_the_turn_opened_is_included(self):
        buffers = [bytes([n]) * 4096 for n in range(1, 7)]

        audio = await self._utterance(buffers, opened_at=3)

        assert bytes([3]) * 4096 in audio, "the buffer before the turn opened was lost"
        assert bytes([2]) * 4096 in audio, "only one buffer of lead-in was kept"
        assert bytes([4]) * 4096 in audio, "the opening buffer itself is missing"

    async def test_it_does_not_reach_back_further_than_the_window(self):
        """400 ms, not the whole session. Otherwise every utterance carries the
        previous one in front of it."""
        buffers = [bytes([n]) * 4096 for n in range(1, 9)]

        audio = await self._utterance(buffers, opened_at=7)

        assert bytes([1]) * 4096 not in audio
        assert len(audio) <= 4096 * 5

    async def test_a_second_utterance_does_not_carry_the_first(self):
        import asyncio

        from app.services.voice import EndOfSpeech

        got = []

        async def keep(u):
            got.append(u)

        eos = EndOfSpeech(on_utterance=keep, sample_rate=16000)
        first = bytes([1]) * 4096
        eos.remember(first)
        eos.begin()
        eos.add(first)
        await eos.finish()
        await asyncio.sleep(0)

        second = bytes([2]) * 4096
        eos.remember(second)
        eos.begin()
        eos.add(second)
        await eos.finish()
        await asyncio.sleep(0)

        assert first not in got[1].audio, "the previous utterance leaked into this one"


class TestABriefConfirmationIsHeard:
    """A plainly spoken "Yes." measured 192 ms of voiced audio at 78 dB through
    the real pipeline, and was discarded for being eight milliseconds under the
    floor. At the review step that is the whole conversation stopping.
    """

    @staticmethod
    def _judge(text, voiced_ms, ratio, modulation, snr, expecting):
        guard = SpeechCommitGuard()
        guard.begin_turn()
        evidence = SpeechEvidence(voiced_ms=voiced_ms, total_ms=int(voiced_ms / ratio),
                                  peak_snr=snr, modulation=modulation)
        return guard.judge(text, evidence, turn=guard.turn,
                           expecting_confirmation=expecting).verdict

    def test_the_yes_that_was_measured(self):
        assert self._judge("Yes", 192, 0.21, 1.181, 78.4, True) is Verdict.COMMIT

    def test_the_same_audio_is_not_an_answer_to_a_question_about_a_name(self):
        assert self._judge("Yes", 192, 0.21, 1.181, 78.4, False) is not Verdict.COMMIT

    @pytest.mark.parametrize("voiced", [60, 96, 128])
    def test_a_click_cannot_confirm_a_petition(self, voiced):
        """Observed: a keyboard click transcribed as the English "Okay". At the
        review step that word would confirm — so the audio gate has to hold."""
        assert self._judge("Okay", voiced, 0.15, 0.9, 20.0, True) is Verdict.TOO_SHORT

    def test_nor_can_a_fan_or_silence(self):
        assert self._judge("yes", 1800, 0.9, 0.05, 3.0, True) is Verdict.NO_SPEECH_EVIDENCE
        assert self._judge("yes", 0, 0.001, 0.0, 0.0, True) is Verdict.TOO_SHORT
