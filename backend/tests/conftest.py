"""Test configuration and shared fixtures.

The suite runs with NO language model, NO dictation and NO PDF converter by
default. That is the deployment this service has to survive — a department
machine with no egress and nothing installed — so it is the one that is tested.
Anything that only works when a model answers is a bug, and running the suite
this way is how it gets caught.

Where a test needs a model, it asks for `fake_llm` (canned answers) or `llm_spy`
(a model that is REACHABLE but must not be called). The spy is the important
one: with no provider configured, "the model was not called" is trivially true
and proves nothing.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="petition-tests-"))

# Set before anything imports `app.config`, which caches settings on first use.
os.environ["LLM_PROVIDER"] = "off"
os.environ["ALLOW_EXTERNAL_AI"] = "false"
os.environ["PDF_ENGINE"] = "off"
os.environ["STREAM_ASR_PROVIDER"] = "off"
os.environ["TTS_PROVIDER"] = "off"
os.environ["DATA_DIR"] = str(_TMP)
os.environ["LOG_FORMAT"] = "json"
os.environ["LOG_LEVEL"] = "INFO"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #

# Verhoeff-valid, never issued, safe to keep in a repository.
#
# The FORM no longer asks for an Aadhaar number. This constant stays because
# the protections around one do: it can still arrive inside a grievance
# somebody dictates or on a card they attach, and the validator, the masking
# and the attachment handling are all still exercised with it.
VALID_AADHAAR = "234567890124"


@pytest.fixture
def valid_aadhaar() -> str:
    return VALID_AADHAAR


@pytest.fixture
def answers() -> dict[str, str]:
    """One complete set, in the order the form asks for them."""
    return {
        "applicant_name": "Ravi Kumar",
        "age": "45",
        "mobile": "9876543210",
        "address": "12 Gandhi Street, Peelamedu, Coimbatore",
        "grievance": (
            "The street light outside my house has not worked for three months. "
            "I have complained twice at the panchayat office and nothing has been done."
        ),
    }


@pytest.fixture
def tamil_answers() -> dict[str, str]:
    return {
        "applicant_name": "ரவி குமார்",
        "age": "45",
        "mobile": "9876543210",
        "address": "12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர்",
        "grievance": "எனது வீட்டின் முன் உள்ள தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை.",
    }


# --------------------------------------------------------------------------- #
# The graph, and a citizen talking to it
# --------------------------------------------------------------------------- #


@pytest.fixture
def graph():
    """The real graph, with an in-memory checkpointer so each test is isolated."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.graph.workflow import build_graph

    return build_graph().compile(checkpointer=InMemorySaver())


class Conversation:
    """A citizen talking to the service, holding a session id as a client would."""

    def __init__(self, graph, language: str = "en") -> None:
        from app.domain.templates import the_template
        from app.graph.state import new_state

        self.graph = graph
        self.session_id = str(uuid.uuid4())
        self.config = {"configurable": {"thread_id": self.session_id}}
        seed = new_state(self.session_id, language)  # type: ignore[arg-type]
        seed["template_id"] = the_template().id
        self._seed = seed
        self.state: dict = {}

    async def open(self, text: str = "") -> dict:
        self._seed["utterance"] = text
        self.state = await self.graph.ainvoke(self._seed, config=self.config)
        return self.state

    async def say(self, text: str) -> dict:
        self.state = await self.graph.ainvoke({"utterance": text}, config=self.config)
        return self.state

    async def send(self, **patch) -> dict:
        """A turn from a form endpoint, bypassing the understanding step."""
        self.state = await self.graph.ainvoke(
            {"_skip_understand": True, "_extracted": {}, "_corrections": {},
             "_correction_target": None, **patch},
            config=self.config,
        )
        return self.state

    async def answer_all(self, values: dict[str, str],
                         attachments: str = "continue with these details") -> dict:
        """Open the session, answer every question, and pass the attachment offer.

        The offer now stands between the last detail and the read-back. A test
        that is not about attachments answers it the way most citizens will —
        pass `attachments=None` to stop before it and drive that step directly.
        """
        await self.open()
        for value in values.values():
            await self.say(value)
        if attachments is not None and self.state.get("status") == "attachments":
            await self.say(attachments)
        return self.state

    @property
    def reply(self) -> str:
        return self.state.get("reply", "")

    @property
    def awaiting(self) -> str | None:
        return self.state.get("awaiting")

    @property
    def status(self) -> str:
        return self.state.get("status", "")


