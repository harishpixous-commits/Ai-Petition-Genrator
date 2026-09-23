"""Turn-taking, and what may be said out loud.

The voice layer is allowed to decide exactly one thing: when the citizen has
finished speaking. Everything else — what is asked, what is accepted, what goes
in the document — belongs to the workflow, and the tests here exist mostly to
prove that the voice layer has not quietly acquired an opinion about any of it.
"""

from __future__ import annotations

import array
import asyncio
import math

import pytest

from app.domain.templates import the_template
from app.services import speech_text
from app.services.voice import (
    EndOfSpeech,
    Speech,
    VadSettings,
    VoiceActivityDetector,
)

RATE = 16000


def tone(ms: int, amplitude: int = 9000, rate: int = RATE) -> bytes:
    """A loud, speech-like frame."""
    n = int(rate * ms / 1000)
    samples = array.array(
        "h", (int(amplitude * math.sin(2 * math.pi * 220 * i / rate)) for i in range(n))
    )
    return samples.tobytes()


def hush(ms: int, amplitude: int = 20, rate: int = RATE) -> bytes:
    """Room tone: not digital silence, which no microphone ever produces."""
    n = int(rate * ms / 1000)
    samples = array.array("h", ((amplitude if i % 7 else -amplitude) for i in range(n)))
    return samples.tobytes()


class TestVoiceActivityDetector:
    def test_quiet_is_never_speech(self):
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE))
        verdicts = vad.feed(hush(2000))
        assert set(verdicts) == {Speech.SILENCE}
        assert vad.speaking is False

    def test_speech_opens_a_turn_once(self):
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE))
        vad.feed(hush(600))
        verdicts = vad.feed(tone(600))
        assert verdicts.count(Speech.STARTED) == 1, verdicts
        assert vad.speaking is True

    def test_a_short_noise_does_not_open_a_turn(self):
        """A cough, a door, a chair. Shorter than `onset_ms` is not an answer."""
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE, onset_ms=200))
        vad.feed(hush(600))
        verdicts = vad.feed(tone(64)) + vad.feed(hush(400))
        assert Speech.STARTED not in verdicts, verdicts

    def test_a_pause_inside_a_sentence_does_not_end_the_turn(self):
        """People stop to think. Ending the turn there cuts them off mid-answer
        and sends half a grievance to be transcribed."""
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE, hangover_ms=700))
        vad.feed(hush(400))
        vad.feed(tone(400))
        verdicts = vad.feed(hush(320))          # a beat, well inside the hangover
        assert Speech.ENDED not in verdicts
        assert vad.speaking is True

    def test_silence_past_the_hangover_ends_the_turn_once(self):
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE, hangover_ms=400))
        vad.feed(hush(400))
        vad.feed(tone(400))
        verdicts = vad.feed(hush(1200))
        assert verdicts.count(Speech.ENDED) == 1, verdicts
        assert vad.speaking is False

    def test_a_noisy_room_is_learnt_rather_than_treated_as_speech(self):
        """A fan, a queue, an air conditioner. Against a fixed threshold this
        is speech for the whole session and the citizen is never heard."""
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE))
        verdicts = vad.feed(hush(3000, amplitude=600))
        assert Speech.STARTED not in verdicts
        # And real speech still gets through, over that floor.
        assert Speech.STARTED in vad.feed(tone(600, amplitude=12000))

    def test_frames_are_whole_and_leftovers_are_kept(self):
        """Browsers do not send frame-aligned buffers."""
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE, frame_ms=32))
        frame = vad.frame_bytes
        assert vad.feed(b"\x00" * (frame - 2)) == []
        assert len(vad.feed(b"\x00" * 2)) == 1

    def test_reset_keeps_what_was_learnt_about_the_room(self):
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE))
        vad.feed(hush(2000, amplitude=500))
        learnt = vad._noise
        vad.reset()
        assert vad.speaking is False
        assert vad._noise == learnt


