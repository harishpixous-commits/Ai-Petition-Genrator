"""Writing a citizen's own words in the script of their petition.

A citizen picks Malayalam, then types their name and address on a Latin
keyboard because that is the keyboard in front of them. The petition comes out
with Malayalam headings and Latin values — correct, and it does not read as a
Malayalam document. This renders those values in the petition's own script.

THE ALGORITHM IS TAMIL'S, GENERALISED. `app/domain/tamil_script.py` solved this
first and its rules are reproduced here unchanged, because they were not
arbitrary:

1.  NEVER A DIFFERENT PLACE. A name this cannot render is left in Latin. A
    translator asked for Coimbatore in Tamil once returned கோயம்பேடூர் —
    Koyambedu, a locality in Chennai, three hundred kilometres away. An
    English word inside a Malayalam address is untidy; the wrong town is a
    wasted journey to a government office. So there is no model here and no
    network call: a fixed table, a phonetic fallback, and the citizen's own
    text kept whenever neither is sure.

2.  NUMBERS ARE NEVER TOUCHED. Door numbers, pin codes, mobile numbers, dates
    and reference numbers pass through exactly as typed. "82/33" is 82/33 in
    every language, and a petition quoting a reference number in Malayalam
    digits cannot be looked up in any register.

3.  THE ORIGINAL IS NEVER OVERWRITTEN. This runs at DISPLAY time against a
    value the record still holds as the citizen entered it. Switching the
    petition back to English shows their own spelling again, and their name
    still matches the card in their pocket.

WHY NOT A TRANSLITERATION LIBRARY. `indic-transliteration` was tried and is
wrong for this input. Its schemes expect strict ITRANS — "hariSh", "tEni" —
and a citizen types "harish" and "theni". Asked for those it returns ഹരിശ്
(the wrong sibilant) and ഥേനി (the ASPIRATED dental, which is a different
word). Rule 1 is the whole reason this module exists; a library that silently
produces a different place name fails it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field

from .languages import DEVANAGARI, MALAYALAM, TAMIL, TELUGU

# A token is a run of letters, or a run of anything else, so numbers and
# punctuation come through untouched and in place.
_TOKENS = re.compile(r"[A-Za-z]+|[^A-Za-z]+")
# Whitespace-separated chunks, keeping the whitespace so it is put back.
_CHUNKS = re.compile(r"\S+|\s+")
_LATIN_WORD = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True)
class Script:
    """Everything that differs between one script and another.

    The tables are the whole of it. Adding a script is data, not code, which
    is the point — the walk below has been exercised by every Tamil petition
    this service has produced.
    """

    code: str
    pattern: re.Pattern[str]
    #: Latin spelling -> base consonant, longest key wins ("th" before "t").
    consonants: dict[str, str]
    #: Latin spelling -> independent vowel, for the start of a word.
    vowels_alone: dict[str, str]
    #: Latin spelling -> dependent sign. "a" is "" — a bare consonant already
    #: carries the inherent a, and writing a sign for it doubles the vowel.
    vowel_signs: dict[str, str]
    virama: str
    places: dict[str, str] = dc_field(default_factory=dict)
    address_words: dict[str, str] = dc_field(default_factory=dict)
    names: dict[str, str] = dc_field(default_factory=dict)
    #: Word-final forms, for scripts that have them. Malayalam writes a
    #: consonant that ends a word as a CHILLU — കുമാർ, not കുമാര് — and the
    #: difference is not decorative: the second reads as an unfinished
    #: syllable. Maps "consonant + virama" to the chillu that replaces it, and
    #: is applied only at the very end of a word.
    final_forms: dict[str, str] = dc_field(default_factory=dict)
    #: Devanagari does not write a virama on a word-final consonant. The
    #: inherent vowel is simply not pronounced — "perumal" is पेरुमल, and
    #: पेरुमल् reads as a word somebody stopped halfway through. Telugu and
    #: Malayalam do mark it, so this is off for them.
    drop_final_virama: bool = False


def _word(word: str, s: Script) -> str:
    """One Latin word in this script, by sound.

    Deliberately plain. It gets ordinary Indian names right — Harish, Kumar,
    Selvan, Meena — and it is the LAST thing tried, after all three tables.
    What it cannot do well is English words that are not pronounced as they
    are spelled, and those are what the tables are for.
    """
    lowered = word.lower()
    out: list[str] = []
    i = 0
    at_start = True
    while i < len(lowered):
        # A vowel: on its own at the start of a word, otherwise a sign hanging
        # off the consonant just written.
        matched_vowel = None
        for length in (2, 1):
            piece = lowered[i:i + length]
            if piece in s.vowels_alone and (length == 2 or piece in "aeiou"):
                matched_vowel = piece
                break
        if matched_vowel:
            if at_start:
                out.append(s.vowels_alone[matched_vowel])
            elif out and out[-1].endswith(s.virama):
                # The consonant before it was written with a virama; that
                # virama becomes the vowel sign.
                out[-1] = out[-1][:-len(s.virama)] + s.vowel_signs[matched_vowel]
            else:
                out.append(s.vowels_alone[matched_vowel])
            i += len(matched_vowel)
            at_start = False
            continue

        matched_consonant = None
        for length in (2, 1):
            piece = lowered[i:i + length]
            if piece in s.consonants:
                matched_consonant = piece
                break
        if matched_consonant:
            out.append(s.consonants[matched_consonant] + s.virama)
            i += len(matched_consonant)
            at_start = False
            continue

        # Anything else — an apostrophe, a stray mark — is kept as it is.
        out.append(lowered[i])
        i += 1
        at_start = False

    written = "".join(out)
    for ending, chillu in s.final_forms.items():
        if written.endswith(ending):
            return written[:-len(ending)] + chillu
    if s.drop_final_virama and written.endswith(s.virama):
        return written[:-len(s.virama)]
    return written


def _chunk(chunk: str, s: Script) -> str:
    out: list[str] = []
    for token in _TOKENS.findall(chunk):
        if not token[:1].isalpha():
            out.append(token)          # spaces, punctuation
            continue
        # A LONE LETTER IS NOT A WORD. It is the initial in "R. Kumar", and a
        # spelled-out consonant in its place is wrong in a way a reader
        # notices at once.
        if len(token) == 1:
            out.append(token)
            continue
        key = token.lower()
        if key in s.places:
            out.append(s.places[key])
        elif key in s.address_words:
            out.append(s.address_words[key])
        elif key in s.names:
            out.append(s.names[key])
        else:
            out.append(_word(token, s))
    return "".join(out)


def render(text: str, s: Script) -> str:
    """The citizen's text in this script, as far as it is safe to go.

    Word by word: a known place, a known address word, a known name, then
    phonetics. Digits, punctuation and anything already in this script pass
    through untouched, which is what keeps "82/33" and "+91 93441 74752"
    intact.
    """
    source = str(text or "")
    if not source.strip() or not _LATIN_WORD.search(source):
        return source

    # Two-word places first — "Tamil Nadu" is not "Tamil" and "Nadu".
    lowered = source.lower()
    for phrase, written in sorted(s.places.items(), key=lambda kv: -len(kv[0])):
        if " " in phrase and phrase in lowered:
            pattern = re.compile(rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])", re.I)
            source = pattern.sub(written, source)
            lowered = source.lower()

    out: list[str] = []
    for part in _CHUNKS.findall(source):
        # ANYTHING WITH A DIGIT IN IT IS LEFT EXACTLY AS TYPED.
        #
        # "82/33" is a door number, "2026/PG/44710012" is a reference an
        # office looks up, "14A" is a flat. The letters inside them are not
        # words — reading "PG" as a word turned a reference number into
        # something no register contains.
        if any(ch.isdigit() for ch in part):
            out.append(part)
            continue
        out.append(_chunk(part, s))
    return "".join(out)


#: The scripts this module can write, filled in by the data modules. Tamil is
#: NOT here: it has its own long-standing module with its own tables, and
#: moving it would be a refactor of working code in the same change that adds
#: three new languages.
SCRIPTS: dict[str, Script] = {}


def register(script: Script) -> None:
    SCRIPTS[script.code] = script


def for_language(text: str, language: str) -> str:
    """What to SHOW for a value, in the petition's language.

    A language with no tables, or a value already written in that script, is
    returned unchanged. The stored value is never altered by this — it is the
    argument, not the destination.
    """
    s = SCRIPTS.get(language)
    if s is None:
        return str(text or "")
    value = str(text or "")
    if s.pattern.search(value):
        return value
    return render(value, s)


#: Which pattern proves a value is already in a given script.
PATTERNS = {"ta": TAMIL, "ml": MALAYALAM, "te": TELUGU, "hi": DEVANAGARI}
