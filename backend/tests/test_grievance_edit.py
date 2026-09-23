"""Editing a dictated grievance by voice.

THE BUG THIS EXISTS FOR, and it is the worst one in the voice path. A
citizen dictated a two-minute complaint, heard it read back, and said
"change five days to three days". That sentence went to
`answer_intent.read`, which found six words of content in it and returned
REPLACE — so the whole complaint was discarded and the petition that
reached the officer read, in its entirety, "Change five days to three
days."

The test at the bottom of TestTheOldBehaviour is that exact sequence.

WHAT IS BEING PROVED HERE. Not that edits are clever — that they are
literal. Every assertion in this file is about characters: the words the
citizen asked to change are changed, every other character survives
byte for byte, and an instruction that does not resolve to a literal
operation is refused with a question instead of guessed at.
"""

from __future__ import annotations

import pathlib

import pytest

from app.domain.grievance_edit import EditRequest, apply, read_edit, sentences

GRIEVANCE = (
    "Water has not been supplied to our street for five days. "
    "We informed the local office but nobody came. "
    "The road is also damaged near the temple."
)

TAMIL = (
    "எங்கள் தெருவில் ஐந்து நாட்களாக தண்ணீர் வரவில்லை. "
    "அலுவலகத்தில் தெரிவித்தோம் ஆனால் யாரும் வரவில்லை. "
    "சாலையும் சேதமடைந்துள்ளது."
)


# ---------------------------------------------------------------------------
# The examples the brief gives, word for word
# ---------------------------------------------------------------------------

class TestTheRequestedExamples:

    def test_change_five_days_to_three_days(self):
        request = read_edit("Change five days to three days.", "en")
        result = apply(GRIEVANCE, request)

        assert request.action == "substitute"
        assert result.ok
        assert "for three days" in result.text
        assert "five days" not in result.text
        # And the rest of the complaint is untouched.
        assert "We informed the local office but nobody came." in result.text
        assert "The road is also damaged near the temple." in result.text

    def test_remove_the_last_sentence(self):
        request = read_edit("Remove the last sentence.", "en")
        result = apply(GRIEVANCE, request)

        assert request.action == "remove_last"
        assert result.ok
        assert "The road is also damaged" not in result.text
        assert result.text.startswith("Water has not been supplied")
        assert "We informed the local office but nobody came." in result.text

    def test_add_that_i_already_complained_last_week(self):
        request = read_edit("Add that I already complained last week.", "en")
        result = apply(GRIEVANCE, request)

        assert request.action == "append"
        assert result.ok
        assert result.text.startswith(GRIEVANCE.strip())
        assert result.text.endswith("I already complained last week")

    def test_add_one_more_point_is_not_an_edit(self):
        """It announces more rather than giving it. The microphone reopens;
        `answer_intent.continuation` owns that, and an append of the literal
        words "one more point" would have printed them in the complaint."""
        assert read_edit("Add one more point.", "en") is None
        assert read_edit("I want to add one more thing.", "en") is None

    @pytest.mark.parametrize("said,expected", [
        ("ஐந்து நாட்கள் என்பதை மூன்று நாட்கள் என்று மாற்றவும்", "substitute"),
        ("கடைசி வரியை நீக்கவும்", "remove_last"),
        ("கடந்த வாரம் புகார் கொடுத்தேன் என்று சேர்க்கவும்", "append"),
    ])
    def test_the_tamil_examples(self, said, expected):
        request = read_edit(said, "ta")

        assert request is not None, said
        assert request.action == expected, said

    def test_the_tamil_substitution_actually_substitutes(self):
        request = read_edit("ஐந்து நாட்கள் என்பதை மூன்று நாட்கள் என்று மாற்றவும்", "ta")
        result = apply(TAMIL, request)

        assert result.ok
        # Inflected, because the grievance says நாட்களாக and the ending
        # belongs to the citizen. See the test below for the exact string.
        assert "மூன்று நாட்களாக" in result.text
        assert "ஐந்து" not in result.text
        assert "சாலையும் சேதமடைந்துள்ளது." in result.text

    def test_the_tamil_substitution_carries_the_grammar_across(self):
        """The citizen says the dictionary form, ஐந்து நாட்கள். What they
        dictated, and what is on the screen, is ஐந்து நாட்களாக — the same
        words with the ending that position requires. The ending is theirs
        and it stays on."""
        request = read_edit("ஐந்து நாட்கள் என்பதை மூன்று நாட்கள் என்று மாற்றவும்", "ta")
        result = apply("எங்கள் தெருவில் ஐந்து நாட்களாக தண்ணீர் வரவில்லை.", request)

        assert result.ok
        assert result.text == "எங்கள் தெருவில் மூன்று நாட்களாக தண்ணீர் வரவில்லை."
        # Not "நாட்கள்ாக", which is not a word, and not "நாட்கள்", which drops
        # a grammatical ending out of the middle of the sentence.
        assert "நாட்கள்ாக" not in result.text

    def test_a_stem_match_will_not_reach_across_a_word(self):
        """The suffix is capped. Without the cap the stem நாட்கள would
        match the first word of a long compound and swallow all of it."""
        result = apply("எங்கள் தெருவில் ஐந்து நாட்களுக்குமேலாகவும் வரவில்லை.",
                       read_edit("ஐந்து நாட்கள் என்பதை மூன்று நாட்கள் என்று மாற்றவும்", "ta"))

        assert result.ok is False
        assert result.problem == "not_found"

    def test_the_tamil_removal_keeps_everything_else(self):
        request = read_edit("கடைசி வரியை நீக்கவும்", "ta")
        result = apply(TAMIL, request)

        assert result.ok
        assert "சாலையும்" not in result.text
        assert "தண்ணீர் வரவில்லை" in result.text

    def test_the_tamil_addition_is_placed_verbatim(self):
        request = read_edit("கடந்த வாரம் புகார் கொடுத்தேன் என்று சேர்க்கவும்", "ta")
        result = apply(TAMIL, request)

        assert result.ok
        assert result.text.endswith("கடந்த வாரம் புகார் கொடுத்தேன்")
        assert TAMIL.strip() in result.text