class TestEndOfSpeech:
    async def test_one_utterance_is_delivered_once(self):
        got = []
        eos = EndOfSpeech(on_utterance=lambda u: got.append(u) or asyncio.sleep(0))
        eos.begin()
        eos.add(tone(500))
        await eos.finish()
        assert len(got) == 1
        assert got[0].turn == 1

    async def test_finishing_twice_delivers_once(self):
        """The failure this whole design exists for. A settled utterance that
        is delivered twice answers the NEXT question with the previous answer."""
        got = []
        eos = EndOfSpeech(on_utterance=lambda u: got.append(u) or asyncio.sleep(0))
        eos.begin()
        eos.add(tone(500))
        await eos.finish()
        await eos.finish()
        await eos.finish()
        assert len(got) == 1

    async def test_two_finishes_racing_each_other_deliver_once(self):
        """The real race. Silence past the hangover and the citizen pressing
        stop arrive on the same tick, and both call finish. The delivery is
        slow — it transcribes and then runs a whole workflow turn — so the
        second call is well inside the first."""
        got = []

        async def slow(u):
            await asyncio.sleep(0.02)
            got.append(u.turn)

        eos = EndOfSpeech(on_utterance=slow)
        eos.begin()
        eos.add(tone(500))
        await asyncio.gather(eos.finish(), eos.finish(), eos.finish())
        assert got == [1], got

    async def test_a_second_utterance_during_a_slow_delivery_still_arrives(self):
        """The other half of it: a citizen who answers again while the first
        answer is still being processed has genuinely said two things, and
        losing the second would be as bad as delivering the first twice."""
        got = []

        async def slow(u):
            await asyncio.sleep(0.02)
            got.append(u.turn)

        eos = EndOfSpeech(on_utterance=slow)
        eos.begin()
        eos.add(tone(500))
        first = asyncio.create_task(eos.finish())
        await asyncio.sleep(0)
        eos.begin()
        eos.add(tone(500))
        await asyncio.gather(first, eos.finish())
        assert got == [1, 2], got

    async def test_turn_numbers_increase_and_never_repeat(self):
        got = []
        eos = EndOfSpeech(on_utterance=lambda u: got.append(u.turn) or asyncio.sleep(0))
        for _ in range(3):
            eos.begin()
            eos.add(tone(400))
            await eos.finish()
        assert got == [1, 2, 3]

    async def test_a_misclick_is_not_an_utterance(self):
        got = []
        eos = EndOfSpeech(on_utterance=lambda u: got.append(u) or asyncio.sleep(0),
                          min_seconds=5.0)
        eos.begin()
        eos.add(tone(100))
        await eos.finish()
        assert got == []

    async def test_abandoned_audio_never_arrives_later(self):
        """Ending the session, or cancelling a turn, must not leave speech in
        flight that turns up as an answer to a question that has moved on."""
        got = []
        eos = EndOfSpeech(on_utterance=lambda u: got.append(u) or asyncio.sleep(0))
        eos.begin()
        eos.add(tone(500))
        eos.abandon()
        await eos.finish()
        assert got == []

    async def test_nothing_is_delivered_without_a_beginning(self):
        got = []
        eos = EndOfSpeech(on_utterance=lambda u: got.append(u) or asyncio.sleep(0))
        assert await eos.finish() is None
        assert got == []


