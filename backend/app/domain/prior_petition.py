"""Reading a petition the citizen has already submitted.

A citizen who comes back because nothing happened is usually holding the
acknowledgement slip from last time. That slip carries the one thing that makes
the new petition actionable — the reference number the office can look up — and
asking them to read it out digit by digit over a phone is how it gets entered
wrong.

Everything in here is deterministic. Reference numbers, dates and department
names are read from a table of patterns in both languages, not from a model,
for the same reason the emblem is: `CBE/2026/12345` has exactly one correct
reading, and a model that is 95% reliable at transcription is 5% unreliable at
the number an officer will use to find the earlier file.

**Nothing extracted here is ever written into the petition on its own.** Each
field carries the snippet of the document it was read from, the citizen is shown
that, and only what they confirm can be used. That is the whole of `confirmed`
below and the reason the type exists instead of a plain dict.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

Language = Literal["en", "ta"]

# What kind of document this is. Classification drives the label printed on the
# petition and nothing else — a misfiled kind costs a wrong enclosure line, not
# a wrong fact.
_CLASSIFIERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("acknowledgement", (
        "acknowledgement", "acknowledgment", "received your petition", "receipt no",
        "token no", "ஒப்புகை", "ஒப்புகைச் சீட்டு", "பெறப்பட்டது", "ரசீது")),
    ("response", (
        "in reply to", "with reference to your petition", "your petition has been",
        "disposed", "closed", "action taken", "பதில்", "நடவடிக்கை எடுக்கப்பட்டது",
        "முடிக்கப்பட்டது")),
    ("notice", (
        "notice", "hereby informed", "show cause", "அறிவிப்பு", "அறிவிக்கப்படுகிறது")),
    ("previous_petition", (
        "petition", "respected sir", "i request", "humbly", "grievance",
        "மனு", "மாண்புமிகு", "வேண்டுகிறேன்", "கோரிக்கை", "குறை")),
    ("aadhaar", ("aadhaar", "unique identification", "ஆதார்", "இந்திய தனிநபர்")),
    ("address_proof", (
        "electricity bill", "ration card", "voter", "property tax",
        "மின் கட்டணம்", "குடும்ப அட்டை", "வாக்காளர்")),
)

# A reference number as Indian government offices write them: CBE/2026/12345,
# TN-REV-2026-0012, 2026/PG/4471. Requires at least one separator and one run of
# digits, which is what keeps it from matching ordinary words.
_REFERENCE = re.compile(
    r"\b([A-Z]{2,12}[/\-][A-Z0-9]{1,12}(?:[/\-][A-Z0-9]{1,12}){1,3}"
    r"|\d{4}[/\-][A-Z]{2,8}[/\-]\d{1,8})\b")

# The words that introduce one, in both languages. Used to pick the RIGHT number
# when a page has several.
_REF_CUES = (
    "acknowledgement", "acknowledgment", "reference", "ref no", "ref.no", "ref:",
    "receipt", "token", "petition no", "petition number", "file no", "grievance id",
    "registration", "ஒப்புகை", "குறிப்பு", "பதிவு எண்", "மனு எண்", "ரசீது எண்",
)

_DATE_PATTERNS = (
    # 12-08-2026, 12/08/2026, 12.08.2026
    re.compile(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b"),
    # 2026-08-12
    re.compile(r"\b(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})\b"),
)
_MONTHS = {m: i for i, m in enumerate(
    ("january february march april may june july august september october "
     "november december").split(), start=1)}
_MONTH_NAME = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b", re.I)

# At most three words before the noun, and none of them ALL-CAPS. Without both
# limits this ran backwards through a letterhead — "OFFICE OF THE DISTRICT
# COLLECTOR, COIMBATORE Revenue Department" came back as the department name,
# because every word in a shouted letterhead matches a capitalised-word class.
_DEPARTMENT = re.compile(
    r"\b([A-Z][a-z][A-Za-z&'\-]*"
    r"(?:\s+(?:[A-Z][a-z][A-Za-z&'\-]*|and|of|for|&)){0,5}\s+"
    r"(?:Department|Directorate|Board|Corporation|Municipality|Panchayat))\b")
_DEPARTMENT_TA = re.compile(r"([^\s]{2,}\s*(?:துறை|வாரியம்|மாநகராட்சி|ஊராட்சி|நகராட்சி))")

_AUTHORITY = re.compile(
    r"\b(District Collector|Collector|Tahsildar|Revenue Divisional Officer|"
    r"Executive Engineer|Assistant Engineer|Commissioner|Block Development Officer|"
    r"Superintendent of Police|Village Administrative Officer|Secretary|Director)\b",
    re.I)
_AUTHORITY_TA = re.compile(
    r"(மாவட்ட ஆட்சியர்|ஆட்சியர்|வட்டாட்சியர்|வருவாய் கோட்டாட்சியர்|"
    r"செயற்பொறியாளர்|உதவிப் பொறியாளர்|ஆணையர்|ஊராட்சி ஒன்றிய வளர்ச்சி அலுவலர்|"
    r"கிராம நிர்வாக அலுவலர்|செயலாளர்|இயக்குநர்)")

_SUBJECT = re.compile(
    r"(?:^|\n)\s*(?:subject|sub|பொருள்)\s*[:\-–]\s*(.{4,180})", re.I)

_STATUS = (
    ("closed", ("closed", "disposed", "முடிக்கப்பட்டது", "முடிவுற்றது")),
    ("pending", ("pending", "under process", "under consideration", "நிலுவையில்",
                 "பரிசீலனையில்")),
    ("rejected", ("rejected", "not admissible", "நிராகரிக்கப்பட்டது")),
    ("forwarded", ("forwarded", "transferred", "அனுப்பப்பட்டது", "மாற்றப்பட்டது")),
)


@dataclass
class Extracted:
    """One value, with the words it was read from.

    `evidence` is not decoration. The citizen is shown it next to the value and
    asked whether it is right, which is only a meaningful question if they can
    see where it came from.
    """

    value: str
    evidence: str = ""
    confidence: float = 0.0
    # Where in the file it was read. `page` is 0 when the location could not
    # be pinned down, which is a different thing from page 1 — see
    # `extraction.locate`. `unit` names what is being counted, because a
    # presentation has slides and telling somebody to check "page 4" of a
    # deck sends them looking for something that does not exist.
    page: int = 0
    unit: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def where(self) -> str:
        """"page 2", "slide 4", or nothing at all."""
        return f"{self.unit} {self.page}" if self.page and self.unit else ""


@dataclass
class PriorPetition:
    """What an earlier petition or acknowledgement appears to say.

    Everything is optional, because a photograph of a slip may carry a reference
    number and nothing else, and a reference number alone is worth having.
    """

    kind: str = "other"
    reference_number: Extracted | None = None
    petition_number: Extracted | None = None
    # Who the earlier petition was from. Read so that it can be COMPARED with
    # what the citizen has told us this time, not so that it can replace it —
    # an old address on an old petition is evidence of where they used to
    # live, which is exactly the thing worth asking about rather than acting on.
    petitioner_name: Extracted | None = None
    address: Extracted | None = None
    submitted_on: Extracted | None = None
    department: Extracted | None = None
    authority: Extracted | None = None
    subject: Extracted | None = None
    grievance: Extracted | None = None
    requested_action: Extracted | None = None
    status: Extracted | None = None
    other_dates: list[str] = field(default_factory=list)
    # Carried through from extraction so the UI can say "we could not read this"
    # rather than showing an empty form that looks like a failure of the citizen.
    readable: bool = True
    reason: str = ""
    low_confidence: bool = False

    @property
    def has_anything(self) -> bool:
        return any((self.reference_number, self.petition_number, self.submitted_on,
                    self.department, self.authority, self.subject, self.status))

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "readable": self.readable,
                               "reason": self.reason,
                               "low_confidence": self.low_confidence,
                               "other_dates": list(self.other_dates)}
        for name in ("reference_number", "petition_number", "petitioner_name",
                     "address", "submitted_on", "department", "authority",
                     "subject", "grievance", "requested_action", "status"):
            value = getattr(self, name)
            out[name] = value.as_dict() if value else None
        return out

    @classmethod
    def from_dict(cls, value: Any) -> PriorPetition | None:
        if not isinstance(value, dict):
            return None
        out = cls(kind=str(value.get("kind") or "other"),
                  readable=bool(value.get("readable", True)),
                  reason=str(value.get("reason") or ""),
                  low_confidence=bool(value.get("low_confidence")),
                  other_dates=[str(d) for d in (value.get("other_dates") or [])])
        for name in ("reference_number", "petition_number", "petitioner_name",
                     "address", "submitted_on", "department", "authority",
                     "subject", "grievance", "requested_action", "status"):
            raw = value.get(name)
            if isinstance(raw, dict) and raw.get("value"):
                setattr(out, name, Extracted(
                    value=str(raw["value"]), evidence=str(raw.get("evidence") or ""),
                    confidence=float(raw.get("confidence") or 0.0),
                    page=int(raw.get("page") or 0),
                    unit=str(raw.get("unit") or "")))
        return out


def _line_around(text: str, needle: str, width: int = 96) -> str:
    """The words a value was found among, for the citizen to check against.

    Snapped to word boundaries and ellipsised. Cutting on a raw character
    offset produced evidence beginning "t ACKNOWLEDGEMENT" and "OLLECTOR,
    THENI" — which reads as a broken system rather than as a quotation, and a
    citizen asked "is this right?" underneath it has been given a reason to
    distrust the question.
    """
    index = text.find(needle)
    if index < 0:
        return ""
    half = max(16, (width - len(needle)) // 2)
    start, end = max(0, index - half), min(len(text), index + len(needle) + half)

    before = " ".join(text[start:index].split())
    after = " ".join(text[index + len(needle):end].split())
    if start > 0 and " " in before:
        before = before.split(" ", 1)[1]
    if end < len(text) and " " in after:
        after = after.rsplit(" ", 1)[0]

    # No space before the punctuation that follows the value: "12-08-2026 ."
    # reads as a typo in the citizen's own document rather than as our joining.
    tail = after if after[:1] in ",.;:!?)]" else f" {after}" if after else ""
    head = f"{before} " if before else ""
    snippet = " ".join(f"{head}{needle}{tail}".split(" "))
    snippet = " ".join(snippet.split())
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


def _iso(day: int, month: int, year: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def find_dates(text: str) -> list[tuple[str, str]]:
    """Every date in the document, ISO, with the words around it."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            a, b, c = (int(g) for g in match.groups())
            iso = _iso(c, b, a) if a > 31 else _iso(a, b, c)
            if iso and iso not in seen:
                seen.add(iso)
                found.append((iso, _line_around(text, match.group(0))))
    for match in _MONTH_NAME.finditer(text):
        iso = _iso(int(match.group(1)), _MONTHS[match.group(2).lower()],
                   int(match.group(3)))
        if iso and iso not in seen:
            seen.add(iso)
            found.append((iso, _line_around(text, match.group(0))))
    return found


