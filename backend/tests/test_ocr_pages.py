"""OCR reads only the pages that need it, and every page keeps its number.

THE TWO DEFECTS THESE HOLD SHUT, the first introduced by me:

  Page provenance was discarded. The OCR engine separates pages with a form
  feed so a value read from a scan can be cited as "page 2"; the ingest path
  collapsed the result into one page with no number, under a comment claiming
  numbers were unrecoverable. They were not. Every chunk from a scanned
  document lost its page citation.

  Mixed PDFs were mishandled. OCR ran only if the WHOLE document lacked text,
  so a Gazette with typeset pages and a scanned annexure lost the annexure —
  and had OCR run, it would have re-read the typeset pages too.

These need no OCR binary. The engine is a fake registered through the same
`register()` seam a deployment uses, and the PDFs are real files built for
each test: one page with a text layer, one with none. What they prove is the
pipeline's handling of OCR output, NOT the quality of any real OCR engine —
that cannot be shown without Tesseract or an equivalent installed, and these
tests do not pretend to show it.
"""

from __future__ import annotations

import pymupdf
import pytest

from app.knowledge import ingest
from app.services import ocr

TYPESET = "Section 1. This page has a real text layer and must be kept exactly."


def make_pdf(path, pages: list[str | None]):
    """A PDF whose pages are typeset text, or None for an image-only page."""
    document = pymupdf.open()
    for content in pages:
        page = document.new_page()
        if content is not None:
            page.insert_text((72, 72), content)
        else:
            # A drawn rectangle and no text: what a scanned page looks like to
            # a text extractor.
            page.draw_rect(pymupdf.Rect(72, 72, 300, 300), color=(0, 0, 0))
    document.save(str(path))
    document.close()
    return path


class FakeEngine:
    """Records what it was asked for; answers with a recognisable string."""

    name = "fake-ocr"

    def __init__(self, *, page_level: bool = True, empty: set[int] | None = None):
        self.asked: list[int] = []
        self.page_level = page_level
        self.empty = empty or set()
        if not page_level:
            # An engine that can only read whole documents.
            del_attr = "pdf_pages"
            self.__dict__.pop(del_attr, None)

    def available(self) -> bool:
        return True

    def _language_argument(self) -> str:
        return "tam+eng"

    def image(self, path):
        return ""

    def pdf(self, path):
        with pymupdf.open(path) as document:
            count = document.page_count
        return "\n\f\n".join(f"OCR READING OF PAGE {n}" for n in range(1, count + 1))

    def pdf_pages(self, path, numbers):
        self.asked.extend(numbers)
        return {n: ("" if n in self.empty else f"OCR READING OF PAGE {n}")
                for n in numbers}


class WholeDocumentEngine(FakeEngine):
    """No page-level method at all."""

    pdf_pages = None  # type: ignore[assignment]

    def __getattribute__(self, name):
        if name == "pdf_pages":
            raise AttributeError(name)
        return super().__getattribute__(name)


