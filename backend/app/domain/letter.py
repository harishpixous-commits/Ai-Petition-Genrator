"""Assembling the petition text.

The SHAPE of the letter is deterministic and lives here, and it follows the
standard Tamil petition format used when writing to a District Collector or a
Corporation Commissioner:

    அனுப்புநர்,            the petitioner: name, address, age, Aadhaar
    பெறுநர்,               the office it is addressed to
    மதிப்பிற்குரிய ஐயா / அம்மா,
    பொருள்: …  தொடர்பாக.    what the petition concerns, in one line
    வணக்கம். …             the opening
    <the grievance>        the citizen's own words, verbatim
    எனவே, …                the prayer
    நன்றி!
    இப்படிக்கு,            the signature block
    நாள்: / இடம்:           date and place, at the foot

Every citizen-supplied value is placed by this code, never by a model. A model
contributes only FRAMING — the subject line, the opening and the closing request
— and each of those has a deterministic fallback used whenever the model is
unavailable, slow, or answers in the wrong script. A letter that reads slightly
flatly is a working letter; a letter with a hallucinated date is a problem for
the citizen at the counter.

The output is plain text with meaningful leading whitespace, because the DOCX
renderer recovers structure from the text itself. That means a citizen or an
officer can edit the letter freely and it still renders as the kind of letter it
now is — and it is why `render.py`'s patterns have to stay in step with the
LABELS below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from .fields import display_value
from .phrasing import DISCLAIMER, Language
from .templates import LetterTemplate

BLOCK_INDENT = "    "
SIGN_GAP = 2

# Every fixed word the letter itself uses, in both languages.
#
# These are here rather than hard-coded in English for one concrete reason: a
# Tamil session filled from a template with Tamil text would otherwise produce a
# letter whose only English was the structural furniture — enough to make
# `needs_translation` true and send the finished letter through a translator to
# change eight words. Localising them means a Tamil petition is assembled
# complete and the translate node is never entered.
#
# `render.py` classifies lines by these same words, so a change here needs the
# matching pattern there.
LABELS: dict[str, dict[str, str]] = {
    "from":       {"en": "From,",               "ta": "அனுப்புநர்,"},
    "to":         {"en": "To,",                 "ta": "பெறுநர்,"},
    "salutation": {"en": "Respected Sir / Madam,", "ta": "மதிப்பிற்குரிய ஐயா / அம்மா,"},
    "subject":    {"en": "Subject",             "ta": "பொருள்"},
    "thanks":     {"en": "Thank you!",          "ta": "நன்றி!"},
    "signoff":    {"en": "Yours faithfully,",   "ta": "இப்படிக்கு,"},
    "date":       {"en": "Date",                "ta": "நாள்"},
    "place":      {"en": "Place",               "ta": "இடம்"},
    "enclosures": {"en": "Enclosures",          "ta": "இணைப்புகள்"},
    "note":       {"en": "Note",                "ta": "குறிப்பு"},
    # The caption above each attached file, on its own page after the letter.
    "enclosure_page": {"en": "Enclosure", "ta": "இணைப்பு"},
    # Printed small under that caption. A reproduction is not the original, and
    # an officer comparing the two should be told which they are holding.
    "enclosure_note": {
        "en": "Reproduced from the document submitted by the petitioner.",
        "ta": "மனுதாரர் சமர்ப்பித்த ஆவணத்திலிருந்து நகலெடுக்கப்பட்டது.",
    },
    # "…தொடர்பாக." closes a Tamil subject line. English subjects do not take a
    # suffix, so it is empty there rather than translated into something odd.
    "subject_suffix": {"en": "", "ta": " தொடர்பாக."},
}


def label(key: str, language: Language) -> str:
    return LABELS[key].get(language) or LABELS[key]["en"]


def reference_number(session_id: str, when: date | None = None) -> str:
    """A stable, human-quotable reference. No randomness: the same session always
    produces the same reference, so a reprint matches the citizen's copy.

    It does not appear in the body — the standard format has no reference line —
    but it is printed in the document footer, which is what an office files by.
    """
    when = when or date.today()
    tail = session_id.replace("-", "")[-6:].upper()
    return f"AP/{when.year}/{tail}"


# The grievance is the substance of the petition and is placed VERBATIM, in the
# body, never passed through a rewriter and never summarised. A petition in
# which the citizen's complaint has been reworded is a different petition.
VERBATIM_FIELDS = ("grievance",)

# Fields that identify the petitioner. They are listed under the sender block,
# which is where a real petition carries them, rather than in a table of their
# own. Order follows the template, not this tuple.
SENDER_ADDRESS_FIELDS = ("address", "applicant_address")
SENDER_NAME_FIELDS = ("applicant_name", "petitioner_name")

# Every field whose value is printed exactly as the citizen typed it.
CITIZEN_TEXT_FIELDS = SENDER_NAME_FIELDS + SENDER_ADDRESS_FIELDS + VERBATIM_FIELDS


# --------------------------------------------------------------------------- #
# Composition — the parts a model may write
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Composition:
    """The parts of the petition a model may write.

    The subject, the opening, the representation and the closing prayer. None of
    them is a NEW fact: the facts are the citizen's particulars and their
    grievance, and both of those are placed by code. What the model adds is the
    development an officer expects to read — why the matter needs attention,
    what it affects, and precisely what is being asked for — drawn only from
    what the citizen actually said.

    `background` is the elaboration, and it is the one field with no standard
    wording behind it. Developing an issue means having read the issue, so a
    petition produced with no model reachable simply does not carry this
    section. It is a complete petition without it; it is a fuller one with it.

    Every field is optional and each falls back on its own.
    """

    subject: str | None = None
    introduction: str | None = None
    background: str | None = None
    request: str | None = None

    @property
    def empty(self) -> bool:
        return not any((self.subject, self.introduction, self.background, self.request))


def fallback_composition(
    template: LetterTemplate,
    fields: dict[str, Any],
    language: Language,
) -> Composition:
    """The wording used when no model is available.

    This is the standard wording of the format itself, not an approximation of
    it: a petition written entirely without a model is still a correctly formed
    petition, only less specific about what it concerns.
    """
    if language == "ta":
        return Composition(
            subject=None,
            introduction=(
                "வணக்கம். நான் மேற்கண்ட முகவரியில் வசித்து வருகிறேன். இந்தக் கடிதத்தின் மூலம் "
                "எங்கள் பகுதியில் உள்ள ஒரு முக்கியப் பிரச்சனை குறித்து தங்கள் கவனத்திற்குக் "
                "கொண்டு வர விரும்புகிறேன்."
            ),
            request=(
                "எனவே, பொதுமக்களின் நலனைக் கருத்தில் கொண்டு, தாங்கள் இந்த விஷயத்தில் தலையிட்டு, "
                "எங்கள் பிரச்சனைக்கு விரைவாகத் தீர்வு காண நடவடிக்கை எடுக்குமாறு தாழ்மையுடன் "
                "கேட்டுக்கொள்கிறேன்."
            ),
        )

    return Composition(
        subject=None,
        introduction=(
            "I reside at the address given above. Through this letter I wish to "
            "bring to your kind attention an important problem in our locality."
        ),
        request=(
            "I therefore humbly request that you intervene in this matter and "
            "take action to resolve our problem at the earliest, in the interest "
            "of the public."
        ),
    )


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def _paragraphs(text: str, indent: str = "   ") -> list[str]:
    """One output line per PARAGRAPH of the citizen's text. No hard wrapping.

    An earlier version wrapped to 88 columns so the plain-text preview looked
    tidy. That was wrong: the DOCX renderer treats every line as its own
    paragraph, so a wrapped sentence became several justified paragraphs and its
    last few words were stranded on a line of their own. Word and LibreOffice
    know the real font metrics and wrap far better than a column count can,
    particularly for Tamil, where a glyph cluster is not one character wide.
    """
    out: list[str] = []
    for paragraph in str(text).split("\n"):
        stripped = paragraph.strip()
        out.append(f"{indent}{stripped}" if stripped else "")
    return out


def verbatim_lines(fields: dict[str, Any]) -> frozenset[str]:
    """Everything in the letter that is the citizen's own text, stripped.

    Three fields reach the page exactly as they were typed: the name, the
    address, and the grievance. Two things depend on knowing which lines those
    are, and both matter.

    The translator must never touch them. The grievance is placed verbatim
    because a petition in which the complaint has been reworded is a different
    petition. A name and an address are worse still: the pinned-terms table in
    `translate.py` exists because a translator once rendered Coimbatore as
    Koyambedu, a locality in Chennai. A petition that names the wrong town is
    not a petition with a translation error in it; it is a petition that will
    not be acted on.

    And their script must not be what decides the letter needs translating at
    all. A citizen may write the complaint in Tamil inside an English petition,
    or sign a Tamil petition with a name spelled in English — both are the
    document working correctly. Before this, either one routed a finished,
    correct letter to the translator, and with no translator configured put a
    warning on it saying it had not been translated.

    Stripped rather than indented, because the same value is printed in three
    shapes: indented in the sender block, indented as a paragraph, and bare on
    the signature line. The callers compare both the raw line and its stripped
    form, so one entry covers all three.
    """
    out: set[str] = set()
    for name in CITIZEN_TEXT_FIELDS:
        for paragraph in str(fields.get(name) or "").splitlines():
            stripped = paragraph.strip()
            if stripped:
                out.add(stripped)
    return frozenset(out)


_TRAILING_PIN = re.compile(r"[\s,–—-]*\b\d{6}\b\s*$")


def derive_place(address: str) -> str:
    """The town a petition is signed in, taken from the petitioner's address.

    A petition carries "இடம்:" at the foot, and the citizen was not asked for it
    separately — so it comes from the last meaningful part of the address they
    did give. "12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர் - 641004" yields
    "கோயம்புத்தூர்".

    Returns "" when the address has no comma to work from. An empty place line
    is omitted entirely rather than guessed at: a wrong town on a petition is
    worse than a missing one, and the citizen can write it in by hand.
    """
    trimmed = _TRAILING_PIN.sub("", str(address or "").strip())
    parts = [p.strip() for p in trimmed.split(",") if p.strip()]
    return parts[-1] if len(parts) > 1 else ""


def _sender_block(
    template: LetterTemplate,
    fields: dict[str, Any],
    language: Language,
) -> list[str]:
    """Name, address, then the identifying details, as a real petition carries
    them — not as a separate table."""
    lines: list[str] = []

    name = next((fields[n] for n in SENDER_NAME_FIELDS if fields.get(n)), "")
    if name:
        lines.append(f"{BLOCK_INDENT}{name}")

    address = next((fields[n] for n in SENDER_ADDRESS_FIELDS if fields.get(n)), "")
    if address:
        lines.append(f"{BLOCK_INDENT}{address}")

    # Everything else the form collected about the petitioner, in template
    # order: age, Aadhaar, and a mobile number or email if the form asks for
    # them. Adding a field to petition.yaml puts it here with no code change.
    skip = set(VERBATIM_FIELDS) | set(SENDER_NAME_FIELDS) | set(SENDER_ADDRESS_FIELDS)
    for spec in template.fields:
        if spec.name in skip or spec.name not in fields:
            continue
        value = display_value(spec.type, fields[spec.name], language)
        lines.append(f"{BLOCK_INDENT}{spec.label_for(language)}: {value}")

    return lines


def build_letter_text(
    *,
    template: LetterTemplate,
    fields: dict[str, Any],
    language: Language,
    composition: Composition | None,
    session_id: str,
    when: date | None = None,
    attachments: Any = None,
    prior_reference: str = "",
) -> str:
    """The complete petition, as text. Pure function of its arguments.

    `attachments` is the citizen's actual enclosures and `prior_reference` a
    sentence about an earlier petition they confirmed. Both default to nothing,
    and nothing is what gets printed when they are absent.
    """
    when = when or date.today()
    lines: list[str] = []

    # -- date and place, at the top ----------------------------------------- #
    #
    # Printed flush right, which is where a letter carries them. In this plain
    # text they are simply the first lines; the renderer and the preview both
    # recognise the opening block by its SHAPE — a short "label: value" run
    # before the first blank line — rather than by the words "Date" and
    # "Place", so a petition translated into a third language keeps them on
    # the right instead of quietly falling back to the left margin.
    #
    # The place is derived from the address the citizen gave, and is left out
    # entirely when it cannot be: a wrong town on a petition is worse than a
    # missing one, and they can write it in by hand.
    lines.append(f"{label('date', language)}: {when.strftime('%d-%m-%Y')}")
    place = derive_place(next((fields[n] for n in SENDER_ADDRESS_FIELDS if fields.get(n)), ""))
    if place:
        lines.append(f"{label('place', language)}: {place}")
    lines.append("")

    # Each slot falls back on its own: a model that produced a good opening and
    # a poor request keeps the opening.
    written = composition or Composition()
    standard = fallback_composition(template, fields, language)
    subject = (written.subject or "").strip() or template.text_for("subject", language)
    introduction = (written.introduction or "").strip() or standard.introduction or ""
    request = (written.request or "").strip() or standard.request or ""
    # No standard wording behind this one: see `Composition`.
    background = (written.background or "").strip()

    # -- அனுப்புநர், / From, ------------------------------------------------ #
    lines.append(label("from", language))
    lines.extend(_sender_block(template, fields, language))
    lines.append("")

    # -- பெறுநர், / To, ----------------------------------------------------- #
    lines.append(label("to", language))
    lines.append(f"{BLOCK_INDENT}{template.text_for('addressee', language)}")
    department = template.text_for("department", language)
    if department:
        lines.append(f"{BLOCK_INDENT}{department}")
    lines.append("")

    # -- salutation, then subject ------------------------------------------- #
    lines.append(label("salutation", language))
    lines.append("")
    suffix = label("subject_suffix", language)
    # A model asked for a Tamil subject sometimes closes it itself; adding the
    # suffix again would read "…தொடர்பாக. தொடர்பாக."
    if suffix and subject.rstrip().endswith(suffix.strip().rstrip(".")):
        suffix = "."
    lines.append(f"{label('subject', language)}: {subject.rstrip('.')}{suffix}")
    lines.append("")

    # -- the opening -------------------------------------------------------- #
    lines.extend(_paragraphs(introduction))
    lines.append("")

    # -- the citizen's own words, exactly as given -------------------------- #
    for name in VERBATIM_FIELDS:
        value = str(fields.get(name) or "").strip()
        if value:
            lines.extend(_paragraphs(value))
            lines.append("")

    # -- the representation, developing what the citizen said --------------- #
    #
    # It sits AFTER the verbatim complaint, never before it. An officer reads
    # what the citizen actually said first, and the development second — which
    # also makes it obvious which of the two is the citizen's own account.
    if background:
        lines.extend(_paragraphs(background))
        lines.append("")

    # -- the earlier petition, when the citizen confirmed one --------------- #
    #
    # Its own paragraph, written in code from values the citizen has read back
    # and agreed to. It is deliberately NOT left to the drafting model: an
    # acknowledgement number is exactly the kind of thing a model reproduces
    # ALMOST correctly, and a petition citing a reference that does not resolve
    # sends an officer looking for a file that is not there.
    if prior_reference:
        lines.extend(_paragraphs(prior_reference))
        lines.append("")

    # -- the prayer --------------------------------------------------------- #
    lines.extend(_paragraphs(request))
    lines.append("")

    # -- what is actually in the envelope ----------------------------------- #
    #
    # This used to print the template's list on every petition ever produced:
    # "Copy of Aadhaar card", "Copy of proof of residence", "Copies of any
    # earlier petition". A receiving officer reading that has been told three
    # documents are enclosed. When they are not, it is the CITIZEN who looks as
    # though they withheld them.
    #
    # So the template's list is now a suggestion, shown when the citizen is
    # asked whether they want to attach anything, and this section lists only
    # files that exist. No attachments, no section.
    enclosures = list(attachments.lines(language)) if attachments else []
    if enclosures:
        lines.append(f"  {label('enclosures', language)}:")
        for i, item in enumerate(enclosures, start=1):
            lines.append(f"  {i}. {item}")
        lines.append("")

    # -- thanks, sign-off, signature ---------------------------------------- #
    lines.append(label("thanks", language))
    lines.append("")
    lines.append(label("signoff", language))
    lines.extend([""] * SIGN_GAP)
    name = next((fields[n] for n in SENDER_NAME_FIELDS if fields.get(n)), "")
    if name:
        lines.append(str(name))
    lines.append("")

    lines.append(f"{label('note', language)}: {DISCLAIMER[language]}")

    return "\n".join(lines)


def verification_targets(
    template: LetterTemplate,
    fields: dict[str, Any],
    language: Language,
) -> dict[str, str]:
    """Field name -> the exact string that MUST appear in the rendered document.

    This is what `verify` checks against the text extracted back out of the
    generated DOCX. Only required fields are targets: an optional value the
    citizen declined is legitimately absent, and asserting on it would fail a
    letter that is correct.
    """
    targets: dict[str, str] = {}
    for spec in template.fields:
        if not spec.required or spec.name not in fields:
            continue
        if spec.name in VERBATIM_FIELDS:
            # Verify the complete account, including the requested remedy at
            # the end. Whitespace normalization already handles line wrapping;
            # checking only the opening words misses truncated complaints.
            targets[spec.name] = " ".join(str(fields[spec.name]).split())
            continue
        targets[spec.name] = display_value(spec.type, fields[spec.name], language)
    return targets