def classify(text: str) -> str:
    """What kind of document this is, by the words it uses."""
    lowered = text.lower()
    best, score = "other", 0
    for kind, markers in _CLASSIFIERS:
        hits = sum(1 for m in markers if m in lowered)
        if hits > score:
            best, score = kind, hits
    return best if score else "other"


def _reference(text: str) -> Extracted | None:
    """The reference number, preferring one a cue word introduces.

    A page can carry several slash-separated codes — a form number in the
    footer, a departmental code in the letterhead. The one that matters is the
    one written after "Acknowledgement No." and picking by position alone gets
    the footer.
    """
    candidates = list(_REFERENCE.finditer(text))
    if not candidates:
        return None
    lowered = text.lower()

    best: tuple[float, str, str] | None = None
    for match in candidates:
        value = match.group(1)
        window = lowered[max(0, match.start() - 90):match.start()]
        cued = any(cue in window for cue in _REF_CUES)
        digits = sum(c.isdigit() for c in value)
        score = (2.0 if cued else 0.0) + min(digits, 8) / 10
        if best is None or score > best[0]:
            best = (score, value, _line_around(text, value))
    if best is None:
        return None
    score, value, evidence = best
    return Extracted(value=value, evidence=evidence,
                     confidence=0.9 if score >= 2 else 0.55)


