"""The generating state over a real WebSocket, with a composition that takes time.

The unit tests next door check that the wiring is present. This one connects to
the actual endpoint and watches what a browser would have received, because the
announcer is a race by construction: it polls the checkpoint while the turn is
running and reports what it finds, and a fix that is merely *written* correctly
can still lose that race and send nothing at all.

The workflow here is a stand-in with one job — take longer than the poll
interval — because the real bug is only visible when composition is slow, and
the real composition is fast when there is no model configured. Two and a half
minutes was the measured case; a second and a half proves the same thing
without making the suite wait.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.api.ws import Phase
from app.main import app
from app.services import asr

COLLECTED = {
    "language": "en",
    "status": "confirming",
    "fields": {"applicant_name": "Harish", "age": 23, "mobile": "9876543210",
               "address": "12 Gandhi Street, Coimbatore", "aadhaar": "234567890124",
               "grievance": "The street light has not worked for three months."},
}

READY = {**COLLECTED, "status": "ready", "confirmed": True,
         "reply": "Your petition is ready."}


class SlowComposition:
    """A workflow that spends a measurable time writing the petition.

    `peek` reports `generating` for as long as the turn is running, which is
    what the real confirm node arranges: it records that status before routing
    to compose, so the announcer has something true to relay.
    """

    def __init__(self, seconds: float = 1.5) -> None:
        self.seconds = seconds
        self.running = False

    async def snapshot(self, session_id: str) -> dict:
        return dict(COLLECTED)

    async def peek(self, session_id: str) -> dict:
        return {**COLLECTED, "status": "generating" if self.running else "confirming"}

    async def invoke(self, session_id: str, payload: dict) -> dict:
        self.running = True
        try:
            await asyncio.sleep(self.seconds)
        finally:
            self.running = False
        return dict(READY)


class NeverGenerates(SlowComposition):
    """The same slow turn, for a turn that is not a composition."""

    async def peek(self, session_id: str) -> dict:
        return {**COLLECTED, "status": "collecting"}


@pytest.fixture
def dictation_available(monkeypatch):
    """Let `voice.start` be accepted with no credentials installed.

    Only the availability check is faked. Nothing here transcribes anything;
    the turns below are typed on the same socket, which is a documented part
    of the protocol and takes the identical path through the workflow.
    """
    monkeypatch.setattr(asr, "status", lambda settings=None: {"ok": True, "provider": "test"})


def converse(workflow, message: dict, *, until: Callable[[dict], bool],
             listen: bool = False, cap: int = 40) -> list[dict]:
    """Send one turn on a live socket and collect what comes back."""
    seen: list[dict] = []
    with TestClient(app) as client:
        # After startup, not before: the lifespan builds the real workflow and
        # assigns it to this same attribute, so a stand-in installed earlier is
        # silently replaced and the test exercises the real graph instead.
        previous = getattr(app.state, "workflow", None)
        app.state.workflow = workflow
        try:
            with client.websocket_connect(f"/ws/voice/{uuid.uuid4()}") as ws:
                if listen:
                    ws.send_json({"type": "voice.start"})
                ws.send_json(message)
                while len(seen) < cap:
                    received = ws.receive_json()
                    seen.append(received)
                    if until(received):
                        break
                else:  # pragma: no cover - only on a protocol change
                    raise AssertionError(f"the turn never settled: {seen}")
        finally:
            app.state.workflow = previous

    return seen


def finished(message: dict) -> bool:
    """The session view that carries the completed petition."""
    return message.get("type") == "state" and message["state"].get("status") != "generating"


def back_to_listening() -> Callable[[dict], bool]:
    """Listening again AFTER the petition arrived.

    Stateful on purpose: `voice.start` reports listening before the turn is
    even sent, and stopping at that one would end the recording before
    anything under test has happened.
    """
    delivered = False

    def settled(message: dict) -> bool:
        nonlocal delivered
        if finished(message):
            delivered = True
        return (delivered and message.get("type") == "voice.state"
                and message["state"] == Phase.LISTENING.value)

    return settled


def phases(seen: list[dict]) -> list[str]:
    return [m["state"] for m in seen if m.get("type") == "voice.state"]


class TestWhatTheBrowserActuallyReceives:
    def test_the_generating_state_arrives_before_the_document_does(self):
        """The whole point. Without it the page shows "Thinking..." for the
        whole composition, and the citizen cannot tell a long wait from a
        hung one."""
        order = phases(converse(SlowComposition(), {"type": "text", "text": "yes"},
                                until=finished))

        assert Phase.GENERATING.value in order, order
        assert order.index(Phase.PROCESSING.value) < order.index(Phase.GENERATING.value), order

    def test_it_arrives_while_the_work_is_still_running(self):
        """Sent afterwards it would be decoration. The message has to precede
        the finished document, or it reported nothing in time."""
        seen = converse(SlowComposition(), {"type": "text", "text": "yes"}, until=finished)
        announced = [i for i, m in enumerate(seen)
                     if m.get("type") == "voice.state" and m["state"] == Phase.GENERATING.value]

        assert announced and announced[0] < len(seen) - 1, [m.get("type") for m in seen]

    def test_the_page_is_given_the_generating_session_too(self):
        """Not only the phase. The panel with the drafting animation is driven
        by the session status, and both have to arrive for the screen to be
        right."""
        seen = converse(SlowComposition(), {"type": "text", "text": "yes"}, until=finished)
        statuses = [m["state"].get("status") for m in seen if m.get("type") == "state"]

        assert statuses[:-1] == ["generating"], statuses
        assert statuses[-1] == "ready", statuses

    def test_a_turn_that_is_not_a_composition_claims_nothing(self):
        """A correction or a question takes the same path and must not say the
        petition is being written. This is what stops the fix from being
        "always send generating"."""
        order = phases(converse(NeverGenerates(),
                                {"type": "text", "text": "change my age to 24"},
                                until=finished))

        assert Phase.PROCESSING.value in order, order
        assert Phase.GENERATING.value not in order, order


class TestTheMachineDoesNotStopThere:
    """GENERATING is a state to pass through. Left behind, the button stays
    amber and the status line goes on claiming work that finished."""

    def test_a_voice_session_returns_to_listening(self, dictation_available):
        seen = converse(SlowComposition(), {"type": "text", "text": "yes"},
                        listen=True, until=back_to_listening())
        order = phases(seen)

        assert Phase.GENERATING.value in order, order
        assert order[-1] == Phase.LISTENING.value, order

    def test_and_the_petition_was_delivered_before_it_did(self, dictation_available):
        """Returning to listening is only right if the document arrived
        first — otherwise the citizen is being asked to speak again while the
        screen still shows the old state."""
        seen = converse(SlowComposition(), {"type": "text", "text": "yes"},
                        listen=True, until=back_to_listening())
        ready = [i for i, m in enumerate(seen)
                 if m.get("type") == "state" and m["state"].get("status") == "ready"]

        assert ready and ready[0] < len(seen) - 1, [m.get("type") for m in seen]