@pytest.fixture
def engine(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setattr(ocr, "_ENGINES", [fake])
    return fake


@pytest.fixture
def no_engine(monkeypatch):
    monkeypatch.setattr(ocr, "_ENGINES", [])


class TestAMixedPdf:
    def test_only_the_scanned_page_is_sent_to_ocr(self, tmp_path, engine):
        path = make_pdf(tmp_path / "mixed.pdf", [TYPESET, None])
        ingest.extract(path)
        assert engine.asked == [2], "the typeset page was sent to OCR"

    def test_the_typeset_page_keeps_its_exact_text(self, tmp_path, engine):
        path = make_pdf(tmp_path / "mixed.pdf", [TYPESET, None])
        pages = {p.number: p.text for p in ingest.extract(path).pages}
        assert "real text layer" in pages[1]
        assert "OCR READING" not in pages[1], "typeset text replaced by OCR"

    def test_the_scanned_page_gets_its_own_page_number(self, tmp_path, engine):
        """THE DEFECT I INTRODUCED. The reading must be on page 2, not on an
        unnumbered page that can never be cited."""
        path = make_pdf(tmp_path / "mixed.pdf", [TYPESET, None])
        pages = {p.number: p.text for p in ingest.extract(path).pages}
        assert pages[2] == "OCR READING OF PAGE 2"
        assert None not in pages

    def test_what_was_ocrd_is_recorded(self, tmp_path, engine):
        path = make_pdf(tmp_path / "mixed.pdf", [TYPESET, None])
        record = ingest.extract(path).meta["ocr"]
        assert record["status"] == "complete"
        assert record["pages_ocrd"] == [2]
        assert record["engine"] == "fake-ocr"
        assert record["languages"] == "tam+eng"


class TestAFullyScannedPdf:
    def test_every_page_is_read_and_numbered(self, tmp_path, engine):
        path = make_pdf(tmp_path / "scan.pdf", [None, None, None])
        pages = ingest.extract(path).pages
        assert [p.number for p in pages] == [1, 2, 3]
        assert [p.text for p in pages] == [
            f"OCR READING OF PAGE {n}" for n in (1, 2, 3)]

    def test_an_unreadable_page_is_reported_not_hidden(self, tmp_path, monkeypatch):
        fake = FakeEngine(empty={2})
        monkeypatch.setattr(ocr, "_ENGINES", [fake])
        path = make_pdf(tmp_path / "scan.pdf", [None, None, None])
        record = ingest.extract(path).meta["ocr"]
        assert record["status"] == "partial"
        assert record["pages_unreadable"] == [2]
        assert record["pages_ocrd"] == [1, 3]

    def test_pages_beyond_the_limit_are_reported_as_not_attempted(
            self, tmp_path, engine, monkeypatch):
        monkeypatch.setattr(ingest, "MAX_OCR_PAGES", 2)
        path = make_pdf(tmp_path / "long.pdf", [None, None, None, None])
        record = ingest.extract(path).meta["ocr"]
        assert record["status"] == "partial"
        assert record["pages_not_attempted"] == [3, 4]
        assert engine.asked == [1, 2]


class TestAnEngineThatOnlyReadsWholeDocuments:
    def test_the_form_feed_split_keeps_only_the_blank_pages(
            self, tmp_path, monkeypatch):
        """The engine reads every page; only the ones that NEEDED reading are
        taken, so the typeset page still keeps its own exact text."""
        monkeypatch.setattr(ocr, "_ENGINES", [WholeDocumentEngine()])
        path = make_pdf(tmp_path / "mixed.pdf", [TYPESET, None])
        pages = {p.number: p.text for p in ingest.extract(path).pages}
        assert "real text layer" in pages[1]
        assert pages[2] == "OCR READING OF PAGE 2"


class TestWithNoEngine:
    def test_a_fully_scanned_pdf_is_still_refused(self, tmp_path, no_engine):
        """An empty document must never be indexed."""
        path = make_pdf(tmp_path / "scan.pdf", [None, None])
        with pytest.raises(ValueError, match="needs OCR"):
            ingest.extract(path)

    def test_a_mixed_pdf_keeps_its_text_and_says_what_it_could_not_read(
            self, tmp_path, no_engine):
        path = make_pdf(tmp_path / "mixed.pdf", [TYPESET, None])
        extracted = ingest.extract(path)
        assert "real text layer" in extracted.text
        assert extracted.meta["ocr"] == {"status": "unavailable",
                                         "pages_needing_ocr": [2]}


class TestTheFileDateIsNotTheLegalDate:
    def test_a_pdfs_creation_timestamp_is_not_stored_as_its_date(self, tmp_path):
        """A file's creation timestamp is when somebody's software wrote it —
        2023 for an Act of 1998. It must not become the document's date."""
        path = make_pdf(tmp_path / "act.pdf", [TYPESET])
        meta = ingest.extract(path).meta
        assert "date" not in meta
