"""Changing how a finished petition READS, without changing what it says.

The distinction this file is about: a detail that is simply WRONG is a
correction — the citizen names the field, it is revalidated, and it is logged
as a correction. How the letter is WRITTEN is a revision, and it is the one
thing a citizen can only judge after they have seen the document.

A revision must never become a way around validation. The particulars were
confirmed before anything was drafted; a revision may change emphasis, tone and
what the subject line names, and it may not change a single recorded value or
the complaint in the citizen's own words.
"""

from __future__ import annotations

import pytest

from app.domain.templates import the_template
from app.graph.nodes import understand, validate


def ready_state(**over):
    """A session with a finished petition in it."""
    base = {
        "session_id": "s1",
        "language": "en",
        "status": "ready",
        "confirmed": True,
        "template_id": the_template().id,
        "fields": {
            "applicant_name": "Harish", "age": 23, "mobile": "9876543210",
            "address": "80/33 perumal kovil street, theni",
            "aadhaar": "234567890124",
            "grievance": "water scarcity in our street for weeks",
        },
        "field_sources": {}, "attempts": {}, "missing": [], "field_errors": {},
        "awaiting": None, "awaiting_correction": False,
        "letter_text": "Subject: Water\n\n   water scarcity in our street for weeks\n",
        "document": {"docx": "a.docx", "reference": "AP/2026/ABCDEF"},
        "verification": {"ok": True, "checked": 6},
        "composition": {"subject": "Water"}, "warnings": [], "corrections": [],
        "revisions": [], "error": None, "turns": [{"who": "assistant", "text": "ready"}],
        "_extracted": {}, "_corrections": {}, "_correction_target": None, "_revision": None,
    }
    base.update(over)
    return base


class TestWhatCountsAsARevision:
    async def test_an_instruction_about_wording_is_a_revision(self):
        state = ready_state(utterance="make the subject mention the water shortage")
        result = await understand(state)
        assert result["intent"] == "revise"
        assert result["_revision"] == "make the subject mention the water shortage"
        # Deterministic: no model was needed to work this out.
        assert result["understood_by"] == "deterministic"

    @pytest.mark.parametrize("said", ["ok", "yes", "thanks", "no", "good", "sure"])
    async def test_an_acknowledgement_is_not_a_revision(self, said):
        """"ok" must not rewrite a finished petition."""
        result = await understand(ready_state(utterance=said))
        assert result["intent"] != "revise", said

    async def test_a_named_field_is_a_correction_not_a_revision(self):
        """"my address is wrong" goes through validation, as it always did."""
        result = await understand(ready_state(utterance="my address is wrong"))
        assert result["intent"] == "correct"
        assert result["_correction_target"] == "address"

    @pytest.mark.parametrize("said,field", [
        ("my address is wrong", "address"),
        ("my name is wrong", "applicant_name"),
        ("the age is incorrect", "age"),
        ("my mobile number is wrong", "mobile"),
    ])
    async def test_a_complaint_is_not_recorded_as_the_new_value(self, said, field):
        """"My name is wrong" once set the petitioner's name TO "wrong".

        The connector "is" made the complaint look like a supplied value, and
        the name validator accepts "wrong" as a name — so a citizen reporting
        an error had the report itself written into their petition.
        """
        result = await understand(ready_state(utterance=said))

        assert result["intent"] == "correct"
        assert result["_correction_target"] == field
        assert not result["_extracted"] and not result["_corrections"], (
            "a complaint must name the field, never fill it")

    async def test_a_real_value_is_still_recorded(self):
        """The guard must not swallow a value that merely looks like one."""
        result = await understand(
            ready_state(utterance="my name is Wrongton Smith"))
        assert result["_corrections"] == {"applicant_name": "Wrongton Smith"}

    async def test_cancel_and_restart_still_win(self):
        assert (await understand(ready_state(utterance="start over")))["intent"] == "restart"
        assert (await understand(ready_state(utterance="cancel")))["intent"] == "cancel"


