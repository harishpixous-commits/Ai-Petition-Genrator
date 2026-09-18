"""Provider credentials set from the operator screen.

The feature exists because an operator at a counter may need to rotate an
exhausted key with no shell on the box. What it must never become is a
credential form on a public government URL: the screen is gated, the values are
write-only, and nothing — no response, no log line, no error — carries one back
out.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI

from app.api.operator import router
from app.config import Settings, get_settings
from app.services import provider_health, provider_store

GEMINI = "gem-aaaaaaaaaaaaaaaaaaaa,gem-bbbbbbbbbbbbbbbbbbbb"
SARVAM = "sar-cccccccccccccccccccc"
TOKEN = "operator-token-for-tests"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A data directory of this test's own, and a genuinely clean environment.

    `Settings` reads `.env` from the working directory, so a test run from the
    repository picks up the developer's real credentials. Running from an empty
    directory is what keeps a live key out of this test — and out of any
    failure message it might print.
    """
    import os

    # `provider_store.apply()` writes to os.environ directly, which monkeypatch
    # cannot undo — so the environment is snapshotted and put back by hand.
    # Without this a test that sets a key leaves it set for every test after it.
    before = {name: os.environ.get(name) for name in provider_store.MANAGED}
    for name in provider_store.MANAGED:
        os.environ.pop(name, None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPERATOR_TOKEN", TOKEN)
    get_settings.cache_clear()
    provider_store._original.clear()
    try:
        yield tmp_path
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        provider_store._original.clear()
        get_settings.cache_clear()


@pytest.fixture
async def api(store):
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
        headers={"x-operator-token": TOKEN},
    ) as client:
        yield client


class TestNoKeyEverLeaves:
    """The whole point of holding them. Every route out is checked."""

    async def test_the_response_to_a_save_carries_no_key(self, api, store):
        response = await api.post("/api/operator/providers",
                                  json={"gemini_api_keys": GEMINI,
                                        "sarvam_api_keys": SARVAM})

        assert response.status_code == 200, response.text
        body = response.text
        for secret in (GEMINI, SARVAM, "gem-aaaaaaaaaaaaaaaaaaaa", "sar-cccccccccccccccccccc"):
            assert secret not in body, "a credential came back in the response"

    async def test_nor_does_reading_the_screen(self, api):
        await api.post("/api/operator/providers", json={"gemini_api_keys": GEMINI})

        body = (await api.get("/api/operator/providers")).text

        assert GEMINI not in body
        assert "gem-" not in body

    async def test_nor_does_a_health_check(self, api, monkeypatch):
        async def never_call(settings=None):
            return {"checked_at": "2026-09-18T00:00:00Z", "providers": []}

        monkeypatch.setattr(provider_health, "check", never_call)
        await api.post("/api/operator/providers", json={"sarvam_api_keys": SARVAM})

        body = (await api.post("/api/operator/providers/check")).text

        assert SARVAM not in body

    async def test_what_it_does_report_is_counts_and_positions(self, api):
        await api.post("/api/operator/providers", json={"gemini_api_keys": GEMINI})

        body = (await api.get("/api/operator/providers")).json()

        assert body["counts"]["GEMINI_API_KEYS"] == 2
        assert body["sources"]["GEMINI_API_KEYS"] == "operator"


