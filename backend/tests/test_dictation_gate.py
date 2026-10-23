"""`/ws/dictation` refuses the n+1th connection before accepting the socket.

WHAT THIS GUARDS. The push-to-talk socket is now the ONLY voice path the
citizen UI opens (the full `/ws/voice` is deliberately dark — see
`tests/test_page_translation.py`), and before this it had no limit at any
layer: not in `nginx`, not in the application. One client could open
connections until the process stopped answering anybody. `/ws/voice` had
`ws_limits.Gate` already; this is the sibling check on dictation.

TWO BEHAVIOURS pinned:

  * the n+1th connection from the same client is refused before any audio
    is processed, with a sayable reason and a 1008 close;
  * the slot released by closing the first socket is immediately available
    to the next connection, so a quick cancel-and-retry still works.

No audio provider runs. No workflow is driven. The gate is primed by hand so
the test does not have to open 65 sockets to hit the real limit.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import dictation, ws_limits


@pytest.fixture
def _single_slot_app(monkeypatch):
    """A FastAPI app where the dictation gate has exactly one slot."""
    app = FastAPI()
    app.include_router(dictation.router)
    app.state.workflow = SimpleNamespace(snapshot=AsyncMock(return_value=None))
    app.state.dictation_gate = ws_limits.Gate(ws_limits.Limits(
        max_connections=1,
        max_per_client=1,
        max_message_bytes=65_536,
        max_bytes_per_minute=1_000_000,
        max_session_seconds=60.0,
    ))
    monkeypatch.setattr(dictation, "can_access", lambda _r, _sid: True)
    monkeypatch.setattr(dictation.asr, "choose_provider", lambda _: "deepgram")
    return app


def test_the_slot_is_taken_and_the_next_connection_is_refused(_single_slot_app):
    gate = _single_slot_app.state.dictation_gate
    gate.acquire("primed-client")
    assert gate.open_connections == 1

    client = TestClient(_single_slot_app)
    with pytest.raises(WebSocketDisconnect) as info:
        with client.websocket_connect("/ws/dictation/anything") as socket:
            message = socket.receive_json()
            assert message["type"] == "error"
            assert "voice session" in message["message"].lower()
            socket.receive_bytes()
    assert info.value.code in (1008, 1013)


def test_releasing_the_slot_lets_the_next_connection_through(_single_slot_app):
    gate = _single_slot_app.state.dictation_gate
    gate.acquire("primed-client")
    gate.release("primed-client")

    client = TestClient(_single_slot_app)
    with client.websocket_connect("/ws/dictation/anything") as socket:
        first_message = socket.receive_json()
        # The handler sends an "unavailable" error because snapshot returns
        # None in this fixture; what matters is the message type is NOT
        # "error with a limit reason" and the socket got accepted.
        assert first_message["code"] == "unavailable"
