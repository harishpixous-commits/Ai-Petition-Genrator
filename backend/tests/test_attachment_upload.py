"""Uploading, and the files reaching the finished petition.

Written after a reported fault: at the attachment step the Send button did
nothing. Four separate causes, each alone enough to break it, and every one of
them invisible — no error, no bubble, nothing happened at all:

  1. the page's submit handler checked the session status against a hard list
     that never gained "attachments", so it returned without sending;
  2. `clean_text` strips a leading "yes" as politeness, so "yes I want to add
     attachments" reached the reader as "i want to add attachments";
  3. the word "attachmentS" did not match a pattern that spelled out
     "attach|attachment" — the plural the question itself uses;
  4. the `attach` node ran again after `validate` had already answered, and
     overwrote the reply with the original question.

Causes 2, 3 and 4 are covered here. Cause 1 was in the page and is held by the
single `canSend()` predicate the handler and the button now share.

The second half covers what the petition actually arrives with: the enclosed
files themselves, as pages, after the letter.
"""

from __future__ import annotations

import zipfile

import httpx
import pytest
from fastapi import FastAPI

from app.api.rest import router
from app.domain import attachments as rules
from app.graph.workflow import Workflow

# TEST DATA — an invented acknowledgement slip.
SLIP = """OFFICE OF THE DISTRICT COLLECTOR, THENI
ACKNOWLEDGEMENT
Received your petition dated 12-08-2026.
Acknowledgement No.: TNI/2026/77777
"""

PNG_HEADER_ONLY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64      # valid header, no body


