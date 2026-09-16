"""Provider failover: what happens when keys run out and models are busy.

All of this was written against a free Gemini tier with six keys and four
models, where 429 ("this key is spent") and 503 ("this model is busy") are
ordinary rather than exceptional. Every test here corresponds to a failure seen
in that setting, where the citizen silently got the standard wording instead of
the petition the service is supposed to produce.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import asr, llm


@pytest.fixture(autouse=True)
def clean_cooldowns():
    llm._KEY_COOLDOWN.clear()
    yield
    llm._KEY_COOLDOWN.clear()


def _response(status: int, body: dict | None = None, text: str = "") -> httpx.Response:
    request = httpx.Request("POST", "https://example.invalid/v1")
    return httpx.Response(status, json=body or {}, text=text or None, request=request)


def _http_error(status: int) -> httpx.HTTPStatusError:
    response = _response(status)
    return httpx.HTTPStatusError(f"HTTP {status}", request=response.request, response=response)


class TestKeyCooldown:
    def test_a_rested_key_is_skipped(self):
        llm._rest_key("spent")
        assert llm._usable_keys(("spent", "fresh")) == ("fresh",)

    def test_order_is_preserved(self):
        llm._rest_key("b")
        assert llm._usable_keys(("a", "b", "c")) == ("a", "c")

    def test_all_resting_falls_back_to_all(self):
        """A likely 429 still beats a guaranteed fallback to standard wording."""
        for key in ("a", "b"):
            llm._rest_key(key)
        assert llm._usable_keys(("a", "b")) == ("a", "b")

    def test_a_working_key_is_revived(self):
        llm._rest_key("a")
        assert llm._usable_keys(("a", "b")) == ("b",)
        llm._revive_key("a")
        assert llm._usable_keys(("a", "b")) == ("a", "b")

    def test_an_expired_cooldown_lets_the_key_back(self):
        llm._rest_key("a", seconds=-1)
        assert llm._usable_keys(("a",)) == ("a",)


class TestFailoverAcrossKeys:
    async def test_a_spent_key_moves_to_the_next_key_not_the_next_model(
        self, monkeypatch
    ):
        """A quota problem is about the credential, not the model. The old loop
        abandoned the model after one 429 and started the next model from key
        one — so the same exhausted keys were re-tried for every model."""
        seen: list[tuple[str, str]] = []

        async def gemini(client, *, key, model, **kwargs):
            seen.append((model, key))
            if key in ("k1", "k2"):
                raise _http_error(429)
            return {"ok": True}

        monkeypatch.setattr(llm, "chain", lambda *a, **k: ["gemini"])
        monkeypatch.setattr(llm, "_gemini", gemini)
        monkeypatch.setattr(llm, "_models_for", lambda *a: ["m1", "m2"])
        monkeypatch.setattr(llm, "_keys_for", lambda *a: ("k1", "k2", "k3"))

        result = await llm.chat_json(system="s", user="u", schema={"type": "object"})
        assert result["ok"] is True
        assert seen == [("m1", "k1"), ("m1", "k2"), ("m1", "k3")]

    async def test_spent_keys_are_not_retried_for_the_next_model(self, monkeypatch):
        calls: list[tuple[str, str]] = []

        async def gemini(client, *, key, model, **kwargs):
            calls.append((model, key))
            if key in ("k1", "k2"):
                raise _http_error(429)
            raise _http_error(503)      # every model busy, so the pass fails

        monkeypatch.setattr(llm, "chain", lambda *a, **k: ["gemini"])
        monkeypatch.setattr(llm, "_gemini", gemini)
        monkeypatch.setattr(llm, "_models_for", lambda *a: ["m1", "m2"])
        monkeypatch.setattr(llm, "_keys_for", lambda *a: ("k1", "k2", "k3"))

        with pytest.raises(llm.LLMUnavailable):
            await llm.chat_json(system="s", user="u", schema={"type": "object"},
                                budget_ms=4000, retry_pass=False)

        second_model = [key for model, key in calls if model == "m2"]
        assert "k1" not in second_model and "k2" not in second_model
        assert second_model == ["k3"], "only the key that has quota is tried again"

    async def test_a_busy_model_is_retried_on_the_next_key_before_being_given_up(
        self, monkeypatch
    ):
        """503 is decided per credential on a free tier, not per model.

        This test asserted the opposite until a live check disproved it: asked
        for the same model in the same second, five of the six keys answered 503
        and the sixth served the request. Treating the first 503 as "this model
        is unavailable" abandoned a model that was working, and the citizen got
        the standard wording with quota still unspent.
        """
        calls: list[tuple[str, str]] = []

        async def gemini(client, *, key, model, **kwargs):
            calls.append((model, key))
            if key in ("k1", "k2"):
                raise _http_error(503)
            return {"ok": True}

        monkeypatch.setattr(llm, "chain", lambda *a, **k: ["gemini"])
        monkeypatch.setattr(llm, "_gemini", gemini)
        monkeypatch.setattr(llm, "_models_for", lambda *a: ["m1", "m2"])
        monkeypatch.setattr(llm, "_keys_for", lambda *a: ("k1", "k2", "k3"))

        assert (await llm.chat_json(system="s", user="u", schema={"type": "object"}))["ok"]
        assert calls == [("m1", "k1"), ("m1", "k2"), ("m1", "k3")]

    async def test_a_busy_key_is_not_rested(self, monkeypatch):
        """A 503 says the model is busy, not that the key is spent. Resting the
        key would hide it from the models still to come."""
        async def gemini(client, *, key, model, **kwargs):
            raise _http_error(503)

        monkeypatch.setattr(llm, "chain", lambda *a, **k: ["gemini"])
        monkeypatch.setattr(llm, "_gemini", gemini)
        monkeypatch.setattr(llm, "_models_for", lambda *a: ["m1"])
        monkeypatch.setattr(llm, "_keys_for", lambda *a: ("k1", "k2"))

        with pytest.raises(llm.LLMUnavailable):
            await llm.chat_json(system="s", user="u", schema={"type": "object"},
                                budget_ms=4000, retry_pass=False)
        assert llm._usable_keys(("k1", "k2")) == ("k1", "k2")

    async def test_a_timeout_still_moves_straight_to_the_next_model(self, monkeypatch):
        """The one failure that costs real time. Six slow keys for one model
        would spend the whole budget, so a timeout gives up on the model rather
        than working through its keys."""
        calls: list[tuple[str, str]] = []

        async def gemini(client, *, key, model, **kwargs):
            calls.append((model, key))
            if model == "m1":
                raise httpx.ReadTimeout("too slow")
            return {"ok": True}

        monkeypatch.setattr(llm, "chain", lambda *a, **k: ["gemini"])
        monkeypatch.setattr(llm, "_gemini", gemini)
        monkeypatch.setattr(llm, "_models_for", lambda *a: ["m1", "m2"])
        monkeypatch.setattr(llm, "_keys_for", lambda *a: ("k1", "k2"))

        assert (await llm.chat_json(system="s", user="u", schema={"type": "object"}))["ok"]
        assert calls == [("m1", "k1"), ("m2", "k1")]

    async def test_a_success_revives_the_key(self, monkeypatch):
        state = {"fail": True}

        async def gemini(client, *, key, model, **kwargs):
            if state["fail"]:
                state["fail"] = False
                raise _http_error(429)
            return {"ok": True}

        monkeypatch.setattr(llm, "chain", lambda *a, **k: ["gemini"])
        monkeypatch.setattr(llm, "_gemini", gemini)
        monkeypatch.setattr(llm, "_models_for", lambda *a: ["m1"])
        monkeypatch.setattr(llm, "_keys_for", lambda *a: ("k1", "k2"))

        await llm.chat_json(system="s", user="u", schema={"type": "object"})
        assert llm._usable_keys(("k2",)) == ("k2",)


class TestTransientRetry:
    async def test_one_more_pass_when_everything_was_temporary(self, monkeypatch):
        """503 on every model within the same second is ordinary on a free tier,
        and clears within a couple of seconds."""
        attempts = {"n": 0}

        async def gemini(client, **kwargs):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise _http_error(503)
            return {"ok": True}

        monkeypatch.setattr(llm, "chain", lambda *a, **k: ["gemini"])
        monkeypatch.setattr(llm, "_gemini", gemini)
        monkeypatch.setattr(llm, "_models_for", lambda *a: ["m1", "m2"])
        monkeypatch.setattr(llm, "_keys_for", lambda *a: ("k1",))
        monkeypatch.setattr(llm.asyncio, "sleep", lambda *_: _noop())

        result = await llm.chat_json(system="s", user="u", schema={"type": "object"},
                                     budget_ms=30000)
        assert result["ok"] is True
        assert attempts["n"] == 3, "the second pass succeeded"

    async def test_no_retry_when_a_failure_was_durable(self, monkeypatch):
        """A 401 will be a 401 next second too. Retrying just spends the budget
        the caller needs for its fallback."""
        attempts = {"n": 0}

        async def gemini(client, **kwargs):
            attempts["n"] += 1
            raise _http_error(401)

        monkeypatch.setattr(llm, "chain", lambda *a, **k: ["gemini"])
        monkeypatch.setattr(llm, "_gemini", gemini)
        monkeypatch.setattr(llm, "_models_for", lambda *a: ["m1"])
        monkeypatch.setattr(llm, "_keys_for", lambda *a: ("k1",))

        with pytest.raises(llm.LLMUnavailable):
            await llm.chat_json(system="s", user="u", schema={"type": "object"},
                                budget_ms=30000)
        assert attempts["n"] == 1, "no second pass"


async def _noop() -> None:
    return None


class TestGeminiThinking:
    """Thinking is billed against the same output budget as the answer, so it
    truncated the JSON on longer complaints. Not every model accepts the field
    that turns it off."""

    async def test_thinking_is_disabled_by_default(self, monkeypatch):
        sent: dict = {}

        class FakeClient:
            async def post(self, url, **kwargs):
                sent.update(kwargs["json"])
                return _response(200, {"candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": '{"ok":true}'}]}}]})

        out = await llm._gemini(FakeClient(), key="k", model="m", system="s", payload="p",
                                schema={"type": "object"}, max_tokens=100, timeout=5,
                                base="https://example.invalid")
        assert out == {"ok": True}
        assert sent["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}

    async def test_a_model_that_rejects_the_field_is_retried_without_it(self, monkeypatch):
        """gemini-3.5-flash-lite answers HTTP 400 for thinkingConfig. Dropping
        the model from the chain over that loses a whole quota bucket."""
        calls: list[dict] = []

        class FakeClient:
            async def post(self, url, **kwargs):
                calls.append(kwargs["json"]["generationConfig"])
                if "thinkingConfig" in kwargs["json"]["generationConfig"]:
                    return _response(400, text="Unknown name \"thinkingConfig\"")
                return _response(200, {"candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": '{"ok":true}'}]}}]})

        out = await llm._gemini(FakeClient(), key="k", model="m", system="s", payload="p",
                                schema={"type": "object"}, max_tokens=100, timeout=5,
                                base="https://example.invalid")
        assert out == {"ok": True}
        assert len(calls) == 2
        assert "thinkingConfig" in calls[0] and "thinkingConfig" not in calls[1]

    async def test_truncation_is_named_rather_than_reported_as_bad_json(self):
        class FakeClient:
            async def post(self, url, **kwargs):
                return _response(200, {"candidates": [
                    {"finishReason": "MAX_TOKENS",
                     "content": {"parts": [{"text": '{"subject":"half a sen'}]}}]})

        with pytest.raises(RuntimeError, match="truncated"):
            await llm._gemini(FakeClient(), key="k", model="m", system="s", payload="p",
                              schema={"type": "object"}, max_tokens=10, timeout=5,
                              base="https://example.invalid")


class TestDictationFallsBackToTheSecondEngine:
    """Sarvam reads Tamil correctly and Groq Whisper is the safety net. The net
    is only worth having if it is actually reached.

    Taken from a live failure: DNS dropped, each of the four Sarvam keys spent
    about twenty seconds failing to resolve the host, the seventy-five second
    budget was gone, and Groq — configured, healthy, and one call away — was
    never tried. The citizen was told dictation had stopped.
    """

    @staticmethod
    def _settings(**over):
        from app.config import Settings
        base = dict(
            sarvam_api_keys="s1,s2,s3,s4",
            groq_api_keys="g1,g2",
            stream_asr_provider="auto",
            stt_timeout_ms=30000,
            stt_budget_ms=75000,
        )
        base.update(over)
        return Settings(**base)

    async def test_a_network_failure_moves_to_the_next_provider_at_once(self, monkeypatch):
        """A DNS or connect failure is about the network, not the credential.
        Working through the other three keys repeats the same failure at the
        same cost and spends the budget the fallback needs."""
        tried: list[str] = []

        async def sarvam(client, *, key, audio, model, language, timeout):
            tried.append("sarvam:" + key)
            raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

        async def groq(client, *, key, audio, model, language, timeout):
            tried.append("groq:" + key)
            return "the street light is not working", 0.9

        monkeypatch.setattr(asr, "_sarvam_stt", sarvam)
        monkeypatch.setattr(asr, "_groq_stt", groq)

        text = await asr.transcribe(b"\x00" * 3200, "ta", self._settings())
        assert text == "the street light is not working"
        assert tried == ["sarvam:s1", "groq:g1"], tried

    async def test_a_rejected_key_still_tries_the_other_keys(self, monkeypatch):
        """The opposite case, which must keep working: an HTTP rejection IS
        about the credential, so the remaining keys are worth trying."""
        tried: list[str] = []

        async def sarvam(client, *, key, audio, model, language, timeout):
            tried.append(key)
            if key in ("s1", "s2"):
                raise httpx.HTTPStatusError(
                    "403", request=httpx.Request("POST", "https://x"),
                    response=httpx.Response(403))
            return "transcribed", None

        monkeypatch.setattr(asr, "_sarvam_stt", sarvam)
        assert await asr.transcribe(b"\x00" * 3200, "ta", self._settings()) == "transcribed"
        assert tried == ["s1", "s2", "s3"], tried

    async def test_the_last_provider_may_use_every_key(self, monkeypatch):
        """Nothing is held back for a fallback that does not exist."""
        tried: list[str] = []

        async def groq(client, *, key, audio, model, language, timeout):
            tried.append(key)
            raise httpx.HTTPStatusError(
                "429", request=httpx.Request("POST", "https://x"),
                response=httpx.Response(429))

        monkeypatch.setattr(asr, "_groq_stt", groq)
        settings = self._settings(sarvam_api_keys="", stream_asr_provider="groq")
        with pytest.raises(RuntimeError, match="Dictation failed"):
            await asr.transcribe(b"\x00" * 3200, "en", settings)
        assert tried == ["g1", "g2"], tried

    async def test_nothing_configured_says_so_rather_than_hanging(self):
        settings = self._settings(sarvam_api_keys="", groq_api_keys="")
        with pytest.raises(RuntimeError, match="not configured"):
            await asr.transcribe(b"\x00" * 3200, "en", settings)


class TestDictationNeverAsksForATranslation:
    """Sarvam does not fail when given the wrong language — it returns a fluent
    translation. On this form that would silently replace the citizen's own
    words with a paraphrase, which is the one thing the grievance rules forbid.
    """

    async def test_the_citizens_chosen_language_is_what_is_sent(self, monkeypatch):
        """This asserted `unknown` — auto-detect — until a live check showed
        what auto-detect does with audio that has no words in it. A keyboard
        click came back as the English "Okay" with language confidence 0.765,
        and a burst of noise in a Tamil session came back as Bengali. The
        citizen has already said which language they are using."""
        seen: dict = {}

        class FakeResponse:
            status_code = 200
            def raise_for_status(self): return None
            def json(self): return {"transcript": "ok"}

        class FakeClient:
            async def post(self, url, **kwargs):
                seen.update(kwargs.get("data") or {})
                return FakeResponse()

        await asr._sarvam_stt(FakeClient(), key="k", audio=b"x",
                              model="saarika:v2.5", language="ta", timeout=5)
        assert seen["language_code"] == "ta-IN", seen
        # Never the translate endpoint's parameter: `target_language_code`
        # would return an English rendering of Tamil speech.
        assert "target_language_code" not in seen

    async def test_an_english_session_asks_for_english(self):
        seen: dict = {}

        class FakeResponse:
            status_code = 200
            def raise_for_status(self): return None
            def json(self): return {"transcript": "ok"}

        class FakeClient:
            async def post(self, url, **kwargs):
                seen.update(kwargs.get("data") or {})
                return FakeResponse()

        await asr._sarvam_stt(FakeClient(), key="k", audio=b"x",
                              model="saarika:v2.5", language="en", timeout=5)
        assert seen["language_code"] == "en-IN", seen

    async def test_whisper_transcribes_and_never_translates(self, monkeypatch):
        """Groq has a sibling endpoint, /audio/translations, that would do the
        same damage. This must point at /audio/transcriptions."""
        seen: dict = {}

        class FakeResponse:
            status_code = 200
            def raise_for_status(self): return None
            def json(self): return {"text": "ok", "segments": []}

        class FakeClient:
            async def post(self, url, **kwargs):
                seen["url"] = url
                seen.update(kwargs.get("data") or {})
                return FakeResponse()

        await asr._groq_stt(FakeClient(), key="k", audio=b"x",
                            model="whisper-large-v3", language="ta", timeout=5)
        assert seen["url"].endswith("/audio/transcriptions"), seen["url"]
        assert "translat" not in seen["url"]
        assert seen["language"] == "ta"


class TestTheRecordingIsCutOff:
    """A dictation that runs forever is a request that gets rejected for size
    and a citizen who said a great deal for nothing."""

    async def test_audio_past_the_cap_is_dropped(self):
        from app.config import Settings
        settings = Settings(sarvam_api_keys="s1", asr_max_seconds=2, asr_sample_rate=16000,
                            stream_asr_provider="auto")
        adapter = await asr.open_stream("ta", settings)
        cap = 2 * 16000 * 2
        for _ in range(40):
            await adapter.send_audio(b"\x00" * 8192)
        await adapter.close()
        assert adapter._size <= cap + 8192
        assert adapter._size >= cap

    async def test_a_misclick_is_not_sent_anywhere(self, monkeypatch):
        """Under a fifth of a second is somebody hitting the button twice."""
        from app.config import Settings
        called = []
        monkeypatch.setattr(asr, "transcribe",
                            lambda *a, **k: called.append(1))
        settings = Settings(sarvam_api_keys="s1", stream_asr_provider="auto")
        adapter = await asr.open_stream("en", settings)
        await adapter.send_audio(b"\x00" * 200)
        await adapter.stop()
        assert called == []
