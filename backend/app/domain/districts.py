"""The places a Tamil Nadu petition can be signed in.

WHAT THIS IS FOR. The petition carries "Place:" at its foot and the citizen is
never asked for it separately, so it is taken from the address they did give.
That was done by splitting on commas and keeping the last piece, which is right
when somebody writes "12 Gandhi Street, Peelamedu, Coimbatore" and wrong the
moment they write anything else:

    80/33, perumal kovil street        ->  Place: perumal kovil street
    14 North Street, near the temple   ->  Place: near the temple
    5 Main Road, opposite bus stand    ->  Place: opposite bus stand
    Door No 7, 2nd Cross               ->  Place: 2nd Cross
    ... theni, tamil nadu              ->  Place: tamil nadu

A street is not a place, and a state is not the town a petition was signed in.
With a list to check against, the pieces are read from the end until one is a
place that exists; when none is, the line is left out, which is what the letter
builder already does and says is right — a wrong town on a petition is worse
than a missing one, and the citizen can write it in by hand.

THIS RECOGNISES, IT DOES NOT REWRITE. A matched piece is returned exactly as
the citizen typed it. Somebody who writes "Madras" gets "Madras" on their
petition; the entry exists so the line is not dropped, not so their spelling
can be corrected for them.

STATES ARE DELIBERATELY ABSENT. "Place: Tamil Nadu" is not where a petition
was signed, and leaving the state out is what lets the scan fall through it to
the town behind it.
"""

from __future__ import annotations

import re

#: The thirty-eight districts of Tamil Nadu.
DISTRICTS: tuple[str, ...] = (
    "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore",
    "Dharmapuri", "Dindigul", "Erode", "Kallakurichi", "Kancheepuram",
    "Kanyakumari", "Karur", "Krishnagiri", "Madurai", "Mayiladuthurai",
    "Nagapattinam", "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai",
    "Ramanathapuram", "Ranipet", "Salem", "Sivaganga", "Tenkasi",
    "Thanjavur", "Theni", "Thoothukudi", "Tiruchirappalli", "Tirunelveli",
    "Tirupathur", "Tiruppur", "Tiruvallur", "Tiruvannamalai", "Tiruvarur",
    "Vellore", "Viluppuram", "Virudhunagar",
)

#: Other spellings and older names, each saying which district it is. A citizen
#: writes the name they have always used, and a petition should not lose its
#: Place line because an office renamed something — nor should an officer
#: filtering for Tiruchirappalli miss the petitions that say Trichy.
_ALIASES: dict[str, str] = {
    "Madras": "Chennai",
    "Kovai": "Coimbatore",
    "Trichy": "Tiruchirappalli",
    "Tirchy": "Tiruchirappalli",
    "Tiruchi": "Tiruchirappalli",
    "Trichinopoly": "Tiruchirappalli",
    "Tanjore": "Thanjavur",
    "Tuticorin": "Thoothukudi",
    "Thoothukkudi": "Thoothukudi",
    "Thuthukudi": "Thoothukudi",
    "Nellai": "Tirunelveli",
    "Ooty": "Nilgiris",
    "Udhagamandalam": "Nilgiris",
    "Udagamandalam": "Nilgiris",
    "Nilgiri": "Nilgiris",
    "The Nilgiris": "Nilgiris",
    "Kanchipuram": "Kancheepuram",
    "Conjeevaram": "Kancheepuram",
    "Kanniyakumari": "Kanyakumari",
    "Nagercoil": "Kanyakumari",
    "Nagarcoil": "Kanyakumari",
    "Cuddalur": "Cuddalore",
    "Dindugal": "Dindigul",
    "Dindukkal": "Dindigul",
    "Villupuram": "Viluppuram",
    "Tirupattur": "Tirupathur",
    "Tiruppattur": "Tirupathur",
    "Virudunagar": "Virudhunagar",
    "Sivagangai": "Sivaganga",
    "Pudukottai": "Pudukkottai",
    "Thiruvarur": "Tiruvarur",
    "Thiruvallur": "Tiruvallur",
    "Thiruvannamalai": "Tiruvannamalai",
    "Thiruppur": "Tiruppur",
    "Tirupur": "Tiruppur",
}

