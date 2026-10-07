"""Every language this service speaks, and everything that differs between them.

ONE TABLE. Before this file the Tamil codepoint block was written out thirteen
times in six different spellings across seven modules and one JavaScript file,
and the set of supported languages was declared seven times as
`Literal["en", "ta"]` of which exactly one was ever imported. Adding a language
meant finding all of them, and missing one did not raise anything — it quietly
produced an English petition for a citizen who asked for Malayalam.

RANGES ARE BUILT FROM CODEPOINTS, never from literal characters pasted into a
pattern. `app/services/translate.py` already did this and it is worth copying:
a file that goes through the wrong encoding once turns a literal Tamil range
into mojibake that still compiles and silently matches nothing.

WHAT THIS MODULE DOES NOT DECIDE. It holds facts about languages — their
script, their name, their locale, the font their script needs. It does not hold
provider capability: which of these a particular speech vendor can transcribe
belongs next to that vendor, because it changes when the vendor changes and not
when the language does.

KNOWN is not the same as OFFERED. A language appears in `LANGUAGES` as soon as
its script and locale are known. It joins `SUPPORTED` — the set a citizen may
actually choose — only once an interview and a finished document have been
walked end to end in it. Keeping the two apart is deliberate: widening the
intake gate is a one-character edit that makes a demo look finished while
thirty code paths quietly answer in English.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Scripts
# --------------------------------------------------------------------------- #


def _block(first: int, last: int) -> re.Pattern[str]:
    """A Unicode block as a pattern, assembled from numbers only."""
    return re.compile("[" + chr(first) + "-" + chr(last) + "]")


TAMIL = _block(0x0B80, 0x0BFF)
MALAYALAM = _block(0x0D00, 0x0D7F)
TELUGU = _block(0x0C00, 0x0C7F)
DEVANAGARI = _block(0x0900, 0x097F)

# Latin is not a block test. Three consecutive letters is the existing rule and
# it is a better one: a single "A" appears inside an address written in any
# script, so requiring a run avoids calling a Tamil line English because it
# contains a door number.
LATIN_WORD = re.compile(r"[A-Za-z]{3}")

# The inside of a character class, for patterns that need to splice ranges
# together rather than test a whole string. Same numbers, same source.
TAMIL_RANGE = chr(0x0B80) + "-" + chr(0x0BFF)
MALAYALAM_RANGE = chr(0x0D00) + "-" + chr(0x0D7F)
TELUGU_RANGE = chr(0x0C00) + "-" + chr(0x0C7F)
DEVANAGARI_RANGE = chr(0x0900) + "-" + chr(0x097F)

#: Every Indic range this service knows, ready to splice into a character
#: class. Python's `\w` does NOT cover Indic combining marks — a virama is
#: category Mn and a vowel sign is Mc, and both fail `\w` — so any pattern that
#: cleans text with `\w` must splice these in or it will mutilate every
#: language here except English.
INDIC_RANGES = TAMIL_RANGE + MALAYALAM_RANGE + TELUGU_RANGE + DEVANAGARI_RANGE


# --------------------------------------------------------------------------- #
# Languages
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LanguageSpec:
    """What the service needs to know to serve one language."""

    code: str
    #: Named in English because this is what a model prompt says, and what an
    #: officer reads in a petition's history.
    english_name: str
    #: The language's own name, for the citizen's own language picker. A person
    #: looking for Malayalam is looking for "മലയാളം", not for "Malayalam".
    endonym: str
    #: The script test. `None` for English, which is tested by LATIN_WORD and
    #: is the fallback rather than a thing to detect.
    script: re.Pattern[str] | None
    #: IETF tag. Most speech and translation vendors take this or a near
    #: variant of it, so it is the one locale worth holding centrally.
    bcp47: str
    #: The font family and the file that carries this script. English and the
    #: Indic languages all fall back to Noto Sans for Latin characters.
    font_family: str
    font_file: str
    #: Tesseract's name for the language, for OCR of an attached document.
    ocr: str


LANGUAGES: tuple[LanguageSpec, ...] = (
    LanguageSpec("en", "English", "English", None,
                 "en-IN", "Noto Sans App", "NotoSans-Regular.ttf", "eng"),
    LanguageSpec("ta", "Tamil", "தமிழ்", TAMIL,
                 "ta-IN", "Noto Sans Tamil", "NotoSansTamil-Regular.ttf", "tam"),
    LanguageSpec("ml", "Malayalam", "മലയാളം", MALAYALAM,
                 "ml-IN", "Noto Sans Malayalam", "NotoSansMalayalam-Regular.ttf", "mal"),
    LanguageSpec("te", "Telugu", "తెలుగు", TELUGU,
                 "te-IN", "Noto Sans Telugu", "NotoSansTelugu-Regular.ttf", "tel"),
    LanguageSpec("hi", "Hindi", "हिन्दी", DEVANAGARI,
                 "hi-IN", "Noto Sans Devanagari", "NotoSansDevanagari-Regular.ttf", "hin"),
)

BY_CODE: dict[str, LanguageSpec] = {spec.code: spec for spec in LANGUAGES}
KNOWN: tuple[str, ...] = tuple(BY_CODE)

#: The languages a citizen may actually choose today.
#:
#: Widen this LAST, one language at a time, and only after an interview and a
#: finished document have been walked end to end in that language. It is the
#: gate in front of every path that still answers in English when it does not
#: recognise a code, and it is the single easiest line in the service to change
#: for a demo and regret in an office.
SUPPORTED: tuple[str, ...] = ("en", "ta")

DEFAULT = "en"


def spec(language: str) -> LanguageSpec:
    """The row for a language, falling back to English rather than raising.

    Callers that must not degrade silently should test `is_supported` first.
    This is for the places where English is a reasonable answer — a font, a
    locale for a date — and a crash is not.
    """
    return BY_CODE.get(language) or BY_CODE[DEFAULT]


def is_supported(language: str | None) -> bool:
    return language in SUPPORTED


def english_name(language: str) -> str:
    """What to call this language when telling a model which one to write in.

    Never derive this from a ternary. `"Tamil" if language == "ta" else
    "English"` is the shape that silently writes an English petition for every
    language that is not Tamil.
    """
    return spec(language).english_name


def script_of(text: str) -> str | None:
    """Which language's script this text is written in, or None.

    None means "no Indic script found" — which is not the same as English, and
    the difference matters. A caller deciding what a citizen typed should keep
    the language the citizen chose when this returns None, rather than treating
    an empty answer, a phone number or a door number as a request for English.
    """
    for row in LANGUAGES:
        if row.script is not None and row.script.search(text):
            return row.code
    return None


def has_indic(text: str) -> bool:
    """Does this text carry any script this service knows?"""
    return script_of(text) is not None