def _first(pattern: re.Pattern[str], text: str, confidence: float,
           group: int = 1) -> Extracted | None:
    match = pattern.search(text)
    if not match:
        return None
    value = " ".join(match.group(group).split())
    if not value:
        return None
    return Extracted(value=value[:180], evidence=_line_around(text, match.group(0)),
                     confidence=confidence)


def _status(text: str) -> Extracted | None:
    """The status, and the words it was read from — as the document spells them.

    The marker is matched case-insensitively but the EVIDENCE has to come from
    the document's own casing. Looking up the lowercased marker left every
    status finding with no evidence at all, because the slip says "Pending" and
    the table says "pending" — and a value the citizen is asked to confirm with
    nothing to check it against is not a question they can answer.
    """
    lowered = text.lower()
    for name, markers in _STATUS:
        for marker in markers:
            index = lowered.find(marker)
            if index >= 0:
                return Extracted(value=name, confidence=0.7,
                                 evidence=_line_around(text, text[index:index + len(marker)]))
    return None


# The heading above the petitioner's own details, in both languages. A petition
# this service produced writes exactly these; a petition typed elsewhere very
# often does too, because it is the standard Indian letter form.
_FROM_HEADINGS = frozenset({"from", "அனுப்புநர்"})
_TO_HEADINGS = frozenset({"to", "பெறுநர்"})

