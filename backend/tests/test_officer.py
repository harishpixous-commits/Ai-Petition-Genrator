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

    # Per SRS §8.5, a conflict is EXPOSED and the grounded findings are
    # still shown. The earlier rule withheld every finding behind one
    # abstention flag, which on the live service hid the District
    # Municipalities Act 1920 §136 (lighting of public streets) behind a
    # ULB Act↔Rules timing conflict that had nothing to do with it.
    conflicted = officer.grounded({
        "department": result["document"]
        if "document" in result else result["department"],
        "conflicts": [{"resolution": "undetermined",
                       "message": "ULB Rules 2023 and ULB Act 1998 both cover this"}],
        "warnings": ["ULB Rules 2023 and ULB Act 1998 both cover this"],
    })
    assert conflicted["department"]["value"] == "Verified department"
    # The analyst-emitted conflict warning rides through; the earlier
    # officer-side append of a GENERIC "Conflicting sources were found"
    # line is gone — on the live screen it rendered right next to the
    # specific "'TN ULB Rules, 2023' and 'TN ULB Act, 1998' both cover
    # this" paragraph and the user saw the same conflict said twice.
    assert any("both cover this" in w for w in conflicted["warnings"])
    assert not any(w.startswith("Conflicting sources were found")
                   for w in conflicted["warnings"]), (
        "the generic duplicate warning must not be appended")


def test_grounding_dedupes_sources_that_cite_the_same_provision():
    """A rule chunked across a page break came through as two separate
    source cards for the same (title, section, page) — rule 312 and
    rule 2 both appeared twice on the user's live screen. The dedup
    keeps the first chunk and folds in the rest."""
    sources = [
        {"document_title": "ULB Rules 2023",
         "section": "312 Removal of television cables from the street light poles",
         "page_number": 275, "authority": "official",
         "excerpt": "312. Removal of television cables..."},
        {"document_title": "ULB Rules 2023",
         "section": "312 Removal of television cables from the street light poles",
         "page_number": 275, "authority": "official",
         "excerpt": "cables should not be removed from the street light poles"},
        {"document_title": "ULB Rules 2023",
         "section": "314 Installation of brackets",
         "page_number": 275, "authority": "official",
         "excerpt": "314. Installation of brackets..."},
    ]
    result = officer.grounded({
        "applicable_rules": [{"value": "ULB Rules 2023", "sources": sources}],
    })
    kept = result["applicable_rules"][0]["sources"]
    assert len(kept) == 2
    assert kept[0]["section"].startswith("312")
    assert kept[1]["section"].startswith("314")


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

    Before an officer account exists `can_access` grandfathers in sessions
    with no owner row — pre-23-September bookmarks that would otherwise be
    unreachable — but the catalogue has never used that carve-out. Listing
    and deleting are and always were `owned_sessions`-scoped. Applied to the
    catalogue, a wildcard scope meant any caller could enumerate every
    petition on the service and then delete all of them, which takes the
    checkpoints, the documents and the attachments with no undo.
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


# --------------------------------------------------------------------- #
# Admin panel. New officers, roles, passwords, deletions — all from the
# portal, no GitHub Actions workflow needed.
# --------------------------------------------------------------------- #


@pytest.fixture
async def admin_api(graph, tmp_path, monkeypatch):
    """A client with one admin (`chief`) and one plain officer (`reviewer`)."""
    settings = get_settings().model_copy(update={"data_dir": tmp_path})
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    app = FastAPI()
    for r in (officer.router, catalog.router, rest.router):
        app.include_router(r)
    workflow = Workflow(graph, None)
    app.state.workflow = workflow
    store.provision("chief", "Chief Admin", "chief-password-1234",
                    role=store.ADMIN)
    store.provision("reviewer", "Review Officer", "reviewer-password-1234")
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test") as client:
        yield client


