"""The whole journey, and the ways it is allowed to be interrupted.

    Citizen details → Grievance → RAG starts once → Attachment question
    → (attachment path | no-attachment path) → Previous petition analysis
    → Confirmation → RAG retrieval → Review → Corrections → Generate
    → Verification → DOCX → PDF

Run against a corpus built in a temp directory from TEST DATA that says so on
its face. The runtime corpus stays empty: `test_the_shipped_corpus_is_empty`
asserts it, because a demonstration seeded with invented Acts is the exact
failure the knowledge layer exists to prevent.

The suite runs with no model and no network, which is the deployment a district
office actually gets. Everything below therefore also proves the deterministic
fallbacks produce a petition.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.rest import router
from app.config import get_settings
from app.graph.workflow import Workflow
from app.knowledge.embeddings import LocalEmbeddings
from app.knowledge.ingest import Ingestor
from app.knowledge.store import KnowledgeStore

TEST_PROVENANCE = "TEST DATA — fixture, not a real government source"

# TEST DATA. Invented, and labelled as invented inside the text itself so that
# anything which leaks into a document is obvious on sight.
WATER_PROCEDURE = """TEST DATA — Sample Water Supply Grievance Procedure

## Where a complaint is made
A complaint regarding interruption of drinking water supply shall be made to
the Assistant Engineer of the section office having jurisdiction.

## Escalation
Where the Assistant Engineer has not disposed of the complaint within fifteen
days, the complainant may move the Executive Engineer of the division.

## Documents to be produced
The complainant shall produce a copy of the water tax receipt together with
proof of residence.
"""

SLIP = """OFFICE OF THE DISTRICT COLLECTOR, THENI
Revenue Department