# ---------------------------------------------------------------------------
# The thing this replaces
# ---------------------------------------------------------------------------

class TestTheOldBehaviour:

    def test_an_edit_instruction_is_not_a_new_grievance(self):
        """`answer_intent.read` returns REPLACE for every one of these,
        because each carries content. Routed there, each would become the
        whole of somebody's complaint."""
        from app.domain.answer_intent import read as read_intent

        for said in ("Change five days to three days.",
                     "Remove the last sentence.",
                     "Add that I already complained last week."):
            assert read_intent(said, "en").intent == "replace", said
            assert read_edit(said, "en") is not None, said

    def test_the_complaint_survives_the_edit(self):
        """The specific failure: a three-sentence complaint replaced by the
        six words of the instruction."""
        result = apply(GRIEVANCE, read_edit("Change five days to three days.", "en"))

        assert len(result.text) > len(GRIEVANCE) - 10
        assert result.text != "Change five days to three days."


# ---------------------------------------------------------------------------
# No invented edits
# ---------------------------------------------------------------------------

class TestNothingIsGuessed:

    def test_no_model_is_reachable_from_here(self):
        """Checked on the imports rather than on substrings: "llm" appears
        inside `fullmatch`, and a test that fails on the letters of a regex
        method proves nothing about what the module can call."""
        source = pathlib.Path("app/domain/grievance_edit.py").read_text(encoding="utf-8")
        imports = [line.strip() for line in source.splitlines()
                   if line.startswith(("import ", "from "))]

        assert imports == ["from __future__ import annotations", "import re",
                           "from dataclasses import dataclass",
                           "from typing import Literal",
                           "from .spoken_numbers import spoken_cardinal"], imports
        # And nothing asynchronous: there is no network call to wait for.
        assert "async def" not in source
        assert "await " not in source

    @pytest.mark.parametrize("said", [
        "Change that.", "Change it.", "Please change that", "Fix that",
        "Correct that.", "Edit that", "Change the thing",
    ])
    def test_a_vague_instruction_asks_rather_than_acting(self, said):
        request = read_edit(said, "en")

        assert request is not None, said
        assert request.action == "unclear", said
        assert request.problem == "no_target", said
        assert apply(GRIEVANCE, request).ok is False, said

    def test_the_vague_tamil_instruction_too(self):
        request = read_edit("அதை மாற்றவும்", "ta")

        assert request is not None
        assert request.action == "unclear"

    def test_words_that_are_not_there_are_refused_not_approximated(self):
        request = read_edit("Change the drainage to the sewer", "en")
        result = apply(GRIEVANCE, request)

        assert result.ok is False
        assert result.problem == "not_found"
        # And nothing was written.
        assert result.text == ""

    def test_removing_the_only_sentence_is_refused(self):
        result = apply("The street light does not work.",
                       read_edit("Remove the last sentence.", "en"))

        assert result.ok is False
        assert result.problem == "only_one"

    def test_an_edit_that_would_empty_the_grievance_is_refused(self):
        one = "The street light does not work."
        result = apply(one, EditRequest("remove", target=one))

        assert result.ok is False
        assert result.problem == "would_empty"

    def test_the_result_contains_no_word_the_citizen_did_not_say(self):
        """The property an LLM cannot offer. Every word of the edited text
        came either from the grievance or from the instruction."""
        request = read_edit("Change five days to three days.", "en")
        result = apply(GRIEVANCE, request)
        allowed = set(GRIEVANCE.lower().split()) | set("change five days to three days".split())

        for word in result.text.lower().split():
            assert word.strip(".,") in {w.strip(".,") for w in allowed}, word