def pdf_bytes(text: str, pages: int = 1) -> bytes:
    import pymupdf

    document = pymupdf.open()
    for number in range(pages):
        page = document.new_page()
        page.insert_text((55, 80), f"{text}\n(page {number + 1})", fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def png_bytes(width: int = 800, height: int = 520) -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.insert_text((40, 80), "TEST DATA", fontsize=20)
    data = page.get_pixmap(dpi=96).tobytes("png")
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


async def _collected(api, answers) -> str:
    session = (await api.post("/api/sessions", json={"language": "en"})).json()
    sid = session["session_id"]
    for name, value in answers.items():
        await api.post(f"/api/sessions/{sid}/field", json={"name": name, "value": value})
    return sid


async def _upload(api, sid, name, content, content_type="application/pdf"):
    return await api.post(f"/api/sessions/{sid}/attachments",
                          files={"file": (name, content, content_type)})


async def _generate(api, sid) -> dict:
    await api.post(f"/api/sessions/{sid}/attachments/done")
    return (await api.post(f"/api/sessions/{sid}/confirm")).json()


async def _docx_parts(api_workflow, sid) -> tuple[str, list[str]]:
    snapshot = await api_workflow.snapshot(sid)
    with zipfile.ZipFile(snapshot["document"]["docx"]) as archive:
        return (archive.read("word/document.xml").decode("utf-8", "replace"),
                [n for n in archive.namelist() if n.startswith("word/media/")])


# --------------------------------------------------------------------------- #
# Saying yes has to reach the uploader
# --------------------------------------------------------------------------- #

class TestSayingYes:
    @pytest.mark.parametrize("said", [
        "yes i want to add attachments",
        "yes, I have attachments",
        "yes",
        "i want to add attachments",
        "attachments",
        "I have photographs",
        "add documents",
        "ஆம், இணைப்புகள் சேர்க்க வேண்டும்",
    ])
    async def test_it_asks_for_the_file_rather_than_repeating_itself(
            self, chat, answers, said):
        citizen = chat()
        await citizen.answer_all(answers, attachments=None)
        assert citizen.status == "attachments"

        state = await citizen.say(said)

        assert state["intent"] == "attach", said
        assert state["status"] == "attachments"
        # NOT the offer question again. That repetition is what read to the
        # citizen as the send button being broken.
        assert ("attach button" in state["reply"]
                or "இணைப்பு பொத்தான" in state["reply"]), state["reply"][:80]

    def test_a_leading_yes_is_not_stripped_before_it_is_read(self):
        """`clean_text` removes politeness that precedes an answer. Here "yes"
        IS the answer, so the reader gets the raw utterance as well."""
        from app.domain.fields import clean_text

        assert clean_text("yes i want to add attachments") == "i want to add attachments"
        assert rules.read_choice("yes") == "add"

    @pytest.mark.parametrize("word", [
        "attachments", "attachment", "documents", "photographs", "copies",
        "enclosures", "receipts", "certificates", "slips",
    ])
    def test_plural_forms_are_recognised(self, word):
        assert rules.read_choice(f"I have {word}") == "add", word

    async def test_the_view_says_a_file_is_awaited(self, api, answers):
        sid = await _collected(api, answers)
        state = (await api.post(f"/api/sessions/{sid}/message",
                                json={"text": "yes i want to add attachments"})).json()

        assert state["attachments"]["awaiting_file"] is True

    async def test_uploading_clears_the_await(self, api, answers):
        sid = await _collected(api, answers)
        await api.post(f"/api/sessions/{sid}/message",
                       json={"text": "yes i want to add attachments"})

        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()

        assert state["attachments"]["awaiting_file"] is False
        assert len(state["attachments"]["items"]) == 1

    async def test_the_step_has_its_own_name_not_the_collecting_one(self, api,
                                                                    answers):
        """The page had no label for this status and fell back to "Collecting
        Information", so the citizen was shown the wrong stage."""
        from pathlib import Path

        script = Path("app/static/app.js").read_text(encoding="utf-8")
        assert "attachments: \"Adding Attachments\"" in script
        assert "attachments: \"இணைப்புகள் சேர்த்தல்\"" in script

    def test_the_page_can_send_at_this_step(self):
        """Cause 1. The handler and the button now share one predicate, so the
        button cannot offer something the handler silently refuses."""
        from pathlib import Path

        script = Path("app/static/app.js").read_text(encoding="utf-8")
        assert "SENDABLE_STATUSES" in script
        assert '"attachments"' in script.split("SENDABLE_STATUSES")[1][:120]
        # Both call sites go through it.
        assert script.count("canSend()") >= 3


# --------------------------------------------------------------------------- #
# Bulk
# --------------------------------------------------------------------------- #

class TestBulk:
    async def test_several_files_in_one_go(self, api, answers):
        sid = await _collected(api, answers)
        for name, body, ctype in (
            ("ack.pdf", pdf_bytes(SLIP), "application/pdf"),
            ("photo.png", png_bytes(), "image/png"),
            ("notes.txt", b"TEST DATA - I complained twice.", "text/plain"),
        ):
            assert (await _upload(api, sid, name, body, ctype)).status_code == 201

        state = (await api.get(f"/api/sessions/{sid}")).json()
        assert len(state["attachments"]["items"]) == 3

        letter = (await _generate(api, sid))["letter_text"]
        enclosures = letter.split("Enclosures:")[1]
        for number in ("1.", "2.", "3."):
            assert number in enclosures

    async def test_one_refusal_does_not_lose_the_others(self, api, answers):
        sid = await _collected(api, answers)
        await _upload(api, sid, "ok.pdf", pdf_bytes(SLIP))
        refused = await _upload(api, sid, "bad.pdf", b"MZ\x90\x00 executable")
        await _upload(api, sid, "also-ok.png", png_bytes(), "image/png")

        assert refused.status_code == 400
        state = (await api.get(f"/api/sessions/{sid}")).json()
        assert len(state["attachments"]["items"]) == 2

    async def test_the_limit_holds_across_a_bulk_add(self, api, answers):
        sid = await _collected(api, answers)
        accepted = 0
        for index in range(rules.MAX_ATTACHMENTS + 3):
            response = await _upload(api, sid, f"f{index}.pdf", pdf_bytes(SLIP))
            accepted += response.status_code == 201

        assert accepted == rules.MAX_ATTACHMENTS

    async def test_a_photograph_is_labelled_a_photograph(self, api, answers):
        """"Supporting document" for a picture of a broken street light is
        needlessly vague on a line an officer reads."""
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "street.png", png_bytes(), "image/png")).json()

        assert state["attachments"]["items"][0]["kind"] == "photo"


