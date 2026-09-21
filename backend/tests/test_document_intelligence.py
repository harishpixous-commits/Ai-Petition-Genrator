"""Reading harder documents, and refusing to over-claim about them.

Three things are under test, and they pull in opposite directions on purpose.

READ MORE. A citizen brings a photograph of an acknowledgement slip, a scanned
petition, a ward's complaint spreadsheet, a .doc from a department that has
not changed template since 2003. Before the document router, all of those
were stored, listed as enclosures, and contributed nothing.

TRUST IT NO FURTHER THAN BEFORE. Reading more is only safe if the new
material is held to the same rule as the old: an OCR result is a guess about
pixels, it is capped below the confidence threshold whatever the engine says
about itself, and it reaches the petition only after the citizen has looked
at it.

AND STILL WORK WITHOUT IT. The engine is optional. Every test that needs it
skips when it is absent, and the tests that matter most are the ones checking
what happens when it IS absent — because that is the configuration a
department without a wheel for its platform will be running.
"""

from __future__ import annotations

import asyncio
import builtins
import io
import sys
import uuid
import zipfile
from pathlib import Path

import pytest

from app.domain import attachment_relevance
from app.domain.attachments import ALLOWED_SUFFIXES, TEXT_SUFFIXES, AttachmentSet
from app.services import attachment_store, document_intelligence, extraction
from app.services.mask import mask_for_display

ENGINE = pytest.mark.skipif(not document_intelligence.available(),
                            reason="the document engine is not installed")


def read(path: Path) -> extraction.Extraction:
    return asyncio.run(document_intelligence.read(path))


@pytest.fixture
def session() -> str:
    name = str(uuid.uuid4())
    yield name
    attachment_store.discard_session(name)


@pytest.fixture
def without_engine(monkeypatch):
    """The service as a deployment with no wheel for its platform sees it."""
    real = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "xberg" or name.startswith("xberg."):
            raise ImportError("no wheel for this platform")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    for module in [m for m in sys.modules if m.startswith("xberg")]:
        monkeypatch.delitem(sys.modules, module, raising=False)


def scanned_pdf(path: Path, lines: list[str]) -> Path:
    """A PDF whose page is a picture of text — no text layer at all."""
    import pymupdf

    source = pymupdf.open()
    page = source.new_page()
    top = 80
    for line in lines:
        page.insert_text((60, top), line, fontsize=14)
        top += 22
    pixmap = page.get_pixmap(dpi=150)
    source.close()

    out = pymupdf.open()
    target = out.new_page(width=pixmap.width * 0.75, height=pixmap.height * 0.75)
    target.insert_image(target.rect, pixmap=pixmap)
    out.save(str(path))
    out.close()
    return path


def text_pdf(path: Path, lines: list[str]) -> Path:
    """A PDF with a real text layer. One line per row: a single joined line
    runs off the page edge and is silently clipped, which looks exactly like
    an extraction failure."""
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    top = 80
    for line in lines:
        page.insert_text((60, top), line, fontsize=11)
        top += 18
    document.save(str(path))
    document.close()
    return path


SLIP = ["OFFICE OF THE COMMISSIONER",
        "Municipal Administration Department, Coimbatore",
        "ACKNOWLEDGEMENT",
        "Acknowledgement number: CBE/2026/12345",
        "Date of receipt: 12-08-2026",
        "Petitioner: Harish Kumar",
        "Status: Pending"]


def csv_bytes() -> bytes:
    return (b"Ward,Complaint,Reference,Days open\n"
            b"12,Street light,CBE/2026/12345,45\n"
            b"12,Water leak,CBE/2026/12346,12\n")


