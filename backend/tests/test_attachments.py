"""Attachments, previous petitions, and what the petition is allowed to claim.

The rule every test here circles is one sentence: **the petition may state only
what was actually supplied and actually confirmed.** Two failures follow from
breaking it, and both land on the citizen rather than on us —

  * an enclosure list naming documents that are not in the envelope makes the
    citizen look as though they withheld them;
  * an acknowledgement number that does not resolve sends a receiving officer
    looking for a file nobody ever opened.

So most of what is asserted below is silence: the number that must NOT appear,
the section that must NOT be printed, the field that must NOT be overwritten.

Everything here is TEST DATA. The acknowledgement slips are invented, they are
written to a temp directory, and nothing in this file touches the government
knowledge corpus — which is the point of `TestSeparation`.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.rest import router
from app.domain import attachments as rules
from app.domain import prior_petition
from app.graph.workflow import Workflow
from app.services import attachment_store

# TEST DATA — an invented acknowledgement slip. No real office issued this.
SLIP = """OFFICE OF THE DISTRICT COLLECTOR, THENI
Revenue Department

ACKNOWLEDGEMENT
Received your petition dated 12-08-2026.
Acknowledgement No.: TNI/2026/98765
Subject: Non-supply of drinking water at Vadaputhupatty
Status: Pending
Form No. TN/RV/07
"""

TAMIL_SLIP = """மாவட்ட ஆட்சியர் அலுவலகம், தேனி
வருவாய்த் துறை

