"""The petition document: how it is built, rendered, and checked afterwards.

DOCX is the primary output and is always produced. PDF goes through an external
converter and may not be available; when it is not, the petition still completes
and says so. Those two facts are what most of this file asserts.
"""

from __future__ import annotations

from datetime import date

import pytest
from docx import Document

from app.config import Settings
from app.domain.letter import (
    LABELS,
    Composition,
    build_letter_text,
    derive_place,
    fallback_composition,
    reference_number,
    verification_targets,
)
from app.domain.templates import the_template
from app.services.render import (
    classify,
    extract_docx_text,
    pdf_available,
    render_docx,
    render_pdf,
)


@pytest.fixture
def fields(answers, valid_aadhaar) -> dict:
    return {**answers, "age": 45, "aadhaar": valid_aadhaar}


@pytest.fixture
def english_letter(fields) -> str:
    return build_letter_text(
        template=the_template(), fields=fields, language="en",
        composition=None, session_id="abc-123-def-456",
    )


@pytest.fixture
def tamil_letter(tamil_answers, valid_aadhaar) -> str:
    return build_letter_text(
        template=the_template(),
        fields={**tamil_answers, "age": 45, "aadhaar": valid_aadhaar},
        language="ta", composition=None, session_id="abc-123-def-456",
    )


# --------------------------------------------------------------------------- #
# The text
# --------------------------------------------------------------------------- #


