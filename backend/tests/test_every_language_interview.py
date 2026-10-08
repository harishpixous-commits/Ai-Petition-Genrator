"""A citizen can finish the interview in every language the picker offers.

WHY THIS EXISTS. Every string was translated, every table carried five
languages, 1,956 tests passed — and a Malayalam citizen still could not get
past the first question. The validators had nothing to do with words: the name
pattern accepted Tamil and Latin only, so "ഹരിഷ് കുമാർ" was refused as "that
could not be read as a name", and every answer after it was read as another
attempt at the name.

Nothing in the suite walked an interview in a language, so nothing caught it.
This does. It drives the real domain functions a turn depends on, in each of
the five, and the assertions are about REACHING THE END rather than about the
wording — the wording belongs to the department and lives in petition.yaml.

Deliberately no model and no HTTP. These are the deterministic paths that
Fixed Decision 5 keeps the model off, which is exactly why they can be tested
exhaustively and must be.
"""

from __future__ import annotations

import pytest

from app.domain import languages
from app.domain.answer_intent import finished, is_refusal, read, wants_more
from app.domain.attachments import read_choice
from app.domain.fields import read_boolean, validate_address, validate_person_name

# A real answer to every question, in each language. Written as the citizen
# would type it, not transliterated.
CITIZENS = {
    "en": {
        "name": "Harish Kumar",
        "address": "80/33 Perumal Kovil Street, Theni",
        "yes": "yes", "no": "no",
        "done": "finished", "more": "one more thing",
    },
    "ta": {
        "name": "ஹரிஷ் குமார்",
        "address": "80/33 பெருமாள் கோவில் தெரு, தேனி",
        "yes": "ஆமாம்", "no": "இல்லை",
        "done": "முடிந்தது", "more": "இன்னும் ஒன்று",
    },
    "ml": {
        "name": "ഹരിഷ് കുമാർ",
        "address": "80/33 പെരുമാൾ കോവിൽ തെരുവ്, തേനി",
        "yes": "അതെ", "no": "ഇല്ല",
        "done": "കഴിഞ്ഞു", "more": "ഒന്നുകൂടി",
    },
    "te": {
        "name": "హరీష్ కుమార్",
        "address": "80/33 పెరుమాళ్ కోవెల వీధి, తేని",
        "yes": "అవును", "no": "లేదు",
        "done": "అయిపోయింది", "more": "ఇంకొకటి",
    },
    "hi": {
        "name": "हरीश कुमार",
        "address": "80/33 पेरुमाल कोविल स्ट्रीट, थेनी",
        "yes": "हाँ", "no": "नहीं",
        "done": "समाप्त", "more": "एक और",
    },
}


def test_every_offered_language_has_a_citizen_here():
    """A language added to the picker without being added here is untested."""
    assert set(CITIZENS) == set(languages.SUPPORTED), (
        f"SUPPORTED is {set(languages.SUPPORTED)}, this file covers {set(CITIZENS)}")


@pytest.mark.parametrize("language", sorted(CITIZENS))
class TestTheInterviewCanBeFinished:
    """Each step a citizen has to get through, in their own language."""

    def test_their_name_is_accepted(self, language):
        """The one that was broken. A refused name stops everything after it,
        because the form keeps asking the same question."""
        result = validate_person_name(CITIZENS[language]["name"])
        assert result.ok, f"{language}: {result.code}"

    def test_their_address_is_accepted(self, language):
        result = validate_address(CITIZENS[language]["address"])
        assert result.ok, f"{language}: {result.code}"

    def test_they_can_say_yes(self, language):
        assert read_boolean(CITIZENS[language]["yes"]) is True
        assert read(CITIZENS[language]["yes"], language).intent == "confirm"

    def test_they_can_say_no(self, language):
        assert read_boolean(CITIZENS[language]["no"]) is False
        assert is_refusal(CITIZENS[language]["no"], language) is True

    def test_they_can_decline_the_attachment_question(self, language):
        """An either/or question. A citizen whose answer matches neither branch
        is sent to the correction flow and asked which detail to change, which
        is where the Malayalam interview used to stop."""
        assert read_choice(CITIZENS[language]["no"]) == "continue"

    def test_they_can_say_they_have_finished_dictating(self, language):
        assert finished(CITIZENS[language]["done"], language) is True

    def test_they_can_say_they_have_more_to_add(self, language):
        assert wants_more(CITIZENS[language]["more"], language) is True


@pytest.mark.parametrize("language", sorted(CITIZENS))
def test_a_grievance_is_never_mistaken_for_an_ending(language):
    """The guard that makes the ending words safe to widen.

    "That's all the water we get" is a complaint, not a citizen saying they
    have finished. Reading it as an ending would cut somebody off mid-sentence
    and print half a grievance on a government form.
    """
    grievance = {
        "en": "that is all the water we get and it is not enough for us",
        "ta": "எங்களுக்கு கிடைப்பது அவ்வளவுதான் அது போதுமானதாக இல்லை",
        "ml": "ഞങ്ങൾക്ക് കിട്ടുന്നത് അത്രമാത്രം ആണ് അത് മതിയാകുന്നില്ല",
        "te": "మాకు వచ్చేది అంతే అది ఏమాత్రం చాలు కావడం లేదు",
        "hi": "हमें बस इतना ही पानी मिलता है और वह पर्याप्त नहीं है",
    }[language]
    assert finished(grievance, language) is False


@pytest.mark.parametrize("language", sorted(CITIZENS))
def test_a_name_in_one_script_is_accepted_in_any_session(language):
    """A citizen is not required to type in the script of the session.

    Somebody who picked Malayalam may still write their name in Latin letters,
    and somebody who picked English routinely does not.
    """
    for other in CITIZENS.values():
        assert validate_person_name(other["name"]).ok