ஒப்புகைச் சீட்டு
தாங்கள் 12-08-2026 அன்று அளித்த மனு பெறப்பட்டது.
ஒப்புகை எண்: TNI/2026/54321
பொருள்: வடபுதுப்பட்டி குடிநீர் தட்டுப்பாடு
"""


def pdf_bytes(text: str) -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((55, 80), text, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64       # a valid header, no readable text


@pytest.fixture
def api_workflow(graph):
    return Workflow(graph, None)


@pytest.fixture
async def api(api_workflow):
    app = FastAPI()
    app.include_router(router)
    app.state.workflow = api_workflow
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _collected(api, answers, language: str = "en") -> str:
    """A session with every detail in, sitting at the attachment question."""
    session = (await api.post("/api/sessions", json={"language": language})).json()
    sid = session["session_id"]
    for name, value in answers.items():
        await api.post(f"/api/sessions/{sid}/field", json={"name": name, "value": value})
    return sid


async def _upload(api, sid, name, content, content_type="application/pdf", **data):
    return await api.post(f"/api/sessions/{sid}/attachments",
                          files={"file": (name, content, content_type)}, data=data)


async def _generate(api, sid) -> dict:
    await api.post(f"/api/sessions/{sid}/attachments/done")
    return (await api.post(f"/api/sessions/{sid}/confirm")).json()


# --------------------------------------------------------------------------- #
# 1. The offer
# --------------------------------------------------------------------------- #

class TestTheOffer:
    async def test_it_is_asked_once_after_the_grievance(self, api, answers):
        sid = await _collected(api, answers)
        state = (await api.get(f"/api/sessions/{sid}")).json()

        assert state["status"] == "attachments"
        assert state["attachments"]["offered"] is True
        assert "attachment" in state["attachments"]["question"].lower()
        # Not the read-back, and certainly not a document.
        assert state["document"] is None

    async def test_the_tamil_wording_is_the_specified_one(self, api, tamil_answers):
        sid = await _collected(api, tamil_answers, language="ta")
        state = (await api.get(f"/api/sessions/{sid}")).json()

        assert "இணைப்புகளைச் சேர்க்க விரும்புகிறீர்களா" in state["attachments"]["question"]
        assert state["attachments"]["add_label"] == "இணைப்புகளைச் சேர்"

    async def test_the_suggestions_are_labelled_as_suggestions(self, api, answers):
        sid = await _collected(api, answers)
        offer = (await api.get(f"/api/sessions/{sid}")).json()["attachments"]

        assert len(offer["suggested"]) == 3
        assert "Aadhaar" in offer["suggested"][0]
        assert "suggestion" in offer["suggestion_note"].lower()
        # Nothing is required unless a retrieved OFFICIAL source says so, and
        # with an empty corpus nothing can.
        assert offer["required"] == []

    async def test_continuing_advances_to_the_read_back(self, api, answers):
        sid = await _collected(api, answers)
        state = (await api.post(f"/api/sessions/{sid}/attachments/done")).json()

        assert state["status"] == "confirming"
        assert state["attachments"]["done"] is True

    async def test_the_question_is_not_asked_again_every_turn(self, api, answers):
        sid = await _collected(api, answers)
        await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.get(f"/api/sessions/{sid}")).json()
        assert state["status"] == "confirming"

        # A wrong detail sends the citizen back; fixing it must not re-ask.
        await api.post(f"/api/sessions/{sid}/field",
                       json={"name": "age", "value": "24"})
        state = (await api.get(f"/api/sessions/{sid}")).json()
        assert state["status"] != "attachments"

    async def test_changing_the_grievance_reopens_it(self, chat, answers):
        """What is worth enclosing depends on what the complaint is about."""
        citizen = chat()
        await citizen.answer_all(answers)
        assert citizen.status == "confirming"

        await citizen.say("the grievance is wrong")
        await citizen.say("Actually the street light has been broken for a year "
                          "and the pole is leaning over the footpath.")

        assert citizen.status == "attachments"


class TestAnsweringInWords:
    """The voice path. Same graph, same question, no buttons."""

    @pytest.mark.parametrize("said", [
        "no", "no documents", "I have no attachments", "continue with these details",
        "தொடரவும்", "இணைப்பு ஏதுமில்லை",
    ])
    async def test_declining_advances(self, chat, answers, said):
        citizen = chat()
        await citizen.answer_all(answers, attachments=None)
        assert citizen.status == "attachments"

        await citizen.say(said)
        assert citizen.status == "confirming", said

    @pytest.mark.parametrize("said", [
        "yes", "I have the acknowledgement slip", "I want to attach my aadhaar copy",
        "ஒப்புகைச் சீட்டு என்னிடம் உள்ளது",
    ])
    async def test_accepting_waits_rather_than_advancing(self, chat, answers, said):
        """"Yes, I have the receipt" is not the receipt."""
        citizen = chat()
        await citizen.answer_all(answers, attachments=None)

        await citizen.say(said)
        assert citizen.status == "attachments", said

    async def test_an_unrecognised_answer_leaves_the_question_standing(
            self, chat, answers):
        """Guessing "no" here throws away the slip in their hand."""
        citizen = chat()
        await citizen.answer_all(answers, attachments=None)

        await citizen.say("what is the weather like")
        assert citizen.status == "attachments"


# --------------------------------------------------------------------------- #
# 2. Files
# --------------------------------------------------------------------------- #

class TestUploads:
    async def test_a_pdf_is_accepted_and_read(self, api, answers):
        sid = await _collected(api, answers)
        response = await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))

        assert response.status_code == 201
        item = response.json()["attachments"]["items"][0]
        assert item["kind"] == "acknowledgement"
        assert item["needs_confirmation"] is True
        values = {f["name"]: f["value"] for f in item["fields"]}
        assert values["reference_number"] == "TNI/2026/98765"
        assert values["submitted_on"] == "2026-08-12"

    async def test_every_extracted_value_carries_the_words_it_came_from(
            self, api, answers):
        """A citizen cannot meaningfully confirm a number they cannot trace."""
        sid = await _collected(api, answers)
        response = await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))

        for field in response.json()["attachments"]["items"][0]["fields"]:
            assert field["evidence"], field["name"]
            assert 0.0 < field["confidence"] <= 1.0

    async def test_an_executable_renamed_as_a_pdf_is_refused(self, api, answers):
        sid = await _collected(api, answers)
        response = await _upload(api, sid, "invoice.pdf", b"MZ\x90\x00 this is a PE")

        assert response.status_code == 400
        assert "does not look like" in response.json()["detail"]

    @pytest.mark.parametrize("name,content,content_type", [
        ("run.exe", b"MZ\x90\x00", "application/x-msdownload"),
        ("shell.svg", b"<svg onload=alert(1)>", "image/svg+xml"),
        ("empty.pdf", b"", "application/pdf"),
    ])
    async def test_what_cannot_be_attached(self, api, answers, name, content,
                                           content_type):
        sid = await _collected(api, answers)
        response = await _upload(api, sid, name, content, content_type)
        assert response.status_code == 400

    async def test_a_traversing_filename_cannot_escape_the_session(self, api, answers):
        sid = await _collected(api, answers)
        response = await _upload(api, sid, "../../../../evil.pdf", pdf_bytes(SLIP))

        assert response.status_code == 201
        item = response.json()["attachments"]["items"][0]
        assert ".." not in item["filename"]
        directory = attachment_store.session_dir(sid)
        assert list(directory.glob("*")), "stored inside the session directory"

    async def test_an_unreadable_photograph_is_still_attached(self, api, answers):
        """It was brought for a reason. It simply carries no extracted values."""
        sid = await _collected(api, answers)
        response = await _upload(api, sid, "street.png", PNG, "image/png")

        assert response.status_code == 201
        item = response.json()["attachments"]["items"][0]
        assert item["readable"] is False
        assert item["reason"]
        assert item["fields"] == []

    async def test_removing_one_takes_it_off_the_petition(self, api, answers):
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()
        aid = state["attachments"]["items"][0]["attachment_id"]

        state = (await api.delete(f"/api/sessions/{sid}/attachments/{aid}")).json()

        assert state["attachments"]["items"] == []
        state = await _generate(api, sid)
        assert "Enclosures" not in (state["letter_text"] or "")


# --------------------------------------------------------------------------- #
# 3. Nothing is used until the citizen confirms it
# --------------------------------------------------------------------------- #

class TestConfirmation:
    async def test_an_unconfirmed_extraction_is_never_cited(self, api, answers):
        sid = await _collected(api, answers)
        await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))

        state = await _generate(api, sid)
        letter = state["letter_text"] or ""

        # In the envelope, so it is listed.
        assert "Enclosures" in letter
        # Not confirmed, so nothing it says is claimed.
        assert "TNI/2026/98765" not in letter
        assert "previously submitted" not in letter

    async def test_a_confirmed_extraction_is_cited_exactly(self, api, answers):
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()
        aid = state["attachments"]["items"][0]["attachment_id"]

        await api.post(f"/api/sessions/{sid}/attachments/{aid}/confirm",
                       json={"confirmed": True, "values": {}})
        state = await _generate(api, sid)
        letter = state["letter_text"] or ""

        assert "TNI/2026/98765" in letter
        assert "12-08-2026" in letter
        assert "previously submitted" in letter

    async def test_a_rejected_extraction_is_dropped(self, api, answers):
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()
        aid = state["attachments"]["items"][0]["attachment_id"]

        await api.post(f"/api/sessions/{sid}/attachments/{aid}/confirm",
                       json={"confirmed": False})
        state = await _generate(api, sid)

        assert "TNI/2026/98765" not in (state["letter_text"] or "")
        assert "Enclosures" in (state["letter_text"] or "")

    async def test_a_citizen_correction_beats_what_was_read(self, api, answers):
        """A citizen reading their own slip is a better source than a regex
        reading a photograph of it."""
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()
        aid = state["attachments"]["items"][0]["attachment_id"]

        await api.post(
            f"/api/sessions/{sid}/attachments/{aid}/confirm",
            json={"confirmed": True, "values": {"reference_number": "TNI/2026/11111"}})
        state = await _generate(api, sid)
        letter = state["letter_text"] or ""

        assert "TNI/2026/11111" in letter
        assert "TNI/2026/98765" not in letter

    async def test_clearing_a_value_removes_it_from_the_claim(self, api, answers):
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()
        aid = state["attachments"]["items"][0]["attachment_id"]

        await api.post(
            f"/api/sessions/{sid}/attachments/{aid}/confirm",
            json={"confirmed": True, "values": {"submitted_on": ""}})
        state = await _generate(api, sid)
        letter = state["letter_text"] or ""

        assert "TNI/2026/98765" in letter
        assert "12-08-2026" not in letter

    async def test_an_unrelated_attachment_produces_no_claim(self, api, answers):
        """A photograph of a broken street light is evidence of nothing citable."""
        sid = await _collected(api, answers)
        await _upload(api, sid, "street.png", PNG, "image/png")

        state = await _generate(api, sid)
        letter = state["letter_text"] or ""

        assert "Enclosures" in letter
        assert "previously submitted" not in letter
        assert "acknowledgement number" not in letter.lower()


# --------------------------------------------------------------------------- #
# 4. Current information always wins
# --------------------------------------------------------------------------- #

class TestPrecedence:
    async def test_an_attachment_never_overwrites_a_confirmed_detail(
            self, api, answers):
        """The slip names a different subject and a different department. The
        record the citizen gave is untouched by all of it."""
        sid = await _collected(api, answers)
        before = {f["name"]: f["value"]
                  for f in (await api.get(f"/api/sessions/{sid}")).json()["collected"]}

        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()
        aid = state["attachments"]["items"][0]["attachment_id"]
        await api.post(f"/api/sessions/{sid}/attachments/{aid}/confirm",
                       json={"confirmed": True, "values": {}})

        after = {f["name"]: f["value"]
                 for f in (await api.get(f"/api/sessions/{sid}")).json()["collected"]}
        assert after == before

    async def test_the_grievance_stays_verbatim_beside_a_prior_reference(
            self, api, answers):
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()
        aid = state["attachments"]["items"][0]["attachment_id"]
        await api.post(f"/api/sessions/{sid}/attachments/{aid}/confirm",
                       json={"confirmed": True, "values": {}})

        state = await _generate(api, sid)
        assert answers["grievance"] in state["letter_text"]

    async def test_an_aadhaar_card_is_not_held_as_extracted_text(self, api, answers):
        """The number is already a validated field. A second copy in session
        state is a second place it can leak from."""
        sid = await _collected(api, answers)
        response = await _upload(api, sid, "aadhaar.pdf",
                                 pdf_bytes("Aadhaar 2345 6789 0124 Government of India"),
                                 kind="aadhaar")

        item = response.json()["attachments"]["items"][0]
        assert item["kind"] == "aadhaar"
        assert item["fields"] == []
        assert item["needs_confirmation"] is False


# --------------------------------------------------------------------------- #
# 5. What the petition prints
# --------------------------------------------------------------------------- #

class TestTheEnclosureList:
    async def test_no_attachments_means_no_enclosure_section(self, api, answers):
        """The template's list used to print on every petition ever produced."""
        sid = await _collected(api, answers)
        state = await _generate(api, sid)
        letter = state["letter_text"] or ""

        assert "Enclosures" not in letter
        assert "Copy of Aadhaar card" not in letter
        assert "Copy of proof of residence" not in letter

    async def test_one_attachment_means_one_line(self, api, answers):
        sid = await _collected(api, answers)
        await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))

        letter = (await _generate(api, sid))["letter_text"]
        body = letter.split("Enclosures:")[1]

        assert "1. Acknowledgement receipt" in body
        assert "2." not in body.split("\n\n")[0]

    async def test_the_tamil_petition_lists_them_in_tamil(self, api, tamil_answers):
        # A .txt rather than a PDF: PyMuPDF's built-in fonts cannot draw Tamil,
        # so a PDF built here would carry no Tamil to extract. The path under
        # test is the Tamil handling, not PDF font embedding.
        sid = await _collected(api, tamil_answers, language="ta")
        await _upload(api, sid, "ack.txt", TAMIL_SLIP.encode("utf-8"), "text/plain")

        letter = (await _generate(api, sid))["letter_text"]

        assert "இணைப்புகள்:" in letter
        assert "ஒப்புகைச் சீட்டு" in letter

    async def test_a_tamil_slip_is_read(self, api, tamil_answers):
        sid = await _collected(api, tamil_answers, language="ta")
        response = await _upload(api, sid, "ack.txt",
                                 TAMIL_SLIP.encode("utf-8"), "text/plain")

        values = {f["name"]: f["value"]
                  for f in response.json()["attachments"]["items"][0]["fields"]}
        assert values.get("reference_number") == "TNI/2026/54321"