# ---------------------------------------------------------------------------
# Finding the words the citizen can see on the screen
# ---------------------------------------------------------------------------

class TestItFindsWhatIsThere:

    def test_a_number_said_in_words_finds_the_digits(self):
        """Sarvam writes "5 days" about as often as "five days", and the
        citizen says "five" either way. Refusing to find words that are
        plainly on the screen is the most irritating failure available."""
        grievance = "Water has not come for 5 days."
        result = apply(grievance, read_edit("Change five days to three days", "en"))

        assert result.ok, result.problem
        assert "three days" in result.text

    def test_and_the_other_way_round(self):
        grievance = "Water has not come for five days."
        result = apply(grievance, read_edit("Change 5 days to 3 days", "en"))

        assert result.ok, result.problem
        assert "3 days" in result.text

    def test_the_match_ignores_case_but_keeps_the_rest_exactly(self):
        grievance = "Five days without water. The tank is empty."
        result = apply(grievance, read_edit("Change five days to three days", "en"))

        assert result.ok
        assert "The tank is empty." in result.text

    def test_every_occurrence_is_changed(self):
        grievance = "No water for five days. Five days is too long."
        result = apply(grievance, read_edit("Change five days to three days", "en"))

        assert result.ok
        assert "five days" not in result.text.lower()
        assert result.text.lower().count("three days") == 2


# ---------------------------------------------------------------------------
# What survives
# ---------------------------------------------------------------------------

