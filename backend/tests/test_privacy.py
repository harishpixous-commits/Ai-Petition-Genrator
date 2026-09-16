"""Aadhaar containment.

The requirement is specific: the full Aadhaar number must never reach an
external model or API, and must not appear in logs, traces, error messages or
model-debug data. It reaches the document through deterministic code alone.

Every test here is a regression test. The leak was real: `_understanding_context`
used to write "[already recorded: <value>]" into the SYSTEM prompt, and
`chat_json` masked only the user turn — so a validated Aadhaar number travelled
to the provider while the citizen's sentence beside it was redacted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.domain.fields import SENSITIVE_TYPES, is_sensitive
from app.domain.templates import the_template
from app.graph import nodes
from app.logging_setup import JsonFormatter, TextFormatter, preview
from app.services.llm import GUARD, chat_json
from app.services.mask import mask_pii
from app.services.render import extract_docx_text
from tests.conftest import VALID_AADHAAR

GROUPED = "2345 6789 0124"


# --------------------------------------------------------------------------- #
# The masker itself
# --------------------------------------------------------------------------- #


class TestMasking:
    @pytest.mark.parametrize(
        "written", [VALID_AADHAAR, GROUPED, "2345-6789-0124"]
    )
    def test_aadhaar_is_redacted_however_it_is_grouped(self, written):
        assert VALID_AADHAAR not in mask_pii(f"my number is {written}")
        assert written not in mask_pii(f"my number is {written}")

    def test_other_identifiers_are_redacted(self):
        text = "call 9876543210 or ravi@example.com, PAN ABCDE1234F, account 123456789012"
        masked = mask_pii(text)
        for secret in ("9876543210", "ravi@example.com", "ABCDE1234F", "123456789012"):
            assert secret not in masked, secret

    def test_ordinary_text_is_left_alone(self):
        text = "The street light outside my house has not worked for three months."
        assert mask_pii(text) == text

    def test_a_named_person_can_be_redacted(self):
        assert "Ravi Kumar" not in mask_pii("Ravi Kumar complained", names=["Ravi Kumar"])


# --------------------------------------------------------------------------- #
# The model boundary
# --------------------------------------------------------------------------- #


class TestModelBoundary:
    def test_identifier_types_are_marked_sensitive(self):
        assert is_sensitive("aadhaar")
        assert "aadhaar" in SENSITIVE_TYPES
        assert not is_sensitive("grievance") and not is_sensitive("text")

    def test_the_understanding_prompt_never_carries_a_value(self, valid_aadhaar, answers):
        """The exact leak that existed. The model is told a field is answered,
        never what the answer was."""
        state = {"fields": {**answers, "aadhaar": valid_aadhaar, "age": 45}}
        context = nodes._understanding_context(state, the_template(), "grievance")

        assert valid_aadhaar not in context
        assert GROUPED not in context
        assert "Ravi Kumar" not in context
        assert answers["address"] not in context
        assert "[already answered]" in context, "but the model still knows it is filled"

    async def test_no_prompt_in_a_whole_conversation_contains_the_aadhaar(
        self, chat, answers, llm_spy
    ):
        """The end-to-end assertion: run a full petition with a reachable model
        and inspect everything that crossed the boundary."""
        c = chat()
        # Deliberately give a bad value first, so the failure paths are covered
        # too — an error path that echoes the value back is still a leak.
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say(answers["age"])
        await c.say(answers["mobile"])
        await c.say(answers["address"])
        await c.say("2345 6789 0125")          # wrong checksum
        await c.say(answers["aadhaar"])
        await c.say(answers["grievance"])
        await c.say("yes")

        sent = llm_spy.payloads
        assert VALID_AADHAAR not in sent
        assert GROUPED not in sent
        assert "2345 6789 0125" not in sent

    async def test_the_compose_prompt_excludes_every_identifier(
        self, chat, answers, llm_spy
    ):
        c = chat()
        await c.answer_all(answers)
        await c.say("yes")

        compose_calls = [
            call for call in llm_spy.calls
            if "introduction" in (call.get("schema") or {}).get("properties", {})
        ]
        assert compose_calls, "compose did reach the boundary"
        body = llm_spy.body(compose_calls[0])
        assert VALID_AADHAAR not in body and GROUPED not in body
        # The name is present — the model needs it to write in the first person.
        assert "Ravi Kumar" in body

    async def test_masking_covers_the_system_prompt_too(self, monkeypatch):
        """Defence in depth under the care taken at the call sites."""
        seen = {}

        async def capture(client, **kwargs):
            seen.update(kwargs)
            return {"ok": True}

        monkeypatch.setattr("app.services.llm.chain", lambda *a, **k: ["ollama"])
        monkeypatch.setattr("app.services.llm._ollama", capture)

        await chat_json(
            system=f"A previous value was {VALID_AADHAAR}",
            user=f"and the citizen said {VALID_AADHAAR}",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        )
        assert VALID_AADHAAR not in seen["system"]
        assert VALID_AADHAAR not in seen["payload"]
        assert GUARD in seen["system"]


# --------------------------------------------------------------------------- #
# Logs
# --------------------------------------------------------------------------- #


def _format(formatter, message: str, **extra) -> str:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return formatter.format(record)


class TestLogs:
    def test_preview_masks_citizen_text(self):
        assert VALID_AADHAAR not in preview(f"my aadhaar is {VALID_AADHAAR}")

    def test_the_json_formatter_scrubs_the_message(self):
        line = _format(JsonFormatter(), f"rejected {VALID_AADHAAR}")
        assert VALID_AADHAAR not in line
        assert "REDACTED" in line

    def test_the_json_formatter_scrubs_extras(self):
        """The safety net: a future call site that puts a value in `extra`
        cannot leak it, even though no call site does today."""
        line = _format(JsonFormatter(), "verify.failed", value=GROUPED)
        assert GROUPED not in line
        assert VALID_AADHAAR not in line

    def test_the_text_formatter_scrubs_too(self):
        line = _format(TextFormatter(), "rejected", aadhaar=VALID_AADHAAR)
        assert VALID_AADHAAR not in line

    def test_the_json_formatter_still_produces_valid_json(self):
        parsed = json.loads(_format(JsonFormatter(), "node.render", ms=12, ok=True))
        assert parsed["message"] == "node.render" and parsed["ms"] == 12

    async def test_a_whole_conversation_logs_no_aadhaar(self, chat, answers, caplog):
        formatter = JsonFormatter()
        with caplog.at_level(logging.DEBUG):
            c = chat()
            await c.answer_all(answers)
            await c.say("yes")

        emitted = "\n".join(formatter.format(r) for r in caplog.records)
        assert VALID_AADHAAR not in emitted
        assert GROUPED not in emitted

    async def test_a_failed_verification_logs_names_not_values(self, chat, answers, caplog):
        """The failure path is where a value is most likely to be echoed."""
        formatter = JsonFormatter()
        with caplog.at_level(logging.DEBUG):
            c = chat()
            await c.open()
            await c.say(answers["applicant_name"])
            await c.say("999")                      # out of range
            await c.say("2345 6789")                # too short
        emitted = "\n".join(formatter.format(r) for r in caplog.records)
        assert "2345 6789" not in emitted


# --------------------------------------------------------------------------- #
# The document — where the Aadhaar is SUPPOSED to be
# --------------------------------------------------------------------------- #


class TestDocument:
    async def test_the_aadhaar_reaches_the_document_deterministically(
        self, chat, answers
    ):
        """Containment is not suppression. The number belongs on the petition,
        placed by code, in the grouping the citizen confirmed."""
        c = chat()
        await c.answer_all(answers)
        state = await c.say("yes")

        produced = extract_docx_text(Path(state["document"]["docx"]))
        assert GROUPED in produced
        assert state["verification"]["ok"] is True

    async def test_the_session_view_carries_it_for_the_citizen_to_check(
        self, chat, answers
    ):
        from app.api.views import session_view

        c = chat()
        await c.answer_all(answers)
        view = session_view(c.state)
        entry = next(f for f in view["collected"] if f["name"] == "aadhaar")
        assert entry["display"] == GROUPED
