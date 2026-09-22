"""How the assistant speaks to a citizen in Tamil, field by field.

WHAT THIS IS FOR. The turn-taking is tested next door; this is about the
WORDS. A form that asks "உங்கள் பெயர் என்ன?" and then says "நான் கேட்டது:
ஹரிஷ்" is correct and sounds like a machine reading a spreadsheet. The
department asked for a conversation: a greeting, an acknowledgement between
questions, and a read-back that names the field it is filling.

THE ONE THAT MATTERS MOST is `TestTheRoomNeverHearsAnIdentifier`. Everything
else here is tone. That one is about a queue standing behind a citizen at a
counter while a speaker reads out their Aadhaar number.

The wording is the department's and lives in `petition.yaml`, so these tests
check the SHAPE of each sentence — that it names the field, that it ends in a
question, that an identifier appears only by its last four digits — rather
than pinning prose that is theirs to change.
"""

from __future__ import annotations

import re

import pytest

from app.domain.fields import SENSITIVE_TYPES, SPEAK_NEVER_TYPES
from app.domain.templates import next_field, the_template
from app.services.speech_text import (
    phrase,
    read_back_sentence,
    should_type_instead,
)

LANGUAGES = ("en", "ta")


def spec_for(name: str):
    return next(f for f in the_template().fields if f.name == name)


def in_order():
    """Every field, in the order the citizen is actually asked."""
    filled: dict[str, str] = {}
    while (spec := next_field(the_template(), filled)) is not None:
        yield spec
        filled[spec.name] = "x"


# THE REAL FUNCTION, not a copy of it. An earlier version of this file
# reproduced the logic instead of calling it, and passed happily while the
# real one was broken — deleting the identifier branch in the socket failed
# nothing at all.
read_back = read_back_sentence


# ---------------------------------------------------------------------------

class TestTheRoomNeverHearsAnIdentifier:
    """A screen is read by the person standing at it. A speaker is heard by
    the queue behind them."""

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_an_aadhaar_is_never_read_out(self, language):
        full = "234567890124"
        said = read_back(spec_for("aadhaar"), full, language)

        assert full not in said
        assert "2345" not in said and "6789" not in said
        assert "0124" in said, "the citizen cannot tell which card it was"

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_an_identifier_is_described_rather_than_spelled_out(self, language):
        """Masking alone is not enough HERE, and this is the test that says
        why. "XXXX XXXX 0124" is safe on a screen and absurd through a
        speaker — a synthesiser reads the mask out, letter by letter, before
        reaching the digits that matter. The sentence has to be built for
        speech, not masked for it.

        Deleting the identifier branch leaves the value safe and the sentence
        unspeakable, which is why the digit assertions above cannot catch it.
        """
        for field in ("aadhaar", "mobile"):
            said = read_back(spec_for(field), "234567890124", language)
            assert "X" not in said, (field, said)
            assert "*" not in said, (field, said)

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_a_mobile_number_is_read_back_by_its_last_four(self, language):
        said = read_back(spec_for("mobile"), "9344174521", language)

        assert "4521" in said
        assert "93441" not in said

    def test_the_citizen_is_not_asked_to_say_an_aadhaar_aloud(self):
        assert should_type_instead("aadhaar", False) is True
        for language in LANGUAGES:
            asked = spec_for("aadhaar").prompt_for(language)
            spoken = phrase("type_it", language,
                            label=spec_for("aadhaar").speech_label_for(language))
            # Both the screen and the voice send them to the keyboard.
            assert ("type" in asked.lower() or "உள்ளிட" in asked)
            assert ("type" in spoken.lower() or "உள்ளிட" in spoken)

    def test_but_a_mobile_number_may_be_spoken(self):
        """A narrower rule than "every identifier". Citizens read their
        mobile number out at counters constantly and it is printed on the
        petition they are about to sign; making them type it adds a keyboard
        step to a voice form for a number they will say anyway."""
        assert should_type_instead("mobile", False) is False
        assert "mobile" not in SPEAK_NEVER_TYPES
        # Still masked whenever it is said back, which is the protection that
        # actually matters for it.
        assert "mobile" in SENSITIVE_TYPES

    def test_the_set_that_must_be_typed_is_the_serious_ones(self):
        assert {"aadhaar", "bank_account", "pan", "voter_id"} <= SPEAK_NEVER_TYPES


