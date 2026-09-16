"""OCR as an optional capability, and what must stay true when it appears.

No engine is installed on this machine, so the interesting tests here register a
fake one. That is not a workaround — it is the actual guarantee under test: the
petition workflow must not change when an engine is installed, so it must be
possible to install one and see nothing move except the fourth line of

    attachment
      → is there extractable text?
          yes → deterministic extraction
          no  → is an OCR engine available?
                  yes → OCR, at reduced confidence
                  no  → say so, and ask the citizen to type it

Everything an engine produces re-enters the same extraction → confidence →
evidence → confirmation pipeline. It never writes a petition field.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from app.api.rest import router
from app.graph.workflow import Workflow
from app.services import extraction, ocr

# TEST DATA — what a fake engine "reads" off a photograph.
RECOGNISED = """OFFICE OF THE DISTRICT COLLECTOR, THENI
ACKNOWLEDGEMENT
Received your petition dated 12-08-2026.
Acknowledgement No.: TNI/2026/44444
Status: Pending
"""

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FakeEngine:
    """An engine that always works. Stands in for a real installation."""

    name = "fake"

    def __init__(self, text: str = RECOGNISED, works: bool = True) -> None:
        self.text = text
        self.works = works
        self.calls: list[str] = []

    def available(self) -> bool:
        return self.works

    def languages(self) -> list[str]:
        return ["eng", "tam"]

    def image(self, path):
        self.calls.append("image")
        return self.text

    def pdf(self, path):
        self.calls.append("pdf")
        return self.text


@pytest.fixture
def engine(monkeypatch):
    """Install a fake engine for the duration of one test."""
    fake = FakeEngine()
    monkeypatch.setattr(ocr, "_ENGINES", [fake])
    return fake


@pytest.fixture
def no_engine(monkeypatch):
    monkeypatch.setattr(ocr, "_ENGINES", [])


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


async def _collected(api, answers):
    session = (await api.post("/api/sessions", json={"language": "en"})).json()
    sid = session["session_id"]
    for name, value in answers.items():
        await api.post(f"/api/sessions/{sid}/field", json={"name": name, "value": value})
    return sid


async def _upload(api, sid, name, content, content_type):
    return await api.post(f"/api/sessions/{sid}/attachments",
                          files={"file": (name, content, content_type)})


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #

class TestTheRegistry:
    def test_no_engine_is_reported_honestly(self, no_engine):
        status = ocr.status()

        assert status["available"] is False
        assert status["engine"] is None
        assert "nothing is guessed" in status["note"]

    def test_an_installed_engine_is_reported(self, engine):
        status = ocr.status()

        assert status["available"] is True
        assert status["engine"] == "fake"
        assert "tam" in status["languages"]
        # Even with an engine, the result still has to be confirmed, and the
        # note has to say so — an operator reading "OCR: available" should not
        # conclude that scanned documents are now trusted.
        assert "confirmed" in status["note"]

    def test_registering_puts_a_new_engine_first(self, monkeypatch):
        preferred = FakeEngine(text="preferred")
        monkeypatch.setattr(ocr, "_ENGINES", [FakeEngine(text="default")])
        ocr.register(preferred)

        assert ocr.active() is preferred

    def test_an_engine_that_is_not_installed_is_skipped(self, monkeypatch):
        absent, present = FakeEngine(works=False), FakeEngine()
        monkeypatch.setattr(ocr, "_ENGINES", [absent, present])

        assert ocr.active() is present

    def test_an_engine_that_raises_is_treated_as_absent(self, monkeypatch):
        class Broken:
            name = "broken"

            def available(self):
                raise RuntimeError("misconfigured")

        working = FakeEngine()
        monkeypatch.setattr(ocr, "_ENGINES", [Broken(), working])

        assert ocr.active() is working

    def test_status_is_not_cached_across_an_installation(self, monkeypatch):
        """An engine installed while the service runs must be picked up without
        a restart, so this must not be memoised."""
        monkeypatch.setattr(ocr, "_ENGINES", [])
        assert ocr.status()["available"] is False

        monkeypatch.setattr(ocr, "_ENGINES", [FakeEngine()])
        assert ocr.status()["available"] is True

    def test_a_failing_read_returns_none_rather_than_raising(self, monkeypatch,
                                                             tmp_path):
        class Exploding:
            name = "exploding"

            def available(self):
                return True

            def image(self, path):
                raise RuntimeError("engine crashed")

            def pdf(self, path):
                raise RuntimeError("engine crashed")

        monkeypatch.setattr(ocr, "_ENGINES", [Exploding()])
        path = tmp_path / "x.png"
        path.write_bytes(PNG)

        assert ocr.read_image(path) is None
        assert ocr.read_pdf(path) is None


# --------------------------------------------------------------------------- #
# Extraction, with and without an engine
# --------------------------------------------------------------------------- #

class TestExtraction:
    def test_without_an_engine_a_photograph_is_unreadable(self, no_engine, tmp_path):
        path = tmp_path / "photo.png"
        path.write_bytes(PNG)

        read = extraction.extract(path)

        assert read.readable is False
        assert "no OCR engine is installed" in read.reason
        assert read.text == ""

    def test_with_an_engine_a_photograph_is_read(self, engine, tmp_path):
        path = tmp_path / "photo.png"
        path.write_bytes(PNG)

        read = extraction.extract(path)

        assert read.readable is True
        assert read.method == "ocr"
        assert "TNI/2026/44444" in read.text
        assert engine.calls == ["image"]

    def test_an_ocr_result_is_always_low_confidence(self, engine, tmp_path):
        """Below `LOW_CONFIDENCE`, so it is always flagged to the citizen —
        whatever the engine claims about itself."""
        path = tmp_path / "photo.png"
        path.write_bytes(PNG)

        read = extraction.extract(path)

        assert read.confidence < extraction.LOW_CONFIDENCE
        assert read.low_confidence is True

    def test_a_text_layer_is_never_sent_to_ocr(self, engine, tmp_path):
        """OCR is the fallback, not the first move. A PDF that already has text
        must not be re-read from pixels — it is slower and worse."""
        import pymupdf

        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((55, 80), RECOGNISED, fontsize=11)
        path = tmp_path / "typed.pdf"
        document.save(str(path))
        document.close()

        read = extraction.extract(path)

        assert read.method == "pdf-text"
        assert engine.calls == [], "the engine must not have been consulted"

    def test_an_engine_that_recognises_nothing_says_so(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ocr, "_ENGINES", [FakeEngine(text="   \n  ")])
        path = tmp_path / "blank.png"
        path.write_bytes(PNG)

        read = extraction.extract(path)

        assert read.readable is False
        assert "No text could be recognised" in read.reason


# --------------------------------------------------------------------------- #
# The pipeline does not change
# --------------------------------------------------------------------------- #

class TestThePipelineIsUnchanged:
    async def test_an_ocr_read_still_needs_confirmation(self, api, answers, engine):
        sid = await _collected(api, answers)
        response = await _upload(api, sid, "slip.png", PNG, "image/png")

        item = response.json()["attachments"]["items"][0]
        assert item["readable"] is True
        assert item["needs_confirmation"] is True, "OCR is never auto-confirmed"
        assert item["confirmed"] is False
        assert item["low_confidence"] is True

    async def test_ocr_values_carry_their_evidence(self, api, answers, engine):
        sid = await _collected(api, answers)
        response = await _upload(api, sid, "slip.png", PNG, "image/png")

        fields = {f["name"]: f for f in response.json()["attachments"]["items"][0]["fields"]}
        assert fields["reference_number"]["value"] == "TNI/2026/44444"
        assert fields["reference_number"]["evidence"], "must show where it came from"
        # Scaled down because the text itself came in weak.
        assert fields["reference_number"]["confidence"] < 0.9

    async def test_an_unconfirmed_ocr_read_is_never_cited(self, api, answers, engine):
        sid = await _collected(api, answers)
        await _upload(api, sid, "slip.png", PNG, "image/png")

        await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()
        letter = state["letter_text"] or ""

        assert "Enclosures" in letter, "it is in the envelope"
        assert "TNI/2026/44444" not in letter, "but nothing it says is claimed"

    async def test_a_confirmed_ocr_read_is_cited(self, api, answers, engine):
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "slip.png", PNG, "image/png")).json()
        aid = state["attachments"]["items"][0]["attachment_id"]

        await api.post(f"/api/sessions/{sid}/attachments/{aid}/confirm",
                       json={"confirmed": True, "values": {}})
        await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()

        assert "TNI/2026/44444" in state["letter_text"]

    async def test_ocr_never_writes_a_petition_field(self, api, answers, engine):
        """The slip names a department and a subject. The citizen's record is
        untouched by all of it."""
        sid = await _collected(api, answers)
        before = {f["name"]: f["value"]
                  for f in (await api.get(f"/api/sessions/{sid}")).json()["collected"]}

        state = (await _upload(api, sid, "slip.png", PNG, "image/png")).json()
        aid = state["attachments"]["items"][0]["attachment_id"]
        await api.post(f"/api/sessions/{sid}/attachments/{aid}/confirm",
                       json={"confirmed": True, "values": {}})

        after = {f["name"]: f["value"]
                 for f in (await api.get(f"/api/sessions/{sid}")).json()["collected"]}
        assert after == before

    async def test_the_workflow_is_identical_with_and_without_an_engine(
            self, api, answers, monkeypatch):
        """The petition is produced either way, and the enclosure line is the
        same. Only whether the citizen is asked to type the number differs."""
        monkeypatch.setattr(ocr, "_ENGINES", [])
        sid = await _collected(api, answers)
        await _upload(api, sid, "slip.png", PNG, "image/png")
        await api.post(f"/api/sessions/{sid}/attachments/done")
        without = (await api.post(f"/api/sessions/{sid}/confirm")).json()

        monkeypatch.setattr(ocr, "_ENGINES", [FakeEngine()])
        sid = await _collected(api, answers)
        await _upload(api, sid, "slip.png", PNG, "image/png")
        await api.post(f"/api/sessions/{sid}/attachments/done")
        with_engine = (await api.post(f"/api/sessions/{sid}/confirm")).json()

        assert without["status"] == with_engine["status"] == "ready"
        assert "Enclosures" in without["letter_text"]
        assert "Enclosures" in with_engine["letter_text"]
        # Neither cites anything, because neither was confirmed.
        assert "TNI/2026/44444" not in without["letter_text"]
        assert "TNI/2026/44444" not in with_engine["letter_text"]

    async def test_health_reports_the_capability(self, api, engine):
        health = (await api.get("/api/health")).json()
        assert health["attachments"]["ocr"]["available"] is True
        assert health["attachments"]["ocr"]["engine"] == "fake"
