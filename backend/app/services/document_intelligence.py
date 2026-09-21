"""Choosing how to read an attachment, and reading it.

WHAT THIS IS FOR. The service could already read a text PDF, a DOCX, a PPTX
and a plain-text file, and it could say honestly when it could not read
something. What it could not read was most of what citizens actually bring to
a government office: a photograph of an acknowledgement slip, a scanned
petition, a spreadsheet of complaints, a .doc from a department that has not
changed template since 2003. Those arrived, were stored, were listed as
enclosures, and contributed nothing.

WHY XBERG. Measured against this service's own readers on a corpus of files
produced by Office itself, xberg read twelve formats the service could not
read at all — including scanned PDFs and photographs through bundled OCR,
legacy .doc/.ppt/.xls binaries, and spreadsheets with their tables intact —
matched it on five, and was worse on exactly one: a hand-built .pptx that was
not a conformant package. It is MIT, has ZERO Python dependencies, ships
prebuilt wheels for this machine and for the manylinux the container is built
on, and needs no network and no model download at runtime. Tamil comes back
byte-identical to the existing reader, which for this service is not a
detail.

WHY IT IS STILL OPTIONAL. Everything above is a reason to prefer it, not a
reason to depend on it. If the import fails, if the wheel is missing on some
future platform, or if a particular file defeats it, this module falls back
to the readers that were already here and the service behaves exactly as it
did before. A parser is not worth a new way for the application to be down.

WHAT IT DELIBERATELY DOES NOT DO. It does not classify, it does not decide
relevance, and it does not put anything on the petition. It turns a file into
text, tables and page markers, with a note of how it was read and how much
that reading can be trusted. Judging what the text MEANS stays where it was:
in `prior_petition`, deterministic and without a model, behind the citizen's
confirmation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import extraction

log = logging.getLogger(__name__)

# A cell count past which a table is summarised rather than reproduced. A
# complaints register with four thousand rows is evidence; pasting it into the
# extracted text is how a 200-page attachment becomes a prompt.
MAX_TABLE_CELLS = 600


@dataclass
class Table:
    """One table, kept as rows rather than flattened into a sentence.

    `where` is the page or sheet it came from, in the same words the rest of
    the service uses, so a citizen checking a figure is told where to look.
    """

    rows: list[list[str]] = field(default_factory=list)
    where: str = ""
    title: str = ""
    truncated: bool = False
    # The engine's own Markdown rendering, kept when it is available because
    # it preserves the header separator that tells a reader which row is the
    # heading. Regenerated from `rows` when it is not.
    markdown: str = ""

    @property
    def header(self) -> list[str]:
        return self.rows[0] if self.rows else []

    def as_dict(self) -> dict[str, Any]:
        return {"rows": self.rows, "where": self.where, "title": self.title,
                "truncated": self.truncated}

    def as_text(self) -> str:
        if self.markdown and not self.truncated:
            return self.markdown
        return "\n".join(" | ".join(str(c) for c in row) for row in self.rows)


def _engine() -> Any | None:
    """The xberg module, or None when it is not installed."""
    try:
        import xberg
    except Exception:  # noqa: BLE001 - absence is a supported state
        return None
    return xberg


def available() -> bool:
    return _engine() is not None


def status() -> dict[str, Any]:
    """What the health endpoint reports about document reading."""
    engine = _engine()
    if engine is None:
        return {
            "available": False,
            "engine": None,
            "formats": 0,
            "note": ("Advanced document reading is not installed. PDFs with a "
                     "text layer, Word files, presentations and text files are "
                     "still read; scans, photographs and spreadsheets are "
                     "attached without being read."),
        }
    try:
        formats = len(engine.list_supported_formats())
        backends = list(engine.list_ocr_backends())
    except Exception as exc:  # noqa: BLE001
        log.info("document_intelligence.status_failed", extra={"error": str(exc)[:120]})
        formats, backends = 0, []
    return {
        "available": True,
        "engine": "xberg",
        "version": getattr(engine, "__version__", ""),
        "formats": formats,
        "ocr_backends": backends,
        "egress": False,
        "note": "Documents are read on this machine. Nothing is sent anywhere.",
    }


def _text_of(document: Any) -> str:
    return str(getattr(document, "content", "") or "")


def _segments_of(document: Any, body: str) -> list[extraction.Segment]:
    """Page markers, in the shape the rest of the service already uses."""
    pages = getattr(document, "pages", None) or []
    out: list[extraction.Segment] = []
    for index, page in enumerate(pages, start=1):
        content = str(getattr(page, "content", "") or getattr(page, "text", "") or "")
        if content.strip():
            number = getattr(page, "page_number", None) or getattr(page, "number", None)
            out.append(extraction.Segment(
                number=int(number) if isinstance(number, int) and number > 0 else index,
                text=content, unit="page"))
    if out or not body.strip():
        return out
    # A format with no page concept — a spreadsheet, a CSV, an HTML page.
    # One segment rather than a fabricated "page 1".
    return [extraction.Segment(number=1, text=body, unit="document")]


def _tables_of(document: Any) -> list[Table]:
    out: list[Table] = []
    for found in (getattr(document, "tables", None) or []):
        rows: list[list[str]] = []
        # `cells` is the engine's name for it; the others are defensive, so a
        # future version that renames the field degrades to no table rather
        # than to a crash in the upload endpoint.
        cells = (getattr(found, "cells", None) or getattr(found, "rows", None)
                 or getattr(found, "data", None) or [])
        for row in cells:
            if isinstance(row, (list, tuple)):
                rows.append([str(c if c is not None else "") for c in row])
        if not rows:
            continue
        total = sum(len(r) for r in rows)
        truncated = total > MAX_TABLE_CELLS
        if truncated:
            kept, running = [], 0
            for row in rows:
                if running + len(row) > MAX_TABLE_CELLS:
                    break
                kept.append(row)
                running += len(row)
            rows = kept
        page = getattr(found, "page_number", None)
        sheet = getattr(found, "sheet_name", None) or getattr(found, "sheet", None)
        where = f"sheet {sheet}" if sheet else (f"page {page}" if page else "")
        out.append(Table(rows=rows, where=str(where),
                         title=str(getattr(found, "title", "") or ""),
                         truncated=truncated,
                         markdown=str(getattr(found, "markdown", "") or "")))
    return out


def _confidence_of(document: Any, method: str) -> float:
    """How much the reading can be trusted, on this service's scale.

    An OCR read is capped below `extraction.LOW_CONFIDENCE` whatever the
    engine reports about itself, because the rule that an OCR result is never
    auto-confirmed is a rule about what may reach a government form, not an
    opinion about the engine's accuracy.
    """
    quality = getattr(document, "quality_score", None)
    score = float(quality) if isinstance(quality, (int, float)) else 0.9
    if method == "ocr":
        return min(score, extraction.OCR_CEILING)
    return max(0.0, min(1.0, score))


def _method_of(document: Any) -> str:
    raw = str(getattr(document, "extraction_method", "") or "").lower()
    return "ocr" if "ocr" in raw else "native"


async def _by_engine(path: Path) -> extraction.Extraction | None:
    """Read through xberg. None when it is absent or produced nothing usable."""
    engine = _engine()
    if engine is None:
        return None
    try:
        from xberg.options import ExtractInput

        result = await engine.extract(ExtractInput(
            kind="bytes", bytes=path.read_bytes(), filename=path.name))
    except Exception as exc:  # noqa: BLE001 - fall back rather than fail
        log.info("document_intelligence.engine_failed",
                 extra={"suffix": path.suffix.lower(), "error": str(exc)[:160]})
        return None

    documents = getattr(result, "results", None) or []
    if not documents:
        return None
    document = documents[0]
    body = _text_of(document)
    tables = _tables_of(document)
    if not body.strip() and not tables:
        return None

    method = _method_of(document)
    # The table text is appended so that the deterministic field readers see a
    # reference number that only appears inside a spreadsheet cell. The rows
    # are ALSO kept structured, because flattening is lossy and a citizen
    # shown "12 | Street light | CBE/2026/12345" can check it; a citizen shown
    # the same three values run together into prose cannot.
    if tables:
        body = "\n\n".join([body.strip(), *(t.as_text() for t in tables)]).strip()

    return extraction.Extraction(
        text=body,
        method=method,
        confidence=_confidence_of(document, method),
        readable=True,
        pages=len(getattr(document, "pages", None) or []) or 1,
        segments=_segments_of(document, body),
        tables=tables,
    )


async def read(path: Path) -> extraction.Extraction:
    """Read one attachment, by whichever route works.

    Order is deliberate. The engine is tried first because it reads strictly
    more than the built-in readers on every format measured except one, and
    the built-in readers are tried second because that one exists — a .pptx
    whose package is malformed is read by this service's forgiving parser and
    refused by a strict one, and a citizen's file being slightly wrong is not
    a reason to tell them it is unreadable.
    """
    path = Path(path)
    if not path.is_file():
        return extraction.Extraction(readable=False, reason="The file is missing.")

    through_engine = await _by_engine(path)
    if through_engine is not None:
        return through_engine

    # Off the event loop: the built-in readers are synchronous, and a large
    # PDF held on the loop stops every other session in the service,
    # including the WebSocket carrying somebody's voice.
    built_in = await asyncio.to_thread(extraction.extract, path)
    if built_in.readable:
        log.info("document_intelligence.fell_back",
                 extra={"suffix": path.suffix.lower(), "method": built_in.method})
    return built_in