class TestLetterText:
    """The standard Tamil petition format: sender block, receiver block,
    salutation, subject, opening, the citizen's own words, the prayer, thanks,
    sign-off, and the date and place at the foot."""

    def test_it_follows_the_standard_petition_format(self, english_letter):
        for marker in ("From,", "To,", "Respected Sir / Madam,", "Subject:",
                       "Thanking you,", "Yours faithfully,", "Date:", "Place:"):
            assert marker in english_letter, marker

    def test_the_closing_is_written_the_way_a_petition_closes_it(self, english_letter):
        """"Thanking you," not "Thank you!". An exclamation mark is the wrong
        register for a document an officer files, and it is the detail that
        makes a letter read as generated rather than written."""
        assert "Thanking you," in english_letter
        assert "Thank you!" not in english_letter
        assert "!" not in english_letter.split("Thanking you,")[1]

    def test_the_sign_off_comes_from_the_template(self):
        """`petition.yaml` carried a `closing:` that nothing read: an office
        changing the prescribed sign-off there saw no effect and no error."""
        import dataclasses

        from app.domain.letter import build_letter_text
        from app.domain.templates import the_template

        template = dataclasses.replace(
            the_template(),
            closing={"en": "Respectfully submitted,", "ta": "வணக்கத்துடன்,"})
        text = build_letter_text(
            template=template, fields={"applicant_name": "Ravi Kumar"},
            language="en", composition=None, session_id="abc-123")

        assert "Respectfully submitted," in text
        assert "Yours faithfully," not in text

    def test_the_blocks_come_in_the_prescribed_order(self, english_letter):
        # The date and place lead the letter now, printed flush right, which is
        # where a letter carries them. They used to sit under the signature.
        order = ["Date:", "Place:", "From,", "To,", "Respected Sir / Madam,",
                 "Subject:", "Thanking you,", "Yours faithfully,"]
        positions = [english_letter.index(marker) for marker in order]
        assert positions == sorted(positions), "the letter reads top to bottom"

    def test_the_tamil_letter_is_labelled_in_tamil(self, tamil_letter):
        for key in ("from", "to", "salutation", "subject", "thanks", "signoff",
                    "date", "place", "note"):
            assert LABELS[key]["ta"] in tamil_letter, key
        for english_only in ("From,", "To,", "Subject:", "Date:", "Place:"):
            assert english_only not in tamil_letter, english_only

    def test_the_tamil_subject_closes_with_thodarbaaga(self, tamil_letter):
        subject = next(ln for ln in tamil_letter.split("\n") if ln.startswith("பொருள்:"))
        assert subject.rstrip().endswith("தொடர்பாக."), subject

    def test_the_sender_block_carries_the_petitioner_details(self, english_letter, answers):
        block = english_letter.split("From,")[1].split("To,")[0]
        assert answers["applicant_name"] in block
        assert answers["address"] in block
        assert "Age: 45" in block
        assert "Aadhaar number: 2345 6789 0124" in block, "grouped as it will be printed"

    def test_the_grievance_sits_between_the_opening_and_the_prayer(
        self, english_letter, answers
    ):
        opening = english_letter.index("I reside at the address given above")
        grievance = english_letter.index(answers["grievance"].split("\n")[0])
        prayer = english_letter.index("I therefore humbly request")
        assert opening < grievance < prayer

    def test_the_place_is_taken_from_the_address(self, english_letter):
        assert "Place: Coimbatore" in english_letter

    def test_a_place_is_omitted_when_the_address_gives_none(self, fields):
        text = build_letter_text(
            template=the_template(), fields={**fields, "address": "Gandhi Street 12"},
            language="en", composition=None, session_id="abc-123",
        )
        assert "Place:" not in text, "a wrong town is worse than a missing one"
        assert "Date:" in text

    def test_the_note_is_present_in_both_languages(self, english_letter, tamil_letter):
        """Where the petition came from, and what to do before signing it."""
        assert "based on the information provided by the petitioner" in english_letter
        assert "Please verify all details before signing" in english_letter
        assert "மனுதாரர் வழங்கிய தகவல்களின் அடிப்படையில்" in tamil_letter
        assert "சரிபார்க்கவும்" in tamil_letter

    def test_the_note_says_those_two_things_and_stops(self, english_letter, tamil_letter):
        """Two sentences. The department has now removed a third twice, and
        this is what keeps both removals from being undone by somebody
        assuming the line was lost rather than taken out."""
        from app.domain.phrasing import DISCLAIMER

        for language in ("en", "ta"):
            sentences = [s for s in DISCLAIMER[language].split(".") if s.strip()]
            assert len(sentences) == 2, DISCLAIMER[language]

    def test_the_note_never_judges_the_citizens_case(self, english_letter, tamil_letter):
        """The note says what the document IS, and stops there.

        An earlier wording added "and it does not decide your eligibility",
        which reads to the person holding it as a verdict the assistant has
        already reached about their claim. It is also untrue in the direction
        that matters: nothing here has assessed their eligibility either way,
        so telling them it has not "decided" it implies the question was
        looked at. Asked for removal, and kept out by this.
        """
        for letter in (english_letter, tamil_letter):
            lowered = letter.lower()
            assert "eligib" not in lowered
            assert "தகுதி" not in letter

    def test_the_note_makes_no_claim_about_legal_advice(self, english_letter,
                                                        tamil_letter):
        """Removed on request. The note should say where the petition came
        from and what to do before signing it, and stop there — so nothing in
        the document now carries a legal-advice disclaimer, in either
        language."""
        assert "legal advice" not in english_letter.lower()
        assert "சட்ட ஆலோசனை" not in tamil_letter

    def test_the_reference_is_stable_and_not_in_the_body(self, english_letter):
        """The format has no reference line, so it lives in the document footer.
        A reprint must still carry the same one as the citizen's copy."""
        session = "11111111-2222-3333-4444-555555555555"
        assert reference_number(session) == reference_number(session)
        assert reference_number(session, date(2026, 1, 1)).startswith("AP/2026/")
        assert "AP/2026" not in english_letter

    def test_the_standard_wording_matches_the_format(self, fields):
        standard = fallback_composition(the_template(), fields, "en")
        assert "address given above" in standard.introduction
        assert "at the earliest" in standard.request
        tamil = fallback_composition(the_template(), fields, "ta")
        assert tamil.introduction.startswith("வணக்கம்.")
        assert tamil.request.startswith("எனவே,")

    def test_a_model_subject_replaces_the_standard_one(self, fields):
        text = build_letter_text(
            template=the_template(), fields=fields, language="en",
            composition=Composition(subject="Non-functioning street light at Peelamedu"),
            session_id="abc-123",
        )
        assert "Subject: Non-functioning street light at Peelamedu" in text
        assert "Petition seeking redressal of a grievance" not in text

    def test_each_slot_falls_back_on_its_own(self, fields):
        """A model that wrote a good subject and nothing else keeps its subject
        and gets the standard wording for the rest."""
        text = build_letter_text(
            template=the_template(), fields=fields, language="en",
            composition=Composition(subject="Blocked drain at Peelamedu"),
            session_id="abc-123",
        )
        assert "Subject: Blocked drain at Peelamedu" in text
        assert "I reside at the address given above" in text
        assert "I therefore humbly request" in text

    def test_a_model_subject_is_not_given_the_suffix_twice(self, fields):
        """Asked for Tamil, a model sometimes closes the subject itself."""
        text = build_letter_text(
            template=the_template(), fields=fields, language="ta",
            composition=Composition(subject="தெருவிளக்கு பழுது தொடர்பாக"),
            session_id="abc-123",
        )
        subject = next(ln for ln in text.split("\n") if ln.startswith("பொருள்:"))
        assert subject.count("தொடர்பாக") == 1, subject
        assert subject.rstrip().endswith("தொடர்பாக.")


