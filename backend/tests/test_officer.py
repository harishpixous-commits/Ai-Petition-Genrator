import time
import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.api import catalog, officer, rest
from app.config import get_settings
from app.graph.state import new_state
from app.graph.workflow import Workflow
from app.services import officer_store as store


@pytest.fixture
async def api(graph, tmp_path, monkeypatch):
    settings = get_settings().model_copy(update={"data_dir": tmp_path})
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    app = FastAPI()
    for router in (officer.router, catalog.router, rest.router):
        app.include_router(router)
    workflow = Workflow(graph, None)
    app.state.workflow = workflow
    store.provision("reviewer", "Review Officer", "test-password-1234")
    sid = str(uuid.uuid4())
    state = {
        **new_state(sid),
        "status": "ready",
        "confirmed": True,
        "fields": {
            "applicant_name": "Test Citizen",
            "grievance": "The light is broken. Please repair it.",
            "address": "Test Street",
        },
        "letter_text": "Subject: Repair the light\nPlease repair it.",
        "document": {"reference": "CP-TEST-1", "docx": "missing.docx"},
        "verification": {"ok": True},
        "analysis": {"department": {"value": "Invented authority", "sources": []}},
    }
    await workflow._compiled.aupdate_state(workflow.config(sid), state, as_node="verify")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, sid, workflow


async def login(client):
    response = await client.post(
        "/api/officer/login", json={"username": "reviewer", "password": "test-password-1234"}
    )
    assert response.status_code == 200, response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]


async def test_auth_expiry_logout(api):
    client, sid, _ = api
    for path in [
        "/me",
        "/petitions",
        "/acknowledgements",
        f"/petitions/{sid}",
        f"/petitions/{sid}/document.docx",
        f"/petitions/{sid}/attachments/file",
    ]:
        assert (await client.get("/api/officer" + path)).status_code == 401
    assert (
        await client.post("/api/officer/login", json={"username": "reviewer", "password": "wrong"})
    ).status_code == 401
    await login(client)
    token = client.cookies.get(store.COOKIE)
    assert (await client.post("/api/officer/logout")).status_code == 204
    client.cookies.set(store.COOKIE, token)
    assert (await client.get("/api/officer/me")).status_code == 401
    client.cookies.clear()
    await login(client)
    with store.database() as db:
        db.execute("UPDATE officer_sessions SET expires=?", (time.time() - 1,))
    assert (await client.get("/api/officer/petitions")).status_code == 401


async def test_real_records_private_notes_and_csrf(api):
    client, sid, _ = api
    assert (await client.get("/api/petitions")).json()["items"] == []
    await login(client)
    rows = (await client.get("/api/officer/petitions")).json()["items"]
    assert rows[0]["id"] == sid
    assert rows[0]["department"] == ""
    path = f"/api/officer/petitions/{sid}/review"
    body = {"status": "Under Review", "note": "Private officer note"}
    assert (
        await client.post(path, json=body, headers={"Origin": "https://evil.example"})
    ).status_code == 403
    assert (await client.post(path, json=body)).status_code == 200
    result = (await client.get(f"/api/officer/petitions/{sid}")).json()
    assert result["status"] == "Under Review"
    assert result["notes"][0]["text"] == "Private officer note"
    assert result["analysis"]["department"] is None
    assert result["summary"] == "The light is broken. Please repair it."
    assert (await client.get(f"/api/sessions/{sid}")).status_code == 403
    assert (
        await client.post("/api/petitions/delete", json={"session_ids": [sid]})
    ).status_code == 403


async def test_rate_limit(api):
    client, _, _ = api
    for _ in range(10):
        assert (
            await client.post(
                "/api/officer/login", json={"username": "reviewer", "password": "wrong"}
            )
        ).status_code == 401
    assert (
        await client.post(
            "/api/officer/login", json={"username": "reviewer", "password": "test-password-1234"}
        )
    ).status_code == 429


async def test_citizen_cookie_and_acknowledgements(api):
    client, sid, workflow = api
    response = await client.post("/api/sessions", json={"language": "en"})
    assert response.status_code == 201
    assert "petition_citizen" in client.cookies
    await workflow._compiled.aupdate_state(
        workflow.config(sid),
        {
            "attachments": [
                {
                    "attachment_id": "receipt",
                    "filename": "receipt.pdf",
                    "stored_name": "receipt.pdf",
                    "content_type": "application/pdf",
                    "size": 10,
                    "kind": "acknowledgement",
                    "confirmed": True,
                    "extracted": {
                        "reference_number": {"value": "ACK-123"},
                        "department": {"value": "Recorded Department"},
                    },
                }
            ]
        },
        as_node="verify",
    )
    await login(client)
    rows = (await client.get("/api/officer/acknowledgements")).json()["items"]
    assert rows[0]["reference"] == "ACK-123"
    assert rows[0]["petition_id"] == sid
    assert (await client.get("/api/officer/acknowledgements/" + rows[0]["id"])).status_code == 200
    assert (await client.get("/api/officer/acknowledgements/missing")).status_code == 404


def test_grounding():
    source = {
        "document_title": "Official document",
        "excerpt": "Relevant passage",
        "authority": "official",
    }
    result = officer.grounded(
        {
            "department": {"value": "Verified department", "sources": [source]},
            "applicable_acts": [{"value": "Unsupported Act", "sources": []}],
        }
    )
    assert result["department"]["value"] == "Verified department"
    assert result["applicable_acts"] == []
    assert (
        officer.grounded(
            {"department": result["department"], "conflicts": [{"resolution": "undetermined"}]}
        ).get("department")
        is None
    )
