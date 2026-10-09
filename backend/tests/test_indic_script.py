"""Writing a citizen's Latin-typed name and address in the petition's script.

A citizen picks Malayalam and types on the Latin keyboard in front of them.
The petition used to come out with Malayalam headings and Latin values, which
is correct and does not read as a Malayalam document.

THE RULE THESE TESTS EXIST FOR is the first one in the module: never a
different place. An untidy address is a cosmetic problem; the wrong town is a
wasted journey to a government office. So the assertions below care far more
about what must NOT change — numbers, initials, text already in the script —
than about the prettiness of what does.
"""

from __future__ import annotations

import random
import string

import pytest

import app.domain.indic_tables  # noqa: F401  — registers the scripts
import app.domain.tamil_script as tamil_script
from app.domain.fields import display_value
from app.domain.indic_script import SCRIPTS, Script, for_language, render
from app.domain.languages import TAMIL


class TestTheGenericWalkIsTheTamilOne:
    """The algorithm was generalised from a module in production use.

    If it has drifted from the original then every Tamil petition this service
    produces has drifted with it, and nothing it does for a new language can
    be trusted either.
    """

    @staticmethod
    def _tamil_as_script() -> Script:
        return Script(
            code="ta", pattern=TAMIL,
            consonants=tamil_script._CONSONANTS,
            vowels_alone=tamil_script._VOWELS_ALONE,
            vowel_signs=tamil_script._VOWEL_SIGNS,
            virama="்",
            places=tamil_script.PLACES,
            address_words=tamil_script.ADDRESS_WORDS,
            names=tamil_script.NAMES,
        )

    def test_it_reproduces_tamil_exactly(self):
        spec = self._tamil_as_script()
        rnd = random.Random(20261009)
        cases = [
            "harish", "kumar", "theni", "perumal kovil street", "82/33",
            "R. Kumar", "Tamil Nadu", "80/33 perumal kovil street, theni",
            "", "   ", "+91 93441 74752", "2026/PG/44710012", "Selvam",
            "chennai", "coimbatore", "14A Main Road", "D'Souza", "madurai",
        ]
        cases += ["".join(rnd.choice(string.ascii_lowercase)
                          for _ in range(rnd.randint(2, 11))) for _ in range(300)]
        for case in cases:
            assert render(case, spec) == tamil_script.to_tamil(case), case


@pytest.mark.parametrize("language", sorted(SCRIPTS))
class TestNothingThatMustSurviveIsChanged:
    """Rule 2 and rule 3, which matter more than rule 1 being pretty."""

    def test_a_number_is_never_touched(self, language):
        """A door number, a pin code, a mobile, a reference.

        "82/33" is 82/33 in every language, and a reference number written in
        another script cannot be looked up in any register.
        """
        for value in ("82/33", "+91 93441 74752", "2026/PG/44710012",
                      "14A", "600001", "08-10-2026"):
            assert for_language(value, language) == value, value

    def test_a_lone_letter_is_left_alone(self, language):
        """It is the initial in "R. Kumar", and a spelled-out consonant in its
        place is wrong in a way a reader notices at once."""
        out = for_language("R. Kumar", language)
        assert out.startswith("R."), out

    def test_text_already_in_the_script_is_returned_unchanged(self, language):
        written = for_language("Harish", language)
        assert for_language(written, language) == written

    def test_english_is_never_transliterated(self, language):
        """The session language decides, not the script of the value."""
        assert for_language("Harish", "en") == "Harish"

    def test_an_empty_value_survives(self, language):
        for value in ("", "   ", None):
            assert for_language(value, language) == (value or "")


@pytest.mark.parametrize("language", sorted(SCRIPTS))
def test_the_result_is_written_in_that_script(language):
    """What the whole exercise is for: no Latin left in the value."""
    import re
    out = for_language("Harish", language)
    assert not re.search(r"[A-Za-z]", out), f"{language}: {out!r} still has Latin"
    assert SCRIPTS[language].pattern.search(out), f"{language}: {out!r} is not in script"