class TestDerivePlace:
    def test_the_last_segment_after_the_pin(self):
        assert derive_place("12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர் - 641004") == "கோயம்புத்தூர்"

    def test_english_address(self):
        assert derive_place("12 Gandhi Street, Peelamedu, Coimbatore") == "Coimbatore"

    def test_a_pin_without_a_dash(self):
        assert derive_place("12 Gandhi Street, Peelamedu, Coimbatore 641004") == "Coimbatore"

    def test_nothing_to_go_on(self):
        assert derive_place("Gandhi Street 12") == ""
        assert derive_place("") == ""


class TestLineClassification:
    @pytest.mark.parametrize(
        "line,kind",
        [
            ("From,", "block"),
            ("To,", "block"),
            ("அனுப்புநர்,", "block"),
            ("பெறுநர்,", "block"),
            ("    Ravi Kumar", "party"),
            ("    ஆதார் எண்: 2345 6789 0124", "party"),
            ("Respected Sir / Madam,", "salutation"),
            ("மதிப்பிற்குரிய ஐயா / அம்மா,", "salutation"),
            ("Subject: Non-functioning street light", "subject"),
            ("பொருள்: தெருவிளக்கு பழுது தொடர்பாக.", "subject"),
            ("Date: 15-09-2026", "foot"),
            ("நாள்: 15-09-2026", "foot"),
            ("Place: Coimbatore", "foot"),
            ("இடம்: கோயம்புத்தூர்", "foot"),
            ("Thanking you,", "thanks"),
            ("நன்றி,", "thanks"),
            # The previous wording, which still arrives from a petition saved
            # before the format was reviewed and from an AI-written closing.
            ("Thank you!", "thanks"),
            ("நன்றி!", "thanks"),
            ("Yours faithfully,", "signoff"),
            ("இப்படிக்கு,", "signoff"),
            ("Note: This letter was prepared", "note"),
            ("குறிப்பு: இந்தக் கடிதம்", "note"),
            ("", "blank"),
        ],
    )
    def test_structure_is_recovered_from_the_text(self, line, kind):
        assert classify(line, 5, 40) == kind

    def test_a_sender_line_with_a_colon_is_still_a_sender_line(self):
        """`வயது: 45` sits inside the அனுப்புநர் block and must not be mistaken
        for a footer line just because it has a colon."""
        assert classify("    வயது: 45", 3, 40) == "party"

    def test_the_signature_is_recognised_near_the_end(self):
        assert classify("Ravi Kumar", 37, 40) == "signature"

    def test_a_sentence_near_the_end_is_not_a_signature(self):
        assert classify("I therefore humbly request that you act.", 37, 40) == "body"


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #


class TestDocx:
    def test_every_required_value_reaches_the_file(self, tmp_path, english_letter, fields):
        path = render_docx(english_letter, tmp_path / "p.docx", reference="AP/2026/ABC123")
        produced = " ".join(extract_docx_text(path).split())
        for name, expected in verification_targets(the_template(), fields, "en").items():
            assert " ".join(expected.split()) in produced, name

    def test_tamil_values_reach_the_file(self, tmp_path, tamil_letter, tamil_answers,
                                         valid_aadhaar):
        path = render_docx(tamil_letter, tmp_path / "ta.docx", reference="AP/2026/ABC123")
        produced = " ".join(extract_docx_text(path).split())
        assert tamil_answers["applicant_name"] in produced
        assert tamil_answers["address"] in produced
        assert "2345 6789 0124" in produced

    def test_the_reference_is_in_the_footer(self, tmp_path, english_letter):
        """An office files by the reference, so it has to be on every page."""
        path = render_docx(english_letter, tmp_path / "p.docx", reference="AP/2026/ABC123")
        footers = [
            p.text for s in Document(str(path)).sections for p in s.footer.paragraphs
        ]
        assert any("AP/2026/ABC123" in t for t in footers)

    def test_runs_carry_a_tamil_capable_font_on_every_face(self, tmp_path, tamil_letter):
        """python-docx sets only the Latin face by default. Without `cs` and
        `eastAsia`, Tamil renders as boxes on the machine that opens the file."""
        from docx.oxml.ns import qn

        path = render_docx(tamil_letter, tmp_path / "ta.docx")
        checked = 0
        for paragraph in Document(str(path)).paragraphs:
            for run in paragraph.runs:
                if not run.text.strip():
                    continue
                rfonts = run._element.rPr.find(qn("w:rFonts"))
                assert rfonts is not None
                for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                    assert rfonts.get(qn(attr)), attr
                checked += 1
        assert checked > 10, "the document was not empty"

    def test_extraction_sees_headers_footers_and_tables(self, tmp_path, english_letter):
        path = render_docx(english_letter, tmp_path / "p.docx", reference="REF/1")
        assert "REF/1" in extract_docx_text(path)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


