"""Credentials that are present but switched off.

THE FAILURE THIS EXISTS FOR. An operator put real API keys into app.env,
redeployed, and nothing changed: no voice, no AI-written narrative, and a
health endpoint reporting `provider: off`. Every obvious explanation was
wrong. The keys were in the file, the file was mounted, the container had
restarted, and the service had read every line correctly.

What defeated them is that three settings must agree, two of which the
deployment template ships in the position that turns everything off:

    LLM_PROVIDER=off            <- template default
    STREAM_ASR_PROVIDER=off     <- template default
    TTS_PROVIDER=off            <- template default
    ALLOW_EXTERNAL_AI=false     <- code default, and deliberate

Each is individually defensible. `off` is right for a service with no keys,
and `allow_external_ai=false` is a deliberate refusal to send citizen text
anywhere merely because a key appeared in a file. Together, and silently,
they meant adding a key accomplished nothing.

`deploy/scripts/write-env.sh` now derives the three provider switches from
which keys are present, so a CI-managed deployment cannot get into this state
at all. This module remains the safety net for every other route to it — a
hand-edited file, a host restored from an old backup, a deployment that does
not use the script — and it is the only thing that will tell the operator
WHY, in the place they are already looking.

Nothing here CHANGES any setting. Switching a provider on because a key was
found is exactly the opt-in-by-accident that `allow_external_ai` exists to
prevent. It reports: the contradiction, in the log at startup and on the
health endpoint, with the line to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings, get_settings


@dataclass(frozen=True)
class Contradiction:
    """A credential that is present and cannot be used."""

    setting: str          # the env var that is switched off
    keys: str             # the env var holding the unused credential
    fix: str              # the line to change, verbatim

    def as_dict(self) -> dict[str, str]:
        return {"setting": self.setting, "keys": self.keys, "fix": self.fix}


# Which switch governs which credential. `off` is the only value that
# disables outright — `auto` and a named provider both count as on, because a
# provider named explicitly is the operator being deliberate.
_GOVERNS: tuple[tuple[str, str, str, str], ...] = (
    ("llm_provider", "LLM_PROVIDER", "gemini_api_keys", "GEMINI_API_KEYS"),
    ("llm_provider", "LLM_PROVIDER", "anthropic_api_key", "ANTHROPIC_API_KEY"),
    ("llm_provider", "LLM_PROVIDER", "groq_api_keys", "GROQ_API_KEYS"),
    ("llm_provider", "LLM_PROVIDER", "openrouter_api_keys", "OPENROUTER_API_KEYS"),
    ("stream_asr_provider", "STREAM_ASR_PROVIDER", "sarvam_api_keys", "SARVAM_API_KEYS"),
    ("stream_asr_provider", "STREAM_ASR_PROVIDER", "deepgram_api_key", "DEEPGRAM_API_KEY"),
    ("stream_asr_provider", "STREAM_ASR_PROVIDER", "assemblyai_api_key",
     "ASSEMBLYAI_API_KEY"),
    # Sarvam drives spoken replies as well as dictation. Reporting only the
    # dictation half leaves an operator fixing one switch and still having a
    # voice agent that cannot speak.
    ("tts_provider", "TTS_PROVIDER", "sarvam_api_keys", "SARVAM_API_KEYS"),
)

# Credentials that only ever reach a provider outside this machine. A key for
# one of these with egress refused is the second way to hold an unusable key.
_NEEDS_EGRESS = ("gemini_api_keys", "anthropic_api_key", "groq_api_keys",
                 "openrouter_api_keys", "sarvam_api_keys", "deepgram_api_key",
                 "assemblyai_api_key")


def _set(settings: Settings, attribute: str) -> bool:
    """Whether a credential field holds anything. Never reads the value out."""
    return bool(str(getattr(settings, attribute, "") or "").strip())


def find(settings: Settings | None = None) -> list[Contradiction]:
    """Every credential that is configured and cannot currently be used."""
    s = settings or get_settings()
    out: list[Contradiction] = []
    seen: set[tuple[str, str]] = set()

    for switch, switch_env, keys, keys_env in _GOVERNS:
        if not _set(s, keys):
            continue
        if str(getattr(s, switch, "") or "").strip().lower() != "off":
            continue
        if (switch_env, keys_env) in seen:
            continue
        seen.add((switch_env, keys_env))
        out.append(Contradiction(setting=switch_env, keys=keys_env,
                                 fix=f"{switch_env}=auto"))

    if not s.allow_external_ai:
        for keys in _NEEDS_EGRESS:
            if not _set(s, keys):
                continue
            keys_env = keys.upper()
            if ("ALLOW_EXTERNAL_AI", keys_env) in seen:
                continue
            seen.add(("ALLOW_EXTERNAL_AI", keys_env))
            out.append(Contradiction(setting="ALLOW_EXTERNAL_AI", keys=keys_env,
                                     fix="ALLOW_EXTERNAL_AI=true"))

    return out


def summary(settings: Settings | None = None) -> dict[str, Any]:
    """For the health endpoint and the operator screen.

    Never contains a key, a fragment of one, or its length — only the NAME of
    the variable holding it and the line that would switch it on.
    """
    found = find(settings)
    if not found:
        return {"ok": True, "unused_credentials": []}
    return {
        "ok": False,
        "unused_credentials": [c.as_dict() for c in found],
        "note": ("Credentials are configured for providers that are switched "
                 "off. They were read correctly; nothing will use them until "
                 "the settings listed here are changed and the container is "
                 "recreated."),
    }