class TestTheReadBackNamesTheField:
    """"I heard Harish" is agreeable even when Harish was meant to be the
    town. "I have recorded your name as Harish" is not."""

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_an_ordinary_answer_is_quoted_under_its_own_name(self, language):
        spec = spec_for("applicant_name")
        said = read_back(spec, "ஹரிஷ்", language)

        assert spec.speech_label_for(language) in said
        assert "ஹரிஷ்" in said

    def test_the_spoken_name_of_a_field_is_not_the_form_column(self):
        """A form column reads "Name of petitioner"; said aloud that becomes
        "your name of petitioner"."""
        spec = spec_for("applicant_name")

        assert spec.label_for("ta") == "மனுதாரர் பெயர்"
        assert spec.speech_label_for("ta") == "பெயர்"
        assert spec.label_for("en") == "Name of petitioner"
        assert spec.speech_label_for("en") == "name"

    def test_a_field_without_one_falls_back_to_its_label(self):
        spec = spec_for("age")
        for language in LANGUAGES:
            assert spec.speech_label_for(language) == spec.label_for(language)

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_quotation_does_not_stack_punctuation(self, language):
        """"your grievance: no water came. is that correct?" reads as two
        broken sentences when spoken."""
        said = read_back(spec_for("grievance"), "தண்ணீர் வரவில்லை.", language)

        assert ". என்று" not in said
        assert ".. " not in said

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_every_read_back_asks_a_question(self, language):
        """It is a question, and a citizen who is not asked one does not
        answer."""
        for spec in in_order():
            said = read_back(spec, "234567890124" if spec.type in SENSITIVE_TYPES
                             else "something", language)
            assert said.rstrip().endswith("?"), (spec.name, said)


class TestItSoundsLikeAConversation:

    def test_the_first_question_greets_the_citizen(self):
        first = next(in_order())

        assert first.name == "applicant_name"
        assert "வணக்கம்" in first.prompt_for("ta")
        assert "hello" in first.prompt_for("en").lower()

    def test_only_the_first_question_greets(self):
        """A greeting before every question is not politeness, it is a
        machine with one sentence."""
        greeted = [s.name for s in in_order() if "வணக்கம்" in s.prompt_for("ta")]

        assert greeted == ["applicant_name"], greeted

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_every_question_is_a_whole_sentence(self, language):
        for spec in in_order():
            asked = spec.prompt_for(language)
            assert asked.rstrip().endswith((".", "?")), (spec.name, asked)
            assert len(asked.split()) >= 4, (spec.name, asked)


class TestTheGrievanceIsAskedDifferently:

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_question_says_what_to_include(self, language):
        """"Tell me your grievance" gets one sentence back. Asking what
        happened, when it started and whether they have complained before is
        what produces the complaint they actually have."""
        asked = spec_for("grievance").prompt_for(language)

        assert len(asked.split()) >= 12, asked

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_pacing_is_added_by_the_voice_layer_not_the_form(self, language):
        """It is only true of speaking. A citizen typing their grievance is
        not waiting for a pause to be interpreted."""
        asked = spec_for("grievance").prompt_for(language)
        pacing = phrase("long_intro", language)

        assert pacing not in asked
        assert "முடிந்தது" in pacing or "finished" in pacing.lower()

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_together_they_do_not_repeat_themselves(self, language):
        """The two halves are said as one sentence. An instruction given
        twice in it is the seam showing."""
        whole = f"{spec_for('grievance').prompt_for(language)} {phrase('long_intro', language)}"
        # No sentence appears twice.
        sentences = [s.strip() for s in re.split(r"[.?]", whole) if s.strip()]
        assert len(sentences) == len(set(sentences)), whole