class TestPdfEngineSelection:
    def test_libreoffice_is_the_default(self):
        """A server must never fall back to Office automation by accident.

        Asserted against the declared default rather than a constructed
        `Settings`, because the test environment sets PDF_ENGINE in the
        environment and would mask the thing being checked."""
        assert Settings.model_fields["pdf_engine"].default == "libreoffice"

    def test_off_reports_docx_only(self):
        ok, note = pdf_available(_settings(pdf_engine="off"))
        assert ok is False
        assert "switched off" in note

    def test_a_missing_converter_is_reported_not_raised(self):
        ok, note = pdf_available(_settings(pdf_engine="libreoffice", soffice_path="no-such-binary"))
        assert ok is False
        assert "LibreOffice" in note

    def test_word_is_not_used_unless_asked_for(self):
        """On a machine with Word but no LibreOffice, the default engine must
        still decline — and say why, so the operator is not left guessing."""
        from app.services import render as render_module

        if not render_module._word_available():
            pytest.skip("Word is not installed on this machine")
        ok, note = pdf_available(_settings(pdf_engine="libreoffice", soffice_path="no-such-binary"))
        assert ok is False
        assert "not used unless" in note

    def test_word_can_be_chosen_explicitly_for_development(self):
        from app.services import render as render_module

        if not render_module._word_available():
            pytest.skip("Word is not installed on this machine")
        ok, note = pdf_available(_settings(pdf_engine="word"))
        assert ok is True
        assert "libreoffice" in note.lower()

    def test_word_produces_a_pdf_but_is_not_reported_production_ready(self):
        """Two questions, and collapsing them is how a demonstration gets
        commissioned as a deployment.

        A workstation with Word CAN produce a PDF, so reporting "no PDF" would
        be false. But Word automation means an interactive Office install, one
        document at a time, and a COM process that can hang — so no department
        server may be signed off on the strength of it.
        """
        from app.services import render as render_module
        from app.services.render import pdf_status

        if not render_module._word_available():
            pytest.skip("Word is not installed on this machine")
        report = pdf_status(_settings(pdf_engine="word"))
        assert report["available"] is True
        assert report["production_ready"] is False
        assert report["engine"] == "word"

    def test_libreoffice_is_the_only_engine_that_can_be_production_ready(
            self, monkeypatch):
        """It is the only candidate — but being installed is not enough.
        `TestProductionReadinessIsEarned` covers what actually unlocks it."""
        from app.services.render import pdf_status

        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/soffice")
        report = pdf_status(_settings(pdf_engine="libreoffice"))

        assert report["available"] is True
        assert report["engine"] == "libreoffice"
        # Present, unverified: it can convert, but nothing has checked that it
        # renders Tamil or keeps A4 on this machine.
        assert report["production_ready"] is False
        assert report["verification"]["reason"] == "not run"

    def test_nothing_installed_is_not_production_ready(self, monkeypatch):
        from app.services import render as render_module
        from app.services.render import pdf_status

        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(render_module, "_word_available", lambda: False)
        report = pdf_status(_settings(pdf_engine="auto"))
        assert report["available"] is False
        assert report["production_ready"] is False
        assert report["engine"] is None


class TestPdfDegradation:
    async def test_render_pdf_returns_a_reason_rather_than_raising(self, tmp_path,
                                                                   english_letter):
        path = render_docx(english_letter, tmp_path / "p.docx")
        pdf, error = await render_pdf(path, _settings(pdf_engine="off"))
        assert pdf is None
        assert error and "switched off" in error

    async def test_a_missing_converter_still_produces_the_petition(self, chat, answers):
        """The DOCX is a complete, usable document. A missing PDF converter
        degrades the result; it must not fail the petition."""
        c = chat()
        await c.answer_all(answers)
        state = await c.say("yes")

        assert state["status"] == "ready"
        assert state["document"]["docx"]
        assert state["document"]["pdf"] is None
        assert any("Word document" in w for w in state["warnings"]), state["warnings"]

    async def test_the_warning_is_localised(self, chat, tamil_answers):
        c = chat("ta")
        await c.answer_all(tamil_answers)
        state = await c.say("ஆம்")
        assert any("PDF" in w and "ஆவணம்" in w for w in state["warnings"]), state["warnings"]

    async def test_the_pdf_url_is_absent_when_no_pdf_exists(self, chat, answers):
        from app.api.views import session_view

        c = chat()
        await c.answer_all(answers)
        await c.say("yes")
        view = session_view(c.state)
        assert view["document"]["pdf_url"] is None
        assert view["document"]["docx_url"].endswith("/document.docx")


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


