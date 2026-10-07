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


# ---------------------------------------------------------------------------
# A petition, not every session anybody ever started
# ---------------------------------------------------------------------------

async def test_the_list_holds_petitions_not_abandoned_drafts(api):
    """REPORTED FROM THE PORTAL. The dashboard showed 412 rows of which 12
    were petitions. The other 400 were sessions abandoned at the first
    question — no reference, no petitioner, no subject — so an officer
    opened the portal onto four hundred blank rows with the real work
    somewhere among them.

    It was also why the page took seconds to arrive: every one of those ids
    was a full checkpoint load, and four hundred of them were loaded to
    produce nothing worth showing.

    A PETITION IS A SESSION THAT PRODUCED A DOCUMENT. That is what the
    citizen's own list means by the word, and the two now agree.
    """
    client, sid, workflow = api

    # Somebody opened the form and walked away.
    for _ in range(3):
        draft = str(uuid.uuid4())
        await workflow._compiled.aupdate_state(
            workflow.config(draft), {**new_state(draft), "status": "collecting"},
            as_node="verify")

    await login(client)
    rows = (await client.get("/api/officer/petitions")).json()["items"]

    assert [r["id"] for r in rows] == [sid]


async def test_no_row_arrives_without_the_things_a_row_shows(api):
    """The table has columns for a reference, a petitioner and a subject.
    A row with none of them is a row an officer cannot act on."""
    client, sid, _ = api
    await login(client)
    rows = (await client.get("/api/officer/petitions")).json()["items"]

    assert rows
    for row in rows:
        assert (row.get("reference") or "").strip(), row
        assert (row.get("petitioner_name") or "").strip(), row


async def test_acknowledgements_come_from_the_same_set(api):
    """They are derived from the petition list, so a receipt attached to a
    draft that was never finished is not an office record either."""
    client, sid, workflow = api

    draft = str(uuid.uuid4())
    await workflow._compiled.aupdate_state(
        workflow.config(draft), {**new_state(draft), "status": "collecting"},
        as_node="verify")

    await login(client)
    petitions = (await client.get("/api/officer/petitions")).json()["items"]
    acks = (await client.get("/api/officer/acknowledgements")).json()["items"]
    known = {p["id"] for p in petitions}

    assert draft not in known
    for ack in acks:
        assert ack["petition_id"] in known, ack


@pytest.fixture
async def before_any_officer_exists(graph, tmp_path, monkeypatch):
    """The state every deployment is in until somebody runs create_officer.

    The live service was still in it on 5 October 2026, which is how this got
    noticed: `/api/petitions` answered an anonymous caller with 31 petitions,
    petitioner names included, and handed over the session id of each one.
    """
    settings = get_settings().model_copy(update={"data_dir": tmp_path})
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    app = FastAPI()
    for router in (officer.router, catalog.router, rest.router):
        app.include_router(router)
    workflow = Workflow(graph, None)
    app.state.workflow = workflow

    async def seed(session_id, name, reference):
        await workflow._compiled.aupdate_state(
            workflow.config(session_id),
            {
                **new_state(session_id),
                "status": "ready",
                "confirmed": True,
                "fields": {"applicant_name": name, "grievance": "A broken pipe.",
                           "address": "Some Street"},
                "letter_text": "Subject: A broken pipe",
                "document": {"reference": reference, "docx": "missing.docx"},
                "verification": {"ok": True},
            },
            as_node="verify",
        )

    stranger = str(uuid.uuid4())
    await seed(stranger, "Somebody Else", "CP-STRANGER-1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, stranger, seed


class TestTheCatalogueNeverWidensToEverybody:
    """Listing and deleting are scoped to the calling browser at all times.

    Before an officer account exists `citizen_scope` answers "do not restrict",
    which is deliberate and still true for opening a petition by an id the
    caller already holds. Applied to the catalogue it meant any caller could
    enumerate every petition on the service and then delete all of them, which
    takes the checkpoints, the documents and the attachments with no undo.
    """

    async def test_a_stranger_is_shown_nothing(self, before_any_officer_exists):
        client, _, _ = before_any_officer_exists
        body = (await client.get("/api/petitions")).json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_a_stranger_cannot_delete_what_it_cannot_see(self, before_any_officer_exists):
        client, stranger, _ = before_any_officer_exists
        response = await client.post("/api/petitions/delete", json={"session_ids": [stranger]})
        assert response.status_code == 403

    async def test_a_browser_still_gets_its_own_petition_back(self, before_any_officer_exists):
        client, stranger, seed = before_any_officer_exists
        mine = (await client.post("/api/sessions", json={"language": "en"})).json()["session_id"]
        await seed(mine, "Test Citizen", "CP-MINE-1")
        rows = (await client.get("/api/petitions")).json()["items"]
        assert [row["session_id"] for row in rows] == [mine]
        assert stranger not in {row["session_id"] for row in rows}

    async def test_a_browser_may_delete_its_own(self, before_any_officer_exists):
        client, _, seed = before_any_officer_exists
        mine = (await client.post("/api/sessions", json={"language": "en"})).json()["session_id"]
        await seed(mine, "Test Citizen", "CP-MINE-2")
        response = await client.post("/api/petitions/delete", json={"session_ids": [mine]})
        assert response.status_code == 200

    async def test_opening_a_petition_by_id_is_left_alone(self, before_any_officer_exists):
        """Deliberately NOT closed here.

        Session recording shipped on 23 September 2026 and the oldest petitions
        on the live service are older than that, so they belong to no browser.
        Closing this door too would lock their owners out of their own
        bookmarks; provisioning the first officer is what closes it.
        """
        client, stranger, _ = before_any_officer_exists
        assert (await client.get(f"/api/sessions/{stranger}")).status_code == 200