def xlsx_zip_bytes() -> bytes:
    """Enough of an XLSX package to be recognised as one."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("[Content_Types].xml", "<Types/>")
        bundle.writestr("xl/workbook.xml", "<workbook/>")
    return buffer.getvalue()


class TestTheServiceWorksWithoutTheEngine:
    """The configuration a department without a prebuilt wheel will run."""

    def test_it_reports_itself_absent_rather_than_guessing(self, without_engine):
        status = document_intelligence.status()

        assert status["available"] is False
        assert status["engine"] is None
        assert "still read" in status["note"]

    def test_a_text_pdf_is_still_read(self, without_engine, tmp_path):
        result = read(text_pdf(tmp_path / "plain.pdf", SLIP))

        assert result.readable
        assert "CBE/2026/12345" in result.text

    def test_a_spreadsheet_says_it_cannot_be_read_rather_than_failing(
            self, without_engine, tmp_path):
        path = tmp_path / "data.csv"
        path.write_bytes(csv_bytes())

        result = read(path)

        # .csv has no built-in reader; the honest answer is that it is
        # attached but unread, not an exception out of the upload endpoint.
        assert result.readable is False
        assert result.reason


@ENGINE
class TestWhatTheEngineAdds:
    def test_a_scanned_page_is_read(self, tmp_path):
        """The case that mattered most: before this, a photographed slip was
        stored, listed as an enclosure, and contributed nothing at all."""
        result = read(scanned_pdf(tmp_path / "scan.pdf", SLIP))

        assert result.readable, result.reason
        assert result.method == "ocr"
        assert "CBE/2026/12345" in result.text

    def test_a_spreadsheet_comes_back_as_a_table(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_bytes(csv_bytes())

        result = read(path)

        assert result.readable
        assert result.tables, "the rows were flattened away"
        assert result.tables[0].header[:2] == ["Ward", "Complaint"]

    def test_a_value_inside_a_table_is_visible_to_the_field_readers(self, tmp_path):
        """The reference number lives in a cell. If the table is kept only as
        structure, the deterministic extractors never see it and the citizen
        is never offered it."""
        path = tmp_path / "data.csv"
        path.write_bytes(csv_bytes())

        assert "CBE/2026/12345" in read(path).text

    def test_pages_survive(self, tmp_path):
        import pymupdf

        document = pymupdf.open()
        document.new_page().insert_text((60, 90), "The first page of two.", fontsize=11)
        document.new_page().insert_text((60, 90), "Reference CBE/2026/54321.", fontsize=11)
        path = tmp_path / "two.pdf"
        document.save(str(path))
        document.close()

        result = read(path)

        assert len(result.segments) == 2
        found = extraction.locate(result.segments, "CBE/2026/54321")
        assert found is not None and found.number == 2


@ENGINE
class TestOcrIsStillNotTrusted:
    def test_an_ocr_read_is_capped_below_the_confidence_threshold(self, tmp_path):
        """However good the engine says it was. The cap is not an opinion
        about accuracy — it is the rule that a guess about pixels must be
        looked at by a person before it becomes a claim on a government form,
        and a better engine must not be able to opt out of it."""
        result = read(scanned_pdf(tmp_path / "scan.pdf", SLIP))

        assert result.method == "ocr"
        assert result.confidence <= extraction.OCR_CEILING
        assert result.low_confidence, "an OCR read must flag for confirmation"

    def test_a_native_read_is_not_capped(self, tmp_path):
        result = read(text_pdf(tmp_path / "plain.pdf", SLIP))

        assert result.method != "ocr"
        assert not result.low_confidence

    def test_the_ceiling_really_is_below_the_threshold(self):
        """Stated as a relationship rather than a number, so tuning one
        cannot silently let OCR through the other."""
        assert extraction.OCR_CEILING < extraction.LOW_CONFIDENCE


class TestIdentifiersAreHiddenBeforeTheyAreShown:
    """An earlier petition carries the petitioner's Aadhaar and mobile in its
    own header, and the evidence snippet beside an extracted value is a line
    of that document."""

    def test_an_aadhaar_keeps_only_its_last_four_digits(self):
        assert mask_for_display("Aadhaar number: 2345 6789 0124") == \
            "Aadhaar number: XXXX XXXX 0124"
        assert mask_for_display("Aadhaar: 234567890124") == "Aadhaar: XXXX XXXX 0124"

    def test_a_mobile_does_too_however_it_is_written(self):
        """Including the spacing this service itself prints, which a plain
        ten-digit pattern missed — and the service's own output is exactly
        the document a returning citizen attaches."""
        for written in ("9344174752", "+91 93441 74752", "+91-9344174752"):
            masked = mask_for_display(f"Mobile: {written}")
            assert "4752" in masked, written
            assert "9344174752" not in masked.replace(" ", ""), written

    def test_a_reference_number_is_left_alone(self):
        """The one value the petition most needs to quote. A catch-all
        numeric rule would mangle it."""
        for reference in ("CBE/2026/12345", "2026/PG/44710012", "TN-REV-2026-0012"):
            assert mask_for_display(f"Ref: {reference}") == f"Ref: {reference}"

    def test_so_are_dates_and_small_numbers(self):
        assert mask_for_display("Dated 12-08-2026, ward 12, 45 days") == \
            "Dated 12-08-2026, ward 12, 45 days"

    def test_nothing_unmasked_reaches_the_stored_record(self):
        """The end-to-end property: analyse an old petition that carries both
        identifiers and check the dictionary that goes into the checkpoint."""
        import json

        from app.domain import prior_petition
        from app.domain.letter import build_letter_text
        from app.domain.templates import the_template

        letter = build_letter_text(
            template=the_template(),
            fields={"applicant_name": "Harish Kumar", "age": 21,
                    "mobile": "9344174752", "address": "72/11 Gandhipuram",
                    "aadhaar": "234567890124",
                    "grievance": "The street light has not worked."},
            language="en", composition=None, session_id="prior-000000000001")

        stored = json.dumps(prior_petition.analyse(letter).as_dict())

        assert "234567890124" not in stored
        assert "2345 6789 0124" not in stored
        assert "9344174752" not in stored
        assert "93441 74752" not in stored


class TestWhetherADocumentHasAnythingToDoWithTheComplaint:
    GRIEVANCE = "The street light outside my house has not worked for three months."

    def test_an_earlier_petition_about_the_same_thing_is_relevant(self):
        found = attachment_relevance.assess(
            kind="previous_petition", grievance=self.GRIEVANCE,
            text=("Petition regarding the street light outside my house which "
                  "has not worked. Reference CBE/2026/12345."))

        assert found.level == "high"
        assert found.mine_for_facts

    def test_a_ration_card_is_not(self):
        found = attachment_relevance.assess(
            kind="other", grievance=self.GRIEVANCE,
            text="Public Distribution System family card. Rice, sugar, kerosene.")

        assert found.level == "unrelated"
        assert not found.mine_for_facts

    def test_but_it_is_still_kept(self):
        """The citizen brought it on purpose. Judging it irrelevant changes
        how it is presented and nothing else."""
        found = attachment_relevance.assess(
            kind="other", grievance=self.GRIEVANCE, text="Something unrelated entirely.")

        assert "stays attached" in found.reason

    def test_a_residence_proof_supports_without_being_about_the_complaint(self):
        found = attachment_relevance.assess(
            kind="address_proof", grievance=self.GRIEVANCE,
            text="Electricity bill for the premises. Consumer number 123456789.")

        assert found.level == "partial"

    def test_something_unreadable_is_unknown_not_unrelated(self):
        """A document that could not be read has not been judged. Calling it
        irrelevant would be a conclusion drawn from a failure."""
        found = attachment_relevance.assess(
            kind="other", grievance=self.GRIEVANCE, text="", readable=False)

        assert found.level == "unknown"
        assert found.mine_for_facts

    def test_nothing_is_judged_before_the_grievance_exists(self):
        found = attachment_relevance.assess(
            kind="previous_petition", grievance="", text="A petition about something.")

        assert found.level == "unknown"

    def test_the_reason_is_in_the_citizens_language(self):
        english = attachment_relevance.assess(
            kind="other", grievance=self.GRIEVANCE, text="Unrelated matter.")
        tamil = attachment_relevance.assess(
            kind="other", grievance=self.GRIEVANCE, text="Unrelated matter.",
            language="ta")

        assert tamil.level == english.level
        assert tamil.reason != english.reason
        assert any("஀" <= c <= "௿" for c in tamil.reason)


class TestTheNewFormatsAreAccepted:
    def test_spreadsheets_and_web_pages_are_allowed(self):
        assert {".xlsx", ".xls", ".csv", ".html"} <= ALLOWED_SUFFIXES

    def test_a_spreadsheet_is_not_mistaken_for_a_word_file(self):
        """XLSX, DOCX and PPTX are all zips with the same leading bytes."""
        assert attachment_store._sniff(xlsx_zip_bytes()) == ".xlsx"

    def test_text_formats_are_checked_for_binary_content_instead(self, session):
        """They have no signature, so the NUL-byte test stands in for one."""
        assert {".csv", ".html"} <= TEXT_SUFFIXES

        with pytest.raises(attachment_store.AttachmentRejected):
            attachment_store.save(session_id=session, filename="evil.csv",
                                  content=b"MZ\x90\x00" + b"\x00" * 400,
                                  existing=AttachmentSet())

    def test_a_real_csv_is_accepted(self, session):
        stored = attachment_store.save(session_id=session, filename="data.csv",
                                       content=csv_bytes(), existing=AttachmentSet())

        assert stored.path.suffix == ".csv"
        assert stored.path.is_file()

    def test_an_html_page_is_accepted_and_never_executed(self, session):
        """It is read for its words. Nothing in this service renders it."""
        page = b"<html><body><p>Acknowledgement CBE/2026/12345</p></body></html>"
        stored = attachment_store.save(session_id=session, filename="page.html",
                                       content=page, existing=AttachmentSet())

        assert stored.path.suffix == ".html"