class TestEverythingElseIsPreserved:

    def test_a_removal_closes_its_own_gap_and_no_other(self):
        grievance = "The drain is blocked, the road is broken, and the light is out."
        result = apply(grievance, read_edit("Remove the road is broken", "en"))

        assert result.ok
        assert "road is broken" not in result.text
        assert "The drain is blocked" in result.text
        assert "the light is out" in result.text
        assert "  " not in result.text
        assert " ," not in result.text

    def test_nothing_is_recapitalised_or_repunctuated(self):
        grievance = "water has not come for five days"
        result = apply(grievance, read_edit("Change five days to three days", "en"))

        assert result.text == "water has not come for three days"

    def test_an_append_does_not_touch_what_is_there(self):
        result = apply(GRIEVANCE, read_edit("Add that the tank is empty", "en"))

        assert result.text[:len(GRIEVANCE.strip())] == GRIEVANCE.strip()

    def test_an_append_past_the_field_limit_is_refused_not_truncated(self):
        """A complaint silently cut in half is worse than an edit refused."""
        result = apply(GRIEVANCE, read_edit("Add that the tank is empty", "en"),
                       limit=len(GRIEVANCE) + 3)

        assert result.ok is False
        assert result.problem == "too_long"

    def test_a_substitution_past_the_limit_is_refused_too(self):
        request = read_edit("Change five days to three days", "en")
        result = apply(GRIEVANCE, request, limit=10)

        assert result.ok is False
        assert result.problem == "too_long"


# ---------------------------------------------------------------------------
# Ordinary replies are not edits
# ---------------------------------------------------------------------------

class TestItStaysOutOfTheWay:
    """Everything here must return None so the existing confirm / retry /
    continue path runs unchanged. A false positive here hijacks a plain
    "yes"."""

    @pytest.mark.parametrize("said", [
        "yes", "yeah that's right", "correct", "okay continue", "go ahead",
        "no", "that's wrong", "retry", "say it again", "start again",
        "ஆமாம்", "சரிதான்", "தொடரலாம்", "மீண்டும்", "தவறு",
        "also the drain is blocked", "I forgot to mention the light is out",
        "one more thing", "I have one more thing",
        "இன்னும் ஒரு விஷயம் இருக்கு", "மேலும் சாலை சேதமடைந்துள்ளது",
        "", "   ",
    ])
    def test_not_an_edit(self, said):
        assert read_edit(said, "en") is None, said
        assert read_edit(said, "ta") is None, said

    def test_a_dictated_sentence_containing_change_is_not_an_edit(self):
        """This only ever runs against a reply to "is that correct?", but
        the words are ordinary enough to be worth pinning."""
        assert read_edit("They promised to change the pipe last month", "en") is None

    def test_a_plain_correction_is_left_to_the_existing_path(self):
        """"No, it is 12 Kumar Street" is a REPLACE and always was. Claiming
        it here would break every short field."""
        assert read_edit("no it is 12 Kumar Street", "en") is None


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

class TestSentences:

    def test_it_splits_on_stops(self):
        assert len(sentences(GRIEVANCE)) == 3

    def test_unpunctuated_speech_is_one_sentence(self):
        """Sarvam frequently returns no punctuation at all. "Remove the last
        sentence" then has nothing to remove, and says so."""
        assert len(sentences("water has not come for five days")) == 1

    def test_it_keeps_the_punctuation_with_its_sentence(self):
        assert sentences("One. Two!")[0] == "One."
        assert sentences("One. Two!")[1] == "Two!"