class TestABufferIsStoredOnceHoweverManyFramesItHolds:
    """The contract between the detector and whatever is collecting audio.

    `feed()` reports on every 32 ms FRAME, and a browser buffer is several
    frames long. A caller that stores the buffer once per verdict stores it
    four times over, and the speech service transcribes exactly that: "My name
    is Harish" came back as three hundred words of "Ni Ni Ni Mi Mi Mi". The
    audio that reaches the transcriber has to be the audio that was spoken.
    """

    @staticmethod
    def collect(vad: VoiceActivityDetector, eos: EndOfSpeech, chunk: bytes):
        """The shape the socket uses: classify per frame, store per buffer."""
        verdicts = vad.feed(chunk)
        started = Speech.STARTED in verdicts
        ended = Speech.ENDED in verdicts
        if started:
            eos.begin()
        if started or ended or vad.speaking:
            eos.add(chunk)
        return started, ended

    async def test_the_audio_delivered_is_the_audio_that_was_spoken(self):
        got = []
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE, frame_ms=32,
                                                hangover_ms=300))
        eos = EndOfSpeech(on_utterance=lambda u: got.append(u) or asyncio.sleep(0),
                          sample_rate=RATE)

        # 128 ms buffers, exactly as a browser sends them: four frames each.
        speech = tone(1024)
        buffers = [hush(128) for _ in range(6)]
        buffers += [speech[i:i + 4096] for i in range(0, len(speech), 4096)]
        buffers += [hush(128) for _ in range(10)]

        for chunk in buffers:
            _, ended = self.collect(vad, eos, chunk)
            if ended:
                await eos.finish()

        assert len(got) == 1, "one utterance"
        stored = len(got[0].audio)
        # Every buffer is 4096 bytes, so the stored audio must be a whole
        # number of them, and close to the ~1 second that was spoken — not
        # four times it.
        assert stored % 4096 == 0
        assert 0.9 <= stored / (RATE * 2) <= 1.5, f"{stored / (RATE * 2):.2f}s stored"

    def test_one_verdict_per_frame_is_the_documented_contract(self):
        vad = VoiceActivityDetector(VadSettings(sample_rate=RATE, frame_ms=32))
        assert len(vad.feed(hush(128))) == 4
        assert len(vad.feed(hush(320))) == 10


class TestWhatMayBeSpoken:
    """A screen is read by one person. A speaker is heard by the queue."""

    def test_an_aadhaar_is_never_read_aloud(self):
        view = {"status": "collecting", "awaiting": "grievance"}
        spoken = speech_text.speech_for(
            display_text="Aadhaar number: 2345 6789 0124. Now tell me your grievance.",
            view=view, template=the_template(), language="en",
        )
        assert "2345" not in spoken
        assert "0124" not in spoken
        assert "6789 0124" not in spoken

    def test_a_mobile_number_is_never_read_aloud(self):
        view = {"status": "collecting", "awaiting": "address"}
        spoken = speech_text.speech_for(
            display_text="I have your mobile number +91 98765 43210. What is your address?",
            view=view, template=the_template(), language="en",
        )
        assert "98765" not in spoken and "43210" not in spoken

    def test_the_read_back_becomes_a_question_not_a_recital(self):
        """The confirmation lists every value. Spoken, that is a citizen's
        Aadhaar announced to a waiting room."""
        view = {"status": "confirming", "awaiting": None}
        spoken = speech_text.speech_for(
            display_text=("Here is what I have recorded.\nName: Harish\n"
                          "Aadhaar number: 2345 6789 0124\nIs all of this correct?"),
            view=view, template=the_template(), language="en",
        )
        assert "2345" not in spoken
        assert "?" in spoken

    def test_an_identifier_that_must_be_typed_is_asked_for_that_way(self):
        """The FORM no longer asks for an Aadhaar. The rule that an
        identifier of that class is typed rather than said in a room with a
        queue in it is unchanged, and this checks the rule rather than the
        field: a template declaring one still gets the typed request.
        """
        import dataclasses

        from app.domain.templates import TemplateField

        template = the_template()
        with_identifier = dataclasses.replace(template, fields=(
            *template.fields,
            TemplateField(name="bank_account", type="bank_account", required=True,
                          label={"en": "Bank account number"},
                          prompt={"en": "Please give your bank account number."}),
        ))
        spoken = speech_text.speech_for(
            display_text="Please give your bank account number.",
            view={"status": "collecting", "awaiting": "bank_account"},
            template=with_identifier, language="en",
        )
        assert "type" in spoken.lower()

    def test_the_form_asks_for_no_such_identifier_at_all(self):
        """The stronger version of the same protection: nothing to type,
        nothing to say, nothing to leak."""
        from app.domain.fields import SPEAK_NEVER_TYPES

        asked = {f.type for f in the_template().fields}
        assert not asked & SPEAK_NEVER_TYPES, sorted(asked)

    def test_an_operator_may_allow_spoken_identifiers(self):
        """A citizen who cannot type is the person this service is for."""
        view = {"status": "collecting", "awaiting": "aadhaar"}
        spoken = speech_text.speech_for(
            display_text="Please say your 12-digit Aadhaar number.",
            view=view, template=the_template(), language="en",
            allow_spoken_identifiers=True,
        )
        assert "type" not in spoken.lower()

    def test_an_ordinary_question_is_spoken_as_written(self):
        view = {"status": "collecting", "awaiting": "applicant_name"}
        spoken = speech_text.speech_for(
            display_text="What is your name?",
            view=view, template=the_template(), language="en",
        )
        assert spoken == "What is your name?"

    def test_identifiers_are_confirmed_by_their_last_four_digits(self):
        said = speech_text.acknowledgement(
            name="mobile", value="9876543210", template=the_template(), language="en")
        assert "3210" in said
        assert "98765" not in said

    def test_ordinary_fields_get_no_spoken_acknowledgement(self):
        """Repeating every answer back is tiring; the next question is the
        acknowledgement."""
        assert speech_text.acknowledgement(
            name="applicant_name", value="Harish",
            template=the_template(), language="en") is None

    def test_both_languages_carry_every_spoken_phrase(self):
        for key, forms in speech_text.SPOKEN.items():
            assert forms.get("en"), key
            assert forms.get("ta"), key

    def test_tamil_speech_redacts_identically(self):
        view = {"status": "confirming", "awaiting": None}
        spoken = speech_text.speech_for(
            display_text="ஆதார் எண்: 2345 6789 0124",
            view=view, template=the_template(), language="ta",
        )
        assert "2345" not in spoken

    @pytest.mark.parametrize("text,gone", [
        ("call 9876543210 now", "9876543210"),
        ("Aadhaar 2345 6789 0124 recorded", "2345 6789 0124"),
        ("+91 98765 43210", "98765"),
    ])
    def test_the_backstop_removes_any_long_number(self, text, gone):
        """`speech_for` builds spoken text deliberately; this catches whatever
        reaches the speaker by some other route."""
        assert gone not in speech_text.redact_for_speech(text)

    def test_short_numbers_survive(self):
        """An age, a house number, a count of fields. Removing these would make
        the assistant unable to say anything useful."""
        assert "23" in speech_text.redact_for_speech("You are 23 years old")
        assert "6" in speech_text.redact_for_speech("6 details checked")