# --------------------------------------------------------------------------- #
# 6. The two stores stay two stores
# --------------------------------------------------------------------------- #

class TestSeparation:
    async def test_an_attachment_never_reaches_the_knowledge_corpus(
            self, api, answers, tmp_path):
        from app.knowledge.store import KnowledgeStore

        corpus = KnowledgeStore(tmp_path / "k.sqlite", dimension=256, provider="local")
        before = corpus.stats()

        sid = await _collected(api, answers)
        await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))
        await _generate(api, sid)

        after = corpus.stats()
        assert after["documents"] == before["documents"] == 0
        assert after["chunks"] == before["chunks"] == 0

    def test_the_knowledge_layer_has_no_writer_but_ingestion(self):
        """Structural, not behavioural: if a path is ever added, this fails."""
        import ast
        import pathlib

        import app.knowledge as package

        # By import, not by method name: `attachment_store.delete` is a
        # perfectly good call that a name-based check flags, and a check that
        # cries wolf gets deleted by whoever hits it next.
        offenders = []
        root = pathlib.Path(package.__file__).parent.parent
        for path in sorted(root.rglob("*.py")):
            if "knowledge" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                if "KnowledgeStore" in names or any(
                        n.endswith("knowledge.store") for n in names):
                    offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, (
            "the corpus store is reachable from outside the knowledge package: "
            f"{offenders}")

    async def test_attachments_live_under_the_session(self, api, answers):
        sid = await _collected(api, answers)
        await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))

        directory = attachment_store.session_dir(sid)
        assert directory.is_dir()
        assert sid in str(directory)
        assert len(list(directory.glob("*"))) == 1


