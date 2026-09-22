"""When the model is called, and — mostly — when it is not.

These tests use `llm_spy`, which makes a provider REACHABLE and records every
request that gets as far as the wire. That matters: with no provider configured,
"the model was not called" is true for free and proves nothing. Here the model is
available and still must not be used.
"""

from __future__ import annotations

from app.domain import phrasing


class TestHappyPathMakesNoModelCall:
    async def test_collecting_five_answers_calls_nothing(self, chat, answers, llm_spy):
        """The latency claim, asserted rather than hoped for. Five questions,
        five answers, zero round trips."""
        c = chat()
        await c.open()
        for value in answers.values():
            await c.say(value)
        assert llm_spy.count == 0, llm_spy.payloads

    async def test_every_answer_is_understood_deterministically(
        self, chat, answers, llm_spy
    ):
        c = chat()
        await c.open()
        for value in answers.values():
            state = await c.say(value)
            assert state["understood_by"] == "fast-path", value

    async def test_asking_a_question_is_never_a_model_call(self, chat, answers, llm_spy):
        """The opening question is a sentence somebody wrote in the template.
        It is not generated, and this compares against the template rather
        than against a copy of the words — a wording change is an edit to
        `petition.yaml`, not a reason for this test to fail."""
        from app.domain.templates import next_field, the_template

        c = chat()
        state = await c.open()
        assert llm_spy.count == 0
        assert state["reply"] == next_field(the_template(), {}).prompt_for("en")

    async def test_the_read_back_and_confirmation_call_nothing(
        self, chat, answers, llm_spy
    ):
        c = chat()
        await c.answer_all(answers)
        assert llm_spy.count == 0, "the read-back is assembled, not written"

    async def test_correcting_a_field_calls_nothing(self, chat, answers, llm_spy):
        c = chat()
        await c.answer_all(answers)
        await c.say("no")
        await c.say("the age is wrong")
        await c.say("31")
        assert llm_spy.count == 0, llm_spy.payloads

    async def test_cancel_and_restart_call_nothing(self, chat, llm_spy):
        c = chat()
        await c.open()
        await c.say("start over")
        await c.say("cancel")
        assert llm_spy.count == 0

    async def test_validation_errors_are_never_generated(self, chat, answers, llm_spy):
        """Including the identifier short-circuit: a malformed Aadhaar is code's
        business, so it never reaches the boundary at all."""
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say("999")            # bad age
        await c.say("45")
        await c.say(answers["mobile"])
        await c.say("Coimbatore")     # bad address
        await c.say(answers["address"])
        await c.say("1234")           # bad aadhaar
        assert llm_spy.count == 0, llm_spy.payloads

    async def test_only_compose_reaches_the_boundary_in_a_whole_petition(
        self, chat, answers, llm_spy
    ):
        c = chat()
        await c.answer_all(answers)
        await c.say("yes")
        assert llm_spy.count == 1, "one call, for the formal wording"
        schema = llm_spy.calls[0]["schema"]["properties"]
        assert {"subject", "introduction", "background", "request"} <= set(schema)