class TestTheVoiceLayerOwnsNoPetitionRules:
    """The rule the whole integration rests on: voice is transport."""

    def test_voice_module_does_not_import_the_workflow_or_the_validators(self):
        import app.services.voice as module

        source = open(module.__file__, encoding="utf-8").read()
        for forbidden in ("from ..graph", "import graph", "validate_", "the_template",
                          "field_errors", "aadhaar"):
            assert forbidden not in source, f"voice.py should not know about {forbidden}"

    def test_speech_text_reads_the_form_but_never_decides_it(self):
        import app.services.speech_text as module

        source = open(module.__file__, encoding="utf-8").read()
        for forbidden in ("workflow.invoke", "from ..graph", "verhoeff", "missing_fields"):
            assert forbidden not in source, f"speech_text.py should not do {forbidden}"


class TestReadingTheFinishedPetitionAloud:
    """The assistant offers to read the petition out. Until this existed the
    offer was empty: `ready` is terminal in the router, so a citizen saying
    "yes" was answering a workflow that had already stopped, and nothing at
    all happened."""

    LETTER = "\n".join([
        "From,",
        "    Harish",
        "    80/33 perumal kovil street, theni",
        "    Age: 23",
        "    Mobile number: +91 98765 43210",
        "    Aadhaar number: 2345 6789 0124",
        "",
        "To,",
        "    The District Collector",
        "",
        "Subject: Provision of regular drinking water supply",
        "",
        "   water scarcity in our street for the past several weeks",
        "",
        "Thank you!",
    ])

    def test_it_is_broken_into_sections_that_can_be_interrupted(self):
        sections = speech_text.readable_sections(self.LETTER)
        assert len(sections) >= 4
        assert all(len(s) < 600 for s in sections), [len(s) for s in sections]

    def test_no_identifier_is_ever_read_out(self):
        """The document on screen carries the Aadhaar. The room does not need
        to hear it, and a counter has a queue behind it."""
        spoken = " ".join(speech_text.readable_sections(self.LETTER))
        for secret in ("2345", "0124", "6789", "98765", "43210"):
            assert secret not in spoken, secret

    def test_a_label_left_with_nothing_after_it_is_dropped(self):
        """Redacting the value leaves "Mobile number:" announcing nothing.
        Two in a row sounded like the service had lost the data rather than
        withheld it."""
        spoken = " ".join(speech_text.readable_sections(self.LETTER))
        assert "Mobile number:" not in spoken
        assert "Aadhaar number:" not in spoken

    def test_what_the_citizen_said_is_still_read_back(self):
        spoken = " ".join(speech_text.readable_sections(self.LETTER))
        assert "water scarcity in our street" in spoken
        assert "Age: 23" in spoken          # an age is not an identifier

    def test_tamil_sections_survive_the_same_treatment(self):
        letter = "\n".join([
            "அனுப்புநர்,", "    Harish", "    வயது: 23",
            "    ஆதார் எண்: 2345 6789 0124", "",
            "பெறுநர்,", "    மாவட்ட ஆட்சியர் அவர்கள்", "",
            "பொருள்: குடிநீர் தட்டுப்பாடு தொடர்பாக.", "",
            "   தெருவில் தண்ணீர் இல்லை.", "", "நன்றி!",
        ])
        sections = speech_text.readable_sections(letter)
        spoken = " ".join(sections)
        assert len(sections) >= 3
        assert "2345" not in spoken and "0124" not in spoken
        assert "ஆதார் எண்:" not in spoken
        assert "தெருவில் தண்ணீர் இல்லை." in spoken

    def test_an_empty_petition_reads_as_nothing(self):
        assert speech_text.readable_sections("") == []
        assert speech_text.readable_sections("   \n  \n") == []


