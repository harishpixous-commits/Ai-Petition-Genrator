"""The operator screen: what it shows, and who is allowed to see it.

There is no user system in this service, so access is one blunt rule that fails
closed on the dangerous side:

    OPERATOR_TOKEN set    → the token is required, from any address
    OPERATOR_TOKEN unset  → loopback only

The second is the one that matters. A deployment that forgets to set a token
must not end up with an open admin panel on its LAN — which is the same class of
mistake as the `python -m http.server` that was serving a projects directory to
the whole Tailscale network.

Nothing on this screen is citizen data. The counts are of government documents
and the flags are about this machine, and `TestNoCitizenData` holds that line.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.operator import authorise, router


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
async def api(app):
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)),
            base_url="http://test") as client:
        yield client


@pytest.fixture
async def remote(app):
    """A caller from somewhere else on the network."""
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("192.168.1.40", 5555)),
            base_url="http://test") as client:
        yield client


def _request(host: str) -> Request:
    return Request({"type": "http", "headers": [], "query_string": b"",
                    "client": (host, 1234), "method": "GET", "path": "/"})


# --------------------------------------------------------------------------- #
# Access
# --------------------------------------------------------------------------- #

class TestAccess:
    async def test_loopback_is_allowed_when_no_token_is_set(self, api):
        response = await api.get("/api/operator/status")

        assert response.status_code == 200
        assert response.json()["access"] == "loopback-only"

    async def test_the_network_is_refused_when_no_token_is_set(self, remote):
        """The forgotten-token case. It must not be an open panel."""
        response = await remote.get("/api/operator/status")

        assert response.status_code == 404

    async def test_it_answers_404_rather_than_401(self, remote):
        """An admin endpoint that announces itself to an unauthenticated caller
        is an invitation. There is nothing here a citizen should discover."""
        response = await remote.get("/api/operator/status")

        assert response.status_code == 404
        assert "operator" not in response.text.lower()
        assert "token" not in response.text.lower()

    async def test_a_token_lets_the_network_in(self, remote, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "operator_token", "s3cret-token")

        response = await remote.get("/api/operator/status",
                                    headers={"x-operator-token": "s3cret-token"})

        assert response.status_code == 200
        assert response.json()["access"] == "token"

    async def test_a_wrong_token_is_refused(self, remote, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "operator_token", "s3cret-token")

        assert (await remote.get(
            "/api/operator/status",
            headers={"x-operator-token": "wrong"})).status_code == 404
        assert (await remote.get("/api/operator/status")).status_code == 404

    async def test_a_token_is_required_even_from_loopback(self, api, monkeypatch):
        """Once a token exists it is the rule, not a second way in alongside
        the address check — otherwise anything running on the box bypasses it."""
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "operator_token", "s3cret-token")

        assert (await api.get("/api/operator/status")).status_code == 404
        assert (await api.get(
            "/api/operator/status?token=s3cret-token")).status_code == 200

    def test_an_unparseable_client_address_is_not_loopback(self, monkeypatch):
        from fastapi import HTTPException

        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "operator_token", "")
        with pytest.raises(HTTPException):
            authorise(_request("not-an-address"))

    def test_a_missing_client_address_is_not_loopback(self, monkeypatch):
        from fastapi import HTTPException

        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "operator_token", "")
        request = Request({"type": "http", "headers": [], "query_string": b"",
                           "client": None, "method": "GET", "path": "/"})
        with pytest.raises(HTTPException):
            authorise(request)


# --------------------------------------------------------------------------- #
# What it reports
# --------------------------------------------------------------------------- #

class TestKnowledgeReport:
    async def test_an_empty_corpus_reports_empty_not_broken(self, api):
        knowledge = (await api.get("/api/operator/status")).json()["knowledge"]

        assert knowledge["health"] == "empty"
        assert knowledge["documents"] == 0
        assert knowledge["last_ingested_at"] is None
        # An empty corpus is a supported state, and the note says what follows
        # from it rather than reading as a fault.
        assert "every petition is produced" in knowledge["note"]

    async def test_every_required_figure_is_present(self, api):
        knowledge = (await api.get("/api/operator/status")).json()["knowledge"]

        for key in ("documents", "official_documents", "unverified_documents",
                    "superseded_documents", "unresolved_conflicts", "chunks",
                    "embeddings", "last_ingested_at", "health"):
            assert key in knowledge, key

    async def test_a_conflicted_corpus_asks_for_attention(self, api, monkeypatch):
        from app.knowledge import capability

        class FakeStore:
            def documents(self, limit=10000):
                return [
                    {"document_id": "a", "title": "Sample Circular",
                     "rule_name": "Sample Circular", "superseded": 0,
                     "authority": "official"},
                    {"document_id": "b", "title": "Sample Circular",
                     "rule_name": "Sample Circular", "superseded": 0,
                     "authority": "official"},
                ]

        class FakeService:
            enabled = True
            store = FakeStore()

            def status(self):
                return {"enabled": True, "documents": 2, "official_documents": 2,
                        "unverified_documents": 0, "superseded": 0, "chunks": 8,
                        "ready": True, "vector_search": True,
                        "indexed_provider": "gemini", "indexed_dimension": 1536,
                        "by_type": {}, "last_ingested_at": 1789500000.0}

        monkeypatch.setattr(capability, "_service", FakeService())
        knowledge = (await api.get("/api/operator/status")).json()["knowledge"]

        assert knowledge["health"] == "attention"
        assert knowledge["unresolved_conflicts"] == 1
        assert "which is in force" in knowledge["conflicts"][0]["message"]
        assert knowledge["last_ingested_at"], "a real timestamp, not an epoch float"

    async def test_a_local_embedder_is_not_reported_as_semantic(self, api,
                                                                monkeypatch):
        """"embeddings: local" reads like success. It is a hashed bag-of-words."""
        from app.knowledge import capability

        class FakeService:
            enabled = True
            store = type("S", (), {"documents": lambda self, limit=1: []})()

            def status(self):
                return {"enabled": True, "documents": 1, "official_documents": 1,
                        "unverified_documents": 0, "superseded": 0, "chunks": 3,
                        "ready": True, "vector_search": True,
                        "indexed_provider": "local", "indexed_dimension": 512,
                        "by_type": {}, "last_ingested_at": None}

        monkeypatch.setattr(capability, "_service", FakeService())
        embeddings = (await api.get(
            "/api/operator/status")).json()["knowledge"]["embeddings"]

        assert embeddings["provider"] == "local"
        assert embeddings["semantic"] is False

    async def test_an_unreadable_corpus_does_not_take_the_screen_down(
            self, api, monkeypatch):
        from app.knowledge import capability

        class Broken:
            enabled = True

            @property
            def store(self):
                raise RuntimeError("the corpus file is locked")

            def status(self):
                return {"enabled": True, "documents": 0, "chunks": 0,
                        "ready": False, "vector_search": False}

        monkeypatch.setattr(capability, "_service", Broken())
        response = await api.get("/api/operator/status")

        assert response.status_code == 200
        assert response.json()["knowledge"]["conflicts"] == []


class TestCapabilityReport:
    async def test_all_five_capabilities_are_reported(self, api):
        capabilities = (await api.get("/api/operator/status")).json()["capabilities"]

        for key in ("rag", "ocr", "pdf", "voice", "word"):
            assert key in capabilities, key
            assert capabilities[key]["name"]
            assert capabilities[key]["state"]
            assert capabilities[key]["detail"]

    async def test_word_generation_is_always_ready(self, api):
        """It is in-process and has no external dependency. It is the
        deliverable, which is why nothing is allowed to make it conditional."""
        capabilities = (await api.get("/api/operator/status")).json()["capabilities"]

        assert capabilities["word"]["state"] == "ready"

    async def test_pdf_on_a_word_only_machine_reads_workstation_only(
            self, api, monkeypatch):
        """The suite runs with PDF_ENGINE=off, so the engine has to be turned
        on for this one — the distinction under test is Word vs LibreOffice,
        not on vs off."""
        from app.config import get_settings
        from app.services import render as render_module

        monkeypatch.setattr(get_settings(), "pdf_engine", "auto")
        monkeypatch.setattr(render_module.shutil, "which", lambda name: None)
        monkeypatch.setattr(render_module, "_word_available", lambda: True)

        capabilities = (await api.get("/api/operator/status")).json()["capabilities"]
        assert capabilities["pdf"]["state"] == "workstation_only"

    async def test_pdf_with_nothing_installed_reads_unavailable(self, api,
                                                                monkeypatch):
        from app.config import get_settings
        from app.services import render as render_module

        monkeypatch.setattr(get_settings(), "pdf_engine", "auto")
        monkeypatch.setattr(render_module.shutil, "which", lambda name: None)
        monkeypatch.setattr(render_module, "_word_available", lambda: False)

        capabilities = (await api.get("/api/operator/status")).json()["capabilities"]
        assert capabilities["pdf"]["state"] == "unavailable"

    async def test_pdf_switched_off_reads_unavailable(self, api):
        """The suite's own default: PDF_ENGINE=off. DOCX is the deliverable."""
        capabilities = (await api.get("/api/operator/status")).json()["capabilities"]

        assert capabilities["pdf"]["state"] == "unavailable"
        assert capabilities["word"]["state"] == "ready"

    async def test_ocr_without_an_engine_reads_not_installed(self, api, monkeypatch):
        from app.services import ocr

        monkeypatch.setattr(ocr, "_ENGINES", [])
        capabilities = (await api.get("/api/operator/status")).json()["capabilities"]

        assert capabilities["ocr"]["state"] == "not_installed"
        assert "nothing is guessed" in capabilities["ocr"]["detail"]

    async def test_rag_without_a_corpus_reads_not_ready(self, api):
        capabilities = (await api.get("/api/operator/status")).json()["capabilities"]

        assert capabilities["rag"]["state"] == "not_ready"
        assert "stays hidden" in capabilities["rag"]["detail"]


# --------------------------------------------------------------------------- #
# The line this screen must not cross
# --------------------------------------------------------------------------- #

class TestNoCitizenData:
    async def test_a_live_petition_leaves_no_trace_on_the_screen(
            self, api, answers, graph, valid_aadhaar):
        """A whole petition, and the operator screen knows nothing about it."""
        from tests.conftest import Conversation

        citizen = Conversation(graph)
        await citizen.answer_all(answers)
        await citizen.say("yes")

        body = (await api.get("/api/operator/status")).text

        for secret in (valid_aadhaar, answers["applicant_name"],
                       answers["mobile"], answers["address"],
                       answers["grievance"][:40]):
            assert secret not in body, secret

    async def test_it_reports_no_session_counts_at_all(self, api):
        """Not even how many petitions were produced. The screen is about the
        machine and the corpus; a session count is a step onto the other side
        of that line and there is no reason to take it."""
        payload = (await api.get("/api/operator/status")).json()

        assert set(payload) == {"generated_at", "knowledge", "capabilities", "access"}
        assert "sessions" not in str(payload).lower()