class TestTheWordsThatMustBeRight:
    """Spot checks on spellings a wrong table would quietly get wrong.

    "theni" is the one to watch. The aspirated dental — ഥേനി, थेनी — is a
    different word, and it is what a transliteration library returns for this
    input, which is why there is no library here.
    """

    EXPECTED = {
        "ml": {"Harish": "ഹരിഷ്", "Kumar": "കുമാർ", "theni": "തേനി",
               "chennai": "ചെന്നൈ"},
        "te": {"Harish": "హరీష్", "Kumar": "కుమార్", "theni": "తేని",
               "chennai": "చెన్నై"},
        "hi": {"Harish": "हरीश", "Kumar": "कुमार", "theni": "तेनी",
               "chennai": "चेन्नई"},
    }

    @pytest.mark.parametrize("language", ["ml", "te", "hi"])
    def test_each_one(self, language):
        for latin, written in self.EXPECTED[language].items():
            assert for_language(latin, language) == written, (
                f"{language}: {latin} came out as {for_language(latin, language)}")

    @pytest.mark.parametrize("language", ["ml", "te", "hi"])
    def test_a_word_ending_in_a_consonant_is_finished_properly(self, language):
        """Malayalam writes a chillu, Devanagari writes nothing, Telugu writes
        the virama. A word left with the wrong ending reads as one somebody
        stopped halfway through."""
        out = for_language("perumal", language)
        endings = {"ml": "ൽ", "te": "ల్", "hi": "ल"}
        assert out.endswith(endings[language]), f"{language}: {out!r}"


class TestTheDocumentUsesIt:
    """The display path, which is where this reaches a petition."""

    @pytest.mark.parametrize("language", ["ta", "ml", "te", "hi"])
    def test_a_name_and_address_are_written_in_the_petitions_script(self, language):
        import re
        name = display_value("person_name", "Harish", language)
        address = display_value("address", "80/33 perumal kovil street, theni", language)
        assert not re.search(r"[A-Za-z]", name), f"{language}: {name!r}"
        # The address keeps its door number, so Latin letters are gone but
        # digits remain.
        assert "80/33" in address, address
        assert not re.search(r"[A-Za-z]", address), f"{language}: {address!r}"

    def test_english_keeps_the_citizens_own_spelling(self):
        assert display_value("person_name", "Harish", "en") == "Harish"

    @pytest.mark.parametrize("language", ["ta", "ml", "te", "hi"])
    def test_the_stored_value_is_never_what_changes(self, language):
        """Display only. Their name still matches the card in their pocket."""
        stored = "Harish"
        display_value("person_name", stored, language)
        assert stored == "Harish"


@pytest.mark.parametrize("language", ["ml", "te", "hi"])
class TestTwoEntriesThatPrintedTheWrongWord:
    """Both were in the first version of the tables, both found by review, and
    both confirmed by running them rather than by reading the data."""

    def test_a_name_with_ny_in_it_keeps_all_its_letters(self, language):
        """"ny" was mapped to ഞ / ఞ / ञ — ONE consonant — so the y vanished.

        "dhanya" came out with a letter missing. Dhanya, Punya, Ananya and
        Sanya are ordinary names, and somebody whose name is printed a letter
        short on a government petition is the only person who will notice.
        """
        for latin in ("dhanya", "punya", "ananya", "sanya"):
            out = for_language(latin, language)
            # The conjunct keeps n and y as two letters joined by the virama,
            # so the rendering is longer than the single-letter version was.
            assert len(out) >= 4, f"{language}: {latin} -> {out!r} is too short to be whole"
            assert SCRIPTS[language].consonants["n"] in out, (
                f"{language}: {latin} -> {out!r} lost its n")
            assert SCRIPTS[language].consonants["y"] in out, (
                f"{language}: {latin} -> {out!r} lost its y")

    def test_st_is_not_read_as_street(self, language):
        """In an Indian address "St" is Saint at least as often as Street.

        St Thomas Church, St Mary's School, St Joseph's Hospital — churches,
        schools and hospitals are the landmarks an address is built around.
        The table turned "St Thomas Church" into "Street Thomas Church". One
        token cannot tell the two apart, so rule 1 gives the tie to leaving it
        alone.
        """
        out = for_language("St Thomas Church", language)
        assert SCRIPTS[language].address_words["street"] not in out, (
            f"{language}: {out!r} reads as 'Street Thomas Church'")

    def test_the_spelled_out_word_still_works(self, language):
        """Removing "st" must not have taken "street" with it."""
        out = for_language("main street", language)
        assert SCRIPTS[language].address_words["street"] in out, out