async def _sign_in(client, username, password):
    response = await client.post(
        "/api/officer/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestTheRoleColumnIsThereAfterUpgrade:
    """Deployments before the admin panel had no role column. The migration
    adds it in place and leaves pre-existing officers as admin — demoting
    them silently would lock the operator out of their own portal."""

    def test_pre_role_deployments_grandfather_to_admin(
            self, tmp_path, monkeypatch):
        import sqlite3
        settings = get_settings().model_copy(update={"data_dir": tmp_path})
        monkeypatch.setattr(store, "get_settings", lambda: settings)
        tmp_path.mkdir(parents=True, exist_ok=True)
        db_path = tmp_path / "officer.sqlite"
        db = sqlite3.connect(db_path)
        db.executescript(
            "CREATE TABLE officers("
            " username TEXT PRIMARY KEY, name TEXT NOT NULL,"
            " salt TEXT NOT NULL, password TEXT NOT NULL,"
            " enabled INTEGER NOT NULL DEFAULT 1);"
        )
        db.execute(
            "INSERT INTO officers VALUES(?,?,?,?,1)",
            ("legacy", "Legacy Operator", "00" * 16, "00" * 32),
        )
        db.commit()
        db.close()

        officers = store.list_officers()
        assert len(officers) == 1
        assert officers[0]["username"] == "legacy"
        assert officers[0]["role"] == store.ADMIN


class TestWhoCanReachTheAdminPanel:
    async def test_a_plain_officer_cannot_list_users(self, admin_api):
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        response = await admin_api.get("/api/officer/users")
        assert response.status_code == 403
        assert "manage_users" in response.json()["detail"]

    async def test_an_admin_can_list_users(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.get("/api/officer/users")
        assert response.status_code == 200
        usernames = {u["username"] for u in response.json()["users"]}
        assert usernames == {"chief", "reviewer"}

    async def test_the_signed_out_browser_is_asked_to_sign_in(self, admin_api):
        response = await admin_api.get("/api/officer/users")
        assert response.status_code == 401


class TestCreatingAnOfficer:
    async def test_an_admin_can_create_a_new_officer(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.post("/api/officer/users", json={
            "username": "ravi",
            "name": "Ravi Kumar",
            "password": "a-password-with-plenty",
            "role": "officer",
        })
        assert response.status_code == 201, response.text
        row = response.json()
        assert row["username"] == "ravi"
        assert row["role"] == "officer"
        await admin_api.post("/api/officer/logout")
        confirm = await admin_api.post("/api/officer/login", json={
            "username": "ravi", "password": "a-password-with-plenty",
        })
        assert confirm.status_code == 200

    async def test_a_duplicate_username_is_refused(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.post("/api/officer/users", json={
            "username": "reviewer",
            "name": "Someone Else",
            "password": "anotherpassword-plenty",
        })
        assert response.status_code == 400
        assert "already taken" in response.json()["detail"]

    async def test_a_short_password_is_refused(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.post("/api/officer/users", json={
            "username": "shorty",
            "name": "Short",
            "password": "short",
        })
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "bad",
        ["ab", "has space", "has/slash", "unicöde", "_leading"],
    )
    async def test_invalid_usernames_are_refused(self, admin_api, bad):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.post("/api/officer/users", json={
            "username": bad,
            "name": "Bad Name",
            "password": "fine-password-1234",
        })
        assert response.status_code in (400, 422)


class TestEditingAnOfficer:
    async def test_an_admin_can_rename_and_change_a_display_name(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.patch("/api/officer/users/reviewer", json={
            "name": "Reviewer Renamed",
            "new_username": "reviewer2",
        })
        assert response.status_code == 200, response.text
        assert response.json()["username"] == "reviewer2"
        assert response.json()["name"] == "Reviewer Renamed"
        assert {u["username"] for u in store.list_officers()} == {
            "chief", "reviewer2",
        }

    async def test_promoting_and_demoting_an_officer(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        promote = await admin_api.patch(
            "/api/officer/users/reviewer", json={"role": "admin"})
        assert promote.status_code == 200
        assert promote.json()["role"] == "admin"
        demote = await admin_api.patch(
            "/api/officer/users/reviewer", json={"role": "officer"})
        assert demote.status_code == 200
        assert demote.json()["role"] == "officer"


class TestTheLastAdminIsProtected:
    async def test_an_admin_cannot_demote_their_own_account(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.patch(
            "/api/officer/users/chief", json={"role": "officer"})
        assert response.status_code == 400
        assert "own account" in response.json()["detail"]

    async def test_the_last_admin_rule_holds_from_a_second_admin(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        await admin_api.patch(
            "/api/officer/users/reviewer", json={"role": "admin"})
        await admin_api.post("/api/officer/logout")
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        await admin_api.patch(
            "/api/officer/users/chief", json={"role": "officer"})
        last = await admin_api.patch(
            "/api/officer/users/reviewer", json={"role": "officer"})
        assert last.status_code == 400
        assert "own account" in last.json()["detail"]

    async def test_the_last_admin_cannot_be_deleted(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.delete("/api/officer/users/chief")
        assert response.status_code == 400
        assert "own account" in response.json()["detail"]


class TestPasswords:
    async def test_an_admin_can_reset_someone_elses_password(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        reset = await admin_api.put(
            "/api/officer/users/reviewer/password",
            json={"new_password": "a-new-reset-password"})
        assert reset.status_code == 204
        bad = await admin_api.post("/api/officer/login", json={
            "username": "reviewer", "password": "reviewer-password-1234"})
        assert bad.status_code == 401
        good = await admin_api.post("/api/officer/login", json={
            "username": "reviewer", "password": "a-new-reset-password"})
        assert good.status_code == 200

    async def test_an_officer_can_change_their_own_password(self, admin_api):
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        response = await admin_api.post("/api/officer/me/password", json={
            "current_password": "reviewer-password-1234",
            "new_password": "the-brand-new-password",
        })
        assert response.status_code == 204
        bad = await admin_api.post("/api/officer/login", json={
            "username": "reviewer", "password": "reviewer-password-1234"})
        assert bad.status_code == 401
        good = await admin_api.post("/api/officer/login", json={
            "username": "reviewer", "password": "the-brand-new-password"})
        assert good.status_code == 200

    async def test_the_current_password_must_be_correct(self, admin_api):
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        response = await admin_api.post("/api/officer/me/password", json={
            "current_password": "wrong-password",
            "new_password": "the-brand-new-password",
        })
        assert response.status_code == 400
        assert "incorrect" in response.json()["detail"].lower()

    async def test_a_new_password_must_differ_from_the_current_one(
            self, admin_api):
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        response = await admin_api.post("/api/officer/me/password", json={
            "current_password": "reviewer-password-1234",
            "new_password": "reviewer-password-1234",
        })
        assert response.status_code == 400


class TestDeletion:
    async def test_an_admin_can_delete_an_officer(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.delete("/api/officer/users/reviewer")
        assert response.status_code == 204
        assert {u["username"] for u in store.list_officers()} == {"chief"}
        try_login = await admin_api.post("/api/officer/login", json={
            "username": "reviewer", "password": "reviewer-password-1234"})
        assert try_login.status_code == 401


# --------------------------------------------------------------------- #
# Role management. Custom roles with any mix of privileges, assigned
# directly to officers, built-ins unchanged.
# --------------------------------------------------------------------- #


class TestTheBuiltinRolesAreSeeded:
    def test_fresh_database_has_admin_and_officer_rows(
            self, tmp_path, monkeypatch):
        settings = get_settings().model_copy(update={"data_dir": tmp_path})
        monkeypatch.setattr(store, "get_settings", lambda: settings)
        tmp_path.mkdir(parents=True, exist_ok=True)
        roles = {r["name"]: r for r in store.list_roles()}
        assert {"admin", "officer"} <= set(roles)
        assert roles["admin"]["builtin"] is True
        assert roles["officer"]["builtin"] is True
        assert store.PRIV_MANAGE_USERS in roles["admin"]["privileges"]
        assert store.PRIV_MANAGE_USERS not in roles["officer"]["privileges"]


class TestWhoCanManageRoles:
    async def test_a_plain_officer_can_see_the_list_but_not_change_it(
            self, admin_api):
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        listed = await admin_api.get("/api/officer/roles")
        assert listed.status_code == 200
        attempt = await admin_api.post("/api/officer/roles", json={
            "name": "village_officer",
            "label": "Village officer",
            "privileges": ["review_petitions"],
        })
        assert attempt.status_code == 403
        assert "manage_roles" in attempt.json()["detail"]

    async def test_an_admin_can_create_a_custom_role(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.post("/api/officer/roles", json={
            "name": "village_officer",
            "label": "Village officer",
            "privileges": ["review_petitions"],
        })
        assert response.status_code == 201, response.text
        row = response.json()
        assert row["name"] == "village_officer"
        assert row["label"] == "Village officer"
        assert row["builtin"] is False
        assert row["privileges"] == ["review_petitions"]

    async def test_the_privilege_catalogue_is_served(self, admin_api):
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        response = await admin_api.get("/api/officer/privileges")
        assert response.status_code == 200
        privs = response.json()["privileges"]
        assert "manage_users" in privs
        assert "review_petitions" in privs


class TestBuiltinRolesAreProtected:
    async def test_admin_role_cannot_be_edited(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.patch(
            "/api/officer/roles/admin", json={"label": "The Chief"})
        assert response.status_code == 400
        assert "built" in response.json()["detail"] or \
               "ship" in response.json()["detail"]

    async def test_officer_role_cannot_be_deleted(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.delete("/api/officer/roles/officer")
        assert response.status_code == 400


class TestRolesInUse:
    async def test_a_role_assigned_to_an_officer_cannot_be_deleted(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        # Create custom role, assign to the reviewer, then try to delete.
        await admin_api.post("/api/officer/roles", json={
            "name": "village_officer",
            "label": "Village officer",
            "privileges": ["review_petitions"],
        })
        await admin_api.patch(
            "/api/officer/users/reviewer",
            json={"role": "village_officer"})
        attempt = await admin_api.delete(
            "/api/officer/roles/village_officer")
        assert attempt.status_code == 400
        assert "assigned" in attempt.json()["detail"]

    async def test_a_role_can_be_deleted_once_members_move_away(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        await admin_api.post("/api/officer/roles", json={
            "name": "village_officer",
            "label": "Village officer",
            "privileges": ["review_petitions"],
        })
        delete_now = await admin_api.delete(
            "/api/officer/roles/village_officer")
        assert delete_now.status_code == 204
        remaining = {r["name"] for r in (
            await admin_api.get("/api/officer/roles")
        ).json()["roles"]}
        assert "village_officer" not in remaining


class TestCustomRoleAssignment:
    async def test_an_officer_assigned_a_custom_role_gets_its_privileges(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        await admin_api.post("/api/officer/roles", json={
            "name": "ward_officer",
            "label": "Ward officer",
            "privileges": ["review_petitions", "delete_petitions"],
        })
        # Create a new officer directly in that role.
        await admin_api.post("/api/officer/users", json={
            "username": "ward1",
            "name": "Ward One",
            "password": "ward-password-1234",
            "role": "ward_officer",
        })
        await admin_api.post("/api/officer/logout")
        await _sign_in(admin_api, "ward1", "ward-password-1234")
        me = (await admin_api.get("/api/officer/me")).json()
        assert me["role"] == "ward_officer"
        assert me["title"] == "Ward officer"
        assert set(me["privileges"]) == {
            "review_petitions", "delete_petitions"
        }

    async def test_a_non_existent_role_is_refused(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.post("/api/officer/users", json={
            "username": "ghost",
            "name": "Ghost",
            "password": "ghost-password-1234",
            "role": "does_not_exist",
        })
        assert response.status_code == 400


class TestCustomAdminLikeRoles:
    async def test_a_custom_role_with_manage_users_satisfies_the_admin_gate(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        await admin_api.post("/api/officer/roles", json={
            "name": "panel_lead",
            "label": "Panel lead",
            "privileges": ["manage_users", "review_petitions"],
        })
        await admin_api.patch(
            "/api/officer/users/reviewer", json={"role": "panel_lead"})
        await admin_api.post("/api/officer/logout")
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        # The reviewer now holds `manage_users` through a non-builtin role.
        response = await admin_api.get("/api/officer/users")
        assert response.status_code == 200

    async def test_the_last_manage_users_cannot_be_removed_from_a_role_in_use(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        # The role must also grant `manage_roles` so the holder can still
        # reach the roles endpoint after being transferred into it.
        await admin_api.post("/api/officer/roles", json={
            "name": "panel_lead",
            "label": "Panel lead",
            "privileges": [
                "manage_users", "manage_roles", "review_petitions"],
        })
        # Transfer the only chief into the custom role, then try to strip
        # manage_users from that role: refused.
        await admin_api.patch(
            "/api/officer/users/chief", json={"role": "panel_lead"})
        strip = await admin_api.patch(
            "/api/officer/roles/panel_lead",
            json={"privileges": ["manage_roles", "review_petitions"]})
        assert strip.status_code == 400
        assert "manage_users" in strip.json()["detail"]


# --------------------------------------------------------------------- #
# Feature switches. The admin's Features tab exposes toggles that turn
# parts of the service on and off; the citizen and officer pages read
# the live state to render.
# --------------------------------------------------------------------- #


class TestFeatureFlags:
    async def test_the_catalogue_is_served_with_every_known_flag(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.get("/api/officer/features")
        assert response.status_code == 200
        names = {f["name"] for f in response.json()["features"]}
        assert "citizen_voice_dictation" in names
        assert "operator_screen" in names
        assert "citizen_multi_language" in names

    async def test_a_plain_officer_can_read_but_not_change_a_flag(
            self, admin_api):
        await _sign_in(admin_api, "reviewer", "reviewer-password-1234")
        get = await admin_api.get("/api/officer/features")
        assert get.status_code == 200
        set_it = await admin_api.patch(
            "/api/officer/features/operator_screen",
            json={"enabled": False})
        assert set_it.status_code == 403
        assert "manage_features" in set_it.json()["detail"]

    async def test_an_admin_can_toggle_a_flag_and_the_change_sticks(
            self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        off = await admin_api.patch(
            "/api/officer/features/citizen_voice_dictation",
            json={"enabled": False})
        assert off.status_code == 200
        assert off.json()["enabled"] is False
        read = await admin_api.get("/api/officer/features")
        row = next(
            f for f in read.json()["features"]
            if f["name"] == "citizen_voice_dictation")
        assert row["enabled"] is False
        # Flip back.
        on = await admin_api.patch(
            "/api/officer/features/citizen_voice_dictation",
            json={"enabled": True})
        assert on.status_code == 200
        assert on.json()["enabled"] is True

    async def test_an_unknown_flag_is_refused(self, admin_api):
        await _sign_in(admin_api, "chief", "chief-password-1234")
        response = await admin_api.patch(
            "/api/officer/features/not_a_real_flag",
            json={"enabled": True})
        assert response.status_code == 404

    async def test_the_citizen_public_endpoint_only_shows_citizen_flags(
            self, admin_api):
        """The citizen page reads /api/features without a login, so it
        must not leak the officer-only flag names."""
        response = await admin_api.get("/api/features")
        assert response.status_code == 200
        names = set(response.json()["features"])
        assert all(n.startswith("citizen_") for n in names)
        assert "operator_screen" not in names
        assert "officer_delete_petition" not in names


# --------------------------------------------------------------------- #
# Admin portal: a separate /admin surface, no longer the review officer
# portal. The front-end file is served at /admin and /admin/login
# redirects a signed-out visitor there.
# --------------------------------------------------------------------- #


class TestTheAdminPortalIsSeparate:
    async def test_officer_portal_no_longer_shows_an_admin_link(self):
        """The officer portal must not advertise an admin link —
        administrators log in through /admin/login instead."""
        from pathlib import Path
        officer_js = (
            Path(__file__).resolve().parent.parent
            / "app" / "static" / "officer.js"
        ).read_text(encoding="utf-8")
        # The actual button text that used to render in the header.
        assert ">Admin panel<" not in officer_js
        # And the legacy /officer/admin URL should redirect to /admin,
        # not render the former admin UI.
        assert 'location.replace("/admin")' in officer_js

    def test_the_admin_shell_file_ships(self):
        """A built container must include admin.html so /admin works."""
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / "app" / "static"
        for name in ("admin.html", "admin.js", "admin.css"):
            assert (root / name).is_file(), f"{name} is missing"
