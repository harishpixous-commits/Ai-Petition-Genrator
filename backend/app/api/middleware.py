"""Cross-cutting ASGI middleware.

CORRELATION ID. Every HTTP request is tagged with a short random id that:

  * attaches to every log line emitted while the request is being handled
    (via `correlation_context`), so an operator reading the log can match
    `knowledge.timed_out` to the specific export it belongs to;
  * echoes back in the `X-Request-ID` response header, so an incident report
    from a citizen or an officer carries the exact thread the server used;
  * can be supplied by a trusted upstream (nginx, a reverse proxy) through
    an `X-Request-ID` request header, which is accepted when it looks like
    a plain id and discarded otherwise. A header a client controls MUST
    NOT be able to inject arbitrary characters into log lines.

Why not reuse `session_id`. Not every request has one. `POST /api/sessions`
creates the session as its first act; `/api/health` has none; a websocket
handshake precedes its session read. The correlation id covers all of them.
Session id continues to be logged where it exists; the two together are the
pair SRS §10.4 asks for.

Websockets are handled too: a `/ws/voice` or `/ws/dictation` connection
gets its own correlation id for the lifetime of the socket, which means a
dropped socket, a late provider response, or a retry can be traced through
one line of audit instead of none.
"""

from __future__ import annotations

import re
import secrets

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..logging_setup import correlation_context

#: An id accepted from upstream must look like one: hex, dashes, letters,
#: 8-64 chars. Anything else is dropped and a fresh id is used, because the
#: value lands in log lines and in a response header where it must not carry
#: injection payloads.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{8,64}$")

HEADER_NAME = b"x-request-id"


def _new_id() -> str:
    """A short, URL-safe, log-safe id. 16 hex chars = 64 bits of entropy."""
    return secrets.token_hex(8)


def _accept(value: bytes | str | None) -> str:
    text = value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else (value or "")
    return text if _SAFE_ID.match(text) else _new_id()


def _header(scope: Scope, name: bytes) -> bytes | None:
    for key, value in scope.get("headers") or ():
        if key == name:
            return value
    return None


class CorrelationIdMiddleware:
    """ASGI middleware. Handles HTTP and websocket scopes.

    Mounted as the OUTER wrapper so the id is set before Starlette's own
    exception handling runs — a 500 raised inside the app still logs with a
    correlation id, and the response that goes back carries the same id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        correlation = _accept(_header(scope, HEADER_NAME))

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((HEADER_NAME, correlation.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        wrapped_send = send_with_header if scope["type"] == "http" else send
        with correlation_context(correlation):
            await self.app(scope, receive, wrapped_send)