@pytest.fixture
def chat(graph):
    def make(language: str = "en") -> Conversation:
        return Conversation(graph, language)

    return make


# --------------------------------------------------------------------------- #
# Language model doubles
# --------------------------------------------------------------------------- #


class _Spy:
    """Records every call that reached the model boundary."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    @property
    def count(self) -> int:
        return len(self.calls)

    @property
    def payloads(self) -> str:
        """Everything that actually left the process, concatenated.

        Captured AFTER masking, at the provider call, because that is where the
        wire is. Asserting on the arguments handed to `chat_json` would test the
        call site and skip the redaction that sits between it and the network.
        """
        return "\n".join(self.body(call) for call in self.calls)

    @staticmethod
    def body(call: dict) -> str:
        """The two halves of one request, as the provider received them."""
        return f"{call.get('system', '')}\n{call.get('payload', '')}"


@pytest.fixture
def llm_spy(monkeypatch) -> _Spy:
    """A model that is REACHABLE but whose every call is recorded and refused.

    The refusal is the point: callers must degrade, so a test using this fixture
    also proves the deterministic fallback still produces a petition. And with a
    provider present, "no model call was made" becomes a real assertion instead
    of a consequence of the test environment.
    """
    spy = _Spy()

    async def refuse(client, **kwargs):
        spy.calls.append(kwargs)
        raise RuntimeError("no model in tests")

    monkeypatch.setattr("app.services.llm.chain", lambda *a, **k: ["ollama"])
    monkeypatch.setattr("app.services.llm._ollama", refuse)
    return spy


@pytest.fixture
def fake_llm(monkeypatch) -> _Spy:
    """A model that answers, so the model-assisted paths can be exercised.

    Answers are keyed off the schema, which is how the real code distinguishes
    the understanding call from the rephrase, the question answer and the
    compose call.
    """
    spy = _Spy()

    async def answer(**kwargs):
        spy.calls.append(kwargs)
        properties = (kwargs.get("schema") or {}).get("properties", {})
        # `intent` first: the understanding schema also declares `question`.
        if "intent" in properties:
            return {"intent": "unclear", "fields": [], "corrections": []}
        if "introduction" in properties:
            return {
                "subject": "Non-functioning street light at Peelamedu",
                "introduction": "I reside at the address given above and write about a street light.",
                "background": "The absence of light makes the road unsafe after dark for "
                              "residents who must walk along it. The matter has not been "
                              "put right and needs your office to direct an inspection.",
                "request": "I request that the street light be restored at the earliest.",
            }
        if "answer" in properties:
            return {"answer": "Please bring a copy of your Aadhaar card."}
        return {"question": "Please tell me the number printed on your Aadhaar card."}

    monkeypatch.setattr("app.services.llm.chain", lambda *a, **k: ["ollama"])
    monkeypatch.setattr("app.graph.nodes.chat_json", answer)
    return spy


@pytest.fixture
def scripted_llm(monkeypatch):
    """Like `fake_llm`, but the understanding reply is supplied per test."""
    spy = _Spy()

    def install(understanding: dict):
        async def answer(**kwargs):
            spy.calls.append(kwargs)
            properties = (kwargs.get("schema") or {}).get("properties", {})
            # `intent` first: the understanding schema also declares `question`.
            if "intent" in properties:
                return understanding
            if "introduction" in properties:
                return {
                    "subject": "Non-functioning street light",
                    "introduction": "I reside at the address given above.",
                    "background": "The road stays dark after nightfall and the matter "
                                  "needs the attention of your office.",
                    "request": "I request that the necessary action be taken.",
                }
            if "answer" in properties:
                return {"answer": "Please bring a copy of your Aadhaar card."}
            return {"question": "Please read the number on your Aadhaar card."}

        monkeypatch.setattr("app.services.llm.chain", lambda *a, **k: ["ollama"])
        monkeypatch.setattr("app.graph.nodes.chat_json", answer)
        return spy

    return install