# --------------------------------------------------------------------------- #
# The files reach the document
# --------------------------------------------------------------------------- #

class TestTheFilesAreInTheDocument:
    async def test_a_pdf_enclosure_becomes_pages(self, api, api_workflow, answers):
        sid = await _collected(api, answers)
        await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP, pages=2))

        await _generate(api, sid)
        xml, media = await _docx_parts(api_workflow, sid)

        # Two pages of the enclosure, reproduced rather than merely listed.
        assert len(media) == 2
        assert "Enclosure: 1." in xml
        assert "Reproduced from the document" in xml

    async def test_a_photograph_becomes_a_page(self, api, api_workflow, answers):
        sid = await _collected(api, answers)
        await _upload(api, sid, "photo.png", png_bytes(), "image/png")

        await _generate(api, sid)
        xml, media = await _docx_parts(api_workflow, sid)

        assert len(media) == 1
        assert "Enclosure: 1." in xml

    async def test_a_text_enclosure_stays_text(self, api, api_workflow, answers):
        """It is already text. Rasterising it would lose the ability to select
        and search it in the finished petition, for nothing."""
        sid = await _collected(api, answers)
        await _upload(api, sid, "notes.txt",
                      b"TEST DATA I complained on 3 June.", "text/plain")

        await _generate(api, sid)
        xml, media = await _docx_parts(api_workflow, sid)

        assert media == []
        assert "I complained on 3 June" in xml

    async def test_no_attachments_means_no_extra_pages(self, api, api_workflow,
                                                       answers):
        sid = await _collected(api, answers)

        await _generate(api, sid)
        xml, media = await _docx_parts(api_workflow, sid)

        assert media == []
        assert "Enclosure:" not in xml

    async def test_a_corrupt_file_does_not_cost_the_petition(self, api, api_workflow,
                                                             answers):
        """A valid PNG header with a truncated body converts happily and then
        throws when it is embedded. It must not take the render down with it."""
        sid = await _collected(api, answers)
        await _upload(api, sid, "cut-short.png", PNG_HEADER_ONLY, "image/png")

        state = await _generate(api, sid)
        assert state["status"] == "ready"
        assert state["verification"]["ok"] is True

        xml, _ = await _docx_parts(api_workflow, sid)
        assert "could not be reproduced here" in xml

    async def test_the_letter_comes_before_the_enclosures(self, api, api_workflow,
                                                          answers):
        """An officer reaches the citizen's own words and their signature
        before a stack of scans, not through it."""
        sid = await _collected(api, answers)
        await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))

        await _generate(api, sid)
        xml, _ = await _docx_parts(api_workflow, sid)

        assert xml.index("Yours faithfully") < xml.index("Enclosure: 1.")

    async def test_the_enclosure_pages_are_capped(self, api, api_workflow, answers):
        """A citizen who attaches a 200-page report has attached the wrong
        thing, and a 200-page petition will not be read."""
        from app.services.enclosures import MAX_PAGES_PER_ATTACHMENT

        sid = await _collected(api, answers)
        await _upload(api, sid, "long.pdf",
                      pdf_bytes(SLIP, pages=MAX_PAGES_PER_ATTACHMENT + 6))

        await _generate(api, sid)
        _, media = await _docx_parts(api_workflow, sid)

        assert len(media) == MAX_PAGES_PER_ATTACHMENT

    async def test_a_deleted_attachment_leaves_no_page_behind(self, api, api_workflow,
                                                              answers):
        sid = await _collected(api, answers)
        state = (await _upload(api, sid, "ack.pdf", pdf_bytes(SLIP))).json()
        aid = state["attachments"]["items"][0]["attachment_id"]
        await api.delete(f"/api/sessions/{sid}/attachments/{aid}")

        await _generate(api, sid)
        xml, media = await _docx_parts(api_workflow, sid)

        assert media == []
        assert "Enclosure:" not in xml
