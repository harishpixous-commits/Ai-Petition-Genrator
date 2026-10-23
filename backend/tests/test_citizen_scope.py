"""Who may reach which petition — the one bar that stands with or without an officer.

THE INCIDENT THIS GUARDS. Before 23 September 2026 session recording did not
exist. The author then added one but kept a "no officer provisioned → do not
restrict" branch for single-machine deployments. On 5 October 2026 that branch
let an anonymous caller list every saved petition on the live service (31
petitions with petitioner names), open each one by the id the listing handed
over, and delete the lot through `remove_sessions`. The listing path moved to
`owned_sessions`; the opening path remained fail-open and is what these tests
close.

THE RULE, with or without an officer:

  * own session       → reachable
  * grandfathered     → reachable (no row at all, pre-23-September bookmarks)
  * someone else's    → DENIED

These are offline tests of `can_access`, `citizen_scope` and
`require_citizen_session`. No workflow is started; no network call is made.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.services import officer_store

BROWSER = "test-browser-a"
OTHER_BROWSER = "test-browser-b"


@pytest.fixture(autouse=True)
def _isolated_officer_store(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path)
    settings.ensure_dirs()
    monkeypatch.setattr(officer_store, "get_settings", lambda: settings)
    return settings


def _record_session(session_id: str, owner_cookie: str) -> None:
    with officer_store.database() as db:
        db.execute(
            "INSERT OR IGNORE INTO citizen_sessions VALUES(?,?)",
            (session_id, officer_store.digest(owner_cookie)),
        )


class _FakeRequest:
    """Minimal duck of fastapi.Request for the officer_store helpers."""

    def __init__(self, cookie_value: str | None, path_session_id: str | None = None):
        self.cookies = {"petition_citizen": cookie_value} if cookie_value else {}
        self.path_params = {"session_id": path_session_id} if path_session_id else {}


class TestCanAccess:
    def test_a_browser_may_reach_a_session_it_owns(self):
        _record_session("own-session", BROWSER)
        request = _FakeRequest(BROWSER)
        assert officer_store.can_access(request, "own-session")

    def test_a_browser_may_reach_a_session_recorded_against_no_owner(self):
        """The grandfather clause. Pre-September bookmarks have no row at all.
        Closing them locks their owners out of their own saved petitions, and
        a new owner-less row cannot be produced from a browser."""
        # No _record_session() call for "legacy-session".
        request = _FakeRequest(BROWSER)
        assert officer_store.can_access(request, "legacy-session")

    def test_a_browser_may_not_reach_another_browsers_session(self):
        _record_session("someone-elses", OTHER_BROWSER)
        request = _FakeRequest(BROWSER)
        assert not officer_store.can_access(request, "someone-elses")

    def test_a_browser_with_no_cookie_still_cannot_take_someone_elses_session(self):
        _record_session("owned-elsewhere", OTHER_BROWSER)
        request = _FakeRequest(cookie_value=None)
        assert not officer_store.can_access(request, "owned-elsewhere")

    def test_someone_elses_session_stays_closed_through_officer_provisioning(self):
        """Nothing about setting up an office may widen access."""
        _record_session("owned-elsewhere", OTHER_BROWSER)
        request = _FakeRequest(BROWSER)
        assert not officer_store.can_access(request, "owned-elsewhere")

        officer_store.provision("supervisor", "A Supervisor", "passphrase-12345")
        assert not officer_store.can_access(request, "owned-elsewhere")

    def test_provisioning_an_officer_closes_the_grandfather_carve_out(self):
        """A legacy bookmark is reachable in single-machine mode. Once an
        office is set up, every session is either owned or denied: an
        officer-created record with no citizen_sessions row must NOT be
        read as a pre-September bookmark and therefore allowed."""
        request = _FakeRequest(BROWSER)
        assert officer_store.can_access(request, "legacy-session")

        officer_store.provision("supervisor", "A Supervisor", "passphrase-12345")
        assert not officer_store.can_access(request, "legacy-session")


class TestRequireCitizenSession:
    def test_an_owned_session_is_allowed_through(self):
        _record_session("own-session", BROWSER)
        officer_store.require_citizen_session(_FakeRequest(BROWSER, "own-session"))

    def test_a_grandfathered_session_is_allowed_through(self):
        officer_store.require_citizen_session(_FakeRequest(BROWSER, "legacy-session"))

    def test_someone_elses_session_is_refused_with_403(self):
        _record_session("owned-elsewhere", OTHER_BROWSER)
        with pytest.raises(HTTPException) as info:
            officer_store.require_citizen_session(
                _FakeRequest(BROWSER, "owned-elsewhere"))
        assert info.value.status_code == 403

    def test_a_request_with_no_session_id_in_path_is_a_no_op(self):
        """Routes that do not take a session_id (listing, health) must not
        raise here. The guard runs on every REST request through FastAPI's
        Depends, so a false positive here would 403 the whole API."""
        officer_store.require_citizen_session(_FakeRequest(BROWSER))


class TestCitizenScopeNoLongerAnswersNone:
    def test_scope_is_the_owned_set_before_any_officer(self):
        _record_session("own-session", BROWSER)
        _record_session("owned-elsewhere", OTHER_BROWSER)

        own = officer_store.citizen_scope(_FakeRequest(BROWSER))

        assert "own-session" in own
        assert "owned-elsewhere" not in own

    def test_scope_never_returns_none(self):
        """The old fail-open sentinel. Nothing in the codebase should rely on
        None any more; this test holds that line."""
        assert officer_store.citizen_scope(_FakeRequest(BROWSER)) is not None