class TestTheModelIsUsedWhereItHelps:
    async def test_an_unexpected_question_reaches_the_model(
        self, chat, answers, scripted_llm
    ):
        spy = scripted_llm({"intent": "question", "question": "What documents do I need?",
                            "fields": [], "corrections": []})
        c = chat()
        await c.open()
        state = await c.say("what documents do I need to bring?")

        assert spy.count >= 1, "a question has no pre-written answer"
        assert state["awaiting"] == "applicant_name", "and the form does not advance"

    async def test_the_answer_is_followed_by_the_pending_question(
        self, chat, scripted_llm
    ):
        scripted_llm({"intent": "question", "question": "What documents do I need?",
                      "fields": [], "corrections": []})
        c = chat()
        await c.open()
        state = await c.say("what documents do I need?")
        from app.domain.templates import next_field, the_template

        assert "Aadhaar card" in state["reply"], "the answer"
        assert next_field(the_template(), {}).prompt_for("en") in state["reply"], (
            "and then the question again")

    async def test_a_fourth_failure_gets_a_fresh_phrasing(
        self, chat, answers, fake_llm
    ):
        """Three identical rejections is the point at which repeating the same
        sentence has demonstrably not worked."""
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say(answers["age"])
        await c.say(answers["mobile"])
        await c.say(answers["address"])

        for _ in range(3):
            state = await c.say("1234")
        assert state["attempts"]["aadhaar"] == 3
        # The fourth ask is allowed to be generated.
        assert "printed on your Aadhaar card" in state["reply"]

    async def test_the_rephrase_carries_no_citizen_text(self, chat, answers, llm_spy):
        c = chat()
        await c.open()
        await c.say(answers["applicant_name"])
        await c.say(answers["age"])
        await c.say(answers["mobile"])
        await c.say(answers["address"])
        for _ in range(3):
            await c.say("1234")

        rephrase = [
            call for call in llm_spy.calls
            if "question" in (call.get("schema") or {}).get("properties", {})
        ]
        assert rephrase, "the rephrase was attempted"
        assert "1234" not in llm_spy.body(rephrase[0])


class TestModelUnavailable:
    async def test_the_petition_still_completes(self, chat, answers, llm_spy):
        """`llm_spy` refuses every call, so this is the model being reachable
        and broken — the worst case, not the absent case."""
        c = chat()
        await c.answer_all(answers)
        state = await c.say("yes")
        assert state["status"] == "ready", state.get("error")
        assert state["verification"]["ok"] is True
        assert state["composition"] is None, "no model wording"
        assert state["letter_text"], "but a complete petition"

    async def test_the_standard_wording_is_used(self, chat, answers, llm_spy):
        c = chat()
        await c.answer_all(answers)
        state = await c.say("yes")
        assert "I reside at the address given above" in state["letter_text"]

    async def test_an_unanswerable_question_falls_back_to_the_pending_question(
        self, chat, scripted_llm, monkeypatch
    ):
        spy = scripted_llm({"intent": "question", "question": "Why?",
                            "fields": [], "corrections": []})

        # The understanding call answers; the question-answering call fails.
        async def half_broken(**kwargs):
            spy.calls.append(kwargs)
            properties = (kwargs.get("schema") or {}).get("properties", {})
            if "answer" in properties:
                raise RuntimeError("provider down")
            return {"intent": "question", "question": "Why?", "fields": [], "corrections": []}

        monkeypatch.setattr("app.graph.nodes.chat_json", half_broken)

        c = chat()
        await c.open()
        state = await c.say("why do you need this?")
        from app.domain.templates import next_field, the_template

        assert phrasing.phrase("not_understood", "en") in state["reply"]
        assert next_field(the_template(), {}).prompt_for("en") in state["reply"]
        assert state["awaiting"] == "applicant_name"

    async def test_a_model_that_returns_nonsense_cannot_widen_the_record(
        self, chat, scripted_llm
    ):
        """A model inventing a field the form does not declare is dropped."""
        scripted_llm({
            "intent": "provide",
            "fields": [{"name": "father_name", "value": "Kumar"},
                       {"name": "age", "value": "45"}],
            "corrections": [],
        })
        c = chat()
        await c.open()
        state = await c.say("something the fast path cannot read")
        assert "father_name" not in state["fields"]

    async def test_a_model_supplied_value_is_still_validated(self, chat, scripted_llm):
        """The model extracts; code decides. An invalid value it reports is
        rejected exactly as if the citizen had typed it."""
        scripted_llm({
            "intent": "provide",
            "fields": [{"name": "age", "value": "900"}],
            "corrections": [],
        })
        c = chat()
        await c.open()
        await c.say("Ravi Kumar")
        # First failure is handled deterministically; the model is only asked on
        # a repeat, so two attempts are needed to reach the path under test.
        await c.say("not a number at all")
        state = await c.say("something only a model could read")
        assert "age" not in state["fields"]
        assert state["field_errors"]["age"]["code"] == "age.range"
