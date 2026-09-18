"""What each provider key is actually doing, reported by position.

An operator needs to know that the third Sarvam key is exhausted. They do not
need to be shown the third Sarvam key to learn it, so nothing here returns,
logs or renders a value — only an index and a verdict.

Probing costs a request against the provider, and a quota, so it happens when
an operator asks for it rather than on every page load. The last result is kept
in memory with the time it was taken; a restart forgets it, which is correct,
because a verdict from before a restart says nothing about the keys the process
is actually holding now.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import Settings, get_settings

log = logging.getLogger(__name__)

# One probe should never hold the screen. Providers that do not answer in this
# long are reported as unreachable, which is the useful thing to know anyway.
_TIMEOUT = 20.0

WORKING = "working"
EXHAUSTED = "exhausted"
RATE_LIMITED = "rate limited"
REJECTED = "rejected"
UNREACHABLE = "unreachable"
UNKNOWN = "unknown"

# What each HTTP status means for a key, in the words an operator needs.
_VERDICTS = {
    200: WORKING, 401: REJECTED, 403: REJECTED, 402: EXHAUSTED, 429: RATE_LIMITED,
}


@dataclass
class KeyReport:
    position: int          # 1-based, matching the order in the setting
    state: str
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"position": self.position, "state": self.state, "detail": self.detail}


@dataclass
class ProviderReport:
    name: str
    configured: bool
    keys: list[KeyReport] = field(default_factory=list)
    note: str = ""

    @property
    def usable(self) -> int:
        return sum(1 for k in self.keys if k.state == WORKING)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "configured": self.configured,
            "keys": [k.as_dict() for k in self.keys],
            "usable": self.usable,
            "total": len(self.keys),
            "note": self.note,
        }


_last: dict[str, Any] = {"checked_at": None, "providers": []}


def last_result() -> dict[str, Any]:
    """The most recent probe, or an empty one. Never a key value."""
    return dict(_last)


async def _probe(client: httpx.AsyncClient, request) -> KeyReport:
    position, coroutine = request
    try:
        response = await coroutine
    except Exception as exc:  # noqa: BLE001 - every failure is "cannot use this key"
        return KeyReport(position, UNREACHABLE, type(exc).__name__)
    state = _VERDICTS.get(response.status_code, UNKNOWN)
    detail = "" if state is WORKING else f"HTTP {response.status_code}"
    return KeyReport(position, state, detail)


async def check(settings: Settings | None = None) -> dict[str, Any]:
    """Probe every configured key once, and report by position.

    The requests are the smallest each provider offers, so a check costs as
    little quota as it can while still proving the key is accepted.
    """
    s = settings or get_settings()
    providers: list[ProviderReport] = []

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # -- Gemini ------------------------------------------------------- #
        gemini = ProviderReport("Gemini", bool(s.gemini_key_list))
        if not s.gemini_key_list:
            gemini.note = "No key configured. Petitions use the standard wording."
        else:
            model = (s.gemini_model_list or ["gemini-3.5-flash"])[0]
            gemini.keys = list(await asyncio.gather(*[
                _probe(client, (i, client.post(
                    f"{s.gemini_base_url}/models/{model}:generateContent?key={key}",
                    json={"contents": [{"parts": [{"text": "ping"}]}]})))
                for i, key in enumerate(s.gemini_key_list, start=1)
            ]))
        providers.append(gemini)

        # -- Sarvam, which carries dictation, spoken replies and translation -- #
        sarvam = ProviderReport("Sarvam", bool(s.sarvam_key_list))
        if not s.sarvam_key_list:
            sarvam.note = "No key configured. Voice is unavailable; typing still works."
        else:
            sarvam.keys = list(await asyncio.gather(*[
                _probe(client, (i, client.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers={"api-subscription-key": key, "Content-Type": "application/json"},
                    json={"text": "ok", "target_language_code": "en-IN",
                          "model": s.sarvam_tts_model, "speaker": s.sarvam_tts_speaker})))
                for i, key in enumerate(s.sarvam_key_list, start=1)
            ]))
        providers.append(sarvam)

    result = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "providers": [p.as_dict() for p in providers],
    }
    _last.clear()
    _last.update(result)
    # Counts only. A log line has no business carrying a verdict per key either,
    # but it has even less business carrying a key.
    log.info("providers.checked", extra={
        "gemini_usable": providers[0].usable, "gemini_total": len(providers[0].keys),
        "sarvam_usable": providers[1].usable, "sarvam_total": len(providers[1].keys)})
    return result


def advice(result: dict[str, Any]) -> list[str]:
    """Plain sentences an operator can act on, derived from the last probe."""
    out: list[str] = []
    for provider in result.get("providers") or []:
        keys = provider.get("keys") or []
        if not keys:
            continue
        working = [k["position"] for k in keys if k["state"] == WORKING]
        broken = [k for k in keys if k["state"] != WORKING]
        if not working:
            out.append(f"{provider['name']}: no usable key. "
                       f"This capability is off until one is added.")
            continue
        if broken and keys[0]["state"] != WORKING:
            out.append(f"{provider['name']}: key 1 is {keys[0]['state']}, so every "
                       f"request tries it first and fails over. Move key "
                       f"{working[0]} to the front.")
        for key in broken:
            if key["state"] == EXHAUSTED:
                out.append(f"{provider['name']} key {key['position']} is out of "
                           f"credit and should be replaced or removed.")
    return out