class TestVerification:
    async def test_it_checks_every_required_value(self, chat, answers):
        c = chat()
        await c.answer_all(answers)
        state = await c.say("yes")
        assert state["verification"]["checked"] == len(answers)
        assert state["verification"]["missing_values"] == []
        assert state["verification"]["bytes"] > 0

    async def test_a_document_missing_a_value_is_withheld(self, chat, answers, monkeypatch):
        """The last deterministic gate. If the file does not contain what the
        citizen confirmed, it is not handed over."""
        import app.graph.nodes as nodes

        real = nodes.render_service.extract_docx_text
        monkeypatch.setattr(
            nodes.render_service, "extract_docx_text",
            lambda path: real(path).replace("2345 6789 0124", "XXXX XXXX XXXX"),
        )
        c = chat()
        await c.answer_all(answers)
        state = await c.say("yes")

        assert state["status"] == "failed"
        assert state["verification"]["ok"] is False
        assert state["verification"]["missing_values"] == ["aadhaar"]
        assert "held back" in state["reply"]

    async def test_an_unreadable_document_fails_closed(self, chat, answers, monkeypatch):
        import app.graph.nodes as nodes

        def explode(path):
            raise OSError("disk gone")

        monkeypatch.setattr(nodes.render_service, "extract_docx_text", explode)
        c = chat()
        await c.answer_all(answers)
        state = await c.say("yes")
        assert state["status"] == "failed"
        assert state["verification"]["ok"] is False

    async def test_a_withheld_document_is_not_downloadable(self, chat, answers, monkeypatch):
        import app.graph.nodes as nodes
        from app.api.views import session_view

        monkeypatch.setattr(
            nodes.render_service, "extract_docx_text", lambda path: "nothing useful"
        )
        c = chat()
        await c.answer_all(answers)
        await c.say("yes")
        assert session_view(c.state)["document"] is None


class TestRepresentation:
    """The developed section. It STATES the complaint and then develops it.

    It used to sit after the citizen's own words, which were printed verbatim
    in a paragraph of their own. That paragraph is gone from the ordinary
    petition: a citizen speaks in the grammar of speech, sometimes in a few
    words, sometimes in a different language from the letter, and pasting that
    between two formal paragraphs read as a mistake rather than as evidence.
    The representation carries the account now — faithfully, in official
    language, adding nothing that was not said.
    """

    def test_it_sits_between_the_opening_and_the_prayer(self, fields):
        text = build_letter_text(
            template=the_template(), fields=fields, language="en",
            composition=Composition(
                introduction="I am a resident of the address given above.",
                background="The road is unsafe after dark for those who must walk along it.",
                request="I request that the light be restored.",
            ),
            session_id="abc-123",
        )
        opening = text.index("I am a resident of the address given above.")
        representation = text.index("The road is unsafe after dark")
        prayer = text.index("I request that the light be restored.")
        assert opening < representation < prayer

    def test_the_raw_words_are_not_printed_as_well(self, fields, answers):
        """The matter is stated once. Printing the citizen's own phrasing too
        put the same complaint in the letter twice — once properly, and once as
        a fragment in whatever words it happened to be spoken in."""
        text = build_letter_text(
            template=the_template(), fields=fields, language="en",
            composition=Composition(
                background="The road is unsafe after dark for those who must walk along it.",
                request="I request that the light be restored.",
            ),
            session_id="abc-123",
        )

        assert answers["grievance"].splitlines()[0] not in text

    def test_with_no_account_the_citizens_own_words_are_the_account(self, fields, answers):
        """`background` has no standard wording behind it. With no model there
        is nothing to state the complaint WITH, and a petition that names no
        problem is not a petition — so the citizen's own account is printed."""
        text = build_letter_text(
            template=the_template(), fields=fields, language="en",
            composition=None, session_id="abc-123",
        )

        assert answers["grievance"].splitlines()[0] in text

    def test_a_partial_answer_counts_as_no_account(self, fields, answers):
        """A model that returned a subject but no representation has said
        nothing about the matter. The citizen's words still have to carry it."""
        text = build_letter_text(
            template=the_template(), fields=fields, language="en",
            composition=Composition(subject="A street light", background=None),
            session_id="abc-123",
        )

        assert answers["grievance"].splitlines()[0] in text

    def test_a_petition_without_a_model_simply_omits_it(self, english_letter):
        """Developing an issue means having read the issue. With no model there
        is nothing to develop from, and the letter is complete without it."""
        standard = fallback_composition(the_template(), {}, "en")
        assert standard.background is None
        assert "Respected Sir / Madam," in english_letter
        assert "Thanking you," in english_letter


