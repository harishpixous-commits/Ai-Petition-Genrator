"""Provider credentials set from the operator screen, and what became of them.

The deployment's own answer to "where do keys live" is `app.env` on the host,
and that remains the documented path: it is outside the container, outside
git, and outside every backup. This store exists for the case that file cannot
answer — an operator who needs to rotate an exhausted key at a counter, with no
shell on the box.

Three decisions are load-bearing.

WHERE. A file in the data directory. It survives `docker compose up -d
--force-recreate`, because the data directory is a named volume, and it stays
out of every backup, because `deploy/scripts/backup.sh` copies two databases by
name rather than archiving the volume. Putting credentials anywhere that gets
archived would scatter them across every backup the service has ever taken.

HOW IT REACHES THE APPLICATION. By setting environment variables, then clearing
the settings cache. The whole service already reads its configuration from the
environment through `get_settings()`, and every one of its call sites re-reads,
so nothing else has to learn that this file exists. A key set here behaves in
every respect like a key set in `app.env`.

WHAT LEAVES. Never a value. Not in a response, not in a log line, not in an
error. The screen shows how many keys are set and what each one's last probe
said — by POSITION. An operator needs to know that key three is exhausted; they
do not need to be shown key three to learn it.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings

log = logging.getLogger(__name__)

STORE_NAME = "providers.json"

# What an operator may set here. Deliberately short: these are the settings
# that decide whether a capability works at all, and nothing that could change
# where the service sends a citizen's data beyond the providers it already has.
MANAGED: tuple[str, ...] = (
    "ALLOW_EXTERNAL_AI",
    "LLM_PROVIDER",
    "GEMINI_API_KEYS",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEYS",
    "OPENROUTER_API_KEYS",
    "STREAM_ASR_PROVIDER",
    "TTS_PROVIDER",
    "SARVAM_API_KEYS",
)

# Which of those carry credentials. A value under one of these names is never
# returned, never logged, and never written to a response.
SECRET = frozenset({
    "GEMINI_API_KEYS", "ANTHROPIC_API_KEY", "GROQ_API_KEYS",
    "OPENROUTER_API_KEYS", "SARVAM_API_KEYS",
})


@dataclass(frozen=True)
class Applied:
    """What the store changed, named but never valued."""

    names: tuple[str, ...]
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {"applied": list(self.names), "source": self.source}


def path(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return s.data_dir / STORE_NAME


def read(settings: Settings | None = None) -> dict[str, str]:
    """What the operator has set here, or an empty mapping."""
    store = path(settings)
    if not store.is_file():
        return {}
    try:
        raw = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("providers.store_unreadable")
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        name: str(value)
        for name, value in raw.items()
        if name in MANAGED and isinstance(value, (str, int, float, bool)) and str(value).strip()
    }


def write(values: dict[str, str], settings: Settings | None = None) -> Applied:
    """Persist what was set, replacing anything held before.

    A name given with an empty value is REMOVED rather than stored blank, so
    clearing a field in the screen hands control back to `app.env` instead of
    overriding it with nothing.
    """
    s = settings or get_settings()
    store = path(s)
    keep = {
        name: str(value).strip()
        for name, value in values.items()
        if name in MANAGED and str(value or "").strip()
    }
    store.parent.mkdir(parents=True, exist_ok=True)
    # Written through a temporary file in the same directory: a half-written
    # credentials file read by a restart is a service with a truncated key.
    temporary = store.with_suffix(".tmp")
    temporary.write_text(json.dumps(keep, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:  # pragma: no cover - platform dependent
        pass
    temporary.replace(store)
    with_secrets = tuple(sorted(keep))
    log.info("providers.updated", extra={"names": list(with_secrets), "count": len(keep)})
    return apply(s)


# What the environment held before this store first overrode it. None means the
# variable did not exist. Kept so that clearing a field in the screen hands
# control BACK to app.env rather than leaving the process with a value the host
# never set and no way to reach the one it did.
_original: dict[str, str | None] = {}


def apply(settings: Settings | None = None) -> Applied:
    """Put the stored values into the environment and reload the settings.

    Called at startup and after every change. Values already present in the
    environment are OVERRIDDEN, because an operator who has just typed a key
    expects the service to use it — and the screen says plainly which source
    each provider's credentials came from, so that is visible rather than
    surprising.

    A name the store no longer carries is restored to whatever the environment
    held before, which is how an operator undoes an override without a shell.
    """
    stored = read(settings)
    for name in MANAGED:
        if name in stored:
            if name not in _original:
                _original[name] = os.environ.get(name)
            os.environ[name] = stored[name]
        elif name in _original:
            previous = _original.pop(name)
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
    # Always: a cleared override changes the configuration as much as a new one.
    get_settings.cache_clear()
    return Applied(names=tuple(sorted(stored)), source=STORE_NAME)


def sources(settings: Settings | None = None) -> dict[str, str]:
    """Where each managed setting's value came from, for the screen.

    "operator" when this store set it, "environment" when app.env or the host
    did, "unset" when nobody has. No value is read out to decide this — only
    whether one exists.
    """
    stored = read(settings)
    out: dict[str, str] = {}
    for name in MANAGED:
        if name in stored:
            out[name] = "operator"
        elif str(os.environ.get(name) or "").strip():
            out[name] = "environment"
        else:
            out[name] = "unset"
    return out