class TestCommandsAfterThePetitionExists:
    """`ready` is terminal in the router, so anything said after generation is
    handled by the socket or not at all. These two patterns are the only words
    the voice layer acts on by itself, and they are worth pinning: a previous
    revision reached disk with a literal backspace where each word boundary
    should have been, and saying "stop" did nothing whatsoever."""

    @pytest.mark.parametrize("said", [
        "yes please read it", "read it", "read my petition aloud", "go ahead",
        "படி", "வாசிக்க",
    ])
    def test_asking_for_it_to_be_read(self, said):
        from app.api.ws import _READ_ALOUD
        assert _READ_ALOUD.search(said), said

    @pytest.mark.parametrize("said", [
        "stop", "stop reading", "that is enough", "quiet please",
        "நிறுத்து", "போதும்",
    ])
    def test_asking_it_to_stop(self, said):
        from app.api.ws import _STOP_READING
        assert _STOP_READING.search(said), said

    @pytest.mark.parametrize("said", [
        "Harish", "twenty three", "my address is wrong",
        "the street light has not worked", "80/33 perumal kovil street",
        "என் பெயர் ஹரிஷ்", "தெருவிளக்கு எரியவில்லை",
    ])
    def test_an_ordinary_answer_is_not_a_command(self, said):
        """These go to the workflow. A name that happened to contain "read"
        being swallowed as a command would lose the citizen's answer."""
        from app.api.ws import _READ_ALOUD, _STOP_READING
        assert not _READ_ALOUD.search(said), said
        assert not _STOP_READING.search(said), said

    def test_the_patterns_contain_no_control_characters(self):
        """The specific failure: `\\b` written through a shell arrived as a
        literal backspace (0x08), which matches nothing a citizen can say."""
        from app.api.ws import _READ_ALOUD, _STOP_READING
        for pattern in (_READ_ALOUD.pattern, _STOP_READING.pattern):
            assert not any(ord(c) < 9 for c in pattern), repr(pattern)