class TestARevisionRegeneratesWithoutTouchingTheRecord:
    async def test_it_goes_straight_back_to_generating(self):
        """No second read-back: nothing about the citizen's details is
        changing, so confirming them again would be ceremony, not a check."""
        state = ready_state(utterance="change the subject to Street light repair",
                            intent="revise",
                            _revision="change the subject to Street light repair")
        result = await validate(state)
        assert result["status"] == "generating"
        assert result["confirmed"] is True

    async def test_an_unclear_instruction_asks_rather_than_regenerating(self):
        """"Say more about the elderly residents" names no target the editor
        can act on. Asking is the honest answer; quietly re-drafting the whole
        petition on a guess is not."""
        state = ready_state(utterance="say more about the elderly residents",
                            intent="revise",
                            _revision="say more about the elderly residents")
        result = await validate(state)

        assert result["status"] == "ready", "the petition is left as it was"
        assert result["pending_edit"]["target"]
        assert result["reply"]

    async def test_the_stale_document_is_cleared(self):
        """The old PDF describes the old wording. Leaving it in place would
        offer a download that no longer matches what is on screen."""
        state = ready_state(utterance="change the subject to Street light repair", intent="revise",
                            _revision="change the subject to Street light repair")
        result = await validate(state)
        assert result["letter_text"] is None
        assert result["document"] is None
        assert result["verification"] is None
        # The composition SURVIVES: the edit is applied to the text that
        # exists rather than re-drafted from scratch, so the wording the
        # citizen already accepted is not thrown away to make one change.
        assert result["composition"] == state["composition"]
        assert result["error"] is None

    async def test_no_recorded_value_is_touched(self):
        state = ready_state(utterance="make it firmer", intent="revise",
                            _revision="make it firmer")
        result = await validate(state)
        # `validate` returns a patch; a revision must not carry field changes.
        assert "fields" not in result
        assert "corrections" not in result

    async def test_what_was_asked_for_is_recorded(self):
        asked = "change the subject to Street light repair"
        state = ready_state(utterance=asked, intent="revise", _revision=asked)
        result = await validate(state)
        assert result["revisions"] == [asked]

    async def test_revisions_accumulate_rather_than_replace(self):
        """A second request builds on the first. Replacing would silently undo
        a change the citizen had already asked for and seen."""
        first = "change the subject to Street light repair"
        second = "add that I already complained twice"
        state = ready_state(utterance=second, intent="revise", _revision=second,
                            revisions=[first])
        result = await validate(state)
        assert result["revisions"] == [first, second]

    async def test_a_revision_with_nothing_in_it_does_nothing(self):
        state = ready_state(utterance="", intent="revise", _revision=None)
        result = await validate(state)
        assert result.get("status") != "generating"


class TestTheDraftingCallIsStillBounded:
    def test_the_revision_brief_forbids_new_facts(self):
        """A revision is an instruction about wording. The prompt says so in
        the same terms the first draft was bound by, and the grounding check in
        `_read_composition` drops any field that invents a number regardless."""
        import app.graph.nodes as nodes

        source = open(nodes.__file__, encoding="utf-8").read()
        assert "revision_brief" in source
        for rule in ("may NOT add a fact", "may NOT alter the complaint",
                     "reproduced separately in the citizen's own words"):
            assert rule in source, rule

    def test_the_grievance_is_never_sent_as_something_to_rewrite(self):
        """It is placed verbatim by code and is not among the four fields the
        model produces, so no instruction can reach it."""
        from app.domain.letter import VERBATIM_FIELDS

        assert "grievance" in VERBATIM_FIELDS


