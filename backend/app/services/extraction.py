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
from dataclasses import dataclass
from pathlib import Path

from . import ocr

log = logging.getLogger(__name__)

# Below this, the text is treated as unreliable: shown to the citizen for
# correction rather than offered as something to confirm.
LOW_CONFIDENCE = 0.55

# A page of a real document has more than this much text on it. Less means the
# PDF is a scan with a stray watermark or page number in its text layer, which
# is the case that most looks like success and is not.
MIN_CHARS_PER_PAGE = 40


@dataclass
class Extraction:
    text: str = ""
    method: str = "none"          # pdf-text | docx | plain | ocr | none
    confidence: float = 0.0
    readable: bool = True
    reason: str = ""              # why it could not be read, for the citizen
    pages: int = 0

    @property
    def low_confidence(self) -> bool:
        return self.readable and self.confidence < LOW_CONFIDENCE


def ocr_status() -> dict[str, object]:
    """Whether scanned images can be read at all on this machine.

    Delegates to the engine registry. Kept here as the name the rest of the
    service already calls, so adding an engine changes nothing above this line.
    """
    return ocr.status()


def _pdf(path: Path) -> Extraction:
    """PDF text layer first, OCR only if there is not one."""
    text, pages = "", 0
    try:
        import pymupdf

        with pymupdf.open(path) as document:
            pages = document.page_count
            text = "\n".join(page.get_text() for page in document)
    except Exception as exc:  # noqa: BLE001
        log.info("extract.pymupdf_failed", extra={"error": str(exc)[:160]})
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = len(reader.pages)
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as inner:  # noqa: BLE001
            return Extraction(readable=False, pages=pages,
                              reason=f"This PDF could not be opened ({str(inner)[:80]}).")

    stripped = " ".join(text.split())
    if pages and len(stripped) >= MIN_CHARS_PER_PAGE * pages:
        return Extraction(text=text, method="pdf-text", confidence=0.95, pages=pages)
    if stripped and pages and len(stripped) >= MIN_CHARS_PER_PAGE:
        # Some text, but thin for the page count — a scan with a header on it.
        return Extraction(text=text, method="pdf-text", confidence=0.45, pages=pages)

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
    return Extraction(text=text, method="ocr", confidence=ocr.OCR_CONFIDENCE,
                      pages=_page_count(path))


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
    return Extraction(text=text, method="ocr", confidence=ocr.OCR_CONFIDENCE, pages=1)


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
        return Extraction(text=text, method="docx", confidence=0.95, pages=1)
    except Exception as exc:  # noqa: BLE001
        return Extraction(readable=False,
                          reason=f"This document could not be opened ({str(exc)[:80]}).")


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
    if suffix in (".txt", ".md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            return Extraction(readable=False, reason="This file is empty.")
        return Extraction(text=text, method="plain", confidence=0.9, pages=1)

    return Extraction(readable=False,
                      reason=f"Files of type '{suffix}' cannot be read here.")