class TestTheTamilMarkerIsNotALetter:
    """Found by probing, not by a failure. Tamil is searched without word
    boundaries, so a one-character marker matches inside ordinary words.

    The pattern listed the bare accusative as "ஐ". That branch could never
    match a real accusative — written Tamil forms it with the vowel SIGN ை
    on the end of a word, not the independent letter ஐ, which only ever
    begins one — and it DID match the ஐ that opens ஐந்து, five.
    """

    def test_a_lead_in_does_not_become_the_target(self):
        """"மேலும் ஐந்து நாட்கள் என்பதை…" parsed with the marker landing
        inside ஐந்து: the target came out as மேலும் and the replacement as
        a word cut in half."""
        request = read_edit(
            "\u0bae\u0bc7\u0bb2\u0bc1\u0bae\u0bcd \u0b90\u0ba8\u0bcd\u0ba4\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bcd \u0b8e\u0ba9\u0bcd\u0baa\u0ba4\u0bc8 \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bcd \u0b8e\u0ba9\u0bcd\u0bb1\u0bc1 \u0bae\u0bbe\u0bb1\u0bcd\u0bb1\u0bb5\u0bc1\u0bae\u0bcd", "ta")

        assert request is not None
        assert request.target == "\u0b90\u0ba8\u0bcd\u0ba4\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bcd"
        assert request.replacement == "\u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bcd"

    def test_and_the_edit_then_actually_lands(self):
        result = apply(
            "\u0b8e\u0b99\u0bcd\u0b95\u0bb3\u0bcd \u0ba4\u0bc6\u0bb0\u0bc1\u0bb5\u0bbf\u0bb2\u0bcd \u0b90\u0ba8\u0bcd\u0ba4\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bbe\u0b95 \u0ba4\u0ba3\u0bcd\u0ba3\u0bc0\u0bb0\u0bcd \u0bb5\u0bb0\u0bb5\u0bbf\u0bb2\u0bcd\u0bb2\u0bc8.",
            read_edit("\u0bae\u0bc7\u0bb2\u0bc1\u0bae\u0bcd \u0b90\u0ba8\u0bcd\u0ba4\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bcd \u0b8e\u0ba9\u0bcd\u0baa\u0ba4\u0bc8 \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bcd \u0b8e\u0ba9\u0bcd\u0bb1\u0bc1 \u0bae\u0bbe\u0bb1\u0bcd\u0bb1\u0bb5\u0bc1\u0bae\u0bcd", "ta"))

        assert result.ok, result.problem
        assert result.text == "\u0b8e\u0b99\u0bcd\u0b95\u0bb3\u0bcd \u0ba4\u0bc6\u0bb0\u0bc1\u0bb5\u0bbf\u0bb2\u0bcd \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bbe\u0b95 \u0ba4\u0ba3\u0bcd\u0ba3\u0bc0\u0bb0\u0bcd \u0bb5\u0bb0\u0bb5\u0bbf\u0bb2\u0bcd\u0bb2\u0bc8."

    def test_the_bare_accusative_asks_rather_than_guessing(self):
        """"ஐந்து நாட்களை மூன்று நாட்கள் ஆக மாற்றவும்" is perfectly good
        Tamil and is not read here. Adding ை as a marker would be worse than
        not reading it: ை ends ordinary Tamil words by the dozen, so the
        pattern would claim a marker in the middle of any sentence. Not
        reading it costs one clarifying question."""
        assert read_edit("\u0b90\u0ba8\u0bcd\u0ba4\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bc8 \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bcd \u0b86\u0b95 \u0bae\u0bbe\u0bb1\u0bcd\u0bb1\u0bb5\u0bc1\u0bae\u0bcd", "ta") is None

    def test_an_addition_keeps_every_word_including_its_opening(self):
        """Lead-ins are trimmed from a TARGET, which is a pointer at text
        that already exists. An addition is the citizen's own sentence, and
        trimming a word off the front of it would edit a complaint."""
        request = read_edit("\u0bae\u0bc7\u0bb2\u0bc1\u0bae\u0bcd \u0b9a\u0bbe\u0bb2\u0bc8 \u0b9a\u0bc7\u0ba4\u0bae\u0bbe\u0b95\u0bbf\u0bb5\u0bbf\u0b9f\u0bcd\u0b9f\u0ba4\u0bc1 \u0b8e\u0ba9\u0bcd\u0bb1\u0bc1 \u0b9a\u0bc7\u0bb0\u0bcd\u0b95\u0bcd\u0b95\u0bb5\u0bc1\u0bae\u0bcd", "ta")

        assert request is not None
        assert request.action == "append"
        assert request.replacement.startswith("\u0bae\u0bc7\u0bb2\u0bc1\u0bae\u0bcd")