class TestEditingTheTextDirectly:
    """The Edit button changes the petition itself, by hand.

    It used to open a box asking what should be said differently and send that
    to the drafting model. That is a REWORDING, and it now lives where every
    other instruction is typed — the chat. The button does the thing there was
    no way to do before: make the document editable and use exactly what the
    citizen types.

    "Exactly" is the whole guarantee. An editor that improves what it was given
    is not an editor, and somebody who corrected one word and got a
    differently-worded document back would be right to stop trusting it.
    """

    @pytest.fixture
    def api_workflow(self, graph):
        from app.graph.workflow import Workflow

        return Workflow(graph, None)

    @pytest.fixture
    async def api(self, api_workflow):
        import httpx
        from fastapi import FastAPI

        from app.api.rest import router

        app = FastAPI()
        app.include_router(router)
        app.state.workflow = api_workflow
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client

    async def _ready(self, api, answers):
        state = (await api.post("/api/sessions", json={"language": "en"})).json()
        sid = state["session_id"]
        for name, value in answers.items():
            await api.post(f"/api/sessions/{sid}/field",
                           json={"name": name, "value": value})
        await api.post(f"/api/sessions/{sid}/attachments/done")
        state = (await api.post(f"/api/sessions/{sid}/confirm")).json()
        assert state["status"] == "ready", state.get("error")
        return sid, state

    async def test_the_edit_is_used_exactly_as_typed(self, api, answers):
        sid, state = await self._ready(api, answers)
        edited = state["letter_text"].replace(
            "Thank you!", "I shall be grateful for an early inspection.\n\nThank you!")

        result = (await api.post(f"/api/sessions/{sid}/document/text",
                                 json={"text": edited})).json()

        assert result["status"] == "ready"
        assert result["letter_text"] == edited, "not one character may differ"

    async def test_no_model_is_called(self, api, answers, llm_spy):
        """A reachable model that must not be asked anything."""
        sid, state = await self._ready(api, answers)
        before = len(llm_spy.calls)

        await api.post(f"/api/sessions/{sid}/document/text",
                       json={"text": state["letter_text"] + "\n\nOne more line."})

        assert len(llm_spy.calls) == before, "a manual edit consults nobody"

    async def test_the_document_is_remade(self, api, api_workflow, answers):
        sid, state = await self._ready(api, answers)
        marker = "This sentence was typed by the citizen."

        await api.post(f"/api/sessions/{sid}/document/text",
                       json={"text": state["letter_text"] + f"\n\n{marker}"})

        from app.services.render import extract_docx_text

        snapshot = await api_workflow.snapshot(sid)
        assert marker in extract_docx_text(snapshot["document"]["docx"])

    async def test_the_session_records_that_it_was_edited(self, api, api_workflow,
                                                          answers):
        """An officer reading the record is entitled to know the wording is the
        citizen's own rather than the form's."""
        sid, state = await self._ready(api, answers)
        await api.post(f"/api/sessions/{sid}/document/text",
                       json={"text": state["letter_text"] + "\n\nAdded by hand."})

        snapshot = await api_workflow.snapshot(sid)
        assert snapshot["manually_edited"] is True

    async def test_removing_a_recorded_detail_warns_but_still_hands_it_over(
            self, api, answers):
        """Verification exists to catch the SYSTEM corrupting a document. A
        citizen deleting their own address from their own letter is not that."""
        sid, state = await self._ready(api, answers)
        without = state["letter_text"].replace(answers["address"], "elsewhere")

        result = (await api.post(f"/api/sessions/{sid}/document/text",
                                 json={"text": without})).json()

        assert result["status"] == "ready"
        assert result["verification"]["ok"] is False
        assert result["verification"]["hand_edited"] is True
        assert "address" in result["verification"]["missing_values"]
        assert any("Address" in w for w in result["warnings"])
        # Still theirs to download.
        assert result["document"]["docx_url"]
        assert (await api.get(f"/api/sessions/{sid}/document.docx")).status_code == 200

    async def test_an_empty_edit_is_refused(self, api, answers):
        sid, _ = await self._ready(api, answers)

        response = await api.post(f"/api/sessions/{sid}/document/text",
                                  json={"text": "   "})
        assert response.status_code == 422

    async def test_it_cannot_be_edited_before_it_exists(self, api, answers):
        state = (await api.post("/api/sessions", json={"language": "en"})).json()

        response = await api.post(f"/api/sessions/{state['session_id']}/document/text",
                                  json={"text": "x" * 80})
        assert response.status_code == 409

    async def test_a_reword_from_the_chat_still_works_afterwards(self, api, answers,
                                                                 fake_llm):
        """The two paths coexist: hand editing, and asking for a rewording."""
        sid, state = await self._ready(api, answers)
        await api.post(f"/api/sessions/{sid}/document/text",
                       json={"text": state["letter_text"] + "\n\nTyped by hand."})

        result = (await api.post(f"/api/sessions/{sid}/message",
                                 json={"text": "make the closing request firmer"})).json()

        assert result["status"] == "ready"
        assert "make the closing request firmer" in result["revisions"]

    async def test_a_tamil_petition_can_be_edited(self, api, tamil_answers):
        sid, state = await self._ready(api, tamil_answers)
        edited = state["letter_text"] + "\n\nகூடுதல் வரி."

        result = (await api.post(f"/api/sessions/{sid}/document/text",
                                 json={"text": edited})).json()

        assert result["letter_text"] == edited
        assert "கூடுதல் வரி." in result["letter_text"]