class TestProductionReadinessIsEarned:
    """`pdf_production_ready` is not "soffice is on PATH".

    A binary being present says nothing about whether it renders Tamil, keeps
    A4, survives four petitions at once, or cleans up after itself — and every
    one of those fails in front of a citizen rather than at startup. So the flag
    is gated on `scripts/verify_pdf.py` having put a real petition through this
    machine's converter, and the stamp is tied to the converter's version so an
    upgrade invalidates it instead of riding along.
    """

    FINGERPRINT = "soffice:LibreOffice 7.6.7.2"

    @pytest.fixture
    def libreoffice(self, monkeypatch, tmp_path):
        """A machine that has LibreOffice, without installing it."""
        from app.services import render as render_module

        monkeypatch.setattr(render_module.shutil, "which",
                            lambda name: "/usr/bin/soffice")
        monkeypatch.setattr(render_module, "engine_fingerprint",
                            lambda settings=None: self.FINGERPRINT)
        return _settings(pdf_engine="libreoffice", data_dir=tmp_path)

    def _stamp(self, settings, **payload):
        import json

        from app.services.render import STAMP_NAME

        path = settings.data_dir / STAMP_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_present_but_never_verified_is_not_production_ready(self, libreoffice):
        from app.services.render import pdf_status

        report = pdf_status(libreoffice)

        assert report["available"] is True, "it can still make a PDF"
        assert report["production_ready"] is False
        assert "verify_pdf" in report["verification"]["note"]

    def test_a_failed_verification_is_not_production_ready(self, libreoffice):
        from app.services.render import pdf_status

        self._stamp(libreoffice, passed=False, fingerprint=self.FINGERPRINT,
                    checks=[{"name": "3  Tamil rendering", "ok": False}])

        report = pdf_status(libreoffice)
        assert report["production_ready"] is False
        assert "Tamil" in report["verification"]["note"]

    def test_a_passed_verification_unlocks_it(self, libreoffice):
        from app.services.render import pdf_status

        self._stamp(libreoffice, passed=True, fingerprint=self.FINGERPRINT,
                    verified_at="2026-09-16T14:00:00+00:00",
                    checks=[{"name": f"c{i}", "ok": True} for i in range(9)])

        report = pdf_status(libreoffice)
        assert report["production_ready"] is True
        assert report["verification"]["checks"] == 9

    def test_upgrading_the_converter_invalidates_the_pass(self, libreoffice,
                                                          monkeypatch):
        """A rendering regression between versions would otherwise ride along
        behind a stamp from the version before it."""
        from app.services import render as render_module
        from app.services.render import pdf_status

        self._stamp(libreoffice, passed=True, fingerprint=self.FINGERPRINT,
                    checks=[{"name": "c", "ok": True}])
        monkeypatch.setattr(render_module, "engine_fingerprint",
                            lambda settings=None: "soffice:LibreOffice 25.2.1.1")

        report = pdf_status(libreoffice)
        assert report["production_ready"] is False
        assert "changed since it was verified" in report["verification"]["note"]

    def test_an_unreadable_stamp_fails_closed(self, libreoffice):
        from app.services.render import STAMP_NAME, pdf_status

        path = libreoffice.data_dir / STAMP_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")

        assert pdf_status(libreoffice)["production_ready"] is False

    def test_word_can_never_be_verified_for_production(self, monkeypatch, tmp_path):
        """Whatever a stamp says. Word automation is not a server dependency."""
        from app.services import render as render_module
        from app.services.render import pdf_status

        monkeypatch.setattr(render_module.shutil, "which", lambda name: None)
        monkeypatch.setattr(render_module, "_word_available", lambda: True)
        settings = _settings(pdf_engine="word", data_dir=tmp_path)
        self._stamp(settings, passed=True, fingerprint="anything",
                    checks=[{"name": "c", "ok": True}])

        report = pdf_status(settings)
        assert report["available"] is True
        assert report["production_ready"] is False