# --------------------------------------------------------------------------- #
# 7. Reading a previous petition
# --------------------------------------------------------------------------- #

class TestReadingAPriorPetition:
    def test_the_reference_number_beats_a_form_number(self):
        """A page carries several slash-separated codes. The one that matters is
        the one a cue word introduces, not the one that comes first."""
        prior = prior_petition.analyse(SLIP)
        assert prior.reference_number.value == "TNI/2026/98765"

    def test_an_unreadable_document_claims_nothing(self):
        prior = prior_petition.analyse(
            "", readable=False, reason="This is a photograph.")

        assert prior.readable is False
        assert prior.has_anything is False
        assert prior_petition.reference_sentence(prior) == ""

    def test_low_confidence_input_lowers_every_confidence(self):
        clean = prior_petition.analyse(SLIP)
        ocr = prior_petition.analyse(SLIP, low_confidence=True)

        assert ocr.low_confidence is True
        assert ocr.reference_number.confidence < clean.reference_number.confidence

    def test_the_sentence_says_only_what_is_evidenced(self):
        number_only = prior_petition.PriorPetition(
            reference_number=prior_petition.Extracted(value="CBE/2026/1"))
        sentence = prior_petition.reference_sentence(number_only)

        assert "CBE/2026/1" in sentence
        # No date was evidenced, so none is stated.
        assert " on " not in sentence
        # And no claim about what the office did or did not do.
        assert "no reply" not in sentence.lower()

    def test_both_languages_produce_a_sentence(self):
        prior = prior_petition.analyse(SLIP)
        for language in ("en", "ta"):
            assert prior_petition.reference_sentence(prior, language).strip()

    def test_nothing_at_all_produces_no_sentence(self):
        assert prior_petition.reference_sentence(prior_petition.PriorPetition()) == ""


class TestFilenames:
    @pytest.mark.parametrize("given,forbidden", [
        ("../../etc/passwd", ".."),
        ("a/b/c.pdf", "/"),
        ("x\\y\\z.pdf", "\\"),
        ('bad<>:"|?*.pdf', "<"),
    ])
    def test_dangerous_names_are_defused(self, given, forbidden):
        assert forbidden not in rules.sanitise_filename(given)

    def test_a_windows_device_name_is_renamed(self):
        assert rules.sanitise_filename("CON.pdf") != "CON.pdf"
        assert rules.sanitise_filename("LPT1.txt") != "LPT1.txt"

    def test_a_blank_name_still_produces_one(self):
        assert rules.sanitise_filename("") == "attachment"
        assert rules.sanitise_filename("   ...  ") == "attachment"

    def test_tamil_filenames_survive(self):
        assert "ஒப்புகை" in rules.sanitise_filename("ஒப்புகை.pdf")
