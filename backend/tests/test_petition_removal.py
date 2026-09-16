"""Deleting a saved petition has to actually delete it.

A citizen who deletes a petition is making a privacy decision, not tidying a
list. These tests hold the service to that: the checkpoint history goes, the
rendered document goes, the attachments go, and the listing stops offering it —
and none of it happens for a petition the citizen did not choose.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.api.catalog import router
from app.config import Settings
from app.graph.state import new_state
from app.graph.workflow import Workflow
from app.services.removal import remove_sessions


def _id() -> str:
    """Session ids are UUIDs, and the removal path validates them as such."""
    return str(uuid.uuid4())


def _saved(session_id: str, *, subject: str = "Repair the blocked drain") -> dict:
    return {
        **new_state(session_id, "en"),
        "fields": {"applicant_name": "Ravi Kumar", "age": 45, "mobile": "9876543210",
                   "aadhaar": "234567890124", "address": "12 Anna Street",
                   "grievance": "The drain outside my house has been blocked for a month."},
        "status": "ready", "confirmed": True,
        "created_at": "2026-09-10T09:00:00+00:00", "updated_at": "2026-09-10T09:00:00+00:00",
        "letter_text": f"Subject: {subject}\nBody",
        "document": {"reference": f"PET-{session_id[:6]}", "docx": "petition.docx",
                     "generated_at": "2026-09-10T09:00:00+00:00", "version": 1},
        "verification": {"ok": True},
    }


@pytest.fixture
def store(tmp_path) -> Settings:
    """A data directory of this test's own, so nothing real is ever at risk."""
    settings = Settings(data_dir=tmp_path)
    settings.ensure_dirs()
    return settings


@pytest.fixture
def workflow(graph):
    return Workflow(graph, None)


@pytest.fixture
async def api(workflow):
    app = FastAPI()
    app.include_router(router)
    app.state.workflow = workflow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client


async def _persist(workflow, session_id, patch):
    await workflow._compiled.aupdate_state(
        workflow.config(session_id), patch, as_node="verify")


async def _list(client):
    response = await client.get("/api/petitions")
    assert response.status_code == 200, response.text
    return response.json()


def _files(settings: Settings, session_id: str) -> tuple:
    """One rendered document and one attachment, as a real petition would have."""
    document = settings.document_dir / f"{session_id}-petition-v1.docx"
    document.write_bytes(b"PK\x03\x04 the citizen's petition")
    attachments = settings.data_dir / "attachments" / session_id
    attachments.mkdir(parents=True, exist_ok=True)
    attachment = attachments / "aadhaar-copy.pdf"
    attachment.write_bytes(b"%PDF-1.4 the citizen's own document")
    return document, attachments


class TestTheDeletionIsReal:
    async def test_the_petition_its_document_and_its_attachments_all_go(
        self, workflow, store,
    ):
        session_id = _id()
        await _persist(workflow, session_id, _saved(session_id))
        document, attachments = _files(store, session_id)
        assert document.is_file() and attachments.is_dir()

        result = await remove_sessions(
            [session_id], saver=workflow._compiled.checkpointer, settings=store)

        assert result.deleted == [session_id]
        assert not document.exists(), "the rendered petition is still on disk"
        assert not attachments.exists(), "the citizen's uploads are still on disk"
        saved = await workflow._compiled.aget_state(workflow.config(session_id))
        assert not saved.values, "the checkpoint history survived the deletion"

    async def test_it_disappears_from_the_saved_list(self, api, workflow, store):
        kept, removed = _id(), _id()
        await _persist(workflow, kept, _saved(kept, subject="Street light"))
        await _persist(workflow, removed, _saved(removed, subject="Blocked drain"))
        assert (await _list(api))["total"] == 2

        response = await api.post("/api/petitions/delete", json={"session_ids": [removed]})
        assert response.status_code == 200, response.text
        assert response.json()["count"] == 1

        listed = await _list(api)
        assert listed["total"] == 1
        assert [item["session_id"] for item in listed["items"]] == [kept]

    async def test_only_the_chosen_petition_is_touched(self, workflow, store):
        """The failure this guards against is the worst one available here."""
        kept, removed = _id(), _id()
        for session_id in (kept, removed):
            await _persist(workflow, session_id, _saved(session_id))
            _files(store, session_id)

        await remove_sessions(
            [removed], saver=workflow._compiled.checkpointer, settings=store)

        assert (store.document_dir / f"{kept}-petition-v1.docx").is_file()
        assert (store.data_dir / "attachments" / kept).is_dir()
        survivor = await workflow._compiled.aget_state(workflow.config(kept))
        assert survivor.values.get("status") == "ready"

    async def test_several_at_once(self, api, workflow, store):
        ids = [_id() for _ in range(3)]
        for session_id in ids:
            await _persist(workflow, session_id, _saved(session_id))

        response = await api.post("/api/petitions/delete", json={"session_ids": ids})
        assert response.status_code == 200
        assert sorted(response.json()["deleted"]) == sorted(ids)
        assert (await _list(api))["total"] == 0


class TestItSaysWhatActuallyHappened:
    async def test_an_id_that_names_nothing_is_reported_as_unknown(self, api):
        response = await api.post(
            "/api/petitions/delete", json={"session_ids": [_id()]})
        body = response.json()
        assert response.status_code == 200
        assert body["deleted"] == [] and body["count"] == 0
        assert len(body["unknown"]) == 1

    async def test_a_deleted_petition_cannot_be_deleted_twice_as_a_success(
        self, api, workflow, store,
    ):
        session_id = _id()
        await _persist(workflow, session_id, _saved(session_id))
        first = await api.post("/api/petitions/delete", json={"session_ids": [session_id]})
        second = await api.post("/api/petitions/delete", json={"session_ids": [session_id]})
        assert first.json()["deleted"] == [session_id]
        assert second.json()["deleted"] == []
        assert second.json()["unknown"] == [session_id]


class TestNothingOutsideThePetitionCanBeReached:
    """`session_ids` arrives in a request body and is used to build paths."""

    @pytest.mark.parametrize("hostile", [
        "../../../../windows/system32/config/sam",
        "..\\..\\sessions.sqlite",
        "*",
        "a/b",
        "",
        "not-a-uuid",
    ])
    async def test_an_id_that_is_not_a_uuid_never_reaches_the_filesystem(
        self, workflow, store, hostile,
    ):
        decoy = store.document_dir / "someone-elses-petition.docx"
        decoy.write_bytes(b"not this one")

        result = await remove_sessions(
            [hostile], saver=workflow._compiled.checkpointer, settings=store)

        assert result.deleted == []
        assert decoy.is_file(), "a malformed id deleted a file it does not name"

    async def test_the_endpoint_will_not_take_an_empty_list_or_an_unbounded_one(self, api):
        empty = await api.post("/api/petitions/delete", json={"session_ids": []})
        assert empty.status_code == 422
        too_many = await api.post(
            "/api/petitions/delete", json={"session_ids": [_id() for _ in range(201)]})
        assert too_many.status_code == 422


class TestDeletionIsNotJustHiding:
    async def test_a_document_left_behind_by_a_lost_session_is_still_removed(
        self, workflow, store,
    ):
        """Checkpoints can be gone while the rendered file remains — and that
        file is the copy carrying the citizen's name, address and grievance."""
        session_id = _id()
        document, attachments = _files(store, session_id)

        result = await remove_sessions(
            [session_id], saver=workflow._compiled.checkpointer, settings=store)

        assert result.unknown == [session_id], "it should not claim to have found a petition"
        assert not document.exists()
        assert not attachments.exists()