class TestTheDateAndPlaceAtTheTop:
    """Where a letter carries them, and printed flush right.

    They used to sit under the signature. Moving them is a format change, and
    the format is the thing an officer recognises a petition by, so both the
    position and the alignment are held here.
    """

    @staticmethod
    def _letter(**over):
        from datetime import date

        from app.domain.letter import build_letter_text
        from app.domain.templates import the_template

        fields = {"applicant_name": "Ravi Kumar", "age": 45, "mobile": "9876543210",
                  "address": "12 Gandhi Street, Peelamedu, Coimbatore",
                  "aadhaar": "234567890124",
                  "grievance": "The drain has been blocked for a month."}
        fields.update(over.pop("fields", {}))
        return build_letter_text(
            template=the_template(), fields=fields, language=over.pop("language", "en"),
            composition=None, session_id="abc-123", when=date(2026, 9, 17), **over)

    def test_they_lead_the_letter(self):
        lines = self._letter().splitlines()

        assert lines[0] == "Date: 17-09-2026"
        assert lines[1] == "Place: Coimbatore"
        assert lines[2] == ""
        assert lines[3] == "From,"

    def test_they_are_no_longer_under_the_signature(self):
        tail = self._letter().splitlines()[-8:]

        assert not [line for line in tail if line.startswith(("Date:", "Place:"))]

    def test_a_place_that_cannot_be_derived_is_left_out_rather_than_guessed(self):
        """A wrong town on a petition is worse than a missing one. The citizen
        was never asked for the place separately, so it comes from the address
        they did give, and only when that address has parts to take it from."""
        lines = self._letter(fields={"address": "theni"}).splitlines()

        assert lines[0].startswith("Date:")
        assert not lines[1].startswith("Place:"), lines[1]
        assert lines[1] == ""

    def test_the_tamil_letter_carries_tamil_labels_at_the_top(self):
        from app.domain.letter import LABELS

        lines = self._letter(language="ta").splitlines()

        assert lines[0].startswith(LABELS["date"]["ta"])
        assert "Date:" not in lines[0]


class TestFindingTheOpeningBlock:
    """By shape and position, never by the words "Date" and "Place".

    Those words are English. A petition translated into Hindi has to keep its
    opening block on the right, and a letter whose block has been deleted by
    hand must not have its sender details flung to the right margin instead.
    """

    @staticmethod
    def _count(lines):
        from app.services.render import opening_block

        return opening_block(lines)

    def test_an_english_opening_block(self):
        assert self._count(["Date: 17-09-2026", "Place: Coimbatore", "", "From,"]) == 2

    def test_a_tamil_one(self):
        assert self._count(["\u0ba8\u0bbe\u0bb3\u0bcd: 17-09-2026",
                            "\u0b87\u0b9f\u0bae\u0bcd: \u0ba4\u0bc7\u0ba9\u0bbf",
                            "", "\u0b85\u0ba9\u0bc1\u0baa\u0bcd\u0baa\u0bc1\u0ba8\u0bb0\u0bcd,"]) == 2

    def test_a_hindi_one_even_though_no_hindi_word_is_listed_anywhere(self):
        assert self._count(["\u0926\u093f\u0928\u093e\u0902\u0915: 17-09-2026",
                            "\u0938\u094d\u0925\u093e\u0928: \u0925\u0947\u0928\u0940",
                            "", "From,"]) == 2

    def test_a_letter_that_opens_with_the_sender_has_no_opening_block(self):
        """The failure this prevents is the loud one: every sender line pushed
        to the right margin on a petition that simply had no dateline."""
        assert self._count(["From,", "    Ravi Kumar", "    12 Gandhi Street", "", "To,"]) == 0

    def test_a_long_run_is_not_an_opening_block(self):
        assert self._count(["A: 1", "B: 2", "C: 3", "D: 4", "", "x"]) == 0

    def test_nothing_at_all(self):
        assert self._count([]) == 0
        assert self._count(["", "", "From,"]) == 0


