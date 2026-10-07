"""The one table every other module asks about a language.

These tests are deliberately pedantic about the script blocks. A range that is
one codepoint out, or that went through a bad encoding on its way into the
file, still compiles and still matches *something* — it just stops matching the
language it was named after, and nothing anywhere raises.
"""

from __future__ import annotations

import re

import pytest

from app.domain import languages as L

# Real words, written as escapes so that no encoding between here and the test
# runner can quietly change what is being asserted.
SAMPLES = {
    "ta": "வணிமை",          # வணிமை
    "ml": "പരാതി",          # പരാതി  (petition)
    "te": "వినతి",          # వినతి  (petition)
    "hi": "प्रार्थना",  # प्रार्थना
    "en": "petition",
}


class TestEveryKnownLanguageIsComplete:
    @pytest.mark.parametrize("code", L.KNOWN)
    def test_it_has_every_field_filled_in(self, code):
        row = L.BY_CODE[code]
        for field in ("english_name", "endonym", "bcp47", "font_family", "font_file", "ocr"):
            assert getattr(row, field), f"{code}.{field} is empty"

    @pytest.mark.parametrize("code", L.KNOWN)
    def test_its_font_file_actually_ships(self, code):
        from app.config import BASE_DIR
        font = BASE_DIR / "app" / "assets" / "fonts" / L.BY_CODE[code].font_file
        assert font.is_file(), f"{code} names {font.name}, which is not in app/assets/fonts"

    def test_the_endonym_is_written_in_that_language_s_own_script(self):
        """A picker offering "Malayalam" in Latin helps nobody looking for it."""
        for code in ("ta", "ml", "te", "hi"):
            row = L.BY_CODE[code]
            assert row.script is not None and row.script.search(row.endonym), (
                f"{code} endonym {row.endonym!r} is not in its own script")
        assert L.BY_CODE["en"].endonym == "English"

    def test_english_has_no_script_test(self):
        """English is the fallback, not something to detect."""
        assert L.BY_CODE["en"].script is None


class TestTheScriptBlocksAreTheRightOnes:
    @pytest.mark.parametrize("code", ["ta", "ml", "te", "hi"])
    def test_a_real_word_is_recognised(self, code):
        assert L.script_of(SAMPLES[code]) == code

    @pytest.mark.parametrize("code", ["ta", "ml", "te", "hi"])
    def test_no_other_script_claims_it(self, code):
        """The blocks are adjacent. An off-by-one range would overlap."""
        for other in ("ta", "ml", "te", "hi"):
            row = L.BY_CODE[other]
            matched = bool(row.script.search(SAMPLES[code]))
            assert matched == (other == code), (
                f"{other} script {'matched' if matched else 'missed'} {code} text")

    def test_latin_is_not_an_indic_script(self):
        assert L.script_of(SAMPLES["en"]) is None
        assert L.script_of("") is None
        assert L.script_of("9344174752") is None

    def test_none_is_not_the_same_as_english(self):
        """The distinction a caller must not collapse.

        A phone number carries no script. Treating that as "the citizen wants
        English" is how a Malayalam session gets switched to English on the
        turn the citizen types their mobile number.
        """
        assert L.script_of("23") is None
        assert L.has_indic("23") is False


class TestTheRangesSurvivedBeingWrittenDown:
    """Guards against a bad encoding, which is why they are built from numbers."""

    @pytest.mark.parametrize("pattern,first,last", [
        (L.TAMIL, 0x0B80, 0x0BFF),
        (L.MALAYALAM, 0x0D00, 0x0D7F),
        (L.TELUGU, 0x0C00, 0x0C7F),
        (L.DEVANAGARI, 0x0900, 0x097F),
    ])
    def test_both_ends_of_every_block_match(self, pattern, first, last):
        assert pattern.search(chr(first)), "first codepoint of the block does not match"
        assert pattern.search(chr(last)), "last codepoint of the block does not match"
        assert not pattern.search(chr(first - 1)), "the block starts too early"
        assert not pattern.search(chr(last + 1)), "the block ends too late"

    def test_the_spliceable_ranges_build_a_working_class(self):
        every = re.compile("[" + L.INDIC_RANGES + "]")
        for code in ("ta", "ml", "te", "hi"):
            assert every.search(SAMPLES[code]), f"{code} not covered by INDIC_RANGES"
        assert not every.search("petition")

    def test_indic_ranges_cover_the_marks_that_word_does_not(self):
        """The reason INDIC_RANGES exists at all.

        Python's `\\w` misses Indic combining marks, so a pattern that cleans
        text with `[^\\w\\s]` strips the viramas and vowel signs out of every
        one of these languages and leaves a mutilated string behind.
        """
        marks = ["്", "్", "्", "ാ", "்"]
        every = re.compile("[" + L.INDIC_RANGES + "]")
        for mark in marks:
            assert not re.match(r"\w", mark), f"{mark!r} unexpectedly matched \\w"
            assert every.search(mark), f"{mark!r} is not inside INDIC_RANGES"


class TestKnownIsNotTheSameAsOffered:
    def test_all_five_are_known(self):
        assert set(L.KNOWN) == {"en", "ta", "ml", "te", "hi"}

    def test_supported_is_a_subset_of_known(self):
        assert set(L.SUPPORTED) <= set(L.KNOWN)

    def test_english_is_always_offered_and_is_the_default(self):
        assert "en" in L.SUPPORTED
        assert L.DEFAULT == "en"

    def test_is_supported_rejects_a_language_that_is_merely_known(self):
        for code in set(L.KNOWN) - set(L.SUPPORTED):
            assert L.is_supported(code) is False
        assert L.is_supported(None) is False
        assert L.is_supported("klingon") is False


class TestNamingALanguageForAModel:
    def test_every_known_language_names_itself(self):
        for code in L.KNOWN:
            assert L.english_name(code) == L.BY_CODE[code].english_name

    def test_an_unknown_language_does_not_raise(self):
        assert L.english_name("zz") == "English"

    def test_no_language_is_named_by_being_the_other_one(self):
        """The shape this module exists to delete.

        `"Tamil" if language == "ta" else "English"` answers "English" for
        Malayalam, Telugu and Hindi alike, and that is how a petition gets
        composed in the wrong language with nothing raised.
        """
        assert len({L.english_name(c) for c in L.KNOWN}) == len(L.KNOWN)
