"""Which local body a place belongs to, from the department's own lists.

THE DATA IS REAL. 13,673 records built by `scripts/build_directory.py` from
the Rural Development and Panchayat Raj Department's published datasets:
12,525 village panchayats, 561 town panchayats, 388 block panchayats, 152
municipalities, 37 districts and 10 municipal corporations — with the Tamil
name beside the English one for 12,950 of them. Every record carries the
dataset and URL it came from, so an answer can be traced to a government file.

WHAT THIS REFUSES TO DO, which matters more than what it does.

A citizen acts on a jurisdiction answer by travelling to an office. Sending
them to the wrong one costs them a day's wages and their trust, so this module
answers only when the answer is unambiguous and says so plainly when it is
not. Three kinds of silence, deliberately distinguished:

    NOT FOUND    no body of that name exists in the department's list. The
                 right response is to ask the citizen, not to pick the
                 nearest-sounding one. There is no fuzzy matching here on
                 purpose: "Kulathur" and "Kulithalai" are different places and
                 an edit-distance match between them is a wasted journey.

    AMBIGUOUS    several bodies share the name. This is NOT an edge case —
                 "Ganapathipalayam" occurs three times inside Tiruppur
                 district alone, and 'Kulathur' three times in Pudukkottai.
                 The candidates are returned so a human can choose; one of
                 them is never picked silently.

    A DISTRICT IS NOT A LOCAL BODY. Asking for "Coimbatore" when the citizen
                 wrote a district name must not return the corporation of the
                 same name. They are different rows with different
                 responsibilities and the question "which office" has not
                 actually been answered.

NOTHING HERE IS INFERRED FROM AN ADDRESS. This maps a NAME to a body. Working
out which body covers a street is a different problem needing ward boundary
data the department does not publish, and guessing at it from a district or a
street name is the failure this exists to prevent.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DIRECTORY_PATH = Path(__file__).resolve().parent.parent.parent / "var" / "local_bodies.sqlite"

#: Urban bodies, in the order a citizen is most likely to mean when a name is
#: shared between types. Used only to REPORT the clash, never to resolve it.
BODY_TYPES = ("municipal_corporation", "municipality", "town_panchayat",
              "village_panchayat", "block_panchayat", "district")

#: Readable names, for an officer's screen.
BODY_LABELS = {
    "municipal_corporation": "Municipal Corporation",
    "municipality": "Municipality",
    "town_panchayat": "Town Panchayat",
    "village_panchayat": "Village Panchayat",
    "block_panchayat": "Panchayat Union (Block)",
    "district": "District",
}

_PUNCT = re.compile(r"[.’'`\-_,()]")


def normalise(text: str) -> str:
    """Must match `scripts/build_directory.normalise` exactly.

    The index is built with that function; a different one here would simply
    fail to find rows that are present, which looks like missing data.
    """
    cleaned = _PUNCT.sub(" ", str(text or ""))
    return " ".join(cleaned.lower().split())


@dataclass(frozen=True)
class Body:
    """One local body, as the department published it."""

    lgd_code: str
    body_type: str
    name_en: str
    name_ta: str
    district: str
    parent: str
    source_url: str
    source_dataset: str

    @property
    def label(self) -> str:
        return BODY_LABELS.get(self.body_type, self.body_type)

    def described(self, language: str = "en") -> str:
        """How this body should be written on a screen or in a petition."""
        name = self.name_ta if (language == "ta" and self.name_ta) else self.name_en
        return f"{name} {self.label}"


@dataclass(frozen=True)
class Answer:
    """What the directory can say about a name.

    `body` is set only when exactly one record matched. When several did,
    `candidates` carries them and `body` is None — the caller must ask rather
    than choose.
    """

    query: str
    body: Body | None = None
    candidates: tuple[Body, ...] = field(default_factory=tuple)
    reason: str = ""

    @property
    def resolved(self) -> bool:
        return self.body is not None

    @property
    def ambiguous(self) -> bool:
        return self.body is None and bool(self.candidates)


@lru_cache(maxsize=1)
def _connection() -> sqlite3.Connection | None:
    if not DIRECTORY_PATH.exists():
        return None
    return sqlite3.connect(f"file:{DIRECTORY_PATH}?mode=ro", uri=True,
                           check_same_thread=False)


def available() -> bool:
    """Has the directory been built? An empty service is a normal state."""
    return _connection() is not None


def _row_to_body(row: tuple) -> Body:
    return Body(lgd_code=row[0], body_type=row[1], name_en=row[2],
                name_ta=row[3] or "", district=row[4] or "",
                parent=row[6] or "", source_url=row[8], source_dataset=row[7])


_COLUMNS = ("lgd_code, body_type, name_en, name_ta, district, district_code, "
            "parent, source_dataset, source_url")


def find(name: str, *, district: str = "",
         body_type: str = "") -> Answer:
    """Look a place up by name, in English or Tamil.

    `district` is the single most useful thing a caller can supply: most
    ambiguity is between districts, and naming one usually turns an ambiguous
    answer into a resolved one.
    """
    key = normalise(name)
    if not key:
        return Answer(query=name, reason="nothing to look up")

    db = _connection()
    if db is None:
        return Answer(query=name, reason="the directory has not been built")

    sql = f"SELECT {_COLUMNS} FROM local_bodies WHERE (key_en = ? OR key_ta = ?)"
    params: list[str] = [key, key]
    if district:
        sql += " AND lower(district) = ?"
        params.append(normalise(district).lower())
    if body_type:
        sql += " AND body_type = ?"
        params.append(body_type)

    rows = db.execute(sql, params).fetchall()
    if not rows:
        return Answer(query=name,
                      reason="no local body of that name is in the directory")

    bodies = tuple(_row_to_body(row) for row in rows)
    if len(bodies) == 1:
        return Answer(query=name, body=bodies[0], reason="one match")

    # SEVERAL. Not resolved — reported. A name shared by three villages in one
    # district cannot be narrowed by anything this module knows, and picking
    # the first row would be picking by insertion order.
    districts = {b.district for b in bodies}
    kinds = {b.body_type for b in bodies}
    if len(districts) > 1:
        reason = f"{len(bodies)} bodies share this name, in {len(districts)} districts"
    elif len(kinds) > 1:
        reason = (f"{len(bodies)} bodies share this name in {bodies[0].district}, "
                  f"of different types")
    else:
        reason = (f"{len(bodies)} different {BODY_LABELS.get(bodies[0].body_type, '')}"
                  f"s in {bodies[0].district} share this name")
    return Answer(query=name, candidates=bodies, reason=reason)


#: How a jurisdiction is written when it is claimed: "Oddanchatram Town
#: Panchayat", "Chennai Municipal Corporation". The directory stores the place
#: name and the type separately, so a claim has to be taken apart before it
#: can be checked against it.
_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("municipal corporation", "municipal_corporation"),
    ("city municipal corporation", "municipal_corporation"),
    ("corporation", "municipal_corporation"),
    ("municipality", "municipality"),
    ("town panchayat", "town_panchayat"),
    ("village panchayat", "village_panchayat"),
    ("panchayat union", "block_panchayat"),
    ("block panchayat", "block_panchayat"),
    ("district panchayat", "district"),
)


def validate_claim(claim: str, *, district: str = "") -> Answer:
    """Is this claimed jurisdiction a body that actually exists?

    THE CHECK THAT STOPS A PLAUSIBLE INVENTION. A retrieval layer can produce
    "Oddanchatram Municipality" from a passage that mentions Oddanchatram and
    a passage that mentions a municipality — grammatical, citable, and not a
    body that exists. Grounding catches a value absent from the text; it
    cannot catch one assembled from text that is present. This can, because
    the department publishes the list.

    A claim is taken apart into a place and a type — "Oddanchatram Town
    Panchayat" is the place Oddanchatram and the type town_panchayat — and
    BOTH have to match the same record. Matching the place alone would accept
    "Oddanchatram Municipality", which is the error being prevented: there is
    a Town Panchayat and a Panchayat Union of that name, and no municipality.

    Returns the same Answer as `find`, so a caller handles "exists",
    "ambiguous" and "no such body" the same way everywhere.
    """
    text = " ".join(str(claim or "").split())
    if not text:
        return Answer(query=claim, reason="nothing to validate")
    if not available():
        return Answer(query=claim,
                      reason="the directory has not been built, so this "
                             "cannot be checked")

    lowered = normalise(text)
    # Longest suffix first: "city municipal corporation" before "corporation".
    for suffix, body_type in sorted(_SUFFIXES, key=lambda s: -len(s[0])):
        if lowered.endswith(suffix):
            place = lowered[: -len(suffix)].strip()
            if not place:
                break
            return find(place, district=district, body_type=body_type)

    # No recognisable type. Check the name alone, which usually comes back
    # ambiguous across types — correctly, because "Oddanchatram" on its own
    # does not say which office.
    return find(text, district=district)


def districts() -> tuple[str, ...]:
    """Every district the department lists, in its own spelling."""
    db = _connection()
    if db is None:
        return ()
    return tuple(row[0] for row in db.execute(
        "SELECT name_en FROM local_bodies WHERE body_type='district' "
        "ORDER BY name_en"))


def stats() -> dict[str, int]:
    """How many of each kind, for a health report."""
    db = _connection()
    if db is None:
        return {}
    return {row[0]: row[1] for row in db.execute(
        "SELECT body_type, count(*) FROM local_bodies GROUP BY body_type")}
