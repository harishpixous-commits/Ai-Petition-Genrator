"""Reading an attachment closely enough to cite it, and to argue with it.

Two things are tested here that the older attachment tests do not cover.

The first is PROVENANCE. A value read out of a document is a claim, and the
citizen is asked to confirm it. That question is only answerable if they are
told where to look — "page 2", "slide 4" — so the location travels with the
value from the extractor to the confirmation card. A location that is wrong is
worse than none, so a value that cannot be found is left unattributed rather
than blamed on page 1.

The second is DISAGREEMENT. A returning citizen attaches the petition they
filed two years ago, from the address they lived at two years ago. Both values
are true and only one belongs on today's letter. Nothing here resolves that:
it is found, both sides are named, and the citizen is asked. The current
answer stays on the petition until they say otherwise.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import Path

import pytest

from app.domain import attachment_conflicts, prior_petition
from app.domain.attachments import (
    ALLOWED_SUFFIXES,
    INDISTINGUISHABLE,
    Attachment,
    AttachmentSet,
)
from app.domain.letter import build_letter_text
from app.domain.templates import the_template
from app.services import attachment_store, extraction

DRAWING_ML = "http://schemas.openxmlformats.org/drawingml/2006/main"
OLE_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def slide_xml(lines: list[str]) -> bytes:
    runs = "".join(f"<a:p><a:r><a:t>{line}</a:t></a:r></a:p>" for line in lines)
    return (f'<?xml version="1.0"?><p:sld xmlns:p="p" xmlns:a="{DRAWING_ML}">'
            f"<p:cSld><p:spTree>{runs}</p:spTree></p:cSld></p:sld>").encode()


def pptx_bytes(slides: dict[int, list[str]],
               notes: dict[int, list[str]] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("[Content_Types].xml", "<Types/>")
        bundle.writestr("ppt/presentation.xml", "<p:presentation/>")
        for number, lines in slides.items():
            bundle.writestr(f"ppt/slides/slide{number}.xml", slide_xml(lines))
        for number, lines in (notes or {}).items():
            bundle.writestr(f"ppt/notesSlides/notesSlide{number}.xml", slide_xml(lines))
    return buffer.getvalue()


def docx_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("[Content_Types].xml", "<Types/>")
        bundle.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


@pytest.fixture
def session() -> str:
    name = str(uuid.uuid4())
    yield name
    attachment_store.discard_session(name)


class TestAPresentationIsReadSlideBySlide:
    def test_a_presentation_is_not_mistaken_for_a_word_file(self):
        """Both are zips with the same four leading bytes. Before the package
        was inspected, a deck was stored as .docx and handed to a Word parser
        that could make nothing of it."""
        assert attachment_store._sniff(pptx_bytes({1: ["x"]})) == ".pptx"
        assert attachment_store._sniff(docx_zip_bytes()) == ".docx"

    def test_a_zip_that_is_neither_is_refused(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("whatever.txt", "not office at all")

        assert attachment_store._sniff(buffer.getvalue()) is None

    def test_it_is_accepted(self, session):
        stored = attachment_store.save(
            session_id=session, filename="deck.pptx",
            content=pptx_bytes({1: ["Ward 12"]}), existing=AttachmentSet())

        assert stored.path.suffix == ".pptx"
        assert stored.path.is_file()

    def test_renaming_one_to_docx_does_not_get_it_past_the_check(self, session):
        with pytest.raises(attachment_store.AttachmentRejected):
            attachment_store.save(
                session_id=session, filename="sneaky.docx",
                content=pptx_bytes({1: ["x"]}), existing=AttachmentSet())

    def test_each_slide_is_its_own_source(self, session):
        stored = attachment_store.save(
            session_id=session, filename="deck.pptx", existing=AttachmentSet(),
            content=pptx_bytes({1: ["Ward 12 review"],
                                2: ["Outstanding", "Reference CBE/2026/12345"]}))

        read = extraction.extract(stored.path)

        assert read.readable, read.reason
        assert read.method == "pptx"
        assert [(s.number, s.unit) for s in read.segments] == [(1, "slide"), (2, "slide")]

    def test_speaker_notes_are_read_too(self, session):
        """A slide says "Ward 12" and the note under it carries the date. The
        date is the part a petition wants to cite."""
        stored = attachment_store.save(
            session_id=session, filename="deck.pptx", existing=AttachmentSet(),
            content=pptx_bytes({1: ["Ward 12"]},
                               notes={1: ["Complaint filed 12-08-2026"]}))

        assert "12-08-2026" in extraction.extract(stored.path).text

    def test_a_deck_of_pictures_says_so_rather_than_coming_back_empty(self, session):
        stored = attachment_store.save(
            session_id=session, filename="deck.pptx", existing=AttachmentSet(),
            content=pptx_bytes({1: [], 2: []}))

        read = extraction.extract(stored.path)

        assert not read.readable
        assert "still be attached" in read.reason


class TestTheOlderOfficeFormats:
    """Accepted and carried, never parsed. A citizen holding a .doc from an
    office should not be turned away, and a format this service does not read
    is a format with no parser to attack."""

    def test_both_are_allowed(self):
        assert {".doc", ".ppt", ".pptx"} <= ALLOWED_SUFFIXES

    def test_they_share_a_signature_and_the_extension_decides(self, session):
        content = OLE_HEADER + b"\x00" * 600

        for name, suffix in (("old.doc", ".doc"), ("old.ppt", ".ppt")):
            stored = attachment_store.save(session_id=session, filename=name,
                                           content=content, existing=AttachmentSet())
            assert stored.path.suffix == suffix

    def test_that_leniency_is_declared_rather_than_incidental(self):
        """If the family table is emptied the store silently starts refusing
        all but one of them, which would look like a corrupt-file bug.

        Asserted as a subset rather than an exact set: .doc, .ppt and .xls all
        share the OLE header, and a fourth legacy format joining them later
        should not fail this."""
        assert any({".doc", ".ppt", ".xls"} <= family
                   for family in INDISTINGUISHABLE)

    def test_an_unreadable_one_is_reported_not_faked(self, session):
        stored = attachment_store.save(session_id=session, filename="old.doc",
                                       content=OLE_HEADER + b"\x00" * 600,
                                       existing=AttachmentSet())

        read = extraction.extract(stored.path)

        assert not read.readable
        assert read.text == ""
        assert "still be attached" in read.reason

    def test_an_executable_named_as_one_is_still_refused(self, session):
        with pytest.raises(attachment_store.AttachmentRejected):
            attachment_store.save(session_id=session, filename="bad.doc",
                                  content=b"MZ\x90\x00" + b"\x00" * 400,
                                  existing=AttachmentSet())


class TestWhereAValueWasRead:
    @staticmethod
    def _pdf(tmp_path: Path, pages: list[str]) -> Path:
        import pymupdf

        document = pymupdf.open()
        for body in pages:
            document.new_page().insert_text((60, 90), body, fontsize=11)
        path = tmp_path / "multi.pdf"
        document.save(str(path))
        document.close()
        return path

    def test_a_pdf_is_split_into_its_pages(self, tmp_path):
        read = extraction.extract(self._pdf(
            tmp_path, ["The subject line and nothing else at all here.",
                       "Acknowledgement number CBE/2026/54321 is on this page."]))

        assert [s.number for s in read.segments] == [1, 2]
        assert all(s.unit == "page" for s in read.segments)

    def test_a_fact_on_page_two_is_cited_as_page_two(self, tmp_path):
        read = extraction.extract(self._pdf(
            tmp_path, ["The subject line and nothing else at all here.",
                       "Acknowledgement number CBE/2026/54321 is on this page."]))
        prior = prior_petition.analyse(read.text, segments=read.segments)

        assert prior.reference_number is not None
        assert prior.reference_number.page == 2
        assert prior.reference_number.unit == "page"
        assert prior.reference_number.where() == "page 2"

    def test_a_value_that_is_not_there_is_not_blamed_on_page_one(self, tmp_path):
        read = extraction.extract(self._pdf(tmp_path, ["one", "two"]))

        assert extraction.locate(read.segments, "nothing like this") is None

    def test_an_unattributed_value_says_nothing_rather_than_something_wrong(self):
        """Callers with no segments — and formats with no pages — lose the
        location and keep everything else."""
        prior = prior_petition.analyse("Reference CBE/2026/11111 was issued.")

        assert prior.reference_number is not None
        assert prior.reference_number.page == 0
        assert prior.reference_number.where() == ""

    def test_the_location_survives_the_checkpoint(self):
        """It goes into the session state as a dict and comes back out. A
        field dropped from either list is invisible until a citizen reopens a
        petition and finds the page numbers gone."""
        original = prior_petition.Extracted(value="CBE/2026/1", confidence=0.9,
                                            page=3, unit="slide")

        restored = prior_petition.PriorPetition.from_dict(
            prior_petition.PriorPetition(reference_number=original).as_dict())

        assert restored is not None
        assert restored.reference_number.page == 3
        assert restored.reference_number.unit == "slide"

    def test_scanned_pages_are_separated_so_they_can_be_cited(self):
        """The OCR engine joins pages with a form feed. A bare newline is
        indistinguishable from the line breaks inside a page, and page
        attribution for a scan is then impossible."""
        source = Path("app/services/ocr.py").read_text(encoding="utf-8")
        body = source[source.rindex("def pdf(self"):]

        assert '"\\n\\f\\n".join(pages)' in body


class TestReadingThisServicesOwnPetition:
    """The document a returning citizen brings is, more often than not, the
    petition this service printed for them last time."""

    @staticmethod
    def _letter(**overrides) -> str:
        fields = {"applicant_name": "Harish Kumar", "age": 21,
                  "mobile": "9344174752", "address": "72/11 Gandhipuram, Coimbatore",
                  "aadhaar": "234567890124",
                  "grievance": "The street light has not worked."}
        fields.update(overrides)
        return build_letter_text(template=the_template(), fields=fields,
                                 language="en", composition=None,
                                 session_id="prior-000000000001")

    def test_the_petitioners_name_is_read(self):
        prior = prior_petition.analyse(self._letter())

        assert prior.petitioner_name is not None
        assert prior.petitioner_name.value == "Harish Kumar"

    def test_the_address_is_read(self):
        prior = prior_petition.analyse(self._letter())

        assert prior.address is not None
        assert prior.address.value == "72/11 Gandhipuram, Coimbatore"

    def test_the_labelled_details_below_it_are_not_swept_into_the_address(self):
        """"Age: 21" and the Aadhaar line sit directly under the address in
        the From block. Reading to the end of the block would put an Aadhaar
        number into a field shown on a confirmation card."""
        prior = prior_petition.analyse(self._letter())

        assert "Age" not in prior.address.value
        assert "234567890124" not in prior.address.value
        assert "2345" not in prior.address.value

    def test_the_addressee_is_not_mistaken_for_the_petitioner(self):
        prior = prior_petition.analyse(self._letter())

        assert "Collector" not in prior.petitioner_name.value


class TestWhenTheDocumentDisagrees:
    @staticmethod
    def _attachment(text: str, *, confirmed: bool = True) -> Attachment:
        return Attachment(
            attachment_id="a1", filename="previous_petition.pdf",
            stored_name="a1.pdf", content_type="application/pdf", size=10,
            kind="previous_petition", confirmed=confirmed,
            extracted=prior_petition.analyse(text).as_dict())

    @staticmethod
    def _letter(address: str = "72/11 Gandhipuram, Coimbatore",
                name: str = "Harish Kumar") -> str:
        return build_letter_text(
            template=the_template(),
            fields={"applicant_name": name, "age": 21, "mobile": "9344174752",
                    "address": address, "aadhaar": "234567890124",
                    "grievance": "The street light has not worked."},
            language="en", composition=None, session_id="prior-000000000001")

    def test_a_different_address_is_raised(self):
        found = attachment_conflicts.find(
            {"address": "80/33 Sidhapudur, Coimbatore 641044"},
            AttachmentSet([self._attachment(self._letter())]))

        assert [c.field for c in found] == ["address"]
        assert found[0].current == "80/33 Sidhapudur, Coimbatore 641044"
        assert "Gandhipuram" in found[0].proposed
        assert found[0].filename == "previous_petition.pdf"

    def test_the_same_address_is_not(self):
        assert not attachment_conflicts.find(
            {"address": "72/11 Gandhipuram, Coimbatore"},
            AttachmentSet([self._attachment(self._letter())]))

    def test_a_postcode_added_is_not_a_disagreement(self):
        """Asking a citizen to choose between an address and the same address
        with the postcode on it teaches them to dismiss the question."""
        assert not attachment_conflicts.find(
            {"address": "72/11 Gandhipuram, Coimbatore 641012"},
            AttachmentSet([self._attachment(self._letter())]))

    def test_neither_is_punctuation(self):
        assert not attachment_conflicts.find(
            {"address": "72/11, GANDHIPURAM, COIMBATORE."},
            AttachmentSet([self._attachment(self._letter())]))

    def test_a_longer_name_is_a_different_person(self):
        """The bug this test exists for: the containment rule that correctly
        treats an extended ADDRESS as the same place said "Harish Kumar" and
        "Harish Kumaresan" were the same man, and the disagreement went
        unreported. Names are compared exactly; addresses are not."""
        found = attachment_conflicts.find(
            {"applicant_name": "Harish Kumaresan"},
            AttachmentSet([self._attachment(self._letter(name="Harish Kumar"))]))

        assert [c.field for c in found] == ["applicant_name"]

    def test_an_unconfirmed_attachment_raises_nothing(self):
        """Until the citizen has looked at what was read, it is not a claim
        about anything, and asking them to arbitrate against it would be
        asking about a string they have never been shown."""
        assert not attachment_conflicts.find(
            {"address": "80/33 Sidhapudur"},
            AttachmentSet([self._attachment(self._letter(), confirmed=False)]))

    def test_a_missing_value_on_either_side_raises_nothing(self):
        assert not attachment_conflicts.find(
            {}, AttachmentSet([self._attachment(self._letter())]))
        assert not attachment_conflicts.find(
            {"address": "80/33 Sidhapudur"},
            AttachmentSet([self._attachment("A note with no From block.")]))

    def test_finding_a_disagreement_changes_nothing(self):
        """The whole module is detection. The current answer is already on the
        petition and stays there until the citizen picks the other one."""
        fields = {"address": "80/33 Sidhapudur", "applicant_name": "Harish Kumar"}
        before = dict(fields)

        attachment_conflicts.find(
            fields, AttachmentSet([self._attachment(self._letter())]))

        assert fields == before

    def test_the_page_it_came_from_is_offered_with_it(self):
        text = self._letter()
        prior = prior_petition.analyse(
            text, segments=[extraction.Segment(number=2, text=text, unit="page")])
        attachment = Attachment(
            attachment_id="a1", filename="p.pdf", stored_name="a1.pdf",
            content_type="application/pdf", size=10, confirmed=True,
            kind="previous_petition", extracted=prior.as_dict())

        found = attachment_conflicts.find({"address": "80/33 Sidhapudur"},
                                          AttachmentSet([attachment]))

        assert found[0].where == "page 2"


class TestTheContentsPageBeforeTheAttachments:
    """An officer holding a petition with six scans behind it should see what
    is there without leafing through."""

    @staticmethod
    def _enclosure(tmp_path: Path, name: str, detail: str = ""):
        import pymupdf

        from app.services.enclosures import Enclosure

        document = pymupdf.open()
        document.new_page().insert_text((60, 90), f"Body of {name}", fontsize=11)
        path = tmp_path / name
        document.save(str(path))
        document.close()
        return Enclosure(label=f"1. {name}", path=path, filename=name, detail=detail)

    def _render(self, tmp_path: Path, enclosures):
        from app.services.render import extract_docx_text, render_docx

        out = render_docx("Respected Sir,\n\nThe body of the petition.\n",
                          tmp_path / "out.docx", reference="AP/2026/T",
                          enclosures=enclosures, enclosure_heading="Enclosure",
                          index_title="Supporting documents")
        return extract_docx_text(out)

    def test_two_enclosures_get_a_contents_page(self, tmp_path):
        text = self._render(tmp_path, [
            self._enclosure(tmp_path, "previous_petition.pdf",
                            detail="Reference: CBE/2026/12345"),
            self._enclosure(tmp_path, "residence_proof.pdf")])

        assert "Supporting documents" in text
        assert "previous_petition.pdf" in text
        assert "residence_proof.pdf" in text
        assert "Reference: CBE/2026/12345" in text

    def test_one_enclosure_does_not(self, tmp_path):
        """Its own caption page already says everything an index would, and a
        contents page listing one item is a wasted sheet of paper."""
        text = self._render(tmp_path, [self._enclosure(tmp_path, "only.pdf")])

        assert "Supporting documents" not in text
        assert "only.pdf" in text or "1. only.pdf" in text

    def test_no_enclosures_get_no_page_at_all(self, tmp_path):
        assert "Supporting documents" not in self._render(tmp_path, [])


class TestWhatTheContentsPageIsAllowedToSay:
    """The index is part of the document. Anything it prints is something the
    petition asserts, so it may only carry values the citizen has confirmed —
    otherwise the extraction reaches the page by the back door, which is the
    one thing the confirmation step exists to prevent."""

    @staticmethod
    def _attachment(*, confirmed: bool):
        text = ("ACKNOWLEDGEMENT\nYour petition has been received and registered.\n"
                "Acknowledgement number: CBE/2026/12345\n"
                "Date of receipt: 12-08-2026\nStatus: Pending\n")
        return Attachment(
            attachment_id="a1", filename="ack.pdf", stored_name="a1.pdf",
            content_type="application/pdf", size=10, kind="acknowledgement",
            confirmed=confirmed, extracted=prior_petition.analyse(text).as_dict())

    def test_a_confirmed_document_may_name_its_reference(self):
        from app.graph.nodes import _enclosure_detail

        detail = _enclosure_detail(self._attachment(confirmed=True), "en")

        assert "CBE/2026/12345" in detail

    def test_an_unconfirmed_one_says_nothing(self):
        from app.graph.nodes import _enclosure_detail

        assert _enclosure_detail(self._attachment(confirmed=False), "en") == ""

    def test_an_attachment_with_nothing_read_says_nothing(self):
        from app.graph.nodes import _enclosure_detail

        bare = Attachment(attachment_id="a2", filename="photo.jpg",
                          stored_name="a2.jpg", content_type="image/jpeg",
                          size=10, kind="photo", confirmed=True, extracted=None)

        assert _enclosure_detail(bare, "en") == ""


class TestADocumentMayNotRenameThePetitioner:
    """REPORTED FROM A GENERATED PETITION, and the worst kind of wrong: it
    looked like a considered choice.

        the citizen typed      Harish
        the attached PDF said  சேதுபாலா
        extraction produced    சேபாலா      (confidence 0.8)

    A syllable short of the name on the page. That misreading was offered as
    a one-click replacement for a name the citizen had typed correctly, they
    took it, and the petition went out under a name belonging to nobody —
    not the citizen, not the person in the document.

    The DISAGREEMENT is still worth raising: a document naming somebody else
    is worth a second look at a counter, and it is often legitimate, because
    a neighbour's earlier petition is real evidence. What is not offered any
    more is the swap.
    """

    @staticmethod
    def _attachment(text: str) -> Attachment:
        return Attachment(
            attachment_id="a1", filename="previous_petition.pdf",
            stored_name="a1.pdf", content_type="application/pdf", size=10,
            kind="previous_petition", confirmed=True,
            extracted=prior_petition.analyse(text).as_dict())

    def _letter(self, name: str) -> str:
        return build_letter_text(
            template=the_template(),
            fields={"applicant_name": name, "age": 23, "mobile": "9344174752",
                    "address": "80/33 Perumal Kovil Street, Theni",
                    "grievance": "The road is damaged."},
            language="en", composition=None, session_id="prior-000000000002")

    def test_the_disagreement_is_still_reported(self):
        found = attachment_conflicts.find(
            {"applicant_name": "Harish",
             "address": "80/33 Perumal Kovil Street, Theni"},
            AttachmentSet([self._attachment(self._letter("Sethubala"))]))

        assert [c.field for c in found] == ["applicant_name"]
        assert found[0].current == "Harish"

    def test_but_the_document_is_not_offered_as_a_replacement(self):
        found = attachment_conflicts.find(
            {"applicant_name": "Harish"},
            AttachmentSet([self._attachment(self._letter("Sethubala"))]))

        assert found[0].adoptable is False
        assert found[0].as_dict()["adoptable"] is False

    def test_an_address_still_may_be_adopted(self):
        """A document's address is often better than the one typed at a
        counter — the same place with the postcode on it."""
        found = attachment_conflicts.find(
            {"applicant_name": "Harish", "address": "Somewhere else entirely"},
            AttachmentSet([self._attachment(self._letter("Harish"))]))

        assert [c.field for c in found] == ["address"]
        assert found[0].adoptable is True

    def test_the_page_offers_no_button_for_a_name(self):
        """The other half of the rule. A server that marks the value
        unadoptable and a page that offers it anyway is no rule at all."""
        import pathlib
        import re

        source = pathlib.Path("app/static/app.js").read_text(encoding="utf-8")
        card = source[source.index('$("attachConflictList").innerHTML'):]
        card = card[:card.index("</div>`).join")]

        assert "adoptable === false" in card
        assert re.search(r"adoptable === false \?\s*\"\"\s*:", card), card
