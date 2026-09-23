"""Real HTTP and workflow regressions for recovery, editing and concurrent turns."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.api.rest import router
from app.graph.state import new_state
from app.graph.workflow import Workflow


@pytest.fixture
def api_workflow(graph):
    return Workflow(graph, None)


@pytest.fixture
async def api(api_workflow):
    app = FastAPI()
    app.include_router(router)
    app.state.workflow = api_workflow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client


async def _start(api):
    response = await api.post("/api/sessions", json={"language": "en"})
    assert response.status_code == 201, response.text
    return response.json()


async def _complete(api, answers):
    state = await _start(api)
    for name, value in answers.items():
        response = await api.post(
            f"/api/sessions/{state['session_id']}/field", json={"name": name, "value": value},
        )
        assert response.status_code == 200, response.text
        state = response.json()
    # The attachment offer stands between the last detail and the read-back.
    if state["status"] == "attachments":
        response = await api.post(
            f"/api/sessions/{state['session_id']}/attachments/done")
        assert response.status_code == 200, response.text
        state = response.json()
    assert state["status"] == "confirming"
    return state


class TestPayloadValidation:
    @pytest.mark.parametrize("text", [" ", "\n\t", "\u2003"])
    async def test_blank_messages_do_not_advance_the_interview(self, api, text):
        original = await _start(api)
        url = f"/api/sessions/{original['session_id']}"
        response = await api.post(f"{url}/message", json={"text": text})
        assert response.status_code == 422
        assert (await api.get(url)).json() == original

    @pytest.mark.parametrize("edit", [
        {"name": "unexpected", "value": "Ravi"},
        {"name": " ", "value": "Ravi"},
        {"name": "applicant_name", "value": "\n\t"},
    ])
    async def test_invalid_form_payloads_never_mutate_a_session(self, api, edit):
        original = await _start(api)
        url = f"/api/sessions/{original['session_id']}"
        assert (await api.post(f"{url}/field", json=edit)).status_code == 422
        assert (await api.get(url)).json() == original

    @pytest.mark.parametrize("endpoint", ["message", "field"])
    async def test_long_grievance_allowed_by_validator_is_accepted_over_http(
        self, api, answers, endpoint,
    ):
        state = await _complete(api, answers)
        url = f"/api/sessions/{state['session_id']}"
        await api.post(f"{url}/message", json={"text": "the grievance is wrong"})
        grievance = "The drain outside my house has been blocked for months. " * 100
        assert 4000 < len(grievance) < 6000
        body = {"text": grievance} if endpoint == "message" else {
            "name": "grievance", "value": grievance,
        }
        response = await api.post(f"{url}/{endpoint}", json=body)
        assert response.status_code == 200, response.text
        saved = next(item for item in response.json()["collected"] if item["name"] == "grievance")
        assert saved["value"] == grievance.strip()
        assert saved["max_length"] == 6000


class TestConfirmationAndEdits:
    async def test_double_confirmation_returns_the_same_document_once(
        self, api, api_workflow, answers, monkeypatch,
    ):
        state = await _complete(api, answers)
        url = f"/api/sessions/{state['session_id']}/confirm"
        calls = 0
        original = api_workflow._compiled.ainvoke

        async def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return await original(*args, **kwargs)

        monkeypatch.setattr(api_workflow._compiled, "ainvoke", counted)
        first, second = await asyncio.gather(api.post(url), api.post(url))
        assert first.status_code == second.status_code == 200
        assert first.json()["status"] == "ready", first.text
        assert first.json() == second.json()
        assert calls == 1

    async def test_a_ready_petition_requires_fresh_confirmation_after_edit(self, api, answers):
        state = await _complete(api, answers)
        url = f"/api/sessions/{state['session_id']}"
        ready = (await api.post(f"{url}/confirm")).json()
        assert ready["status"] == "ready"
        assert (await api.get(f"{url}/document.docx")).status_code == 200

        response = await api.post(f"{url}/field", json={"name": "age", "value": "31"})
        edited = response.json()
        assert edited["status"] == "confirming"
        assert edited["confirmed"] is False
        for key in ("letter_text", "document", "verification", "composition"):
            assert edited[key] is None, key
        assert (await api.get(f"{url}/document.docx")).status_code == 409

        updated = (await api.post(f"{url}/confirm")).json()
        assert updated["status"] == "ready", updated
        assert "31" in updated["letter_text"]
        assert (await api.get(f"{url}/document.docx")).status_code == 200

    async def test_invalid_correction_is_visible_and_blocks_confirmation_after_other_edits(
        self, api, answers,
    ):
        state = await _complete(api, answers)
        url = f"/api/sessions/{state['session_id']}"
        await api.post(f"{url}/confirm")
        invalid = (await api.post(f"{url}/field", json={"name": "age", "value": "500"})).json()
        age = next(item for item in invalid["collected"] if item["name"] == "age")
        assert age["value"] == 45
        assert age["error"] == invalid["field_errors"]["age"]["message"]
        assert invalid["document"] is None

        await api.post(f"{url}/field", json={"name": "applicant_name", "value": "Meena Kumar"})
        assert (await api.post(f"{url}/confirm")).status_code == 409
        assert (await api.get(f"{url}/document.docx")).status_code == 409
        fixed = (await api.post(f"{url}/field", json={"name": "age", "value": "31"})).json()
        assert fixed["field_errors"] == {}
        assert fixed["status"] == "confirming"

    async def test_rejected_readback_cannot_be_confirmed_until_corrected(self, api, answers):
        state = await _complete(api, answers)
        url = f"/api/sessions/{state['session_id']}"
        await api.post(f"{url}/message", json={"text": "no"})
        assert (await api.post(f"{url}/confirm")).status_code == 409

    async def test_form_edit_cannot_replay_a_previous_named_correction(self, api, answers):
        state = await _complete(api, answers)
        url = f"/api/sessions/{state['session_id']}"
        await api.post(f"{url}/message", json={"text": "the age is wrong"})
        edited = (await api.post(f"{url}/field", json={"name": "age", "value": "31"})).json()
        assert edited["status"] == "confirming"
        assert next(item["value"] for item in edited["collected"] if item["name"] == "age") == 31

    async def test_cancelled_complete_session_stays_closed_until_restart(self, api, answers):
        state = await _complete(api, answers)
        url = f"/api/sessions/{state['session_id']}"
        await api.post(f"{url}/confirm")
        cancelled = (await api.post(f"{url}/cancel")).json()
        assert cancelled["status"] == "cancelled"
        assert cancelled["letter_text"] is None
        assert cancelled["document"] is None
        assert cancelled["confirmed"] is False
        assert (await api.post(f"{url}/confirm")).status_code == 409
        assert (await api.post(f"{url}/field", json={"name": "age", "value": "31"})).status_code == 409
        assert (await api.post(f"{url}/restart")).json()["awaiting"] == "applicant_name"

    async def test_confirmation_recomputes_required_fields(self, api, api_workflow):
        state = await _start(api)
        # A stale/legacy checkpoint's cached missing list is not proof that
        # all values needed to generate a government document actually exist.
        await api_workflow.update(state["session_id"], {"missing": [], "status": "confirming"})
        assert (await api.post(f"/api/sessions/{state['session_id']}/confirm")).status_code == 409

    async def test_interrupted_generation_is_recoverable_without_losing_details(
        self, api, api_workflow, answers,
    ):
        state = await _complete(api, answers)
        url = f"/api/sessions/{state['session_id']}"
        await api_workflow.update(state["session_id"], {"status": "generating", "confirmed": True})
        recovered = (await api.get(url)).json()
        assert recovered["status"] == "failed"
        assert recovered["collected"] == state["collected"]
        assert "interrupted" in recovered["error"]
        retried = (await api.post(f"{url}/confirm")).json()
        assert retried["status"] == "ready", retried
        assert retried["error"] is None


class TestConcurrentTurns:
    async def test_simultaneous_rest_and_voice_updates_keep_both_answers(
        self, api, api_workflow, monkeypatch,
    ):
        state = await _start(api)
        session_id = state["session_id"]
        original = api_workflow._compiled.ainvoke
        active = peak = 0

        async def slow(*args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.02)
                return await original(*args, **kwargs)
            finally:
                active -= 1

        monkeypatch.setattr(api_workflow._compiled, "ainvoke", slow)
        # Voice uses Workflow.invoke directly; form edits arrive over REST.
        voice = asyncio.create_task(api_workflow.invoke(session_id, {"utterance": "Ravi Kumar"}))
        await asyncio.sleep(0)
        form = await api.post(
            f"/api/sessions/{session_id}/field", json={"name": "age", "value": "31"},
        )
        await voice
        assert form.status_code == 200
        latest = (await api.get(f"/api/sessions/{session_id}")).json()
        values = {item["name"]: item["value"] for item in latest["collected"]}
        assert values == {"applicant_name": "Ravi Kumar", "age": 31}
        assert peak == 1
        assert len(api_workflow._locks) == 0

    async def test_different_citizens_can_advance_at_the_same_time(self, api_workflow, monkeypatch):
        original = api_workflow._compiled.ainvoke
        both_started = asyncio.Event()
        active = 0

        async def concurrent(*args, **kwargs):
            nonlocal active
            active += 1
            if active == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=2)
            return await original(*args, **kwargs)

        monkeypatch.setattr(api_workflow._compiled, "ainvoke", concurrent)
        first, second = await asyncio.gather(
            api_workflow.invoke("first", new_state("first")),
            api_workflow.invoke("second", new_state("second")),
        )
        assert first["session_id"] == "first"
        assert second["session_id"] == "second"


async def test_rest_speech_never_reads_the_full_identifier_to_tts(api, answers, monkeypatch):
    state = await _complete(api, answers)
    spoken = []

    async def capture(text, language):
        spoken.append(text)
        return b"audio"

    monkeypatch.setattr("app.api.rest.tts.speak", capture)
    result = await api.get(f"/api/sessions/{state['session_id']}/speech")
    assert result.status_code == 200
    assert spoken
    assert answers["mobile"] not in "".join(spoken).replace(" ", "")
    assert answers["mobile"] not in "".join(spoken).replace(" ", "")


async def test_spoken_confirmation_after_ready_does_not_regenerate(chat, answers, llm_spy):
    conversation = chat()
    await conversation.answer_all(answers)
    ready = await conversation.say("yes")
    count = llm_spy.count
    repeated = await conversation.say("yes")
    assert repeated["status"] == "ready"
    assert repeated["document"] == ready["document"]
    assert llm_spy.count == count


# ---------------------------------------------------------------------------
# Hearing something again
# ---------------------------------------------------------------------------
#
# Two controls added at the citizen's request: a speaker beside each thing
# the assistant said, and a Read button on the finished petition. Both come
# through the same endpoint, and both are PRESENTATION — nothing they reach
# touches the record, the document or the workflow.

async def test_a_past_question_can_be_said_again(api, answers, monkeypatch):
    state = await _complete(api, answers)
    spoken = []

    async def capture(text, language):
        spoken.append(text)
        return b"audio"

    monkeypatch.setattr("app.api.rest.tts.speak", capture)
    result = await api.get(f"/api/sessions/{state['session_id']}/speech?turn=0")

    assert result.status_code == 200
    assert spoken and spoken[0].strip()


async def test_only_the_assistants_side_is_addressable(api, answers):
    """`turn` indexes the ASSISTANT's turns, so no index reaches one of the
    citizen's. Their own sentences are not something a speaker icon beside a
    question should be able to play into the room.

    Their ANSWERS are still spoken, because the assistant quotes them back
    when it asks "is all of this correct?" — that is what a read-back is
    for, and the test below is the rule that actually matters: identifiers
    are described, never recited."""
    state = await _complete(api, answers)
    sid = state["session_id"]
    view = (await api.get(f"/api/sessions/{sid}")).json()
    assistant_turns = len([t for t in view["transcript"] if t["who"] == "assistant"])
    citizen_turns = len([t for t in view["transcript"] if t["who"] == "citizen"])

    assert citizen_turns, "nothing to be protected from"
    reachable = 0
    for turn in range(len(view["transcript"]) + 5):
        if (await api.get(f"/api/sessions/{sid}/speech?turn={turn}")).status_code == 404:
            break
        reachable += 1

    assert reachable == assistant_turns


async def _generated(api, answers):
    """A session with a finished document, which `_complete` stops short of."""
    state = await _complete(api, answers)
    ready = await api.post(f"/api/sessions/{state['session_id']}/confirm")
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "ready"
    return ready.json()


async def test_the_finished_petition_is_read_in_sections(api, answers, monkeypatch):
    """A petition runs past what a speech service takes in one request, and
    a citizen who has heard enough can stop between sections."""
    state = await _generated(api, answers)

    async def capture(text, language):
        return b"audio"

    monkeypatch.setattr("app.api.rest.tts.speak", capture)
    first = await api.get(f"/api/sessions/{state['session_id']}/speech?section=0")

    assert first.status_code == 200
    total = int(first.headers["x-speech-sections"])
    assert total >= 1

    past_the_end = await api.get(
        f"/api/sessions/{state['session_id']}/speech?section={total}")
    assert past_the_end.status_code == 404


async def test_the_document_is_not_recited_with_its_identifiers(api, answers, monkeypatch):
    """The petition on the screen carries the mobile number. The room does
    not need to hear it."""
    state = await _generated(api, answers)
    spoken = []

    async def capture(text, language):
        spoken.append(text)
        return b"audio"

    monkeypatch.setattr("app.api.rest.tts.speak", capture)
    for section in range(20):
        result = await api.get(
            f"/api/sessions/{state['session_id']}/speech?section={section}")
        if result.status_code == 404:
            break

    assert spoken
    assert answers["mobile"] not in "".join(spoken).replace(" ", "")


async def test_asking_for_a_turn_and_a_section_at_once_is_refused(api, answers):
    state = await _complete(api, answers)
    result = await api.get(
        f"/api/sessions/{state['session_id']}/speech?turn=0&section=0")

    assert result.status_code == 400


async def test_reading_changes_nothing(api, answers, monkeypatch):
    """Presentation only. The record must be identical afterwards."""
    state = await _complete(api, answers)
    sid = state["session_id"]

    async def capture(text, language):
        return b"audio"

    monkeypatch.setattr("app.api.rest.tts.speak", capture)
    before = (await api.get(f"/api/sessions/{sid}")).json()
    await api.get(f"/api/sessions/{sid}/speech?turn=0")
    await api.get(f"/api/sessions/{sid}/speech?section=0")
    after = (await api.get(f"/api/sessions/{sid}")).json()

    assert after["status"] == before["status"]
    assert after["letter_text"] == before["letter_text"]
    assert after["transcript"] == before["transcript"]
    assert after["version"] == before["version"]
