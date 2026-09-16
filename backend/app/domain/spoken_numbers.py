"""Spoken numbers, in English and Tamil, resolved deterministically.

There are two completely different things a citizen can say that look alike:

    "two three"              a digit SEQUENCE   -> 23 as two digits
    "twenty three"           a CARDINAL         -> the number 23

and the difference matters, because "twenty three" is an age and "two three"
is the start of a phone number. `digits_from_speech` in `fields.py` handles the
first: it collects digits in order and is exactly right for an Aadhaar or a
mobile number. It is exactly wrong for an age — it read "twenty three" as "3",
because "twenty" carries no digit of its own, and a citizen aged 23 had 3
written on their petition.

This module handles the second. It is ordinary arithmetic over a word list: no
model, no guessing, and a refusal rather than an approximation when the words
do not add up. A government form takes the number the citizen said or it asks
again.
"""

from __future__ import annotations

import re
import unicodedata

from .phrasing import Language

# --------------------------------------------------------------------------- #
# English
# --------------------------------------------------------------------------- #

_EN_UNITS = {
    "zero": 0, "nought": 0, "oh": 0,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_EN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_EN_SCALE = {"hundred": 100, "thousand": 1000}

# --------------------------------------------------------------------------- #
# Tamil
# --------------------------------------------------------------------------- #
#
# Tamil compounds a tens word with a unit and the tens word CHANGES shape when
# it does: இருபது (20) becomes இருபத்து in "இருபத்து மூன்று" (23), முப்பது
# (30) becomes முப்பத்து or முப்பத்தி. Both the standalone and the combining
# forms have to be listed, and the spellings people actually use as well as the
# ones a grammar would prefer — a transcript is what was said, not what is
# correct.

_TA_UNITS = {
    "பூஜ்ஜியம்": 0, "பூஜ்யம்": 0, "சுழியம்": 0,
    "ஒன்று": 1, "ஒன்னு": 1, "ஓர்": 1, "ஒரு": 1,
    "இரண்டு": 2, "ரெண்டு": 2,
    "மூன்று": 3, "மூணு": 3,
    "நான்கு": 4, "நாலு": 4,
    "ஐந்து": 5, "அஞ்சு": 5,
    "ஆறு": 6,
    "ஏழு": 7,
    "எட்டு": 8,
    "ஒன்பது": 9, "ஒம்பது": 9,
    "பத்து": 10,
    "பதினொன்று": 11, "பதினொன்னு": 11,
    "பன்னிரண்டு": 12, "பன்னெண்டு": 12,
    "பதிமூன்று": 13, "பதின்மூன்று": 13,
    "பதினான்கு": 14, "பதிநான்கு": 14,
    "பதினைந்து": 15,
    "பதினாறு": 16,
    "பதினேழு": 17,
    "பதினெட்டு": 18,
    "பத்தொன்பது": 19, "பத்தொம்பது": 19,
}

# Standalone tens, and the combining forms that precede a unit.
_TA_TENS = {
    "இருபது": 20, "இருபத்து": 20, "இருபத்தி": 20,
    "முப்பது": 30, "முப்பத்து": 30, "முப்பத்தி": 30,
    "நாற்பது": 40, "நாற்பத்து": 40, "நாற்பத்தி": 40,
    "ஐம்பது": 50, "ஐம்பத்து": 50, "ஐம்பத்தி": 50,
    "அறுபது": 60, "அறுபத்து": 60, "அறுபத்தி": 60,
    "எழுபது": 70, "எழுபத்து": 70, "எழுபத்தி": 70,
    "எண்பது": 80, "எண்பத்து": 80, "எண்பத்தி": 80,
    "தொண்ணூறு": 90, "தொண்ணூற்று": 90, "தொண்ணூற்றி": 90,
}
_TA_SCALE = {"நூறு": 100, "நூற்று": 100, "ஆயிரம்": 1000, "ஆயிரத்து": 1000}

# Words that are not numbers and must not stop the parse: "my age is twenty
# three", "எனக்கு வயது இருபத்து மூன்று".
_SKIP = {
    "my", "age", "is", "am", "i", "years", "year", "old", "the", "a", "an",
    "and", "of", "it", "its", "about", "around", "approximately", "roughly",
    "வயது", "எனக்கு", "என்", "என்னுடைய", "ஆகிறது", "ஆகும்", "இருக்கிறது",
    "வருடம்", "வயசு", "ஆண்டு", "ஆண்டுகள்", "வருடங்கள்",
}

# Split on separators rather than matching "word characters".
#
# `[^\W\d_]+` looks like the right pattern and is wrong for every Indic script:
# it excludes combining marks, so இருபத்து — which is one word carrying two
# vowel signs and a virama — comes out as ['இர', 'பத', 'த'] and matches
# nothing. Splitting on what separates words works in any script.
_SEPARATORS = re.compile(r"[\s,.;:!?\-–—/|()\[\]\"'`]+", re.UNICODE)


def _fold_digits(text: str) -> str:
    """Tamil (௦-௯) and Devanagari (०-९) digits become ASCII ones."""
    out = []
    for ch in str(text or ""):
        if ch.isdigit() and not ch.isascii():
            try:
                out.append(str(unicodedata.decimal(ch)))
                continue
            except (TypeError, ValueError):
                pass
        out.append(ch)
    return "".join(out)


def spoken_cardinal(text: str, language: Language = "en") -> int | None:
    """The number a citizen said, or None when the words do not settle on one.

    Returns None rather than a best guess. "Dirty" is not thirty, a half-heard
    "twenty ..." is not twenty, and a form that fills itself in from a guess is
    worse than one that asks again.
    """
    folded = _fold_digits(text)
    tokens = [t.lower() for t in _SEPARATORS.split(folded) if t]
    if not tokens:
        return None

    units = dict(_EN_UNITS)
    tens = dict(_EN_TENS)
    scale = dict(_EN_SCALE)
    # Both vocabularies are always live. A Tamil speaker may well say "thirty",
    # and a transcript of Tamil speech often carries English numerals.
    units.update(_TA_UNITS)
    tens.update(_TA_TENS)
    scale.update(_TA_SCALE)

    total = 0          # completed groups
    current = 0        # the group being built
    seen = False
    last_kind: str | None = None

    for token in tokens:
        if token in _SKIP:
            continue

        if token.isdigit():
            # A bare figure inside a spoken phrase: "my age is 23".
            if seen and last_kind is not None:
                return None          # "twenty 3" is not a number anyone said
            current = int(token)
            seen = True
            last_kind = "figure"
            continue

        if token in tens:
            if last_kind in ("tens", "unit", "figure"):
                return None          # "twenty thirty"
            current += tens[token]
            seen = True
            last_kind = "tens"
            continue

        if token in units:
            value = units[token]
            if last_kind == "tens":
                # "twenty three". A tens word only combines with 1-9.
                if not 1 <= value <= 9:
                    return None
                current += value
                last_kind = "unit"
                seen = True
                continue
            if last_kind in ("unit", "figure"):
                return None          # "three four" is a digit sequence, not 34
            current += value
            seen = True
            last_kind = "unit"
            continue

        if token in scale:
            if not seen or current == 0:
                current = 1          # "hundred and five"
            multiplier = scale[token]
            if multiplier >= 1000:
                total = (total + current) * multiplier
                current = 0
            else:
                current *= multiplier
            seen = True
            last_kind = "scale"
            continue

        # An unrecognised word between number words. "twenty odd" is not a
        # number, and neither is a mis-hearing.
        if seen:
            return None
        return None

    return total + current if seen else None