# "Age: 23", "Mobile number: +91 …" — the labelled lines that follow the name
# and address and mark the end of them.
_LABELLED_DETAIL = re.compile(r"\S\s*:\s*\S")


def _heading(line: str) -> str:
    return line.strip().rstrip(",:.").strip().casefold()


def _sender(text: str) -> tuple[Extracted | None, Extracted | None]:
    """The petitioner's name and address out of a petition's From block.

    Positional rather than pattern-matched, because the form is positional:
    the heading, then the name, then the address, then labelled details. There
    is no regex for "is this line a person's name" that does not also match
    half a letterhead.

    Read ONLY to be compared against what the citizen has said this time. See
    `attachment_conflicts` — an address found here never becomes the address on
    the new petition without the citizen choosing it.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if _heading(line) not in _FROM_HEADINGS:
            continue
        collected: list[str] = []
        for following in lines[index + 1:index + 9]:
            body = following.strip()
            if not body:
                if collected:
                    break
                continue                      # blank line before the block
            if _LABELLED_DETAIL.search(body) or _heading(body) in _TO_HEADINGS:
                break                         # into "Age: 23", or the To block
            collected.append(body)
        if not collected:
            continue
        name = Extracted(value=collected[0][:80], evidence=collected[0],
                         confidence=0.8)
        address = None
        if len(collected) > 1:
            joined = ", ".join(collected[1:])
            address = Extracted(value=joined[:240], evidence=joined, confidence=0.8)
        return name, address
    return None, None


def analyse(text: str, *, readable: bool = True, reason: str = "",
            low_confidence: bool = False, segments: Any = None) -> PriorPetition:
    """Read an attached document. Deterministic; no model involved.

    A document that could not be read comes back saying so, with no fields —
    which is the honest result and the one that makes the conversation ask the
    citizen to type the reference number instead of inventing one.

    `segments` is optional. When the caller supplies the document's pages or
    slides, each value is also told which one it came from, so the citizen is
    asked "is this the reference number, from page 2?" rather than being asked
    about a number with no address. Callers that do not have them lose only
    that, and every other behaviour here is unchanged.
    """
    if not readable or not str(text or "").strip():
        return PriorPetition(readable=False,
                             reason=reason or "Nothing could be read from this file.")

    body = str(text)
    prior = PriorPetition(kind=classify(body), low_confidence=low_confidence)
    prior.reference_number = _reference(body)

    petition_no = re.search(
        r"(?:petition|மனு)\s*(?:no\.?|number|எண்)\s*[:\-]?\s*([A-Z0-9/\-]{3,32})",
        body, re.I)
    if petition_no:
        prior.petition_number = Extracted(
            value=petition_no.group(1), evidence=_line_around(body, petition_no.group(0)),
            confidence=0.85)

    dates = find_dates(body)
    if dates:
        prior.submitted_on = Extracted(value=dates[0][0], evidence=dates[0][1],
                                       confidence=0.7 if len(dates) == 1 else 0.5)
        prior.other_dates = [d for d, _ in dates[1:6]]

    prior.department = (_first(_DEPARTMENT, body, 0.8)
                        or _first(_DEPARTMENT_TA, body, 0.7))
    prior.authority = (_first(_AUTHORITY, body, 0.8)
                       or _first(_AUTHORITY_TA, body, 0.75))
    prior.subject = _first(_SUBJECT, body, 0.85)
    prior.status = _status(body)
    prior.petitioner_name, prior.address = _sender(body)

    # Confidence is scaled down wholesale when the text itself came in weak, so
    # an OCR read never presents as though it were a clean text layer.
    if low_confidence:
        for name in ("reference_number", "petition_number", "petitioner_name",
                     "address", "submitted_on", "department", "authority",
                     "subject", "status"):
            value = getattr(prior, name)
            if value:
                value.confidence = round(value.confidence * 0.6, 2)

    _attribute(prior, segments)
    _mask(prior)
    return prior


def _mask(prior: PriorPetition) -> None:
    """Hide identifiers in anything that will be stored or shown.

    The evidence snippet beside each value is a LINE of the citizen's
    document, and a previous petition carries their Aadhaar and mobile in its
    own header. Without this, confirming a reference number read from page 2
    could put a full Aadhaar number onto the confirmation card and into the
    checkpoint, which is the one place this service has always refused to
    keep one.

    The values themselves are masked too, not just the evidence. A reference
    number is never twelve grouped digits, so nothing the petition needs to
    quote is affected — and if a document ever does yield an identifier as a
    value, it must not survive in full either.
    """
    from ..services.mask import mask_for_display

    for name in ("reference_number", "petition_number", "petitioner_name",
                 "address", "submitted_on", "department", "authority",
                 "subject", "grievance", "requested_action", "status"):
        value = getattr(prior, name, None)
        if value is None:
            continue
        value.value = mask_for_display(value.value)
        value.evidence = mask_for_display(value.evidence)


def _attribute(prior: PriorPetition, segments: Any) -> None:
    """Record which page or slide each value was read from.

    Looked up by the value first and by the surrounding line second: a
    reference number is distinctive enough to find on its own, and when it is
    not — a bare date — the line it sits in usually is.

    A value printed on several pages, as a header is, reports the FIRST page
    it appears on. That is the honest reading of "where can I find this", and
    it is the page a citizen turning to check will reach first. A value that
    cannot be found at all is left unattributed rather than assigned to
    page 1.
    """
    if not segments:
        return
    from ..services.extraction import locate

    for name in ("reference_number", "petition_number", "petitioner_name",
                 "address", "submitted_on", "department", "authority",
                 "subject", "status"):
        value = getattr(prior, name)
        if not value:
            continue
        found = locate(segments, value.value) or locate(segments, value.evidence)
        if found is not None:
            value.page = found.number
            value.unit = found.unit


# --------------------------------------------------------------------------- #
# What the petition may say about it
# --------------------------------------------------------------------------- #

def reference_sentence(prior: PriorPetition, language: Language = "en") -> str:
    """The sentence a new petition may carry about the earlier one.

    Built from confirmed values only, and it says only what those values
    support: with a date and a number it names both, with a number alone it
    names the number. It never says "I received no reply" — that is a claim
    about the office's conduct that no acknowledgement slip evidences.
    """
    number = prior.reference_number.value if prior.reference_number else ""
    when = prior.submitted_on.value if prior.submitted_on else ""
    if not number and not when:
        return ""

    if language == "ta":
        pretty = _ta_date(when)
        if number and when:
            return (f"இதே விவகாரம் தொடர்பாக {pretty} அன்று ஒப்புகை எண் {number} "
                    f"மூலம் ஏற்கனவே மனு அளித்துள்ளேன். எனினும் பிரச்சினை "
                    f"இதுவரை தீர்க்கப்படவில்லை.")
        if number:
            return (f"இதே விவகாரம் தொடர்பாக ஒப்புகை எண் {number} மூலம் ஏற்கனவே "
                    f"மனு அளித்துள்ளேன். எனினும் பிரச்சினை இதுவரை "
                    f"தீர்க்கப்படவில்லை.")
        return (f"இதே விவகாரம் தொடர்பாக {pretty} அன்று ஏற்கனவே மனு அளித்துள்ளேன். "
                f"எனினும் பிரச்சினை இதுவரை தீர்க்கப்படவில்லை.")

    pretty = _en_date(when)
    if number and when:
        return (f"I had previously submitted a petition regarding the same issue "
                f"on {pretty} under acknowledgement number {number}. However, the "
                f"issue remains unresolved.")
    if number:
        return (f"I had previously submitted a petition regarding the same issue "
                f"under acknowledgement number {number}. However, the issue "
                f"remains unresolved.")
    return (f"I had previously submitted a petition regarding the same issue on "
            f"{pretty}. However, the issue remains unresolved.")


def _en_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d-%m-%Y")
    except ValueError:
        return iso


def _ta_date(iso: str) -> str:
    return _en_date(iso)
