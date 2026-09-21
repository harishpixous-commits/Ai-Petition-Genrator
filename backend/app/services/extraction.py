"""Reading what a citizen attached — and saying so when it cannot be read.

The important behaviour here is the failure. A photograph of a petition taken on
a phone has no text layer, and without an OCR engine installed there is no
honest way to turn it into words. The wrong answer is to hand the image to a
model and let it describe what it thinks the document says: that produces an
acknowledgement number nobody issued, which then gets printed on a new petition
as evidence of an earlier one.

So `extract` returns a confidence and a method alongside the text, and a file it
could not read comes back `readable=False` with a sentence explaining why. The
conversation then asks the citizen to type the details instead. Nothing is
guessed.

OCR is pluggable rather than assumed. If Tesseract is installed and
`pytesseract` importable, scanned pages go through it at reduced confidence; if
not, `ocr_status()` says so plainly and the health endpoint reports it. It is
not installed on this machine.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import ocr

log = logging.getLogger(__name__)

# Pages are joined by a form feed so that a page boundary survives into the
# extracted text and a fact can be traced back to the page it came from. A
# newline on each side as well, because the evidence shown to the citizen is
# built by finding the LINE around a value, and without them the last line of
# one page and the first of the next would read as a single sentence that
# appears nowhere in the document.
PAGE_BREAK = "\n\f\n"

# Below this, the text is treated as unreliable: shown to the citizen for
# correction rather than offered as something to confirm.
LOW_CONFIDENCE = 0.55

# No OCR result may be reported above this, whatever the engine says about
# its own accuracy. It is not a claim about any engine: it is the rule that a
# guess about pixels must be looked at by the person who took the photograph
# before it can become a claim on a government form, expressed as a number so
# that a better engine cannot quietly opt out of it.
OCR_CEILING = LOW_CONFIDENCE - 0.05

# A page of a real document has more than this much text on it. Less means the
# PDF is a scan with a stray watermark or page number in its text layer, which
# is the case that most looks like success and is not.
MIN_CHARS_PER_PAGE = 40


@dataclass
class Segment:
    """One addressable piece of a document: a page, or a slide.

    A value read out of an attachment is only worth showing to a citizen if
    they can be told where it came from. "Reference number CBE/2026/12345" is
    a claim; "reference number CBE/2026/12345, from page 2" is a claim they
    can check against the paper in their hand.

    `unit` rather than a bare page number because a presentation has slides
    and a Word file has neither — calling a slide "page 4" on the confirmation
    card would send someone looking for something that is not there.
    """

    number: int
    text: str
    unit: str = "page"            # page | slide | document


@dataclass
class Extraction:
    text: str = ""
    method: str = "none"          # pdf-text | docx | pptx | plain | ocr | none
    confidence: float = 0.0
    readable: bool = True
    reason: str = ""              # why it could not be read, for the citizen
    pages: int = 0
    # Where each piece of the text came from. Empty when the format has no
    # meaningful divisions, which is not the same as "page 1" and is why this
    # is a list rather than a default.
    segments: list[Segment] = field(default_factory=list)
    # Tables, kept as rows rather than flattened into the text. Only the
    # document router fills this in; the built-in readers have no table model
    # and leave it empty, which is honest rather than an empty table.
    tables: list[Any] = field(default_factory=list)

    @property
    def low_confidence(self) -> bool:
        return self.readable and self.confidence < LOW_CONFIDENCE


def locate(segments: Sequence[Segment], needle: str) -> Segment | None:
    """The page or slide a piece of text sits on, if it can be pinned down.

    Whitespace is normalised on both sides: a value extracted from a PDF is
    frequently split across a line break that is not in the value itself, and
    an exact match would then attribute nothing.

    Returns None rather than guessing page 1. An unattributed fact is still a
    usable fact; a wrongly attributed one sends the citizen to the wrong page.
    """
    probe = " ".join(str(needle or "").split())
    if not probe:
        return None
    for segment in segments:
        if probe in " ".join(segment.text.split()):
            return segment
    return None


def ocr_status() -> dict[str, object]:
    """Whether scanned images can be read at all on this machine.

    Delegates to the engine registry. Kept here as the name the rest of the
    service already calls, so adding an engine changes nothing above this line.
    """
    return ocr.status()


def _paged(texts: list[str]) -> list[Segment]:
    """One segment per page that actually has something on it."""
    return [Segment(number=index, text=body, unit="page")
            for index, body in enumerate(texts, start=1) if body.strip()]


def _pdf(path: Path) -> Extraction:
    """PDF text layer first, OCR only if there is not one."""
    text, pages, per_page = "", 0, []
    try:
        import pymupdf

        with pymupdf.open(path) as document:
            pages = document.page_count
            per_page = [page.get_text() for page in document]
    except Exception as exc:  # noqa: BLE001
        log.info("extract.pymupdf_failed", extra={"error": str(exc)[:160]})
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = len(reader.pages)
            per_page = [(p.extract_text() or "") for p in reader.pages]
        except Exception as inner:  # noqa: BLE001
            return Extraction(readable=False, pages=pages,
                              reason=f"This PDF could not be opened ({str(inner)[:80]}).")

    text = PAGE_BREAK.join(per_page)
    segments = _paged(per_page)

    stripped = " ".join(text.split())
    if pages and len(stripped) >= MIN_CHARS_PER_PAGE * pages:
        return Extraction(text=text, method="pdf-text", confidence=0.95,
                          pages=pages, segments=segments)
    if stripped and pages and len(stripped) >= MIN_CHARS_PER_PAGE:
        # Some text, but thin for the page count — a scan with a header on it.
        return Extraction(text=text, method="pdf-text", confidence=0.45,
                          pages=pages, segments=segments)

    ocr = _ocr_pdf(path)
    if ocr is not None:
        return ocr
    return Extraction(
        readable=False, pages=pages,
        reason=("This PDF has no text in it — it is a scan or a photograph. "
                "No OCR engine is installed, so it cannot be read here."))


def _ocr_pdf(path: Path) -> Extraction | None:
    """A scanned PDF, through whichever engine is installed. None if none is.

    The result re-enters the ordinary pipeline — the same chunker, the same
    deterministic field extraction, the same confirmation card. The only thing
    that differs is the confidence, which is capped below `LOW_CONFIDENCE` so an
    OCR read is always flagged to the citizen as something to check.
    """
    text = ocr.read_pdf(path)
    if text is None:
        return None
    if not text.strip():
        return Extraction(
            readable=False,
            reason=("This PDF was scanned and the text could not be recognised. "
                    "Please tell me what it says."))
    # The engine separates pages with a form feed, so a scanned page can be
    # cited the same way a text one is. A build that returns no separator
    # simply yields one segment, and nothing is attributed to a page — which
    # is the honest outcome, not a fallback to page 1.
    per_page = text.split("\f")
    return Extraction(text=text, method="ocr", confidence=ocr.OCR_CONFIDENCE,
                      pages=_page_count(path),
                      segments=_paged(per_page) if len(per_page) > 1 else [])


def _page_count(path: Path) -> int:
    try:
        import pymupdf

        with pymupdf.open(path) as document:
            return document.page_count
    except Exception:  # noqa: BLE001
        return 0


def _image(path: Path) -> Extraction:
    text = ocr.read_image(path)
    if text is None:
        return Extraction(
            readable=False,
            reason=("This is a photograph, and no OCR engine is installed, so "
                    "its text cannot be read here. It will still be attached to "
                    "the petition — please tell me anything it says that the "
                    "petition should mention."))
    if not text.strip():
        return Extraction(
            readable=False,
            reason=("No text could be recognised in this photograph. It will "
                    "still be attached to the petition."))
    return Extraction(text=text, method="ocr", confidence=ocr.OCR_CONFIDENCE, pages=1,
                      segments=[Segment(number=1, text=text, unit="page")])


def _docx(path: Path) -> Extraction:
    try:
        import docx

        document = docx.Document(str(path))
        lines = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    lines.append(" | ".join(cells))
        text = "\n".join(lines)
        if not text.strip():
            return Extraction(readable=False, reason="This document is empty.")
        return Extraction(text=text, method="docx", confidence=0.95, pages=1,
                          segments=[Segment(number=1, text=text,
                                            unit="document")])
    except Exception as exc:  # noqa: BLE001
        return Extraction(readable=False,
                          reason=f"This document could not be opened ({str(exc)[:80]}).")


# A text run in a slide. PowerPoint stores every scrap of visible text as one
# of these, whatever shape, table cell or placeholder it happens to sit in.
_PPTX_TEXT = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
_SLIDE_FILE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


def _pptx(path: Path) -> Extraction:
    """Slide text, one segment per slide.

    Read straight out of the OOXML package rather than through a presentation
    library. A .pptx IS a zip of XML, the text runs are all one tag, and the
    service deliberately carries no library for this — adding a dependency to
    reach four lines of ElementTree would be the larger change.

    Speaker notes are included. A slide reading "Ward 12 street light" whose
    note says "complaint filed 12-08-2026" carries the date in the note, and a
    date is exactly the sort of thing the petition wants to cite.

    Nothing here decides the presentation is RELEVANT. It is read, attributed
    to its slides, and put in front of the citizen like any other attachment.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    segments: list[Segment] = []
    slide_count = 0
    try:
        with zipfile.ZipFile(path) as bundle:
            names = set(bundle.namelist())
            slides = sorted(
                (int(found.group(1)), name)
                for name in names if (found := _SLIDE_FILE.match(name)))
            slide_count = len(slides)
            for number, name in slides:
                pieces = [(node.text or "").strip() for node
                          in ET.fromstring(bundle.read(name)).iter(_PPTX_TEXT)]
                notes = f"ppt/notesSlides/notesSlide{number}.xml"
                if notes in names:
                    pieces += [(node.text or "").strip() for node
                               in ET.fromstring(bundle.read(notes)).iter(_PPTX_TEXT)]
                body = "\n".join(piece for piece in pieces if piece)
                if body:
                    segments.append(Segment(number=number, text=body, unit="slide"))
    except Exception as exc:  # noqa: BLE001
        return Extraction(
            readable=False,
            reason=f"This presentation could not be opened ({str(exc)[:80]}).")

    if not slide_count:
        return Extraction(readable=False,
                          reason="This presentation has no slides in it.")
    if not segments:
        return Extraction(
            readable=False, pages=slide_count,
            reason=("No text could be read from this presentation — the slides "
                    "appear to be images. It will still be attached."))
    return Extraction(text=PAGE_BREAK.join(s.text for s in segments),
                      method="pptx", confidence=0.95,
                      pages=slide_count, segments=segments)


def extract(path: Path) -> Extraction:
    """Read an attachment, or explain why it could not be read."""
    path = Path(path)
    if not path.is_file():
        return Extraction(readable=False, reason="The file is missing.")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf(path)
    if suffix in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff"):
        return _image(path)
    if suffix == ".docx":
        return _docx(path)
    if suffix == ".pptx":
        return _pptx(path)
    if suffix in (".doc", ".ppt"):
        # The pre-2007 binary formats. They are accepted and attached — a
        # citizen holding one should not be turned away — but nothing here
        # can read them without an office suite, and saying so is better than
        # a silent empty extraction that looks like a document with nothing
        # in it. The citizen is asked to type what it says.
        return Extraction(
            readable=False, pages=1,
            reason=("This is an older Office file, which cannot be read here. "
                    "It will still be attached to the petition — please tell "
                    "me anything in it the petition should mention."))
    if suffix in (".txt", ".md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            return Extraction(readable=False, reason="This file is empty.")
        return Extraction(text=text, method="plain", confidence=0.9, pages=1,
                          segments=[Segment(number=1, text=text, unit="document")])

    return Extraction(readable=False,
                      reason=f"Files of type '{suffix}' cannot be read here.")
