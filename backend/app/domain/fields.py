"""Deterministic validation of Indian government-form fields.

DESIGN RULE, and it is the one that matters most in this codebase: a language
model may EXTRACT a raw string from what a citizen said, but only the code in
this module decides whether that string is an acceptable value. Nothing here
calls a model, nothing here is probabilistic, and every function is a pure
function of its input.

The reason is not purity for its own sake. A model that approves a malformed
Aadhaar number on one run in fifty produces a certificate application that the
Taluk office rejects weeks later, and the citizen is the one who pays for it.

Two things here exist specifically because the input arrives by voice:

1.  SPOKEN DIGITS. A citizen reading out an Aadhaar number says "four five
    six ... " with pauses, and the transcript comes back as "4 5 6 7" or as
    number words, in English or Tamil, or in Tamil digit glyphs (௦-௯). All of
    those are the same twelve digits, so they are normalised before validation
    rather than rejected as malformed.

2.  VERHOEFF. Aadhaar's twelfth digit is a Verhoeff checksum. Checking only
    "twelve digits" accepts a transposition — the single most common error when
    a number is read aloud and typed back — while the checksum catches it at the
    point where the citizen can still repeat it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .spoken_numbers import spoken_cardinal

# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FieldResult:
    """Outcome of validating one raw value against one field type.

    `code` is a stable machine key (never shown to a citizen). The human wording
    lives in `phrasing.py`, in both languages, so that the same failure reads
    correctly in Tamil without this module knowing any Tamil.
    """

    ok: bool
    value: Any = None
    code: str | None = None
    detail: dict[str, Any] | None = None

    @staticmethod
    def good(value: Any) -> FieldResult:
        return FieldResult(True, value=value)

    @staticmethod
    def bad(code: str, **detail: Any) -> FieldResult:
        return FieldResult(False, code=code, detail=detail or None)


Validator = Callable[[str], FieldResult]


# --------------------------------------------------------------------------- #
# Spoken-input normalisation
# --------------------------------------------------------------------------- #

_EN_DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "nought": "0", "naught": "0",
    "one": "1", "won": "1",
    "two": "2", "to": "2", "too": "2",
    "three": "3", "tree": "3",
    "four": "4", "for": "4", "fore": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8", "ate": "8",
    "nine": "9",
    "double": "__DOUBLE__", "triple": "__TRIPLE__",
}

_TA_DIGIT_WORDS = {
    "பூஜ்ஜியம்": "0", "பூஜ்யம்": "0", "சுழியம்": "0",
    "ஒன்று": "1", "ஒன்னு": "1",
    "இரண்டு": "2", "ரெண்டு": "2",
    "மூன்று": "3", "மூணு": "3",
    "நான்கு": "4", "நாலு": "4",
    "ஐந்து": "5", "அஞ்சு": "5",
    "ஆறு": "6",
    "ஏழு": "7",
    "எட்டு": "8",
    "ஒன்பது": "9", "ஒம்பது": "9",
}

# Tamil digit glyphs ௦..௯ (U+0BE6..U+0BEF) and Devanagari ०..९ both appear in
# transcripts from Indic ASR. unicodedata knows their numeric value; trusting it
# is shorter and more correct than a hand-written table.
def _fold_unicode_digits(text: str) -> str:
    out = []
    for ch in text:
        if ch.isdigit() and not ch.isascii():
            out.append(str(unicodedata.digit(ch)))
        else:
            out.append(ch)
    return "".join(out)


def digits_from_speech(text: str) -> str:
    """Every digit in `text`, in order, whether spoken as words or as figures.

    "my aadhaar is four one two double three ..." -> "412330..."
    Returns "" when the utterance carries no digits at all.
    """
    if not text:
        return ""
    folded = _fold_unicode_digits(str(text))
    tokens = re.split(r"[\s,\-./|]+", folded.lower())

    out: list[str] = []
    repeat = 1
    for token in tokens:
        if not token:
            continue
        word = _EN_DIGIT_WORDS.get(token) or _TA_DIGIT_WORDS.get(token)
        if word == "__DOUBLE__":
            repeat = 2
            continue
        if word == "__TRIPLE__":
            repeat = 3
            continue
        if word is not None:
            out.append(word * repeat)
            repeat = 1
            continue
        # A bare run of figures, possibly glued to other characters.
        for run in re.findall(r"\d+", token):
            out.append(run * repeat if repeat > 1 and len(run) == 1 else run)
            repeat = 1
    return "".join(out)


def clean_text(text: str) -> str:
    """Collapse whitespace and strip the filler that dictation leaves behind."""
    s = unicodedata.normalize("NFC", str(text or "")).strip()
    s = re.sub(r"\s+", " ", s)
    # Leading politeness is not part of an answer: "sir, my name is Ravi".
    s = re.sub(r"^(sir|madam|ok|okay|yes|hello|ஐயா|அம்மா|சரி)[\s,.:-]+", "", s, flags=re.I)
    return s.strip(" ,.;:-")


# --------------------------------------------------------------------------- #
# Aadhaar — Verhoeff
# --------------------------------------------------------------------------- #

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_valid(number: str) -> bool:
    """True when `number` (digits only) carries a correct Verhoeff check digit."""
    check = 0
    for i, ch in enumerate(reversed(number)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[i % 8][int(ch)]]
    return check == 0


def validate_aadhaar(raw: str) -> FieldResult:
    digits = digits_from_speech(raw)
    if not digits:
        return FieldResult.bad("aadhaar.empty")
    if len(digits) != 12:
        return FieldResult.bad("aadhaar.length", got=len(digits))
    if digits[0] in "01":
        # UIDAI never issues a number beginning 0 or 1.
        return FieldResult.bad("aadhaar.leading")
    if not verhoeff_valid(digits):
        return FieldResult.bad("aadhaar.checksum")
    return FieldResult.good(digits)


# --------------------------------------------------------------------------- #
# Other identifiers
# --------------------------------------------------------------------------- #


def validate_mobile(raw: str) -> FieldResult:
    digits = digits_from_speech(raw)
    if not digits:
        return FieldResult.bad("mobile.empty")
    # Accept +91 / 0091 / leading 0 and reduce to the national 10-digit number.
    for prefix in ("0091", "91", "0"):
        if len(digits) > 10 and digits.startswith(prefix):
            digits = digits[len(prefix):]
            break
    if len(digits) != 10:
        return FieldResult.bad("mobile.length", got=len(digits))
    if digits[0] not in "6789":
        return FieldResult.bad("mobile.series")
    if len(set(digits)) == 1:
        return FieldResult.bad("mobile.repeated")
    return FieldResult.good(digits)


def validate_pincode(raw: str) -> FieldResult:
    digits = digits_from_speech(raw)
    if not digits:
        return FieldResult.bad("pincode.empty")
    if len(digits) != 6:
        return FieldResult.bad("pincode.length", got=len(digits))
    if digits[0] == "0":
        # No Indian postal circle begins with 0.
        return FieldResult.bad("pincode.leading")
    return FieldResult.good(digits)


_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def validate_pan(raw: str) -> FieldResult:
    s = re.sub(r"[\s-]+", "", clean_text(raw)).upper()
    if not s:
        return FieldResult.bad("pan.empty")
    if not _PAN_RE.match(s):
        return FieldResult.bad("pan.format")
    return FieldResult.good(s)


_EPIC_RE = re.compile(r"^[A-Z]{3}[0-9]{7}$")


def validate_voter_id(raw: str) -> FieldResult:
    s = re.sub(r"[\s-]+", "", clean_text(raw)).upper()
    if not s:
        return FieldResult.bad("voter_id.empty")
    if not _EPIC_RE.match(s):
        return FieldResult.bad("voter_id.format")
    return FieldResult.good(s)


_IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def validate_ifsc(raw: str) -> FieldResult:
    s = re.sub(r"[\s-]+", "", clean_text(raw)).upper()
    if not s:
        return FieldResult.bad("ifsc.empty")
    if not _IFSC_RE.match(s):
        return FieldResult.bad("ifsc.format")
    return FieldResult.good(s)


def validate_bank_account(raw: str) -> FieldResult:
    digits = digits_from_speech(raw)
    if not digits:
        return FieldResult.bad("bank_account.empty")
    if not 9 <= len(digits) <= 18:
        return FieldResult.bad("bank_account.length", got=len(digits))
    return FieldResult.good(digits)


_RATION_RE = re.compile(r"^[A-Z0-9]{8,14}$")


def validate_ration_card(raw: str) -> FieldResult:
    s = re.sub(r"[\s-]+", "", clean_text(raw)).upper()
    if not s:
        return FieldResult.bad("ration_card.empty")
    if not _RATION_RE.match(s):
        return FieldResult.bad("ration_card.format")
    return FieldResult.good(s)


# Deliberately not RFC 5322. A permissive-but-sane shape catches the errors that
# actually occur in dictation ("ravi at gmail dot com" arriving unconverted)
# without rejecting addresses that work.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def validate_email(raw: str) -> FieldResult:
    s = clean_text(raw)
    if not s:
        return FieldResult.bad("email.empty")
    # Dictation regularly produces the spoken form. The conversion has to happen
    # BEFORE the spaces are removed: once "ravi at example dot com" has been
    # collapsed to "raviatexampledotcom" there is no word boundary left to
    # match on, and a perfectly good address is rejected.
    s = re.sub(r"\s+at\s+", "@", s, flags=re.I)
    s = re.sub(r"\s+dot\s+", ".", s, flags=re.I)
    s = s.replace(" ", "").replace("@@", "@").strip(".")
    if not _EMAIL_RE.match(s):
        return FieldResult.bad("email.format")
    if len(s) > 254:
        return FieldResult.bad("email.length")
    return FieldResult.good(s.lower())


# --------------------------------------------------------------------------- #
# People and places
# --------------------------------------------------------------------------- #

# Tamil block, Latin letters, and the punctuation that appears inside real
# Indian names: "K. Ravi Kumar", "D'Souza", "Abdul-Rahman".
_NAME_RE = re.compile(r"^[஀-௿ A-Za-z.'\-]+$")


def validate_person_name(raw: str) -> FieldResult:
    s = clean_text(raw)
    # "my name is Ravi" / "என் பெயர் ரவி"
    s = re.sub(r"^(my name is|name is|i am|this is|என்\s*பெயர்|பெயர்)\s*", "", s, flags=re.I).strip()
    if not s:
        return FieldResult.bad("name.empty")
    if len(s) < 2:
        return FieldResult.bad("name.short")
    if len(s) > 80:
        return FieldResult.bad("name.long")
    if re.search(r"\d", s):
        return FieldResult.bad("name.digits")
    if not _NAME_RE.match(s):
        return FieldResult.bad("name.characters")
    # Title-case Latin names; Tamil has no case, so leave it untouched.
    if s.isascii():
        s = " ".join(w if w.isupper() and len(w) <= 3 else w.capitalize() for w in s.split())
    return FieldResult.good(s)


def validate_address(raw: str) -> FieldResult:
    s = clean_text(raw)
    if not s:
        return FieldResult.bad("address.empty")
    # A postal address has at least a place and something locating it within
    # that place. One word is a district name, and a letter addressed to it
    # cannot be delivered.
    if len(s) < 10 or len(s.split()) < 2:
        return FieldResult.bad("address.short")
    if len(s) > 400:
        return FieldResult.bad("address.long")
    return FieldResult.good(s)


# A grievance longer than this is refused with an explanation rather than cut.
# The citizen's own words are reproduced verbatim in the petition, so silently
# dropping the end of a complaint would be the one thing this system must never
# do — and a citizen told their statement is too long can shorten it themselves.
MAX_FREE_TEXT = 6000


def validate_text(raw: str) -> FieldResult:
    """Free text — a grievance, a purpose, a description.

    Three things are deliberately NOT done here, each of which would be an edit
    to the citizen's own words:

    * `clean_text` is not used. It strips trailing punctuation, which is right
      for a name and wrong for a sentence.
    * Newlines are PRESERVED. A citizen who set their complaint out in
      paragraphs has said something with that structure; collapsing it to one
      block runs their separate points together.
    * Nothing is truncated. Over the limit is an error, not a quiet cut.

    Runs of spaces and tabs within a line are collapsed, and three or more blank
    lines become one blank line. That is layout, not content.
    """
    s = unicodedata.normalize("NFC", str(raw or "")).replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[^\S\n]+", " ", s)          # spaces and tabs, but never newlines
    s = re.sub(r"\n{3,}", "\n\n", s)         # at most one blank line between paragraphs
    s = "\n".join(line.strip() for line in s.split("\n")).strip()
    if not s:
        return FieldResult.bad("text.empty")
    if len(s) < 2:
        return FieldResult.bad("text.short")
    if len(s) > MAX_FREE_TEXT:
        return FieldResult.bad("text.long", got=len(s), limit=MAX_FREE_TEXT)
    return FieldResult.good(s)


def validate_district(raw: str) -> FieldResult:
    s = clean_text(raw)
    if not s:
        return FieldResult.bad("district.empty")
    if len(s) > 60 or re.search(r"\d", s):
        return FieldResult.bad("district.format")
    return FieldResult.good(s.title() if s.isascii() else s)


# --------------------------------------------------------------------------- #
# Numbers, dates, money
# --------------------------------------------------------------------------- #


# Words that multiply a spoken number. `digits_from_speech` collects digits and
# ignores these, so "nine hundred" collapses to "9" — a plausible age that the
# citizen never said. An age carrying a scale word is refused outright.
_SCALE_WORDS = re.compile(
    "(?<![A-Za-z])(hundred|thousand|lakh|lakhs|lac|crore|crores|million)(?![A-Za-z])"
    "|நூறு|ஆயிர|இலட்ச|லட்ச|கோடி",
    re.I,
)


def validate_age(raw: str) -> FieldResult:
    if _SCALE_WORDS.search(str(raw or "")):
        return FieldResult.bad("age.format")

    # An age is a CARDINAL NUMBER, not a run of digits, and the difference is
    # not academic: `digits_from_speech` reads "twenty three" as "3", because
    # "twenty" carries no digit of its own. A citizen who said they were
    # twenty-three had 3 written on their petition, and nothing downstream
    # could tell. The same held for "thirty", "முப்பது" and "இருபத்து மூன்று",
    # which were refused outright as carrying no digits at all.
    spoken = spoken_cardinal(raw)
    if spoken is not None:
        if not 1 <= spoken <= 120:
            return FieldResult.bad("age.range", got=spoken)
        return FieldResult.good(spoken)

    digits = digits_from_speech(raw)
    if not digits:
        return FieldResult.bad("age.empty")
    # "31 years" gives "31"; a date of birth spoken instead gives 8 digits, which
    # is a different answer to the question and must not be truncated into an age.
    if len(digits) > 3:
        return FieldResult.bad("age.format")
    n = int(digits)
    if not 1 <= n <= 120:
        return FieldResult.bad("age.range", got=n)
    return FieldResult.good(n)


def validate_amount(raw: str) -> FieldResult:
    """Rupee amount. Indian grouping ("1,20,000") and "lakh"/"crore" are handled."""
    s = clean_text(raw).lower()
    if not s:
        return FieldResult.bad("amount.empty")
    multiplier = 1
    if re.search(r"\b(lakh|lakhs|lac|இலட்ச|லட்ச)\w*", s):
        multiplier = 100_000
    elif re.search(r"\b(crore|crores|கோடி)\w*", s):
        multiplier = 10_000_000
    elif re.search(r"\b(thousand|ஆயிர)\w*", s):
        multiplier = 1_000
    m = re.search(r"\d+(?:,\d+)*(?:\.\d+)?", _fold_unicode_digits(s))
    if not m:
        return FieldResult.bad("amount.format")
    try:
        base = float(m.group(0).replace(",", ""))
    except ValueError:
        return FieldResult.bad("amount.format")
    total = int(round(base * multiplier))
    if total < 0 or total > 1_000_000_000:
        return FieldResult.bad("amount.range")
    return FieldResult.good(total)


_TA_MONTHS = {
    "ஜனவரி": 1, "பிப்ரவரி": 2, "மார்ச்": 3, "ஏப்ரல்": 4, "மே": 5, "ஜூன்": 6,
    "ஜூலை": 7, "ஆகஸ்ட்": 8, "செப்டம்பர்": 9, "அக்டோபர்": 10, "நவம்பர்": 11, "டிசம்பர்": 12,
}

_EN_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date(raw: str) -> date | None:
    """Day-first date parsing, deliberately without dateutil.

    dateutil resolves "03/04/2020" by locale guesswork; in an Indian government
    form the day always comes first, so the ambiguity is settled here rather than
    left to a library default that could silently swap the two.
    """
    s = _fold_unicode_digits(clean_text(raw))
    if not s:
        return None

    m = re.search(r"\b(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2,4})\b", s)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        if y < 100:
            y += 2000 if y <= (date.today().year % 100) else 1900
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    for table, pattern in (
        (_EN_MONTHS, r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b"),
        (_TA_MONTHS, r"\b(\d{1,2})\s+([஀-௿]+)\s+(\d{4})\b"),
    ):
        m = re.search(pattern, s)
        if not m:
            continue
        day, word, year = m.group(1), m.group(2), m.group(3)
        key = word.lower()[:4] if table is _EN_MONTHS else word
        month = table.get(key) or table.get(key[:3])
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None

    m = re.search(r"\b(\d{4})\b", s)
    if m:
        year = int(m.group(1))
        if 1900 <= year <= date.today().year:
            # A bare year is a real answer to "when did you retire". Anchor it to
            # 1 January and let the caller decide whether that precision is enough.
            return date(year, 1, 1)
    return None


def validate_date(raw: str) -> FieldResult:
    d = _parse_date(raw)
    if d is None:
        return FieldResult.bad("date.format")
    if d.year < 1900:
        return FieldResult.bad("date.range")
    return FieldResult.good(d.isoformat())


def validate_past_date(raw: str) -> FieldResult:
    r = validate_date(raw)
    if not r.ok:
        return r
    if date.fromisoformat(r.value) > date.today():
        return FieldResult.bad("date.future")
    return r


def validate_dob(raw: str) -> FieldResult:
    r = validate_past_date(raw)
    if not r.ok:
        return r
    d = date.fromisoformat(r.value)
    years = (date.today() - d).days // 365
    if years > 120:
        return FieldResult.bad("dob.range")
    return r


_YES = re.compile(
    r"\b(yes|yeah|yep|yup|correct|right|true|done|issued|received|i did|i have|ok|okay)\b"
    r"|ஆம்|ஆமா|ஆமாம்|சரி|இருக்கு|உள்ளது|வழங்கப்பட்ட|கிடைத்த|செய்தேன்",
    re.I,
)
_NO = re.compile(
    r"\b(no|nope|not|never|didn'?t|haven'?t|nothing|pending|wrong|incorrect|false)\b"
    r"|இல்ல|இல்லை|வேண்டாம்|தவறு|வழங்கப்படவில்லை|கிடைக்கவில்லை|செய்யவில்லை|நிலுவை",
    re.I,
)


def read_boolean(raw: str) -> bool | None:
    """Yes/no from a spoken answer, or None when genuinely ambiguous.

    Ported from the Node intake module, where it was measured against real
    dictation. When both a positive and a negative marker appear, the one nearer
    the start of the utterance wins — "no, yes I received it" is a correction of
    the speaker's own first word.
    """
    text = str(raw or "")
    yes = _YES.search(text)
    no = _NO.search(text)
    if yes and not no:
        return True
    if no and not yes:
        return False
    if yes and no:
        return yes.start() > no.start()
    return None


def validate_boolean(raw: str) -> FieldResult:
    value = read_boolean(raw)
    if value is None:
        return FieldResult.bad("boolean.unclear")
    return FieldResult.good(value)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

VALIDATORS: dict[str, Validator] = {
    "aadhaar": validate_aadhaar,
    "address": validate_address,
    "age": validate_age,
    "amount": validate_amount,
    "bank_account": validate_bank_account,
    "boolean": validate_boolean,
    "date": validate_date,
    "district": validate_district,
    "dob": validate_dob,
    "email": validate_email,
    "ifsc": validate_ifsc,
    "mobile": validate_mobile,
    "pan": validate_pan,
    "past_date": validate_past_date,
    "person_name": validate_person_name,
    "pincode": validate_pincode,
    "ration_card": validate_ration_card,
    "text": validate_text,
    "voter_id": validate_voter_id,
}


# Field types whose values are personal identifiers. These are never sent to an
# external model — not in a prompt, not as context, not for drafting. The model
# does not need an Aadhaar number to write "I request that this petition be
# examined", and a value it never receives is one it can never place wrongly.
# The identifiers reach the document through `domain/letter.py` alone.
SENSITIVE_TYPES: frozenset[str] = frozenset(
    {"aadhaar", "bank_account", "email", "ifsc", "mobile", "pan", "ration_card", "voter_id"}
)


def is_sensitive(field_type: str) -> bool:
    return field_type in SENSITIVE_TYPES


def validate_field(field_type: str, raw: str) -> FieldResult:
    """Validate `raw` as `field_type`. An unknown type is a template bug, not a
    citizen error, so it fails loudly rather than silently accepting anything."""
    validator = VALIDATORS.get(field_type)
    if validator is None:
        raise KeyError(f"No validator registered for field type {field_type!r}")
    return validator(raw)


def display_value(field_type: str, value: Any, language: str = "en") -> str:
    """How a validated value is read back to a citizen for confirmation.

    Identifiers are grouped the way they are printed on the document itself, so a
    citizen checking the read-back is comparing like with like.
    """
    if value is None:
        return ""
    if field_type == "aadhaar":
        s = str(value)
        return f"{s[0:4]} {s[4:8]} {s[8:12]}"
    if field_type == "mobile":
        s = str(value)
        return f"+91 {s[0:5]} {s[5:10]}"
    if field_type == "boolean":
        if language == "ta":
            return "ஆம்" if value else "இல்லை"
        return "Yes" if value else "No"
    if field_type in ("date", "past_date", "dob"):
        try:
            return datetime.fromisoformat(str(value)).strftime("%d-%m-%Y")
        except ValueError:
            return str(value)
    if field_type == "amount":
        return f"Rs. {int(value):,}".replace(",", ",")
    return str(value)
