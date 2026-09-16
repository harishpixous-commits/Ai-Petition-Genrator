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
