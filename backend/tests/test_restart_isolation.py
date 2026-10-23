"""Start Over leaves nothing of the previous petition on the record.

THE INCIDENT THIS CLOSES. The restart branch in `graph/nodes.py` reset the
fields, the composition and the document — but left `attachments`,
`attachments_offered`, `attachments_done`, `analysis`, `emblem`,
`submitted_at` and `translation_origin` in place, AND did not delete the
attachment files on disk. The next petition on the same session_id
inherited the earlier citizen's enclosures and, through
`translation_origin`, the earlier citizen's own-language text. Every one of
those is a privacy and provenance failure the SRS §3 and §10.2 forbid.

What this fixture pins:

  * the state keys above are cleared;
  * `attachment_store.discard_session` is called with the real session_id;
  * `turns` and `corrections` are also cleared the way they always were;
  * no new chat turn from the previous citizen appears after the restart.

These tests go through the real graph with a seeded state. No model is
called; the restart branch is an intent handler that runs before the
language-model path.
"""

from __future__ import annotations

import pytest

from app.graph.state import new_state
from app.graph.workflow import Workflow
from app.services import attachment_store


@pytest.fixture
def workflow(graph):
    return Workflow(graph, None)


@pytest.fixture
def discard_calls(monkeypatch):
    calls: list[str] = []

    def fake_discard(session_id, settings=None):
        calls.append(str(session_id))

    monkeypatch.setattr(attachment_store, "discard_session", fake_discard)
    return calls


async def _seed_a_busy_session(workflow, session_id):
    """A session that is deep into its first petition, with everything the
    SRS says must not leak into a new one."""
    state = {
        **new_state(session_id, "en"),
        "status": "ready",
        "confirmed": True,
        "fields": {"applicant_name": "First Citizen",
                   "address": "22 Older Street",
                   "grievance": "The old lamp is broken."},
        "attachments": [{"attachment_id": "a1",
                         "filename": "aadhaar.pdf",
                         "stored_name": "stored-aadhaar.pdf"}],
        "attachments_offered": True,
        "attachments_done": True,
        "analysis": {"department": {"value": "Streetlights"}},
        "emblem": {"align": "left", "pages": "first"},
        "submitted_at": "2026-10-10T09:00:00+00:00",
        "translation_origin": {"text": "Tamil original",
                               "language": "ta"},
        "letter_text": "Older petition body",
        "document": {"reference": "PET-OLD", "docx": "old.docx", "version": 2},
        "document_version": 2,
        "petition_reference": "PET-OLD",
    }
    await workflow._compiled.aupdate_state(
        workflow.config(session_id), state, as_node="verify")


async def test_restart_clears_the_fields_and_the_output(workflow):
    await _seed_a_busy_session(workflow, "sid-1")
    after = await workflow.invoke(
        "sid-1",
        {"utterance": "", "intent": "restart", "understood_by": "form",
         "_extracted": {}, "_corrections": {}, "_correction_target": None,
         "_edited_text": None, "_skip_understand": True},
    )
    assert after["status"] == "collecting"
    assert after.get("fields") == {}
    assert after.get("letter_text") is None
    assert after.get("document") is None
    assert after.get("petition_reference") is None
    assert after.get("document_version") == 0


async def test_restart_clears_every_leak_class_the_bug_left_behind(workflow, discard_calls):
    await _seed_a_busy_session(workflow, "sid-2")
    after = await workflow.invoke(
        "sid-2",
        {"utterance": "", "intent": "restart", "understood_by": "form",
         "_skip_understand": True, "_extracted": {}, "_corrections": {},
         "_correction_target": None, "_edited_text": None},
    )
    assert after.get("attachments") == []
    assert after.get("attachments_offered") is False
    assert after.get("attachments_done") is False
    assert after.get("analysis") is None
    assert after.get("emblem") is None
    assert after.get("submitted_at") is None
    assert after.get("translation_origin") is None


async def test_restart_actually_deletes_the_attachment_files(workflow, discard_calls):
    await _seed_a_busy_session(workflow, "sid-3")
    await workflow.invoke(
        "sid-3",
        {"utterance": "", "intent": "restart", "understood_by": "form",
         "_skip_understand": True, "_extracted": {}, "_corrections": {},
         "_correction_target": None, "_edited_text": None},
    )
    assert discard_calls == ["sid-3"], (
        "the real attachment_store.discard_session must be called "
        "with the exact session_id — the stored files from the previous "
        "petition must leave the disk")


async def test_old_conversation_messages_do_not_reappear(workflow):
    """After a restart the next turn must not carry the previous petition's
    chat. The reply is the restart message and nothing else from the past.

    THE SPECIFIC REGRESSION the Phase 1 brief asks for: old conversation
    messages used to remain after reset. This holds that line.
    """
    session_id = "sid-4"
    await _seed_a_busy_session(workflow, session_id)
    # Install a long previous conversation. `as_node` because an existing
    # session has an ambiguous "which node wrote this" otherwise, and
    # LangGraph refuses without being told.
    await workflow._compiled.aupdate_state(
        workflow.config(session_id),
        {"turns": [{"who": "citizen", "text": "I complained about the lamp."},
                   {"who": "assistant", "text": "OK, I will note that."}]},
        as_node="confirm",
    )
    after = await workflow.invoke(
        session_id,
        {"utterance": "", "intent": "restart", "understood_by": "form",
         "_skip_understand": True, "_extracted": {}, "_corrections": {},
         "_correction_target": None, "_edited_text": None},
    )
    # The restart appends ONE assistant turn (the "Start over" acknowledgement).
    # Nothing from the previous petition's dialogue carries over.
    for existing_turn in after.get("turns", []):
        assert "lamp" not in existing_turn.get("text", "").lower()
        assert "complained" not in existing_turn.get("text", "").lower()
