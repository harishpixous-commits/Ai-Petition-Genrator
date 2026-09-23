"""Validator tests.

These matter more than the rest of the suite. Every other component degrades
gracefully — no model means the standard wording, no LibreOffice means DOCX
only — but a validator that accepts a malformed Aadhaar number produces a
petition that a Taluk office rejects weeks later, and the citizen pays for it.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.fields import (
    digits_from_speech,
    display_value,
    read_boolean,
    validate_aadhaar,
    validate_address,
    validate_age,
    validate_amount,
    validate_date,
    validate_dob,
    validate_email,
    validate_mobile,
    validate_past_date,
    validate_person_name,
    validate_pincode,
    validate_text,
    verhoeff_valid,
)

# Verhoeff-valid, never issued, safe to keep in a repository.
VALID_AADHAAR = "234567890124"


# --------------------------------------------------------------------------- #
# Spoken input
# --------------------------------------------------------------------------- #


class TestDigitsFromSpeech:
    def test_plain_digits(self):
        assert digits_from_speech("641001") == "641001"

    def test_spaced_digits_from_dictation(self):
        assert digits_from_speech("2 3 4 5 6 7 8 9 0 1 2 4") == VALID_AADHAAR

    def test_english_number_words(self):
        assert digits_from_speech("six four one zero zero one") == "641001"

    def test_double_and_triple(self):
        assert digits_from_speech("nine double four triple two") == "9442 22".replace(" ", "")

    def test_tamil_number_words(self):
        assert digits_from_speech("ஆறு நான்கு ஒன்று பூஜ்ஜியம் பூஜ்ஜியம் ஒன்று") == "641001"

    def test_tamil_digit_glyphs(self):
        assert digits_from_speech("௬௪௧௦௦௧") == "641001"

    def test_mixed_separators(self):
        assert digits_from_speech("2345-6789/0124") == VALID_AADHAAR

    def test_no_digits(self):
        assert digits_from_speech("my name is Ravi") == ""


# --------------------------------------------------------------------------- #
# Aadhaar
# --------------------------------------------------------------------------- #


class TestAadhaar:
    def test_accepts_valid(self):
        result = validate_aadhaar(VALID_AADHAAR)
        assert result.ok and result.value == VALID_AADHAAR

    def test_accepts_grouped(self):
        assert validate_aadhaar("2345 6789 0124").value == VALID_AADHAAR

    def test_accepts_spoken(self):
        assert validate_aadhaar("two three four five six seven eight nine zero one two four").ok

    def test_rejects_short(self):
        result = validate_aadhaar("2345 6789")
        assert not result.ok and result.code == "aadhaar.length"
        assert result.detail == {"got": 8}

    def test_rejects_leading_zero_or_one(self):
        # 012345678901 would otherwise pass a naive length check.
        assert validate_aadhaar("012345678901").code == "aadhaar.leading"
        assert validate_aadhaar("112345678901").code == "aadhaar.leading"

    def test_rejects_transposition(self):
        """The reason the checksum is here at all: a swapped pair of digits is
        the commonest error when a number is read aloud, and it passes every
        length and prefix check."""
        swapped = VALID_AADHAAR[:9] + VALID_AADHAAR[10] + VALID_AADHAAR[9] + VALID_AADHAAR[11]
        assert swapped != VALID_AADHAAR
        assert validate_aadhaar(swapped).code == "aadhaar.checksum"

    def test_rejects_empty(self):
        assert validate_aadhaar("").code == "aadhaar.empty"

    def test_rejects_all_zeroes(self):
        """Caught twice over: the leading digit is checked before the checksum,
        and the checksum would reject it anyway."""
        assert not verhoeff_valid("000000000000")
        assert validate_aadhaar("000000000000").code == "aadhaar.leading"


# --------------------------------------------------------------------------- #
# Contact and postal
# --------------------------------------------------------------------------- #


class TestMobile:
    @pytest.mark.parametrize(
        "raw",
        ["9876543210", "+91 98765 43210", "098765 43210", "0091-9876543210",
         "nine eight seven six five four three two one zero"],
    )
    def test_accepts_national_forms(self, raw):
        assert validate_mobile(raw).value == "9876543210"

    def test_rejects_wrong_series(self):
        assert validate_mobile("5876543210").code == "mobile.series"

    def test_rejects_short(self):
        assert validate_mobile("98765").code == "mobile.length"

    def test_rejects_all_same_digit(self):
        assert validate_mobile("9999999999").code == "mobile.repeated"


class TestPincode:
    def test_accepts_valid(self):
        assert validate_pincode("641001").value == "641001"

    def test_rejects_leading_zero(self):
        assert validate_pincode("041001").code == "pincode.leading"

    def test_rejects_wrong_length(self):
        assert validate_pincode("64100").code == "pincode.length"


class TestEmail:
    def test_accepts_plain(self):
        assert validate_email("Ravi.Kumar@Example.COM").value == "ravi.kumar@example.com"

    def test_converts_dictated_form(self):
        """Dictation produces "ravi at example dot com" and a naive validator
        rejects a perfectly good address."""
        assert validate_email("ravi at example dot com").value == "ravi@example.com"

    def test_rejects_incomplete(self):
        assert validate_email("ravi@").code == "email.format"


# --------------------------------------------------------------------------- #
# People
# --------------------------------------------------------------------------- #


class TestPersonName:
    def test_accepts_and_title_cases_latin(self):
        assert validate_person_name("ravi kumar").value == "Ravi Kumar"

    def test_strips_lead_in(self):
        assert validate_person_name("my name is Ravi Kumar").value == "Ravi Kumar"

    def test_strips_tamil_lead_in(self):
        assert validate_person_name("என் பெயர் ரவி").value == "ரவி"

    def test_accepts_tamil_unchanged(self):
        assert validate_person_name("ரவி குமார்").value == "ரவி குமார்"

    def test_accepts_initials_and_punctuation(self):
        assert validate_person_name("K. Ravi-Kumar").ok
        assert validate_person_name("D'Souza").ok

    def test_rejects_digits(self):
        assert validate_person_name("Ravi 123").code == "name.digits"

    def test_rejects_too_short(self):
        assert validate_person_name("R").code == "name.short"


class TestAge:
    def test_accepts_number(self):
        assert validate_age("45").value == 45

    def test_accepts_with_words(self):
        assert validate_age("I am 45 years old").value == 45

    def test_accepts_tamil_words(self):
        assert validate_age("நான்கு ஐந்து").value == 45

    def test_rejects_out_of_range(self):
        result = validate_age("150")
        assert result.code == "age.range" and result.detail == {"got": 150}

    def test_rejects_a_date_given_as_an_age(self):
        """A citizen answering "age" with a date of birth must be re-asked, not
        silently truncated to the first two digits."""
        assert validate_age("15-03-1980").code == "age.format"


class TestAddress:
    def test_accepts_full_address(self):
        assert validate_address("12 Gandhi Street, Peelamedu, Coimbatore").ok

    def test_rejects_too_short(self):
        assert validate_address("Coimbatore").code == "address.short"


# --------------------------------------------------------------------------- #
# Dates and money
# --------------------------------------------------------------------------- #


class TestDates:
    def test_day_first_slash(self):
        assert validate_date("03/04/2020").value == "2020-04-03"

    def test_day_first_is_not_guessed(self):
        """An Indian government form is always day-first. A library default that
        reads 03/04 as March would silently change the date."""
        assert validate_date("15-03-2020").value == "2020-03-15"

    def test_english_month_name(self):
        assert validate_date("15 March 2020").value == "2020-03-15"

    def test_tamil_month_name(self):
        assert validate_date("15 மார்ச் 2020").value == "2020-03-15"

    def test_bare_year_anchors_to_january(self):
        assert validate_date("2015").value == "2015-01-01"

    def test_rejects_unparseable(self):
        assert validate_date("sometime last year").code == "date.format"

    def test_rejects_impossible_day(self):
        assert validate_date("31-02-2020").code == "date.format"

    def test_past_date_rejects_future(self):
        future = (date.today() + timedelta(days=30)).strftime("%d-%m-%Y")
        assert validate_past_date(future).code == "date.future"

    def test_dob_rejects_implausible_age(self):
        assert validate_dob("01-01-1850").code in ("date.range", "dob.range")


class TestAmount:
    def test_plain(self):
        assert validate_amount("50000").value == 50000

    def test_indian_grouping(self):
        assert validate_amount("1,20,000").value == 120000

    def test_lakh(self):
        assert validate_amount("2 lakh").value == 200000

    def test_tamil_lakh(self):
        assert validate_amount("2 லட்சம்").value == 200000

    def test_rejects_nonsense(self):
        assert validate_amount("quite a lot").code == "amount.format"


# --------------------------------------------------------------------------- #
# Yes / no
# --------------------------------------------------------------------------- #


class TestBoolean:
    @pytest.mark.parametrize("raw", ["yes", "yeah", "correct", "ஆம்", "சரி"])
    def test_positive(self, raw):
        assert read_boolean(raw) is True

    @pytest.mark.parametrize("raw", ["no", "not yet", "இல்லை", "வேண்டாம்"])
    def test_negative(self, raw):
        assert read_boolean(raw) is False

    def test_self_correction_takes_the_later_word(self):
        """"no, yes I received it" is the speaker correcting their own first word."""
        assert read_boolean("no, yes I received it") is True

    def test_ambiguous_returns_none(self):
        assert read_boolean("hmm") is None


# --------------------------------------------------------------------------- #
# Read-back formatting
# --------------------------------------------------------------------------- #


class TestDisplayValue:
    def test_aadhaar_grouped_as_printed(self):
        """A citizen confirming a value must see it in the form the letter will
        carry, or they are confirming something else."""
        assert display_value("aadhaar", VALID_AADHAAR) == "2345 6789 0124"

    def test_mobile(self):
        assert display_value("mobile", "9876543210") == "+91 98765 43210"

    def test_date(self):
        assert display_value("date", "2020-03-15") == "15-03-2020"

    def test_boolean_in_tamil(self):
        assert display_value("boolean", True, "ta") == "ஆம்"


def test_text_accepts_a_grievance():
    result = validate_text("The street light outside my house has not worked for three months.")
    assert result.ok and result.value.startswith("The street light")


# ---------------------------------------------------------------------------
# A number said the way people actually say it
# ---------------------------------------------------------------------------

class TestANumberSaidInTwos:
    """REPORTED FROM A TAMIL SESSION. The citizen was asked for their mobile
    number, said it, and the box filled with Tamil words — so the transcript
    reaching the form was:

        தொண்ணூற்றி மூன்று நாற்பத்தி நாலு பதினேழு நாற்பத்தி ஏழு ஐம்பத்தி இரண்டு

    which is 93 44 17 47 52 — 9344174752, said the way a phone number is
    printed and the way everybody here reads one out.

    `digits_from_speech` returned "3472".

    THAT IS THE DANGEROUS KIND OF WRONG. Only the single-digit words were in
    its tables, so every tens word carried no digit of its own and was
    dropped in silence: மூன்று, நாலு, ஏழு, இரண்டு survived and தொண்ணூற்றி,
    நாற்பத்தி, பதினேழு, ஐம்பத்தி did not. Not empty, not obviously broken —
    four digits that look like the start of a number, from somebody who said
    ten. A petition carrying it gives the office no way to reach the citizen.

    `validate_age` had known for a while: it tries `spoken_cardinal` first
    and says in a comment that "twenty three" arrives here as "3". The
    workaround guarded the age field and nothing else.
    """

    def test_the_number_from_the_report(self):
        said = ("\u0ba4\u0bca\u0ba3\u0bcd\u0ba3\u0bc2\u0bb1\u0bcd\u0bb1\u0bbf \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0bb1\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0ba8\u0bbe\u0bb2\u0bc1 \u0baa\u0ba4\u0bbf\u0ba9\u0bc7\u0bb4\u0bc1 "
                "\u0ba8\u0bbe\u0bb1\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b8f\u0bb4\u0bc1 \u0b90\u0bae\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b87\u0bb0\u0ba3\u0bcd\u0b9f\u0bc1")

        assert digits_from_speech(said) == "9344174752"

    def test_and_it_reaches_the_field_as_a_mobile_number(self):
        said = ("\u0ba4\u0bca\u0ba3\u0bcd\u0ba3\u0bc2\u0bb1\u0bcd\u0bb1\u0bbf \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0bb1\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0ba8\u0bbe\u0bb2\u0bc1 \u0baa\u0ba4\u0bbf\u0ba9\u0bc7\u0bb4\u0bc1 "
                "\u0ba8\u0bbe\u0bb1\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b8f\u0bb4\u0bc1 \u0b90\u0bae\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b87\u0bb0\u0ba3\u0bcd\u0b9f\u0bc1")
        result = validate_mobile(said)

        assert result.ok
        assert result.value == "9344174752"

    def test_the_habit_of_saying_correct_afterwards_is_not_a_digit(self):
        """The citizen in the report ended with "\u0b9a\u0bb0\u0bbf \u0b9a\u0bb0\u0bbf" \u2014 a habit left over
        from the assistant that used to ask them to confirm out loud."""
        said = ("\u0ba4\u0bca\u0ba3\u0bcd\u0ba3\u0bc2\u0bb1\u0bcd\u0bb1\u0bbf \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1 \u0ba8\u0bbe\u0bb1\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0ba8\u0bbe\u0bb2\u0bc1 \u0baa\u0ba4\u0bbf\u0ba9\u0bc7\u0bb4\u0bc1 "
                "\u0ba8\u0bbe\u0bb1\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b8f\u0bb4\u0bc1 \u0b90\u0bae\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b87\u0bb0\u0ba3\u0bcd\u0b9f\u0bc1 \u0b9a\u0bb0\u0bbf \u0b9a\u0bb0\u0bbf")

        assert validate_mobile(said).value == "9344174752"

    @pytest.mark.parametrize("said,expected", [
        ("ninety three forty four seventeen forty seven fifty two", "9344174752"),
        ("\u0ba4\u0bca\u0ba3\u0bcd\u0ba3\u0bc2\u0bb1\u0bcd\u0bb1\u0bbf \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1", "93"),
        ("\u0b90\u0bae\u0bcd\u0baa\u0ba4\u0bcd\u0ba4\u0bbf \u0b87\u0bb0\u0ba3\u0bcd\u0b9f\u0bc1", "52"),
        ("seventeen", "17"),
        ("\u0baa\u0ba4\u0bbf\u0ba9\u0bc7\u0bb4\u0bc1", "17"),
        ("ninety", "90"),
        ("\u0b87\u0bb0\u0bc1\u0baa\u0ba4\u0bc1", "20"),
    ])
    def test_both_languages_read_the_same_way(self, said, expected):
        assert digits_from_speech(said) == expected

    def test_a_teen_is_already_two_digits(self):
        """"Seventeen" is 17, not 1 and 7 \u2014 and not 7 with the ten lost."""
        assert digits_from_speech("nineteen seventeen") == "1917"

    def test_a_tens_word_only_takes_a_unit_that_follows_it(self):
        """"Ninety three" is 93. "Ninety, three" spoken as two separate
        numbers is the same sound, and 93 is the reading that matches how a
        number is dictated."""
        assert digits_from_speech("ninety three") == "93"
        assert digits_from_speech("three ninety") == "390"

    def test_zero_is_never_swallowed_by_a_tens_word(self):
        """"Ninety zero" is not how anybody says a number, and folding it
        into 90 would lose a digit the citizen actually said."""
        assert digits_from_speech("ninety zero") == "900"


class TestTheOldBehaviourIsStillIntact:
    """Everything that worked before the tens words were understood. This
    function is read by the mobile, Aadhaar, PAN, ration-card and voter-id
    fields, and a change here reaches all of them."""

    @pytest.mark.parametrize("said,expected", [
        ("nine three four four one seven four seven five two", "9344174752"),
        ("93441 74752", "9344174752"),
        ("my number is 9344174752", "9344174752"),
        ("double nine three four", "9934"),
        ("triple seven one two", "77712"),
        ("\u0b92\u0ba9\u0bcd\u0bb1\u0bc1 \u0b87\u0bb0\u0ba3\u0bcd\u0b9f\u0bc1 \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1", "123"),
        ("no digits here at all", ""),
        ("", ""),
    ])
    def test_unchanged(self, said, expected):
        assert digits_from_speech(said) == expected

    def test_an_age_is_still_a_cardinal_not_a_digit_run(self):
        """`validate_age` reads "twenty three" as the number 23. It reaches
        `spoken_cardinal` before this function and must keep doing so \u2014
        digits_from_speech now returns "23" for it too, but an age of
        "one hundred and five" is a cardinal and not three digits."""
        assert validate_age("twenty three").value == 23
        assert validate_age("\u0b87\u0bb0\u0bc1\u0baa\u0ba4\u0bcd\u0ba4\u0bc1 \u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1").value == 23