class TestTheScreenIsGated:
    async def test_without_the_token_the_endpoints_do_not_exist(self, store):
        app = FastAPI()
        app.include_router(router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as anonymous:
            # No token header, and ASGITransport is not loopback.
            for call in (anonymous.get("/api/operator/providers"),
                         anonymous.post("/api/operator/providers",
                                        json={"gemini_api_keys": GEMINI})):
                response = await call
                assert response.status_code == 404, (
                    "an admin endpoint announced itself to an unauthenticated caller")

    async def test_a_wrong_token_is_equally_invisible(self, store):
        app = FastAPI()
        app.include_router(router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
            headers={"x-operator-token": "not-the-token"},
        ) as wrong:
            assert (await wrong.get("/api/operator/providers")).status_code == 404


class TestWhereTheValuesGo:
    async def test_written_to_the_data_directory_not_to_app_env(self, api, store):
        await api.post("/api/operator/providers", json={"sarvam_api_keys": SARVAM})

        written = store / provider_store.STORE_NAME
        assert written.is_file(), "nothing was persisted"
        assert json.loads(written.read_text(encoding="utf-8"))["SARVAM_API_KEYS"] == SARVAM

    async def test_the_backup_does_not_take_it(self):
        """`deploy/scripts/backup.sh` copies two databases BY NAME rather than
        archiving the volume. That is the reason this file may live here at
        all, so it is asserted rather than remembered."""
        from pathlib import Path

        script = Path(__file__).resolve().parents[2] / "deploy/scripts/backup.sh"
        if not script.is_file():  # pragma: no cover - running outside the repo
            pytest.skip("deployment scripts not present")
        text = script.read_text(encoding="utf-8")

        assert "for db in sessions knowledge" in text, (
            "the backup no longer copies two databases by name; a credentials "
            "file in the data directory may now be inside every backup")
        assert provider_store.STORE_NAME not in text

    async def test_it_applies_at_once_without_a_restart(self, api):
        assert len(get_settings().sarvam_key_list) == 0

        await api.post("/api/operator/providers", json={"sarvam_api_keys": SARVAM})

        applied = get_settings().sarvam_key_list
        assert len(applied) == 1 and applied[0] == SARVAM


class TestClearingHandsControlBack:
    async def test_an_emptied_field_restores_what_the_host_had(self, api, monkeypatch):
        """An operator who overrides app.env from the screen has to be able to
        undo it without a shell — which means restoring the host's value, not
        leaving the process with nothing."""
        monkeypatch.setenv("SARVAM_API_KEYS", "from-app-env")
        get_settings.cache_clear()

        await api.post("/api/operator/providers", json={"sarvam_api_keys": SARVAM})
        assert get_settings().sarvam_key_list[0] == SARVAM

        await api.post("/api/operator/providers", json={"sarvam_api_keys": ""})

        restored = get_settings().sarvam_key_list
        assert restored and restored[0] == "from-app-env", (
            "clearing the override did not hand the setting back to app.env")

    async def test_the_source_says_which_one_is_in_force(self, api, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEYS", "from-app-env")
        get_settings.cache_clear()
        provider_store.apply()

        assert (await api.get("/api/operator/providers")).json()[
            "sources"]["GEMINI_API_KEYS"] == "environment"

        await api.post("/api/operator/providers", json={"gemini_api_keys": GEMINI})

        assert (await api.get("/api/operator/providers")).json()[
            "sources"]["GEMINI_API_KEYS"] == "operator"

    async def test_an_empty_request_changes_nothing(self, api):
        assert (await api.post("/api/operator/providers", json={})).status_code == 422


class TestTheHealthReport:
    def test_a_verdict_is_a_position_and_a_state_and_nothing_else(self):
        report = provider_health.KeyReport(position=2, state=provider_health.EXHAUSTED,
                                           detail="HTTP 402")

        assert set(report.as_dict()) == {"position", "state", "detail"}

    def test_it_tells_an_operator_what_to_do_about_a_dead_leading_key(self):
        result = {"providers": [{
            "name": "Sarvam",
            "keys": [{"position": 1, "state": provider_health.EXHAUSTED, "detail": "HTTP 402"},
                     {"position": 2, "state": provider_health.WORKING, "detail": ""}],
        }]}

        said = " ".join(provider_health.advice(result))

        assert "Move key 2 to the front" in said
        assert "out of credit" in said

    def test_no_usable_key_is_said_plainly(self):
        result = {"providers": [{
            "name": "Gemini",
            "keys": [{"position": 1, "state": provider_health.REJECTED, "detail": "HTTP 401"}],
        }]}

        assert "no usable key" in " ".join(provider_health.advice(result))


class TestOnlyTheseSettingsCanBeChanged:
    async def test_an_unmanaged_setting_is_ignored(self, api, store):
        """The screen may configure providers. It may not point the service at
        a different data directory, turn off the operator token, or change
        where anything is written."""
        await api.post("/api/operator/providers",
                       json={"gemini_api_keys": GEMINI, "data_dir": "/tmp/elsewhere",
                             "operator_token": ""})

        written = json.loads((store / provider_store.STORE_NAME).read_text(encoding="utf-8"))
        assert set(written) <= set(provider_store.MANAGED)
        assert "DATA_DIR" not in written
        assert "OPERATOR_TOKEN" not in written

    def test_every_managed_secret_is_declared_secret(self):
        for name in provider_store.MANAGED:
            if "KEY" in name:
                assert name in provider_store.SECRET, f"{name} is not marked secret"


class TestTheScreenSaysWhenAKeyCannotBeUsed:
    """`app.env.example` ships with ALLOW_EXTERNAL_AI=false and LLM_PROVIDER=off.

    That is the right default — a service must not opt itself into egress — but
    it means an operator can paste a perfectly good key, watch it be counted,
    and see nothing change. This is the deployment's actual state today, so the
    screen has to say so rather than leave them guessing.
    """

    @pytest.fixture(autouse=True)
    def _clean(self, store):
        """`Settings(_env_file=None)` still reads os.environ, so a stray key
        left by another test would change what this one sees."""

    @staticmethod
    def _advice(**over):
        from app.api.operator import _configuration_advice

        return " ".join(_configuration_advice(Settings(_env_file=None, **over)))

    def test_a_key_with_external_ai_switched_off(self):
        said = self._advice(gemini_api_keys="k1", allow_external_ai=False)

        assert "external AI is switched off" in said

    def test_a_key_allowed_but_no_provider_chosen(self):
        said = self._advice(gemini_api_keys="k1", allow_external_ai=True,
                            llm_provider="off")

        assert "language model is set to 'off'" in said

    def test_sarvam_keys_with_voice_switched_off(self):
        said = self._advice(sarvam_api_keys="k1", stream_asr_provider="off",
                            tts_provider="off")

        assert "dictation is switched off" in said
        assert "spoken replies are switched off" in said

    def test_nothing_to_say_when_it_is_configured_properly(self):
        said = self._advice(gemini_api_keys="k1", allow_external_ai=True,
                            llm_provider="auto", sarvam_api_keys="k2",
                            stream_asr_provider="auto", tts_provider="auto")

        assert said == ""

    def test_and_nothing_to_say_when_no_key_is_set_at_all(self):
        """A deployment running deliberately offline is not misconfigured."""
        assert self._advice(allow_external_ai=False, llm_provider="off") == ""
