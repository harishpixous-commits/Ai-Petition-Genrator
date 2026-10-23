"""Every HTTP request carries a correlation id, in logs and in a header.

WHAT THIS PROTECTS. SRS §10.4 asks for an audit event that joins actor,
action, target and outcome. Without a correlation id an operator reading the
log cannot tell which `knowledge.timed_out` or which `attachment.rejected`
belongs to the citizen who reported the incident, because the only thread
today is `session_id` and some requests do not have one (`POST /api/sessions`
on its first byte, `/api/health`, early websocket errors).

THREE BEHAVIOURS the middleware must get right and these tests pin:

  * a fresh id is generated per request and echoed in `X-Request-ID`;
  * an id supplied by a trusted upstream (nginx) through `X-Request-ID` is
    accepted when it looks like a plain id;
  * an id that does not look like a plain id — "a\\nb", a 2 KB payload, a
    newline, control characters — is DROPPED and a fresh id is used in its
    place, so a header a client controls cannot inject log lines.

Logs are checked through `caplog`; the response header is checked through a
TestClient. No network, no provider.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.middleware import CorrelationIdMiddleware
from app.logging_setup import current_correlation_id

log = logging.getLogger("app.test.correlation")


@pytest.fixture
def app_with_middleware():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/probe")
    def probe():
        current = current_correlation_id()
        log.info("probe.hit", extra={"seen_correlation_id": current})
        return {"cid": current}

    @app.get("/error")
    def error():
        raise RuntimeError("deliberate")

    return app


class TestAGeneratedId:
    def test_the_response_carries_an_x_request_id(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        response = client.get("/probe")
        assert response.status_code == 200
        assert response.headers.get("x-request-id")

    def test_the_id_is_set_in_the_logging_context(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        response = client.get("/probe")
        assert response.json()["cid"] == response.headers["x-request-id"]

    def test_two_requests_get_two_different_ids(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        assert (
            client.get("/probe").headers["x-request-id"]
            != client.get("/probe").headers["x-request-id"]
        )


class TestAnUpstreamSuppliedId:
    def test_a_well_formed_header_is_passed_through(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        response = client.get("/probe", headers={"X-Request-ID": "abc123xyz-trace"})
        assert response.headers["x-request-id"] == "abc123xyz-trace"

    def test_a_header_with_a_newline_is_dropped(self, app_with_middleware):
        """A header value a browser or an upstream can control must not be
        able to inject log lines or response headers. A newline is the
        canonical log-injection payload, and this test holds that line."""
        client = TestClient(app_with_middleware)
        response = client.get("/probe", headers={"X-Request-ID": "ab\ncd"})
        value = response.headers["x-request-id"]
        assert "\n" not in value
        assert value != "ab\ncd"

    def test_a_header_longer_than_the_cap_is_dropped(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        payload = "a" * 2000
        response = client.get("/probe", headers={"X-Request-ID": payload})
        assert response.headers["x-request-id"] != payload
        assert len(response.headers["x-request-id"]) < 100

    def test_a_header_with_a_space_or_quote_is_dropped(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        for bad in ('abc def', 'ab"cd', "ab'cd", "ab,cd"):
            response = client.get("/probe", headers={"X-Request-ID": bad})
            assert response.headers["x-request-id"] != bad


class TestAcrossMiddlewareAndHandlers:
    def test_a_handler_exception_still_logs_with_a_correlation_id(
            self, app_with_middleware, caplog):
        """Starlette's ServerErrorMiddleware generates the 500 response
        itself, outside this middleware's send(), so the response header is
        best-effort there. What matters is that any log line emitted DURING
        the exception path still carries a correlation id — that is the
        audit thread SRS §10.4 asks for, and the response header on the
        happy path is only convenience."""
        logger = logging.getLogger("app.test.correlation.error")

        async def _handler():
            logger.info("about-to-raise",
                        extra={"seen_correlation_id": current_correlation_id()})
            raise RuntimeError("deliberate")

        app_with_middleware.add_api_route("/error-logged", _handler, methods=["GET"])
        client = TestClient(app_with_middleware, raise_server_exceptions=False)
        with caplog.at_level(logging.INFO):
            response = client.get("/error-logged")
        assert response.status_code == 500
        hits = [r for r in caplog.records if r.getMessage() == "about-to-raise"]
        assert hits and hits[0].seen_correlation_id

    def test_the_id_is_cleared_after_the_request_leaves(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        client.get("/probe")
        assert current_correlation_id() is None


class TestItShowsUpInLogs:
    def test_a_json_log_line_emitted_during_the_request_carries_the_id(
            self, app_with_middleware, caplog):
        with caplog.at_level(logging.INFO):
            response = TestClient(app_with_middleware).get("/probe")
        cid = response.headers["x-request-id"]
        hits = [record for record in caplog.records
                if record.getMessage() == "probe.hit"]
        assert hits, "the probe did not log"
        # The ContextVar is set at log-formatter time, so compare against the
        # extra the handler saved rather than against the record's attribute.
        assert hits[0].seen_correlation_id == cid