class TestItIsPrintedOnTheRight:
    def test_the_opening_block_is_right_aligned_and_nothing_else_is(self, tmp_path):
        import re
        import zipfile

        from app.services.render import render_docx

        text = ("Date: 17-09-2026" + chr(10) + "Place: Coimbatore" + chr(10) + chr(10)
                + "From," + chr(10) + "    Ravi Kumar" + chr(10) + chr(10)
                + "To," + chr(10) + "    The District Collector" + chr(10) + chr(10)
                + "Respected Sir / Madam," + chr(10) + chr(10)
                + "Subject: A blocked drain." + chr(10) + chr(10)
                + "The drain has been blocked for a month." + chr(10))
        out = tmp_path / "petition.docx"
        render_docx(text, out, reference="AP/2026/ABCDEF", title="Citizen Petition")

        with zipfile.ZipFile(out) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        right = [
            "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", paragraph))
            for paragraph in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
            if 'w:val="right"' in paragraph
        ]

        assert right == ["Date: 17-09-2026", "Place: Coimbatore"], right


class TestALongGrievanceSurvivesToTheDocument:
    """A grievance dictated over two minutes is about two thousand
    characters. The sentence that gets cut is the last one, and the last one
    is where the citizen says what they want done — so the whole of it has to
    reach the page, not most of it.

    The voice layer's own tests prove the transcript is assembled intact.
    These prove the document does not then quietly shorten it.
    """

    @staticmethod
    def _long_grievance() -> str:
        return " ".join(
            f"Point {i}: the water supply to our street failed again and the "
            f"office was informed on the {i}th."
            for i in range(1, 21))

    def test_the_letter_carries_every_word(self):
        from app.domain.letter import build_letter_text
        from app.domain.templates import the_template

        grievance = self._long_grievance()
        assert len(grievance) > 1500, "the fixture stopped being long"
        text = build_letter_text(
            template=the_template(),
            fields={"applicant_name": "Ravi Kumar", "age": 45,
                    "mobile": "9344174752", "aadhaar": "234567890124",
                    "address": "12 Gandhi Street, Coimbatore",
                    "grievance": grievance},
            language="en", composition=None, session_id="abc-123")

        assert grievance in text
        assert "Point 20:" in text, "the end of the complaint was dropped"
        assert "Point 1:" in text

    def test_the_verifier_would_catch_it_being_shortened(self):
        """The check that runs against the generated DOCX asks for the field
        VERBATIM, so a document that truncated it would fail verification
        rather than being handed over quietly."""
        from app.domain.letter import verification_targets
        from app.domain.templates import the_template

        grievance = self._long_grievance()
        targets = verification_targets(
            the_template(),
            {"applicant_name": "Ravi Kumar", "age": 45, "mobile": "9344174752",
             "aadhaar": "234567890124", "address": "12 Gandhi Street, Coimbatore",
             "grievance": grievance},
            "en")

        assert targets.get("grievance") == grievance

    def test_a_long_tamil_grievance_is_kept_whole(self):
        from app.domain.letter import build_letter_text
        from app.domain.templates import the_template

        grievance = " ".join(
            f"{i}. எங்கள் தெருவில் தண்ணீர் வரவில்லை, அலுவலகத்தில் தெரிவித்தோம்."
            for i in range(1, 21))
        text = build_letter_text(
            template=the_template(),
            fields={"applicant_name": "ரவி குமார்", "age": 45,
                    "mobile": "9344174752", "aadhaar": "234567890124",
                    "address": "12 காந்தி தெரு, கோயம்புத்தூர்",
                    "grievance": grievance},
            language="ta", composition=None, session_id="abc-123")

        assert grievance in text
        assert text.count("எங்கள் தெருவில்") == 20

    def test_the_word_document_contains_the_whole_complaint(self, tmp_path):
        """Not the letter text — the actual .docx a citizen downloads.

        Read back out of `word/document.xml`, because a renderer that split,
        dropped or reflowed a long paragraph would still have produced a
        plausible-looking letter string on the way in.
        """
        import re
        import zipfile

        from app.domain.letter import build_letter_text
        from app.domain.templates import the_template
        from app.services.render import render_docx

        grievance = self._long_grievance()
        text = build_letter_text(
            template=the_template(),
            fields={"applicant_name": "Ravi Kumar", "age": 45,
                    "mobile": "9344174752", "aadhaar": "234567890124",
                    "address": "12 Gandhi Street, Coimbatore",
                    "grievance": grievance},
            language="en", composition=None, session_id="abc-123")
        path = render_docx(text, tmp_path / "petition.docx")

        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        # Runs can be split anywhere by the writer, so compare the visible
        # characters rather than the markup.
        visible = re.sub(r"<[^>]+>", "", xml)

        assert grievance in visible, "the complaint was altered on the way in"
        assert "Point 20:" in visible, "the end of the complaint is missing"
