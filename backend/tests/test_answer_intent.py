"""What the citizen means when they answer "is that correct?".

These cases are the ones a real person actually says, not the ones a keyword
table would expect. Several encode bugs that reached a working state and were
only caught by reading the output aloud:

  * "okay continue" was read as a NEW ANSWER, because stripping only the first
    decision word left "continue" behind looking like content.
  * "தொடரலாம்" was read as a new answer, because removing the stem "தொடர"
    leaves "லாம்" stranded — Tamil inflects by suffix.
  * "no, 36" was read as a bare retry, because "36" was under the residue
    floor — and that is the brief's own worked example for a corrected age.

The two order-dependent traps are asserted explicitly at the bottom.
"""

from __future__ import annotations

import pytest

from app.domain.answer_intent import read

# --- agreement: every ordinary way of saying yes ---------------------------
CONFIRMS_EN = [
    "yes", "yeah", "yep", "yup", "ya", "okay", "ok", "OK.", "fine", "sure",
    "alright", "all right", "correct", "that's correct", "that is correct",
    "thats right", "right", "confirmed", "confirm", "continue", "proceed",
    "go ahead", "carry on", "next", "good", "perfect", "exactly", "done",
    "save it", "keep it", "yes please", "okay continue", "yeah that's right",
    "yes, that is correct", "ok sir", "correct, thank you", "yes thanks",
]

CONFIRMS_TA = [
    "ஆம்", "ஆமாம்", "சரி", "சரிதான்", "ஓகே", "உறுதி",
    "தொடரலாம்", "அடுத்தது போகலாம்", "இதுதான்", "பரவாயில்லை",
    "ஆமாம் சரி", "சரி நன்றி",
]


@pytest.mark.parametrize("said", CONFIRMS_EN)
def test_english_agreement(said: str) -> None:
    assert read(said, "en").intent == "confirm", said


@pytest.mark.parametrize("said", CONFIRMS_TA)
def test_tamil_agreement(said: str) -> None:
    assert read(said, "ta").intent == "confirm", said


# --- refusal with no correction in it: ask again ---------------------------
RETRIES_EN = [
    "no", "nope", "nah", "wrong", "that's wrong", "that is wrong",
    "incorrect", "not correct", "not right", "that's not correct",
    "retry", "try again", "say again", "let me say again", "repeat",
    "repeat it", "again please", "let me repeat", "change it", "redo",
    "start over", "that's a mistake", "no, let me say it again",
]

RETRIES_TA = [
    "இல்லை", "தவறு", "சரியில்லை", "மீண்டும்", "மறுபடியும்",
    "மாற்ற வேண்டும்", "திரும்ப சொல்லுகிறேன்", "இல்லை மீண்டும் சொல்கிறேன்",
    "வேண்டாம்",
]


@pytest.mark.parametrize("said", RETRIES_EN)
def test_english_refusal_without_a_correction(said: str) -> None:
    got = read(said, "en")
    assert got.intent == "retry", f"{said} -> {got}"
    assert got.replacement == ""


@pytest.mark.parametrize("said", RETRIES_TA)
def test_tamil_refusal_without_a_correction(said: str) -> None:
    got = read(said, "ta")
    assert got.intent == "retry", f"{said} -> {got}"
    assert got.replacement == ""


# --- correction: the new answer is already in the sentence -----------------
# Making the citizen repeat what they just said is asking a third time.
REPLACEMENTS = [
    ("no, it is 12 Kumar Street", "12 Kumar Street"),
    ("no it's twelve Kumar Street", "twelve Kumar Street"),
    ("No, 36.", "36"),
    ("no, 36", "36"),
    ("wrong, my name is Harish Kumar", "my name is Harish Kumar"),
    ("actually 24 Gandhi Road", "24 Gandhi Road"),
    ("change it to 24 Gandhi Road", "24 Gandhi Road"),
    ("I said Chennai 600001", "Chennai 600001"),
    ("no, Madurai", "Madurai"),
]


@pytest.mark.parametrize("said,expected", REPLACEMENTS)
def test_a_correction_carries_its_own_answer(said: str, expected: str) -> None:
    got = read(said, "en")
    assert got.intent == "replace", f"{said} -> {got}"
    assert got.replacement == expected, f"{said} -> {got.replacement!r}"


def test_the_citizens_own_words_survive_intact() -> None:
    """The replacement is the ORIGINAL text, not the normalised residue.

    An earlier version returned the residue, which is lowercased, has its
    punctuation removed and has filler words taken out. "Water has not been
    supplied for five days" came back as "water has not been supplied five
    days" — a grievance with a word missing, printed on a government form.
    """
    got = read("No, water has not been supplied for five days.", "en")
    assert got.intent == "replace"
    assert got.replacement == "water has not been supplied for five days"


def test_tamil_correction_keeps_the_answer() -> None:
    got = read("இல்லை, மதுரை", "ta")
    assert got.intent == "replace"
    assert "மதுரை" in got.replacement


# --- the two traps, both of which reverse the meaning ----------------------
def test_not_correct_is_never_read_as_correct() -> None:
    """"not correct" contains "correct". Checking agreement first would
    commit the wrong value to a government form."""
    assert read("not correct", "en").intent == "retry"
    assert read("that is not correct", "en").intent == "retry"


def test_sariyillai_is_never_read_as_sari() -> None:
    """"சரியில்லை" (not right) contains "சரி" (right)."""
    assert read("சரியில்லை", "ta").intent == "retry"


# --- nothing usable ---------------------------------------------------------
@pytest.mark.parametrize("said", ["", "   ", None, "...", "um"])
def test_silence_and_noise_ask_again(said: str | None) -> None:
    """Never a confirm. An empty or unintelligible reply must not be taken
    as consent to save what was read back."""
    assert read(said, "en").intent == "retry"  # type: ignore[arg-type]


def test_code_switching_is_ordinary_here() -> None:
    """A Tamil session answered with "ok" is not a mistake."""
    assert read("ok", "ta").intent == "confirm"
    assert read("சரி", "en").intent == "confirm"


def test_no_path_from_speech_to_a_saved_field_without_consent() -> None:
    """A replacement is a CANDIDATE, never a commit: it goes back for its own
    read-back. This asserts the contract the caller relies on — a replace
    always carries the text to read back, so there is nothing to commit
    silently."""
    got = read("no, 36", "en")
    assert got.intent == "replace"
    assert got.replacement, "a replacement with no text would commit nothing"
