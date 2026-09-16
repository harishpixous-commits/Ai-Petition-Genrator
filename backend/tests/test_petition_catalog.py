"""Saved-petition navigation reads durable sessions, not a browser's history."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI

from app.api.catalog import router
from app.config import Settings
from app.graph.state import new_state
from app.graph.workflow import Workflow, workflow_lifespan
from app.services.petition_catalog import PetitionCatalog


def _saved(session_id: str, *, name: str = "Ravi Kumar", language: str = "en",
           created_at: str = "2026-09-10T09:00:00+00:00", version: int = 1,
           subject: str = "Repair the blocked drain", department: str = "Public Works",
           category: str = "Sanitation") -> dict:
    return {
        **new_state(session_id, language),
        "fields": {"applicant_name": name, "age": 45, "mobile": "9876543210",
                   "aadhaar": "234567890124", "address": "Private address not for the list",
                   "grievance": "PRIVATE COMPLAINT DETAILS MUST NEVER APPEAR IN A CATALOG"},
        "status": "ready", "confirmed": True,
        "created_at": created_at, "updated_at": created_at,
        "letter_text": f"Subject: {subject}\nPrivate body",
        "composition": {"subject": "Older subject before manual edit"},
        "analysis": {"department": {"value": department}, "petition_category": {"value": category}},
        "document": {"reference": f"PET-2026-{session_id}", "docx": "C:/private/petition.docx",
                     "pdf": "C:/private/petition.pdf", "generated_at": created_at, "version": version},
        "verification": {"ok": True},
        "attachments": [{"filename": "private-filename.pdf", "stored_name": "private-path"}],
        "turns": [{"who": "citizen", "text": "Private conversation"}],
    }


@pytest.fixture
def catalog_workflow(graph):
    return Workflow(graph, None)


@pytest.fixture
async def catalog_api(catalog_workflow):
    app = FastAPI()
    app.include_router(router)
    app.state.workflow = catalog_workflow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        yield client


async def _list(client, **params):
    response = await client.get("/api/petitions", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _persist(workflow, session_id, patch):
    # Simulate durable node checkpoints without generating files: explicitly
    # identify the node because this fixture never executes a graph turn.
    await workflow._compiled.aupdate_state(workflow.config(session_id), patch, as_node="verify")


async def test_catalog_is_empty_before_any_successful_generation(catalog_api, catalog_workflow):
    await _persist(catalog_workflow, "draft", new_state("draft"))
    await _persist(catalog_workflow, "failed", {**_saved("failed"), "status": "failed"})
    result = await _list(catalog_api)
    assert result["items"] == []
    assert result["total"] == result["total_saved"] == result["pages"] == 0
    assert result["has_next"] is False


async def test_legacy_petition_is_listed_once_and_only_safe_metadata_leaves_catalog(
    catalog_api, catalog_workflow,
):
    await _persist(catalog_workflow, "legacy", _saved("legacy", subject="Restore phone 9876543210"))
    await _persist(catalog_workflow, "legacy", {"updated_at": "2026-09-12T09:00:00+00:00"})
    result = await _list(catalog_api)
    assert result["total_saved"] == 1
    row = result["items"][0]
    assert row["reference"] == "PET-2026-legacy"
    assert row["subject"] == "Restore phone [PHONE REDACTED]"
    assert row["version"] == 1
    assert row["status_label"] == "Generated"
    assert row["document"]["docx_url"] == "/api/sessions/legacy/document.docx"
    serialized = json.dumps(result)
    for private in ("234567890124", "9876543210", "Private address", "PRIVATE COMPLAINT",
                    "private-filename", "private-path", "Private conversation", "C:/private"):
        assert private not in serialized


async def test_generated_session_remains_listed_while_a_correction_is_pending(
    catalog_api, catalog_workflow,
):
    await _persist(catalog_workflow, "editing", _saved("editing"))
    await _persist(catalog_workflow, "editing", {
        "status": "confirming", "confirmed": False, "document": None,
        "letter_text": None, "composition": None, "verification": None,
        "updated_at": "2026-09-15T10:00:00+00:00",
    })
    result = await _list(catalog_api, status="draft")
    assert result["total"] == 1
    row = result["items"][0]
    assert row["reference"] == "PET-2026-editing"
    assert row["subject"] == "Repair the blocked drain"
    assert row["status"] == "confirming"
    assert row["status_label"] == "Draft"
    assert row["document"] is None
    assert row["updated_at"] == "2026-09-15T10:00:00+00:00"


async def test_regenerated_version_updates_same_row_and_status_filter(catalog_api, catalog_workflow):
    await _persist(catalog_workflow, "same", _saved("same"))
    assert (await _list(catalog_api))["items"][0]["version"] == 1
    await _persist(catalog_workflow, "same", _saved("same", version=3, subject="A new subject"))
    result = await _list(catalog_api, status="updated")
    assert result["total"] == result["total_saved"] == 1
    assert result["items"][0]["version"] == 3
    assert result["items"][0]["subject"] == "A new subject"
    assert result["items"][0]["status_label"] == "Updated"
    assert (await _list(catalog_api, status="generated"))["total"] == 0
    assert (await _list(catalog_api, status="ready"))["total"] == 1


async def test_manual_edit_with_warning_is_visible_and_downloadable(catalog_api, catalog_workflow):
    await _persist(catalog_workflow, "manual", {
        **_saved("manual", version=2), "verification": {"ok": False, "hand_edited": True},
    })
    row = (await _list(catalog_api))["items"][0]
    assert row["document"]["docx_url"]
    assert row["verification"] == {"ok": False}
    assert row["attention_required"] is True


@pytest.fixture
async def searchable(catalog_workflow):
    await _persist(catalog_workflow, "one", _saved("one", name="Ravi Kumar",
        created_at="2026-09-10T00:00:00+00:00", department="Public Works", category="Roads"))
    await _persist(catalog_workflow, "two", _saved("two", name="Meena Devi", language="ta",
        created_at="2026-09-11T23:59:59+00:00", department="Revenue", category="Land"))
    await _persist(catalog_workflow, "three", _saved("three", name="Kumar Ravi",
        created_at="2026-09-12T12:00:00+00:00", version=2, department="Revenue", category="Land"))
    await _persist(catalog_workflow, "one", {"updated_at": "2026-09-15T09:00:00+00:00"})


@pytest.mark.parametrize(("params", "sessions"), [
    ({"q": "meena"}, ["two"]),
    ({"reference": "2026-ONE"}, ["one"]),
    ({"petitioner_name": "ravi"}, ["three", "one"]),
    ({"department": "Revenue", "category": "Land"}, ["three", "two"]),
    ({"language": "ta"}, ["two"]),
    ({"date_from": "2026-09-10", "date_to": "2026-09-11"}, ["two", "one"]),
    ({"status": "updated"}, ["three"]),
    ({"sort": "oldest"}, ["one", "two", "three"]),
    ({"sort": "updated"}, ["one", "three", "two"]),
])
async def test_search_filters_and_sorting(catalog_api, searchable, params, sessions):
    result = await _list(catalog_api, **params)
    assert [item["session_id"] for item in result["items"]] == sessions
    assert result["total"] == len(sessions)
    assert result["total_saved"] == 3
    assert result["filters"]["departments"] == ["Public Works", "Revenue"]


async def test_pagination_does_not_repeat_items(catalog_api, searchable):
    first = await _list(catalog_api, page_size=2)
    second = await _list(catalog_api, page=2, page_size=2)
    outside = await _list(catalog_api, page=3, page_size=2)
    assert first["pages"] == second["pages"] == 2
    assert first["has_next"] is True
    assert second["has_next"] is False
    ids = [item["session_id"] for item in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 3
    assert outside["items"] == []


@pytest.mark.parametrize("params", [
    {"date_from": "2026-09-12", "date_to": "2026-09-10"},
    {"date_from": "invalid"}, {"page": 0}, {"page_size": 101}, {"sort": "unknown"},
    {"language": "unsupported"},
])
async def test_invalid_queries_are_rejected(catalog_api, params):
    assert (await catalog_api.get("/api/petitions", params=params)).status_code == 422


async def test_sqlite_catalog_survives_service_restart_and_incremental_edits(tmp_path):
    settings = Settings(data_dir=tmp_path)
    async with workflow_lifespan(settings) as workflow:
        await _persist(workflow, "persisted", _saved("persisted"))
        catalog = PetitionCatalog(workflow._saver)
        first = await catalog.list_petitions()
        cursor = catalog._cursor
        assert first["total"] == 1
        assert (await catalog.list_petitions())["total"] == 1
        assert catalog._cursor == cursor
        await _persist(workflow, "persisted", {"status": "confirming", "document": None})
        edited = await catalog.list_petitions()
        assert edited["items"][0]["status"] == "confirming"
        assert edited["items"][0]["document"] is None
        assert catalog._cursor > cursor

    async with workflow_lifespan(settings) as reopened:
        fresh_catalog = PetitionCatalog(reopened._saver)
        restored = await fresh_catalog.list_petitions()
        assert restored["total"] == 1
        assert restored["items"][0]["reference"] == "PET-2026-persisted"
        assert restored["items"][0]["status_label"] == "Draft"


async def test_sqlite_initial_scan_handles_more_than_one_checkpoint_batch(tmp_path):
    settings = Settings(data_dir=tmp_path)
    async with workflow_lifespan(settings) as workflow:
        await _persist(workflow, "old-generated", _saved("old-generated"))
        for index in range(130):
            await _persist(workflow, "working", {**new_state("working"), "utterance": str(index)})
        result = await PetitionCatalog(workflow._saver).list_petitions()
        assert result["total"] == 1
        assert result["items"][0]["session_id"] == "old-generated"
