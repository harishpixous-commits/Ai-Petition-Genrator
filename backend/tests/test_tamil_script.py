"""A citizen's own words, written in Tamil script for a Tamil petition.

A citizen picks Tamil and then types on the Latin keyboard in front of them.
The petition used to come out with Tamil headings over English values —
correct, and not a Tamil document. These values are now rendered in Tamil.

THE RULE THAT MATTERS MOST, and the reason there is no model behind this: a
translator asked for Coimbatore in Tamil once returned கோயம்பேடூர் —
Koyambedu, a locality in Chennai, three hundred kilometres away. A petition
that names the wrong town is not a petition with a translation error in it;
it is a petition that will not be acted on. So a fixed table decides the
places, phonetics handle the rest, and nothing here can invent a locality.

THE OTHER TWO, in order: numbers are never touched, and the stored value is
never overwritten — this runs at display time, and switching the petition
back to English shows the citizen's own spelling again.
"""

from __future__ import annotations

import pytest

from app.domain.fields import display_value
from app.domain.letter import build_letter_text, verification_targets
from app.domain.tamil_script import PLACES, for_language, to_tamil
from app.domain.templates import the_template

FIELDS = {
    "applicant_name": "Harish",
    "age": 23,
    "mobile": "9344174752",
    "address": "82/33 perumal kovil street, theni",
    "grievance": "எங்கள் தெருவில் ஐந்து நாட்களாக தண்ணீர் வரவில்லை.",
}


class TestTheCasesThatWereAskedFor:

    @pytest.mark.parametrize("english,tamil", [
        ("Harish", "ஹரிஷ்"),
        ("82/33 perumal kovil street, theni", "82/33 பெருமாள் கோவில் தெரு, தேனி"),
        ("Theni", "தேனி"),
        ("Coimbatore", "கோயம்புத்தூர்"),
        ("Chennai", "சென்னை"),
        ("Madurai", "மதுரை"),
    ])
    def test_it_renders_them(self, english, tamil):
        assert to_tamil(english) == tamil


class TestItCanNeverNameADifferentPlace:
    """The Koyambedu rule. Everything else in this file is tidiness; this is
    the one that decides whether a citizen's journey is wasted."""

    def test_coimbatore_is_coimbatore(self):
        assert to_tamil("Coimbatore") == "கோயம்புத்தூர்"
        assert to_tamil("Coimbatore") != "கோயம்பேடூர்"

    def test_the_places_come_from_a_table_not_a_guess(self):
        """A table cannot return a locality three hundred kilometres away.
        A model can, and did."""
        assert len(PLACES) > 40
        for english, tamil in PLACES.items():
            assert english == english.lower(), english
            assert tamil.strip(), english

    def test_nothing_here_calls_a_model(self):
        """No network on the render path, and nothing that can improvise."""
        import pathlib

        source = pathlib.Path("app/domain/tamil_script.py").read_text(encoding="utf-8")
        for forbidden in ("httpx", "chat_json", "llm", "async def", "await "):
            assert forbidden not in source, forbidden

    def test_an_unknown_word_is_rendered_by_sound_not_replaced(self):
        """Phonetics can spell a name imperfectly. It cannot swap in a
        different name, which is the failure that matters."""
        got = to_tamil("Zzyxville")

        assert got != "Zzyxville", "it should still be written in Tamil"
        assert not any(place in got for place in PLACES.values()), got


class TestNumbersSurviveExactly:
    """A door number, a pin code and a mobile number are the same in every
    language, and a reference number in Tamil digits cannot be looked up."""

    @pytest.mark.parametrize("value", [
        "82/33", "+91 93441 74752", "641004", "14A", "2026/PG/44710012",
        "23-09-2026",
    ])
    def test_digits_and_punctuation_pass_through(self, value):
        assert value in to_tamil(f"door {value} street")

    def test_a_lone_letter_is_left_alone(self):
        """The "A" of door number 14A, and the initial in "R. Kumar". "அ" in
        place of either is wrong in a way a reader notices at once."""
        assert "14A" in to_tamil("no 14A")
        assert to_tamil("R. Kumar").startswith("R.")