#: Towns large enough that a citizen signs there and writes that, rather than
#: the district. Kept short on purpose: every entry is a chance to read a word
#: as a town that was not meant as one.
_TOWNS: tuple[str, ...] = (
    "Avadi", "Ambattur", "Tambaram", "Poonamallee", "Pallavaram",
    "Hosur", "Pollachi", "Mettupalayam", "Sivakasi", "Rajapalayam",
    "Karaikudi", "Kumbakonam", "Gobichettipalayam", "Bhavani", "Sankari",
    "Palani", "Oddanchatram", "Bodinayakanur", "Cumbum", "Periyakulam",
    "Aruppukottai", "Paramakudi", "Srivilliputhur", "Tiruchengode",
    "Arakkonam", "Gudiyatham", "Vaniyambadi", "Ambur", "Tindivanam",
    "Chidambaram", "Neyveli", "Mannargudi", "Pattukkottai", "Arani",
    "Peelamedu", "Saidapet", "Velachery", "Adyar", "Mylapore", "Egmore",
)

#: A trailing "district", "dist", "dt", "taluk", "tk", "post" or "po" is how
#: these are written on an envelope and is not part of the name.
_SUFFIX = re.compile(
    r"\s*[-,]?\s*(district|dist\.?|dt\.?|taluk|tk\.?|post|p\.?o\.?)\s*$", re.I)
#: A leading house or door number, which a one-line address runs into the town.
_LEADING_NUMBER = re.compile(r"^\s*(?:no\.?|door\s*no\.?|d\.?no\.?)?\s*[\d/\-]+\s*")
_PUNCTUATION = re.compile(r"[.’']")


def _key(text: str) -> str:
    """One spelling of a name reduced to something comparable.

    Case, spacing, full stops and apostrophes go. The letters do not: this
    matches names, and two different towns can differ by one letter.
    """
    cleaned = _PUNCTUATION.sub("", str(text or ""))
    cleaned = _SUFFIX.sub("", cleaned)
    return " ".join(cleaned.lower().split())


_KNOWN: frozenset[str] = frozenset(
    _key(name) for name in DISTRICTS + tuple(_ALIASES) + _TOWNS
)

#: Every spelling that names a district, pointing at the district. A town is
#: not in here: a town is a place a petition can be signed in, which is what
#: `is_place` answers, and saying which district it sits in is a different
#: question with a different cost of being wrong.
_TO_DISTRICT: dict[str, str] = {
    **{_key(name): name for name in DISTRICTS},
    **{_key(alias): district for alias, district in _ALIASES.items()},
}


def _tamil_keys() -> frozenset[str]:
    """The same places as a citizen writing in Tamil would type them.

    Taken from the transliteration table rather than listed again, so the two
    cannot disagree about how a town is spelled.
    """
    from .tamil_script import PLACES

    return frozenset(
        _key(written) for latin, written in PLACES.items()
        if _key(latin) in _KNOWN
    )


_KNOWN_TAMIL: frozenset[str] | None = None


def is_place(text: str) -> bool:
    """Is this piece of an address the name of a place a petition is signed in?

    Matches the whole piece, not a word inside it. "perumal kovil street" is
    not Coimbatore because it happens to sit in the same address, and a street
    named after a town must not be read as that town.
    """
    global _KNOWN_TAMIL
    key = _key(text)
    if not key:
        return False
    if key in _KNOWN:
        return True
    # A one-line address runs the door number into the town: "80/33 Theni".
    without_number = _key(_LEADING_NUMBER.sub("", str(text or "")))
    if without_number and without_number in _KNOWN:
        return True
    if _KNOWN_TAMIL is None:
        _KNOWN_TAMIL = _tamil_keys()
    return key in _KNOWN_TAMIL


def without_suffix(text: str) -> str:
    """The piece with its administrative label removed, nothing else changed.

    "Theni Dist" is a town with a label after it. Removing the label is not
    correcting anybody's spelling — it is the same thing the letter builder
    already does to a trailing pin code.
    """
    return _SUFFIX.sub("", str(text or "")).strip() or str(text or "").strip()


def canonical(text: str) -> str | None:
    """The district this names, in the spelling the state uses, or None.

    For a validator and for an officer's filters — NOT for the petition, which
    keeps whatever the citizen wrote.
    """
    return _TO_DISTRICT.get(_key(text))