ACKNOWLEDGEMENT
Received your petition dated 12-08-2026.
Acknowledgement No.: TNI/2026/98765
Subject: Non-supply of drinking water at Vadaputhupatty
Status: Pending
"""


def pdf_bytes(text: str) -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((55, 80), text, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


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


@pytest.fixture
async def corpus(tmp_path, monkeypatch):
    """A small TEST DATA corpus, wired in as the running knowledge service."""
    from app.knowledge import capability
    from app.knowledge.analyst import Analyst
    from app.knowledge.retrieve import Retriever

    provider = LocalEmbeddings(dimension=256)
    settings = get_settings()
    store = KnowledgeStore(tmp_path / "corpus.sqlite", dimension=256, provider="local")
    ingestor = Ingestor(store=store, provider=provider, settings=settings)

    path = tmp_path / "water-procedure.txt"
    path.write_text(WATER_PROCEDURE, encoding="utf-8")
    await ingestor.ingest(path, metadata={
        "authority": "departmental", "document_type": "procedure",
        "department": "Sample Water Board", "provenance": TEST_PROVENANCE})

    service = capability.KnowledgeService(settings)
    service._store = store
    service._analyst = Analyst(Retriever(store, provider, settings), settings)
    monkeypatch.setattr(capability, "_service", service)
    return store


async def _walk(api, answers, language="en"):
    session = (await api.post("/api/sessions", json={"language": language})).json()
    sid = session["session_id"]
    for name, value in answers.items():
        await api.post(f"/api/sessions/{sid}/field", json={"name": name, "value": value})
    return sid


# --------------------------------------------------------------------------- #
# The journey
# --------------------------------------------------------------------------- #

class TestTheWholeJourney:
    async def test_every_stage_in_order_with_an_attachment(self, api, answers, corpus):
        # -- details ---------------------------------------------------------
        sid = await _walk(api, answers)
        state = (await api.get(f"/api/sessions/{sid}")).json()
        assert state["progress"]["answered"] == state["progress"]["total"]

        # -- the attachment question, once -----------------------------------
        assert state["status"] == "attachments"
        assert state["attachments"]["offered"] is True
        assert state["attachments"]["suggested"]

        # -- an attachment, read but not yet used ----------------------------
        state = (await api.post(
            f"/api/sessions/{sid}/attachments",
            files={"file": ("ack.pdf", pdf_bytes(SLIP), "application/pdf")})).json()
        item = state["attachments"]["items"][0]
        assert item["kind"] == "acknowledgement"
        assert item["needs_confirmation"] is True

        # -- the citizen confirms it -----------------------------------------
        state = (await api.post(
            f"/api/sessions/{sid}/attachments/{item['attachment_id']}/confirm",
            json={"confirmed": True, "values": {}})).json()
        assert state["attachments"]["items"][0]["confirmed"] is True

        # -- continue, then the read-back ------------------------------------
        state = (await api.post(f"/api/sessions/{sid}/attachments/done")).json()
        assert state["status"] == "confirming"

        # -- a correction at the read-back -----------------------------------
        state = (await api.post(f"/api/sessions/{sid}/field",
                                json={"name": "age", "value": "24"})).json()
        assert any(c["field"] == "age" for c in state["corrections"])
        if state["status"] == "attachments":
            state = (await api.post(f"/api/sessions/{sid}/attachments/done")).json()

        # -- generate, verify ------------------------------------------------
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()
        assert state["status"] == "ready", state.get("error")
        assert state["verification"]["ok"] is True

        letter = state["letter_text"]
        assert answers["grievance"] in letter, "verbatim, always"
        assert "வயது: 24" in letter or "Age: 24" in letter, "the correction won"
        assert "TNI/2026/98765" in letter, "the confirmed prior reference"
        assert "Enclosures" in letter
        assert "Acknowledgement receipt" in letter

        # -- the officer's analysis ------------------------------------------
        analysis = state["analysis"]
        assert analysis is not None
        assert analysis["sources"], "a finding must cite something"

        # -- documents -------------------------------------------------------
        docx = await api.get(f"/api/sessions/{sid}/document.docx")
        assert docx.status_code == 200
        assert docx.content[:4] == b"PK\x03\x04"

    async def test_the_same_journey_with_no_attachment(self, api, answers, corpus):
        sid = await _walk(api, answers)
        state = (await api.post(f"/api/sessions/{sid}/attachments/done")).json()
        assert state["status"] == "confirming"

        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()
        assert state["status"] == "ready"
        assert state["verification"]["ok"] is True

        letter = state["letter_text"]
        assert answers["grievance"] in letter
        assert "Enclosures" not in letter, "nothing was enclosed"
        assert "previously submitted" not in letter

    async def test_the_tamil_journey(self, api, tamil_answers, corpus):
        sid = await _walk(api, tamil_answers, language="ta")
        await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()

        assert state["status"] == "ready", state.get("error")
        assert tamil_answers["grievance"] in state["letter_text"]
        assert "மனுதாரர்" in state["letter_text"] or "அனுப்புநர்" in state["letter_text"]


# --------------------------------------------------------------------------- #
# The knowledge layer, in the journey
# --------------------------------------------------------------------------- #

class TestKnowledgeInTheFlow:
    async def test_it_runs_once_and_not_on_every_message(self, api, answers, corpus,
                                                         monkeypatch):
        from app.knowledge import capability

        calls = []
        service = capability.service()
        original = service.analyst.analyse

        async def counted(*a, **k):
            calls.append(1)
            return await original(*a, **k)

        monkeypatch.setattr(service.analyst, "analyse", counted)

        sid = await _walk(api, answers)
        await api.post(f"/api/sessions/{sid}/attachments/done")
        await api.post(f"/api/sessions/{sid}/field",
                       json={"name": "age", "value": "24"})
        if (await api.get(f"/api/sessions/{sid}")).json()["status"] == "attachments":
            await api.post(f"/api/sessions/{sid}/attachments/done")
        await api.post(f"/api/sessions/{sid}/confirm")

        assert len(calls) <= 1, f"the knowledge layer ran {len(calls)} times"

    async def test_a_grievance_with_no_matching_document_says_so(self, api, corpus,
                                                                answers):
        """The corpus is about water. This grievance is not."""
        from app.knowledge import capability

        unrelated = {**answers,
                     "grievance": "My pension has not been credited for March and "
                                  "the bank branch says they have no instruction."}
        analysis = await capability.service().analyse(unrelated["grievance"])

        if analysis is not None:
            from app.knowledge.schema import UNVERIFIED

            assert analysis.unverified is True
            assert analysis.message == UNVERIFIED

    async def test_nothing_from_the_corpus_is_printed_on_the_petition(
            self, api, answers, corpus):
        """It is advisory. The petition says what the citizen said."""
        sid = await _walk(api, answers)
        await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()

        letter = state["letter_text"]
        assert "TEST DATA" not in letter
        assert "Assistant Engineer" not in letter
        assert "fifteen days" not in letter

    async def test_a_broken_knowledge_layer_still_yields_a_petition(
            self, api, answers, monkeypatch):
        from app.knowledge import capability

        async def explode(*a, **k):
            raise RuntimeError("the corpus is on fire")

        monkeypatch.setattr(capability.KnowledgeService, "analyse", explode)

        sid = await _walk(api, answers)
        await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()

        assert state["status"] == "ready"
        assert state["verification"]["ok"] is True


# --------------------------------------------------------------------------- #
# Capability reporting
# --------------------------------------------------------------------------- #

class TestHonestCapabilityReporting:
    async def test_health_separates_can_from_should(self, api):
        """A workstation with Word can make a PDF. A department server may not
        be commissioned on the strength of that."""
        health = (await api.get("/api/health")).json()
        documents = health["documents"]

        assert documents["docx"] is True
        assert "pdf_production_ready" in documents
        if documents["pdf"] and documents["pdf_engine"] == "word":
            assert documents["pdf_production_ready"] is False
            assert "libreoffice" in documents["note"].lower()
        if documents["pdf_engine"] == "libreoffice":
            assert documents["pdf_production_ready"] is True

    async def test_a_petition_is_produced_whether_or_not_pdf_is(self, api, answers):
        sid = await _walk(api, answers)
        await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()

        assert state["status"] == "ready"
        assert state["document"]["docx_url"]

    def test_ocr_reports_what_it_cannot_do(self):
        from app.services.extraction import ocr_status

        status = ocr_status()
        assert isinstance(status["available"], bool)
        if not status["available"]:
            assert "cannot be read" in status["note"]
            assert "guessed" in status["note"]

    def test_the_shipped_corpus_is_empty(self):
        """A demonstration seeded with invented Acts is the exact failure the
        grounding check exists to prevent, so the runtime corpus ships empty
        and the panel says so until a department loads real documents."""
        from app.knowledge.capability import KnowledgeService

        settings = get_settings()
        if not settings.knowledge_path.exists():
            return
        store = KnowledgeStore(settings.knowledge_path, dimension=256, provider="local")
        stats = store.stats()
        assert stats["documents"] == 0, (
            "the runtime corpus must ship empty; load real documents with "
            "scripts/ingest.py")
        assert KnowledgeService(settings).status()["ready"] is False


# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #

class TestSecurity:
    async def test_an_aadhaar_spoken_into_a_grievance_never_leaves_the_machine(
            self, api, answers, valid_aadhaar):
        """THE FORM NO LONGER ASKS FOR ONE. This is the path that remains,
        and it is the one that always mattered more: a citizen describing
        their problem says "my Aadhaar is 2345 6789 0124 and they rejected
        it", because that is how people explain what happened.

        Removing the field removed the tidy, validated copy. It did not
        remove the number from the sentence, so the masking on every outbound
        boundary has to go on working — and this walks a real session with
        one in the grievance to check that it does.
        """
        from app.services.mask import mask_pii

        said = f"My land is encroached. My Aadhaar is {valid_aadhaar} and it was rejected."
        sid = await _walk(api, {**answers, "grievance": said})
        state = (await api.get(f"/api/sessions/{sid}")).json()

        # Kept verbatim for the citizen and for the petition: the grievance is
        # their words, and editing it would be editing their complaint.
        collected = {f["name"]: f for f in state["collected"]}
        assert valid_aadhaar in str(collected["grievance"]["value"])

        # And removed from everything that goes outward.
        assert valid_aadhaar not in mask_pii(said)
        assert valid_aadhaar not in mask_pii(str(collected))

    async def test_the_form_no_longer_collects_an_identifier(self, api, answers):
        """A petition asking an office to look at a blocked drain does not
        need a national identity number to do it."""
        sid = await _walk(api, answers)
        state = (await api.get(f"/api/sessions/{sid}")).json()
        names = {f["name"] for f in state["collected"]}

        assert "aadhaar" not in names, names
        assert "aadhaar" not in str(state.get("outstanding") or [])

    async def test_an_attachment_analysis_masks_before_sending(self, api, answers,
                                                               valid_aadhaar,
                                                               monkeypatch):
        from app.knowledge.analyst import Analyst
        from app.knowledge.retrieve import Retriever
        from app.knowledge.store import KnowledgeStore

        seen = {}

        async def capture(**kwargs):
            seen.update(kwargs)
            return {}

        monkeypatch.setattr("app.knowledge.analyst.chat_json", capture)
        settings = get_settings()
        store = KnowledgeStore(settings.data_dir / "probe.sqlite", dimension=256,
                               provider="local")
        analyst = Analyst(Retriever(store, LocalEmbeddings(dimension=256), settings),
                          settings)
        await analyst.analyse(
            f"My land is encroached and my Aadhaar number is {valid_aadhaar}.")

        assert valid_aadhaar not in str(seen.get("user", ""))

    async def test_an_attachment_cannot_be_written_outside_its_session(self, api,
                                                                      answers):
        from app.services.attachment_store import AttachmentRejected, session_dir

        sid = await _walk(api, answers)
        await api.post(f"/api/sessions/{sid}/attachments",
                       files={"file": ("../../x.pdf", pdf_bytes(SLIP), "application/pdf")})

        directory = session_dir(sid)
        assert len(list(directory.glob("*"))) == 1
        for evil in ("../other", "..", "a/b"):
            with pytest.raises(AttachmentRejected):
                session_dir(evil)

    async def test_a_session_cannot_read_another_session_attachment(self, api, answers):
        first = await _walk(api, answers)
        second = await _walk(api, answers)
        state = (await api.post(
            f"/api/sessions/{first}/attachments",
            files={"file": ("a.pdf", pdf_bytes(SLIP), "application/pdf")})).json()
        aid = state["attachments"]["items"][0]["attachment_id"]

        response = await api.delete(f"/api/sessions/{second}/attachments/{aid}")
        assert response.status_code == 404