class TestTheStoredValueIsNeverChanged:

    def test_rendering_does_not_touch_the_record(self):
        fields = dict(FIELDS)
        build_letter_text(template=the_template(), fields=fields, language="ta",
                          composition=None, session_id="abc-123")

        assert fields["applicant_name"] == "Harish"
        assert fields["address"] == "82/33 perumal kovil street, theni"

    def test_english_shows_the_citizens_own_spelling(self):
        """Their name still matches the card in their pocket."""
        assert display_value("person_name", "Harish", "en") == "Harish"
        assert display_value("address", "82/33 perumal kovil street, theni",
                             "en") == "82/33 perumal kovil street, theni"

    def test_switching_language_is_reversible(self):
        tamil = display_value("person_name", "Harish", "ta")
        english = display_value("person_name", "Harish", "en")

        assert tamil != english
        assert english == "Harish"

    def test_a_value_already_in_tamil_is_left_as_it_is(self):
        """A citizen who typed or dictated in Tamil has already said it the
        way they want it said."""
        assert for_language("ரவி குமார்", "ta") == "ரவி குமார்"


class TestTheWholeLetterIsOneLanguage:

    def test_the_tamil_petition_has_no_latin_in_its_own_words(self):
        text = build_letter_text(template=the_template(), fields=dict(FIELDS),
                                 language="ta", composition=None,
                                 session_id="abc-123")
        head = text[:text.index("பெறுநர்")]

        assert "ஹரிஷ்" in head
        assert "பெருமாள் கோவில் தெரு" in head
        assert "Harish" not in head
        assert "perumal" not in head

    def test_the_place_line_matches_the_address(self):
        """"இடம்: theni" under a Tamil heading is the seam showing."""
        text = build_letter_text(template=the_template(), fields=dict(FIELDS),
                                 language="ta", composition=None,
                                 session_id="abc-123")

        assert "இடம்: தேனி" in text

    def test_the_signature_is_in_the_same_script_as_the_letter(self):
        """REPORTED FROM A PRINT PREVIEW. The From block at the top said
        ஹரிஷ் and the line under இப்படிக்கு, said Harish — on the same
        sheet of paper. The sign-off was the one place the name was written
        out raw instead of through `display_value`."""
        text = build_letter_text(template=the_template(), fields=dict(FIELDS),
                                 language="ta", composition=None,
                                 session_id="abc-123")
        closing = text[text.index("இப்படிக்கு,"):]

        assert "ஹரிஷ்" in closing
        assert "Harish" not in closing

    def test_and_the_english_one_still_signs_in_english(self):
        text = build_letter_text(template=the_template(), fields=dict(FIELDS),
                                 language="en", composition=None,
                                 session_id="abc-123")
        closing = text[text.index("Yours faithfully,"):]

        assert "Harish" in closing

    def test_the_english_petition_is_unchanged(self):
        text = build_letter_text(template=the_template(), fields=dict(FIELDS),
                                 language="en", composition=None,
                                 session_id="abc-123")

        assert "Harish" in text
        assert "82/33 perumal kovil street, theni" in text
        assert "ஹரிஷ்" not in text


class TestTheGrievanceIsNotTouched:
    """Locked: the complaint is placed in the citizen's own words. An English
    sentence spelled in Tamil letters is not a Tamil sentence — it is an
    unreadable one."""

    def test_an_english_grievance_stays_english_in_a_tamil_petition(self):
        fields = {**FIELDS, "grievance": "The street light has not worked."}
        text = build_letter_text(template=the_template(), fields=fields,
                                 language="ta", composition=None,
                                 session_id="abc-123")

        assert "The street light has not worked." in text

    def test_display_value_leaves_free_text_alone(self):
        assert display_value("text", "The drain is blocked.", "ta") == (
            "The drain is blocked.")


class TestVerificationLooksForWhatIsOnThePage:
    """The document is checked by searching the generated file for the values
    it should contain. If the page is transliterated and the check is not, it
    searches for a string that was never in it and withholds a correct
    petition."""

    def test_the_targets_are_the_rendered_forms(self):
        targets = verification_targets(the_template(), dict(FIELDS), "ta")

        assert targets["applicant_name"] == "ஹரிஷ்"
        assert targets["address"] == "82/33 பெருமாள் கோவில் தெரு, தேனி"

    def test_and_the_document_actually_contains_them(self):
        text = build_letter_text(template=the_template(), fields=dict(FIELDS),
                                 language="ta", composition=None,
                                 session_id="abc-123")
        targets = verification_targets(the_template(), dict(FIELDS), "ta")

        for name, expected in targets.items():
            assert expected in text, name
