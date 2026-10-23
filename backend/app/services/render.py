"""Rendering the petition to DOCX and PDF, and reading it back out again.

The central idea, carried over from the Node service's `letter-docx.mjs`: the
structure of the letter is recovered FROM THE TEXT rather than rebuilt from the
record. That is what lets a citizen or an officer edit a line and have it still
render as the kind of line it now is — and it is why `verify` can read the
finished document back and check it against the values that went in.

The font default matters more than it looks. A DOCX whose runs carry a
Latin-only font renders Tamil as boxes on the machine that opens it, and nobody
discovers this until a citizen is standing at a counter with an unreadable
letter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor, Twips

from ..config import Settings, get_settings
from ..domain import languages
from ..domain.emblem import Placement
from . import enclosures as enclosure_service

log = logging.getLogger(__name__)

INDENT = Twips(420)      # ~0.3 inch

def _enclosures_line_pattern() -> re.Pattern[str]:
    """Pattern that moves the Enclosures count out of the body text and
    into the signature block (where the brief says it belongs — opposite
    the physical signature).

    The ENGLISH / TAMIL / MALAYALAM / TELUGU / HINDI labels are read off
    `app/domain/letter.py::LABELS["enclosures"]` so the two files stay in
    sync: adding a sixth language updates both ends in one place. The
    older hard-coded regex missed `संलग्नक` because the Hindi label was
    the slightly different `संलग्न`, and a Hindi petition verified in
    production but failed on the DOCX text-content check.
    """
    from ..domain.letter import LABELS
    labels = sorted(set(LABELS.get("enclosures", {}).values()),
                    key=len, reverse=True)
    if not labels:
        labels = ["Enclosures"]
    joined = "|".join(re.escape(label) for label in labels)
    return re.compile(rf"^\s*({joined})\s*:\s*(.+)$")


_ENCLOSURES_LINE: re.Pattern[str] | None = None


def _enclosures_match(stripped: str):
    """Lazy-init cached compile. See `_enclosures_line_pattern`."""
    global _ENCLOSURES_LINE
    if _ENCLOSURES_LINE is None:
        _ENCLOSURES_LINE = _enclosures_line_pattern()
    return _ENCLOSURES_LINE.match(stripped)



# --------------------------------------------------------------------------- #
# The emblem
# --------------------------------------------------------------------------- #


def emblem_path(settings: Settings | None = None) -> Path | None:
    """The emblem file to print, or None when the deployment has none.

    Configurable rather than fixed, because the same service run by a different
    department prints a different emblem, and because a deployment that has not
    been given one must still produce a petition rather than fail.
    """
    s = settings or get_settings()
    configured = (s.letter_emblem or "").strip()
    if configured.lower() in ("", "off", "none"):
        return None
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parent.parent / candidate
    return candidate if candidate.is_file() else None


_ALIGNMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
}


def _draw_emblem(paragraph, path: Path, placement: Placement, settings: Settings) -> None:
    paragraph.alignment = _ALIGNMENTS[placement.align]
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.add_run().add_picture(str(path), height=Twips(int(settings.letter_emblem_twips)))


def _add_emblem_header(document, settings: Settings, placement: Placement) -> bool:
    """Draw the emblem where it was asked for, on the pages it was asked for.

    In a header rather than in the body, because a petition that runs to two
    pages is ordinary and an emblem that appears only on the first is not a
    letterhead — it is a picture someone pasted at the top. Word and
    LibreOffice both repeat a header on every page, and the PDF is converted
    from this same file, so one placement covers both formats.

    "First page only" uses the section's own different-first-page setting
    rather than a second section or a manual page break: it is the mechanism
    the format has for exactly this, and it survives the citizen later editing
    the wording and the letter changing length.
    """
    path = emblem_path(settings)
    if path is None or placement.pages == "none":
        return False

    section = document.sections[0]
    try:
        if placement.pages == "first":
            section.different_first_page_header_footer = True
            header = section.first_page_header
        else:
            section.different_first_page_header_footer = False
            header = section.header
        # python-docx gives a new header one empty paragraph; use it rather
        # than adding a second, which would push the body down by a blank line.
        paragraph = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        _draw_emblem(paragraph, path, placement, settings)
    except Exception as exc:  # noqa: BLE001
        # A missing or unreadable emblem is a letterhead problem, never a
        # reason a citizen leaves without their petition.
        log.warning("render.emblem_failed", extra={"error": str(exc)[:160],
                                                   "path": str(path)})
        return False
    return True


# --------------------------------------------------------------------------- #
# Line classification
# --------------------------------------------------------------------------- #

# These must stay in step with `domain/letter.py`'s LABELS table: the letter is
# written with those words and its structure is recovered here by matching them.
# Both languages are recognised, because a Tamil petition is assembled complete
# in Tamil rather than translated afterwards.
#
# The format is the standard Tamil petition to a District Collector:
#
#   அனுப்புநர்,            block heading, bold, on its own line
#       name / address / age / Aadhaar
#   பெறுநர்,               block heading
#       office
#   மதிப்பிற்குரிய ஐயா / அம்மா,
#   பொருள்: …  தொடர்பாக.    bold, one line
#   body paragraphs, the middle one being the citizen's own words
#   நன்றி,
#   இப்படிக்கு,            sign-off, then the signature
#   நாள்: / இடம்:           at the foot

# "அனுப்புநர்," and "பெறுநர்," stand alone — no colon, nothing after them.
_BLOCK = re.compile(r"^(From|To|அனுப்புநர்|பெறுநர்)\s*,?\s*$", re.I)
_SALUTATION = re.compile(r"^(Respected|Sir\s*/\s*Madam|மதிப்பிற்குரிய|ஐயா)", re.I)
_SUBJECT = re.compile(r"^(Subject|Sub\b|பொருள்)[^:]*:", re.I)
# Date and place close the letter and are read as a pair.
_FOOT = re.compile(r"^(Date|Place|நாள்|இடம்)\s*:", re.I)
_SIGNOFF = re.compile(r"^(Yours faithfully|Yours sincerely|இப்படிக்கு|தங்கள் உண்மையுள்ள)", re.I)
# "Thanking you" as well as "Thank you": the letter says the first, and an
# AI-written closing or an older saved petition may say the second. A
# sign-off this does not recognise is centred as body text, which puts the
# signature block in the middle of the page.
_THANKS = re.compile(r"^(Thanking you|Thank you|நன்றி)", re.I)
_NUMBERED = re.compile(r"^\s*\d+\.\s")
_NOTE = re.compile(r"^(Note|குறிப்பு)\s*:", re.I)
_SECTION_WORDS = re.compile(r"^(Encl|Enclosure|இணைப்புகள்)", re.I)


def _localized_label_alternation(*keys: str) -> str:
    """Build classifier patterns from the same labels used to assemble letters.

    Translated letters are rendered from text too, so every supported language
    must retain the same DOCX structure when it is read back for verification.
    """
    from ..domain.letter import LABELS

    values = {
        value.rstrip(" ,:").strip()
        for key in keys
        for value in LABELS.get(key, {}).values()
        if value.strip()
    }
    return "|".join(re.escape(value) for value in sorted(values, key=len, reverse=True))


_BLOCK = re.compile(rf"^(?:{_localized_label_alternation('from', 'to')})\s*,?\s*$", re.I)
_SALUTATION = re.compile(rf"^(?:{_localized_label_alternation('salutation')})", re.I)
_SUBJECT = re.compile(rf"^(?:{_localized_label_alternation('subject')})[^:]*:", re.I)
_FOOT = re.compile(
    rf"^(?:{_localized_label_alternation('date', 'place')})\s*:", re.I,
)
_SIGNOFF = re.compile(rf"^(?:{_localized_label_alternation('signoff')})", re.I)
_THANKS = re.compile(
    rf"^(?:{_localized_label_alternation('thanks')}|Thank you)", re.I,
)
_NOTE = re.compile(rf"^(?:{_localized_label_alternation('note')})\s*:", re.I)
_SECTION_WORDS = re.compile(
    rf"^(?:{_localized_label_alternation('enclosures')})", re.I,
)


# A short "label: value" line. Deliberately not "Date" or "Place": those words
# are English, and a petition translated into a third language has to keep its
# opening block on the right rather than quietly sliding back to the margin.
_LABELLED = re.compile(r"^[^:\n]{1,24}:\s*\S")
_MAX_OPENING_LINES = 3


def opening_block(lines: list[str]) -> int:
    """How many lines at the top are the date-and-place block, if any.

    Recognised by SHAPE and POSITION — a short run of "label: value" lines
    before the first blank one — so it survives translation, and so a letter
    that opens with "From," (a hand edit that removed the block, or an older
    petition) is read as having no opening block rather than having its sender
    details flung to the right margin.
    """
    head: list[str] = []
    for line in lines:
        if not line.strip():
            break
        head.append(line)
        if len(head) > _MAX_OPENING_LINES:
            return 0
    if not head:
        return 0
    return len(head) if all(_LABELLED.match(line.strip()) for line in head) else 0


def classify(line: str, index: int, total: int) -> str:
    """What kind of line is this? Recovered from the text, so edits survive.

    Order matters: the specific patterns are tested before the generic
    "indented means part of a block" rule, so a sender line that happens to
    contain a colon is still a sender line.
    """
    text = line.rstrip()
    if not text.strip():
        return "blank"
    if _BLOCK.match(text.strip()):
        return "block"
    if _SALUTATION.match(text):
        return "salutation"
    if _SUBJECT.match(text):
        return "subject"
    if _FOOT.match(text):
        return "foot"
    if _SIGNOFF.match(text):
        return "signoff"
    if _THANKS.match(text):
        return "thanks"
    if _NOTE.match(text):
        return "note"
    if _SECTION_WORDS.match(text.strip()):
        return "section"
    if _NUMBERED.match(text):
        return "numbered"
    if re.match(r"^\s{4,}\S", line):
        # Inside an அனுப்புநர் / பெறுநர் block.
        return "party"
    if re.match(r"^\s{2,}\S", line):
        return "indented"
    # The petitioner's name under the sign-off: a short, unindented line among
    # the last few, carrying no sentence punctuation of its own.
    if index > total - 6 and len(text) < 60 and not text.endswith((".", ":", "!", "?")):
        return "signature"
    return "body"


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #


def _face_for(text: str, default: str) -> str:
    """The font family this particular text needs.

    Chosen by the script actually present, never by the session language: a
    petition in one language routinely carries the citizen's own words in
    another, and their name and address stay in whatever script they typed.
    Falls back to the configured family, so English runs and anything this
    service does not recognise behave exactly as before.
    """
    code = languages.script_of(str(text or ""))
    return languages.spec(code).font_family if code else default


def _style_run(run, font: str, size: int = 11, *, bold: bool = False,
               italic: bool = False, color: str | None = None) -> None:
    font = _face_for(run.text, font)
    run.font.name = font
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    # python-docx sets only the Latin face by default; without eastAsia and cs
    # the Tamil runs fall back to whatever the reader picks, which is usually
    # not a Tamil font at all.
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), font)


def _set_cell_border(cell, *, sides=("top", "left", "right", "bottom"),
                     color="333333", size="6") -> None:
    """Draw a solid border on the named sides of a DOCX table cell.

    `size` is in eighths of a point (6 = 0.75pt), which is the python-docx
    convention for `w:sz`. Done through OxmlElement because python-docx has
    no high-level setter for per-side borders.
    """
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for side in sides:
        tag = qn(f"w:{side}")
        existing = borders.find(tag)
        if existing is not None:
            borders.remove(existing)
        element = OxmlElement(f"w:{side}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:color"), color)
        borders.append(element)


def _qr_png_bytes(payload: str, box: int = 4) -> bytes | None:
    """A small QR encoding `payload` as PNG bytes, or None if qrcode is
    unavailable or encoding fails. `box` is the module pixel count — 4
    makes a ~1in square at 300 dpi."""
    try:
        import qrcode  # soft dependency, see requirements.txt
    except Exception:  # noqa: BLE001
        return None
    try:
        from io import BytesIO
        image = qrcode.make(payload, box_size=box, border=1)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _add_official_header(document, reference: str, font: str) -> None:
    """The three-cell header: Ref No + QR on the left, title centred, a
    bordered "For Office Use" box on the right.

    Rendered as a 1x3 DOCX table so LibreOffice lays it out at the top of
    page 1 without pushing the body down a line each time another header
    element is added. Autofits off; column widths are set explicitly so a
    long reference does not squeeze the middle title into a wrap.
    """
    table = document.add_table(rows=1, cols=3)
    table.autofit = False
    table.allow_autofit = False
    # Fixed widths that fit the A4 text area after the chosen margins.
    widths = (Inches(1.95), Inches(2.95), Inches(1.8))
    for cell, width in zip(table.rows[0].cells, widths, strict=True):
        cell.width = width
        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    left, centre, right = table.rows[0].cells

    # --- LEFT: reference number + QR ----------------------------------- #
    ref_paragraph = left.paragraphs[0]
    ref_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    ref_paragraph.paragraph_format.space_after = Pt(2)
    label_run = ref_paragraph.add_run("Petition Ref No: ")
    _style_run(label_run, font, size=10, bold=True)
    value_run = ref_paragraph.add_run(reference or "AP/—/—")
    _style_run(value_run, font, size=10, bold=True)

    qr_bytes = _qr_png_bytes(reference) if reference else None
    if qr_bytes:
        from io import BytesIO
        qr_paragraph = left.add_paragraph()
        qr_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        qr_paragraph.paragraph_format.space_after = Pt(0)
        qr_run = qr_paragraph.add_run()
        qr_run.add_picture(BytesIO(qr_bytes), width=Inches(0.75))

    # --- CENTRE: the title --------------------------------------------- #
    centre_paragraph = centre.paragraphs[0]
    centre_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    centre_paragraph.paragraph_format.space_before = Pt(3)
    centre_paragraph.paragraph_format.space_after = Pt(0)
    title_run = centre_paragraph.add_run("PUBLIC GRIEVANCE REDRESSAL PETITION")
    _style_run(title_run, font, size=10, bold=True)
    subtitle_paragraph = centre.add_paragraph()
    subtitle_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_paragraph.paragraph_format.space_after = Pt(0)
    subtitle_run = subtitle_paragraph.add_run("Tamil Nadu — District Collectorate")
    _style_run(subtitle_run, font, size=9, color="666666")

    # --- RIGHT: the bordered "For Office Use" box ---------------------- #
    _set_cell_border(right)
    endorsement_paragraph = right.paragraphs[0]
    endorsement_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    endorsement_paragraph.paragraph_format.space_before = Pt(2)
    endorsement_paragraph.paragraph_format.space_after = Pt(2)
    heading_run = endorsement_paragraph.add_run("FOR OFFICE USE")
    _style_run(heading_run, font, size=9, bold=True)
    sub = right.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(2)
    sub_run = sub.add_run("Collector Endorsement\n(Dept / Priority)")
    _style_run(sub_run, font, size=8, italic=True, color="555555")
    # Three blank lines leave the writing room the brief asked for.
    for _ in range(3):
        blank = right.add_paragraph()
        blank.paragraph_format.line_spacing = Pt(10)
        blank.paragraph_format.space_after = Pt(0)


def _add_signature_block(document, name: str | None,
                         enclosure_label: str, enclosure_value: str,
                         font: str) -> None:
    """A 1x2 table at the end of the letter: Enclosures count on the left,
    signature space + typed name on the right. An 18pt top gap gives about
    25px of room for a physical signature without adding extra blank lines.

    `enclosure_label` and `enclosure_value` are the words captured off the
    body-text "Enclosures:" / "இணைப்புகள்:" / "संलग्न:" line, so the signature
    table always speaks the language the letter was composed in. The
    English-hard-coded earlier version lost the Tamil word on a Tamil
    petition and verification found the line missing from the DOCX."""
    table = document.add_table(rows=1, cols=2)
    table.autofit = False
    for cell, width in zip(table.rows[0].cells,
                           (Inches(2.8), Inches(4.0)), strict=True):
        cell.width = width
        cell.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM

    left, right = table.rows[0].cells

    # LEFT — enclosures count, opposite the signature.
    enc_paragraph = left.paragraphs[0]
    enc_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    enc_paragraph.paragraph_format.space_before = Pt(0)
    enc_label_run = enc_paragraph.add_run(f"{enclosure_label}: ")
    _style_run(enc_label_run, font, size=11, bold=True)
    enc_value_run = enc_paragraph.add_run(enclosure_value)
    _style_run(enc_value_run, font, size=11)

    # RIGHT — signature space, then (Signature) / Name.
    #
    # 18pt is approximately 25 CSS pixels of clear signing space.
    # Applying it before the marker keeps the name and marker together and
    # saves the spare blank lines that used to push the closing onto page 2.
    marker = right.paragraphs[0]
    marker.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    marker.paragraph_format.space_before = Pt(18)
    marker.paragraph_format.space_after = Pt(0)
    marker_run = marker.add_run("(Signature)")
    _style_run(marker_run, font, size=10, italic=True, color="555555")
    if name:
        name_run = marker.add_run(f" / {name}")
        _style_run(name_run, font, size=11, bold=True)


def render_docx(
    text: str,
    destination: Path,
    *,
    reference: str = "",
    title: str = "Petition",
    settings: Settings | None = None,
    placement: Placement | None = None,
    enclosures: list | None = None,
    enclosure_heading: str = "Enclosure",
    enclosure_note: str = "",
    index_title: str = "",
) -> Path:
    """Write `text` to `destination` as a formatted DOCX. Returns the path.

    `enclosures` are appended after the letter, one caption and page per file,
    so the petition arrives with its evidence rather than a list of promises.
    """
    s = settings or get_settings()
    font = s.letter_font
    lines = str(text).replace("\r", "").split("\n")

    document = Document()
    section = document.sections[0]
    # Word's default template is Letter on some Windows installations, so
    # setting A4 explicitly is required for the printable layout to hold.
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    # Tighter A4 margins: ~1.4cm top/bottom and right, ~2.0cm left. Chosen
    # so a standard 3-paragraph petition (sender block + three paragraphs
    # + signature block) fits on a single A4 page. The brief's "Thanking
    # you / Yours faithfully should not spill onto page 2" is the test
    # case this is sized for.
    section.top_margin = Twips(794)      # ~1.4 cm
    section.bottom_margin = Twips(794)
    section.left_margin = Twips(1134)    # ~2.0 cm, slightly wider for binding
    section.right_margin = Twips(794)

    normal = document.styles["Normal"]
    normal.font.name = font
    normal.font.size = Pt(10.5)
    # Line-height 1.35 is within the requested range and keeps standard letters
    # compact enough for a single A4 page without shrinking the signature gap.
    paragraph_format = normal.paragraph_format
    paragraph_format.line_spacing = 1.35

    # Capture any body-line that would otherwise land in the running text
    # — "Enclosures: Nil" or "இணைப்புகள்: இல்லை" — so it can be rendered
    # next to the signature instead. The letter TEXT keeps the line so a
    # plain-text preview and `verify` still see it; the DOCX moves it
    # visually. Both the LABEL and the VALUE are captured so the signature
    # table speaks the petition's own language — a Tamil petition keeps
    # its Tamil word.
    enclosure_label: str | None = None
    enclosure_value: str | None = None
    signature_name: str | None = None
    disclaimer_note: str | None = None
    closing_block = False

    _add_emblem_header(document, s, placement or Placement())
    _add_official_header(document, reference, font)

    opening = opening_block(lines)
    for index, line in enumerate(lines):
        kind = "dateline" if index < opening else classify(line, index, len(lines))
        stripped = line.strip()

        if kind == "signoff":
            closing_block = True
        elif kind == "note":
            closing_block = False

        # The original plain text reserves several blank lines for a
        # handwritten signature. The signature table supplies that space, so
        # omit those blank paragraphs from the running text to keep the A4
        # closing together.
        if not stripped and closing_block:
            continue

        # Enclosures line goes to the signature block. Capture its label
        # AND value so the Tamil word stays Tamil, then skip the body
        # rendering so the line does not appear twice.
        enclosure_match = _enclosures_match(stripped)
        if enclosure_match:
            enclosure_label = enclosure_match.group(1).strip()
            enclosure_value = enclosure_match.group(2).strip()
            continue

        # The citizen's name belongs beside the signature marker, not above
        # the enclosure/signature row as a second, detached signature.
        if kind == "signature":
            signature_name = signature_name or stripped
            continue

        # Keep the short legal disclaimer at the very foot of the letter,
        # after the signature/enclosure row. It remains in the extracted DOCX
        # text and render round-trip check, without sitting between the
        # sign-off and the place the citizen signs.
        if kind == "note":
            disclaimer_note = stripped
            continue

        paragraph = document.add_paragraph()
        fmt = paragraph.paragraph_format
        fmt.space_after = Pt(1)

        if kind == "blank":
            fmt.space_after = Pt(0)
            fmt.line_spacing = Pt(4)
            continue

        if kind == "dateline":
            # Flush right, which is where a letter carries the date it was
            # written and the place it was signed.
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            fmt.space_after = Pt(1)
            _style_run(paragraph.add_run(stripped), font)

        elif kind == "block":
            # "அனுப்புநர்," / "From," — a heading for the lines beneath it.
            fmt.space_before = Pt(3)
            fmt.space_after = Pt(1)
            _style_run(paragraph.add_run(stripped), font, bold=True)

        elif kind == "party":
            fmt.left_indent = INDENT
            fmt.space_after = Pt(0)
            _style_run(paragraph.add_run(stripped), font)

        elif kind == "salutation":
            fmt.space_before = Pt(4)
            fmt.space_after = Pt(2)
            _style_run(paragraph.add_run(stripped), font)

        elif kind == "subject":
            match = re.match(r"^([^:]+):\s*(.*)$", stripped)
            fmt.space_before = Pt(3)
            fmt.space_after = Pt(4)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            # The label is taken from the line rather than re-emitted in
            # English, so a Tamil letter keeps its Tamil "பொருள்".
            _style_run(paragraph.add_run(f"{match.group(1)}: " if match else ""), font, bold=True)
            _style_run(paragraph.add_run(match.group(2) if match else stripped), font, bold=True)

        elif kind == "foot":
            fmt.space_after = Pt(1)
            _style_run(paragraph.add_run(stripped), font)

        elif kind == "signoff":
            fmt.space_before = Pt(4)
            fmt.space_after = Pt(1)
            _style_run(paragraph.add_run(stripped), font)

        elif kind == "thanks":
            fmt.space_before = Pt(4)
            fmt.space_after = Pt(1)
            _style_run(paragraph.add_run(stripped), font)

        elif kind == "numbered":
            fmt.left_indent = INDENT
            fmt.first_line_indent = Twips(-260)
            fmt.space_after = Pt(1)
            _style_run(paragraph.add_run(stripped), font)

        elif kind == "section":
            fmt.space_before = Pt(4)
            fmt.space_after = Pt(2)
            _style_run(paragraph.add_run(stripped.rstrip(":")), font, bold=True)

        elif kind == "indented":
            fmt.left_indent = INDENT
            fmt.space_after = Pt(2)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _style_run(paragraph.add_run(stripped), font)

        else:
            fmt.first_line_indent = INDENT
            fmt.space_after = Pt(2)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _style_run(paragraph.add_run(stripped), font)

    # The Enclosures count + signature block at the foot of the letter.
    # Rendered as a 1×2 table so Enclosures sits opposite the signature
    # — the brief's layout, and the layout a receiving office counts
    # attachments against. See `_add_signature_block`.
    #
    # The typed name is captured from the original text and printed beside
    # the signature marker. A hand-edited letter without a name still gets
    # the marker and the enclosure count.
    if enclosure_label is not None and enclosure_value is not None:
        _add_signature_block(document, name=signature_name,
                             enclosure_label=enclosure_label,
                             enclosure_value=enclosure_value,
                             font=font)

    if disclaimer_note:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(2)
        paragraph.paragraph_format.space_after = Pt(0)
        _style_run(paragraph.add_run(disclaimer_note), font, size=9,
                   italic=True, color="555555")

    # The footer carries the reference, which is what an office files by. The
    # standard petition format has no reference line in the body, so this is
    # where the citizen's copy and the office's copy agree.
    footer_paragraph = document.sections[0].footer.paragraphs[0]
    footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _style_run(footer_paragraph.add_run(reference or title), font, size=8, color="777777")

    # The enclosures, after the letter and after the signature — a reader
    # should reach the citizen's own words and their sign-off before a stack of
    # scans, not through it.
    if enclosures:
        appended = enclosure_service.append_to_document(
            document, enclosures, heading=enclosure_heading,
            caption_font=font, note=enclosure_note, index_title=index_title)
        log.info("render.enclosures",
                 extra={"files": len(enclosures), "pages": appended.pages,
                        "failed": len(appended.failures)})

    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(destination))
    return destination


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #


def _word_available() -> bool:
    """Microsoft Word, on Windows, as a second route to PDF.

    Not the deployment answer — a server should not depend on an interactive
    Office install — but it is what is present on the machines this is developed
    and demonstrated on, and a correct PDF from Word beats no PDF at all.
    """
    if os.name != "nt":
        return False
    return any(
        Path(p).exists()
        for p in (
            r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
            r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
        )
    )


# Word is driven through PowerShell rather than pywin32 so that no extra
# dependency is needed. 17 is wdFormatPDF.
_WORD_SCRIPT = """
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {{
    $doc = $word.Documents.Open('{src}', $false, $true)
    $doc.SaveAs([ref]'{dst}', [ref]17)
    $doc.Close($false)
}} finally {{
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}}
"""


async def _pdf_via_word(docx_path: Path) -> tuple[Path | None, str | None]:
    """Drive Word over COM. `docx_path` must already be absolute."""
    target = docx_path.with_suffix(".pdf")
    # PowerShell single-quoted literals escape an apostrophe by doubling it.
    script = _WORD_SCRIPT.format(
        src=str(docx_path).replace("'", "''"), dst=str(target).replace("'", "''")
    )
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-NonInteractive", "-Command", script,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
    except TimeoutError:
        await _stop_converter(process)
        return None, "PDF conversion through Word timed out."
    except asyncio.CancelledError:
        await _stop_converter(process)
        raise
    except OSError as exc:
        return None, f"PDF conversion through Word could not start: {exc}"
    if process.returncode == 0 and _complete_pdf(target):
        return target, None
    return None, "Word did not produce a complete PDF."


async def _stop_converter(process) -> None:
    """Reap a converter when the request times out or is cancelled."""
    if process is None:
        return
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await process.communicate()


def _complete_pdf(path: Path) -> bool:
    """Reject empty, wrong-format and interrupted converter output."""
    try:
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                return False
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 1024))
            return b"%%EOF" in handle.read()
    except OSError:
        return False



# Where `scripts/verify_pdf.py` records that this machine's converter was put
# through a real petition and came back with correct Tamil, correct layout, an
# intact enclosure list and a clean temp directory.
STAMP_NAME = "pdf-verification.json"


def engine_fingerprint(settings: Settings | None = None) -> str:
    """Which converter, and which build of it.

    The stamp is tied to this, so upgrading LibreOffice invalidates a previous
    pass rather than carrying it forward. A rendering regression between
    versions is exactly the thing that would otherwise ride along unnoticed.
    """
    s = settings or get_settings()
    binary = shutil.which(s.soffice_path)
    if not binary:
        return "none"
    try:
        result = subprocess.run([binary, "--version"], capture_output=True,
                                timeout=20, text=True, check=False)
        version = " ".join((result.stdout or result.stderr or "").split())[:80]
    except Exception:  # noqa: BLE001
        version = "unknown"
    return f"{Path(binary).name}:{version}" if version else Path(binary).name


def verification(settings: Settings | None = None) -> dict[str, object]:
    """What `scripts/verify_pdf.py` last found, if anything.

    An absent stamp is not a failure — it is an unverified machine, which is the
    normal state of a workstation and a blocking one for a server.
    """
    s = settings or get_settings()
    stamp = s.data_dir / STAMP_NAME
    if not stamp.is_file():
        return {"verified": False, "reason": "not run",
                "note": "Run scripts/verify_pdf.py to verify this machine."}
    try:
        recorded = json.loads(stamp.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"verified": False, "reason": "unreadable",
                "note": f"The verification stamp could not be read ({exc})."}

    if not recorded.get("passed"):
        failed = [c.get("name") for c in recorded.get("checks", []) if not c.get("ok")]
        return {"verified": False, "reason": "failed", "failed": failed,
                "verified_at": recorded.get("verified_at"),
                "note": f"Verification failed: {', '.join(str(f) for f in failed)}."}

    current = engine_fingerprint(s)
    if recorded.get("fingerprint") and recorded["fingerprint"] != current:
        return {"verified": False, "reason": "stale",
                "verified_at": recorded.get("verified_at"),
                "note": ("The converter has changed since it was verified "
                         f"({recorded['fingerprint']} -> {current}). "
                         "Re-run scripts/verify_pdf.py.")}

    return {"verified": True, "reason": "passed",
            "verified_at": recorded.get("verified_at"),
            "checks": len(recorded.get("checks", [])),
            "note": "Verified on this machine by scripts/verify_pdf.py."}


def pdf_status(settings: Settings | None = None) -> dict[str, object]:
    """What this machine can actually do about PDF, stated precisely.

    `available` and `production_ready` are deliberately two different questions.
    A developer workstation with Microsoft Word installed CAN produce a PDF, so
    reporting "no PDF" would be wrong; but driving Word means an interactive
    Office installation, one document at a time, and a COM process that can
    hang, so a department server must not be commissioned on the strength of
    it. Reporting a flat `pdf: true` for both cases is how that distinction
    gets lost between a demonstration and a deployment.

    PDF goes through LibreOffice rather than a pure-Python writer on purpose.
    Tamil needs OpenType shaping - vowel signs reorder around the consonant they
    attach to - and the pure-Python PDF libraries do not shape; they would emit
    a file whose Tamil is subtly wrong in a way nobody notices until a citizen
    is at the counter with it. LibreOffice shapes through HarfBuzz, as Word does.
    """
    s = settings or get_settings()
    engine = (s.pdf_engine or "libreoffice").lower()
    have_soffice = bool(shutil.which(s.soffice_path))
    have_word = _word_available()

    def status(available, using, production_ready, note):
        return {"available": available, "engine": using,
                "production_ready": production_ready, "note": note,
                "libreoffice_found": have_soffice, "word_found": have_word,
                "configured_engine": engine,
                "verification": {"verified": False, "reason": "not applicable",
                                 "note": "Only LibreOffice can be verified for "
                                         "production use."}}

    if engine == "off":
        return status(False, None, False,
                      "PDF generation is switched off. Only DOCX is produced.")

    if engine in ("libreoffice", "auto") and have_soffice:
        # Present is not the same as proven. A binary on PATH says nothing about
        # whether it renders Tamil, keeps A4, survives four petitions at once or
        # cleans up after itself — and each of those fails in front of a citizen
        # rather than at startup. So the production flag is gated on
        # `scripts/verify_pdf.py` having actually put a petition through it.
        checked = verification(s)
        report = status(True, "libreoffice", bool(checked["verified"]),
                        "PDF is produced from the DOCX through headless "
                        "LibreOffice. " + str(checked["note"]))
        report["verification"] = checked
        return report

    if engine in ("word", "auto") and have_word:
        return status(
            True, "word", False,
            "PDF is produced through Microsoft Word. This machine can produce "
            "PDFs, but Word automation is NOT a supported server dependency: "
            "install LibreOffice and set PDF_ENGINE=libreoffice before "
            "deploying. Until then treat DOCX as the deliverable.")

    if engine == "libreoffice" and have_word:
        # Present but not chosen. Saying so is the point - an operator who sees
        # "no PDF" on a machine with Word installed needs to know why.
        return status(
            False, None, False,
            "LibreOffice was not found, so no PDF is produced. Microsoft Word "
            "is installed but is not used unless PDF_ENGINE is set to 'word' "
            "or 'auto', because a server should not depend on Office automation.")

    return status(
        False, None, False,
        "No PDF converter is available, so only DOCX is produced. Install "
        "LibreOffice and make `soffice` reachable on PATH.")


def pdf_available(settings: Settings | None = None) -> tuple[bool, str]:
    """Whether a PDF can be produced here, and a sentence saying why not.

    Kept as the two-value form the callers already use. `pdf_status` is the one
    that also says WHICH engine and whether it is fit for a server.
    """
    report = pdf_status(settings)
    return bool(report["available"]), str(report["note"])


async def render_pdf(docx_path: Path, settings: Settings | None = None) -> tuple[Path | None, str | None]:
    """Convert a DOCX to PDF. Returns (path, error).

    A missing converter is NOT a failure of the request: the DOCX is the
    deliverable and the API says plainly that no PDF was made. Pretending
    otherwise would fail a petition that is perfectly usable.
    """
    s = settings or get_settings()
    engine = (s.pdf_engine or "libreoffice").lower()
    if engine == "off":
        return None, "PDF generation is switched off."

    # Both converters run as subprocesses with their own working directory, so
    # a relative path reaches them meaningless: Word answers with a bare
    # COMException and LibreOffice writes nothing and reports success.
    docx_path = docx_path.resolve()

    executable = shutil.which(s.soffice_path) if engine in ("libreoffice", "auto") else None
    use_word = not executable and engine in ("word", "auto") and _word_available()
    if not executable and not use_word:
        return None, pdf_available(s)[1]

    # A previous generation may have used this name. Convert in an isolated
    # directory and publish only a successful, complete output, so a failed
    # retry can never return the previous citizen details as the new PDF.
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix=".petition-pdf-", dir=docx_path.parent) as temporary:
            out_dir = Path(temporary)
            source = out_dir / docx_path.name
            shutil.copyfile(docx_path, source)
            if use_word:
                candidate, error = await _pdf_via_word(source)
                if candidate is None:
                    return None, error
            else:
                # Separate profiles prevent concurrent requests or a desktop
                # LibreOffice session from silently swallowing conversion jobs.
                profile = (out_dir / "profile").as_uri()
                process = await asyncio.create_subprocess_exec(
                    executable, f"-env:UserInstallation={profile}",
                    "--headless", "--norestore", "--convert-to", "pdf",
                    "--outdir", str(out_dir), str(source),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                try:
                    await asyncio.wait_for(process.communicate(), timeout=120)
                except (TimeoutError, asyncio.CancelledError):
                    # Stop before TemporaryDirectory attempts to remove files
                    # still open in the converter, especially on Windows.
                    await _stop_converter(process)
                    raise
                candidate = source.with_suffix(".pdf")
                if process.returncode != 0 or not _complete_pdf(candidate):
                    return None, "PDF conversion did not produce a complete PDF."

            destination = docx_path.with_suffix(".pdf")
            os.replace(candidate, destination)
            return destination, None
    except TimeoutError:
        return None, "PDF conversion timed out."
    except OSError:
        log.exception("render.pdf.failed")
        return None, "PDF conversion could not complete."


# --------------------------------------------------------------------------- #
# Reading a document back — the input to `verify`
# --------------------------------------------------------------------------- #


def extract_docx_text(path: Path) -> str:
    """All text in the document, including headers, footers and tables.

    `verify` asserts against this, so it has to see everything a reader would.
    Missing the footer here would let a reference number vanish from the file
    while the check still passed.
    """
    document = Document(str(path))
    parts: list[str] = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    for section in document.sections:
        for container in (section.header, section.footer):
            parts.extend(p.text for p in container.paragraphs)
    return "\n".join(parts)
