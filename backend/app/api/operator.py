"""The operator's view of the machine. Not for citizens.

A district office running this needs one screen that answers: is the knowledge
base loaded, is any of it in conflict, and which capabilities are actually
working today. None of that belongs on the page a citizen uses — it is
operational detail, and a corpus document count on a petition form is noise at
best and alarming at worst.

**Access.** There is no user system in this service, so the rule is deliberately
blunt and fails closed on the dangerous side:

  * `OPERATOR_TOKEN` set     → the token is required, from any address.
  * `OPERATOR_TOKEN` unset   → loopback only. A workstation developer sees it;
                               a service bound to an interface does not expose
                               it to the network.

The second case is the one that matters. A deployment that forgets to set a
token does not get an open admin panel on its LAN; it gets a 404 from anywhere
but the machine itself, and a warning in the startup log.

Nothing here reads a session, a field, or an attachment. There is no citizen
data on this screen at all — the counts are of government documents, and the
capability flags are about this machine.
"""

from __future__ import annotations

import ipaddress
import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..services import asr, extraction, llm, provider_health, provider_store, tts
from ..services.render import pdf_status

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator")

_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _from_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    if host in _LOOPBACK:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def authorise(request: Request, settings: Settings | None = None) -> None:
    """Let an operator in, or behave as though the screen does not exist.

    404 rather than 401 when the token is absent or wrong: an admin endpoint
    that announces itself to an unauthenticated caller is an invitation, and
    there is nothing here a citizen has any reason to discover.
    """
    s = settings or get_settings()
    token = (s.operator_token or "").strip()

    if not token:
        if _from_loopback(request):
            return
        log.warning("operator.blocked",
                    extra={"reason": "no OPERATOR_TOKEN set; loopback only"})
        raise HTTPException(404, "Not found")

    supplied = (request.headers.get("x-operator-token")
                or request.query_params.get("token") or "")
    # Constant-time, so the endpoint does not leak the token a character at a
    # time to somebody timing the responses.
    if not secrets.compare_digest(supplied, token):
        log.warning("operator.rejected", extra={"reason": "bad token"})
        raise HTTPException(404, "Not found")


def _knowledge() -> dict[str, Any]:
    from ..knowledge.capability import service
    from ..knowledge.conflicts import corpus_conflicts

    knowledge = service()
    stats = knowledge.status()
    if not stats.get("enabled"):
        return {"enabled": False, "health": "disabled",
                "note": "The knowledge layer is switched off."}

    documents: list[dict] = []
    conflicts: list[dict] = []
    try:
        documents = knowledge.store.documents(limit=10000)
        conflicts = corpus_conflicts(documents)
    except Exception as exc:  # noqa: BLE001
        log.warning("operator.corpus_unreadable", extra={"error": str(exc)[:160]})

    unresolved = [c for c in conflicts if c["resolution"] == "undetermined"]
    total = int(stats.get("documents") or 0)
    official = int(stats.get("official_documents") or 0)
    unverified = int(stats.get("unverified_documents") or 0)

    # One word for an operator glancing at it, and the reason underneath.
    if total == 0:
        health, note = "empty", (
            "No documents are indexed. The analysis panel stays hidden and every "
            "petition is produced exactly as it is today. Load verified sources "
            "with scripts/ingest.py.")
    elif unresolved:
        health, note = "attention", (
            f"{len(unresolved)} instrument(s) are covered by two live documents "
            f"with nothing to say which is in force. Date them, or supersede one.")
    elif unverified and not official:
        health, note = "attention", (
            "Nothing in the corpus carries official rank. Every finding will be "
            "cited, but none of it outranks anything or can be called mandatory.")
    elif not stats.get("vector_search"):
        health, note = "degraded", (
            "sqlite-vec did not load, so retrieval is lexical only. Results are "
            "narrower but nothing is wrong with what is returned.")
    else:
        health, note = "ready", "The corpus is loaded and internally consistent."

    last = stats.get("last_ingested_at")
    return {
        "enabled": True,
        "documents": total,
        "official_documents": official,
        "unverified_documents": unverified,
        "superseded_documents": int(stats.get("superseded") or 0),
        "chunks": int(stats.get("chunks") or 0),
        "by_type": stats.get("by_type") or {},
        "conflicts": conflicts,
        "unresolved_conflicts": len(unresolved),
        "embeddings": {
            "provider": stats.get("indexed_provider"),
            "dimension": stats.get("indexed_dimension"),
            "configured_provider": stats.get("configured_provider"),
            "vector_search": bool(stats.get("vector_search")),
            # A hashed bag-of-words is not a semantic model and the screen says
            # so, because "embeddings: local" reads like success otherwise.
            "semantic": stats.get("indexed_provider") not in (None, "local"),
        },
        "last_ingested_at": (
            datetime.fromtimestamp(float(last), UTC).isoformat() if last else None),
        "health": health,
        "note": note,
        "path": stats.get("path"),
    }


async def _capabilities(settings: Settings) -> dict[str, Any]:
    from ..knowledge.capability import service

    def state(name: str, level: str, detail: str) -> dict[str, str]:
        return {"name": name, "state": level, "detail": detail}

    pdf = pdf_status(settings)
    if not pdf["available"]:
        pdf_state, pdf_detail = "unavailable", str(pdf["note"])
    elif pdf["production_ready"]:
        pdf_state, pdf_detail = "ready", str(pdf["note"])
    else:
        pdf_state, pdf_detail = "workstation_only", str(pdf["note"])

    ocr = extraction.ocr_status()
    dictation = asr.status(settings)
    speech = tts.status(settings)
    language = await llm.available(settings)

    try:
        corpus_ready = bool(service().status().get("ready"))
    except Exception:  # noqa: BLE001
        corpus_ready = False

    # Dictation and spoken replies fail separately: a citizen can be heard but
    # not answered aloud, which is usable and should not read as "ready".
    voice_ok = bool(settings.voice_enabled and dictation.get("ok"))
    voice_detail = (
        "Dictation and spoken replies are both available."
        if voice_ok and speech.get("ok") else
        "Dictation works; spoken replies are unavailable, so the assistant "
        "answers in writing." if voice_ok else
        "Voice is off or no speech provider is reachable; typing works.")
    return {
        "rag": state(
            "Government knowledge", "ready" if corpus_ready else "not_ready",
            "Retrieval is answering from indexed documents." if corpus_ready
            else "No documents indexed; the analysis panel stays hidden."),
        "ocr": state(
            "OCR", "available" if ocr["available"] else "not_installed",
            str(ocr["note"])),
        "pdf": state("PDF", pdf_state, pdf_detail),
        "voice": state(
            "Voice",
            "ready" if voice_ok and speech.get("ok")
            else "degraded" if voice_ok else "unavailable",
            voice_detail),
        "word": state(
            "Word generation", "ready",
            "DOCX is produced in-process and is the deliverable."),
        "language_model": state(
            "Language model",
            "ready" if language.get("available") else "not_available",
            str(language.get("detail") or language.get("note") or "")),
    }


@router.get("/status")
async def operator_status(request: Request) -> dict[str, Any]:
    """Everything an operator needs, and nothing a citizen does."""
    settings = get_settings()
    authorise(request, settings)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "knowledge": _knowledge(),
        "capabilities": await _capabilities(settings),
        "access": (
            "token" if (settings.operator_token or "").strip() else "loopback-only"),
    }


class ProviderSettings(BaseModel):
    """What an operator may change from the screen.

    Every field is optional, and an EMPTY string is meaningful: it clears the
    override and hands that setting back to `app.env`. That is how a key set
    here is undone without a shell on the box.

    Nothing in this model is ever echoed back. The response to a save is the
    same report as a fresh read: how many keys are set, and what each one's
    last probe said, by position.
    """

    allow_external_ai: bool | None = None
    llm_provider: str | None = Field(default=None, max_length=40)
    gemini_api_keys: str | None = Field(default=None, max_length=8000)
    groq_api_keys: str | None = Field(default=None, max_length=8000)
    anthropic_api_key: str | None = Field(default=None, max_length=400)
    openrouter_api_keys: str | None = Field(default=None, max_length=8000)
    stream_asr_provider: str | None = Field(default=None, max_length=40)
    tts_provider: str | None = Field(default=None, max_length=40)
    sarvam_api_keys: str | None = Field(default=None, max_length=8000)

    def as_environment(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, value in self.model_dump(exclude_none=True).items():
            if isinstance(value, bool):
                out[name.upper()] = "true" if value else "false"
            else:
                out[name.upper()] = str(value)
        return out


def _counts(settings: Settings) -> dict[str, int]:
    """How many keys each setting holds. A count is not a key."""
    return {
        "GEMINI_API_KEYS": len(settings.gemini_key_list),
        "GROQ_API_KEYS": len(settings.groq_key_list),
        "OPENROUTER_API_KEYS": len(settings.openrouter_key_list),
        "SARVAM_API_KEYS": len(settings.sarvam_key_list),
        "ANTHROPIC_API_KEY": 1 if settings.anthropic_api_key.strip() else 0,
    }


def _configuration_advice(settings: Settings) -> list[str]:
    """Traps a key alone does not escape.

    `app.env.example` ships with ALLOW_EXTERNAL_AI=false and LLM_PROVIDER=off,
    which is the correct default for a service that must not opt itself into
    egress. It also means an operator can paste a perfectly good key, see it
    counted, and watch nothing change. The screen says so rather than leaving
    them to work it out.
    """
    out: list[str] = []
    keys = bool(settings.gemini_key_list or settings.groq_key_list
                or settings.openrouter_key_list or settings.anthropic_api_key.strip())
    if keys and not settings.allow_external_ai:
        out.append("Keys are set but external AI is switched off, so none of them "
                   "is used. Tick 'Allow external AI'.")
    if keys and settings.allow_external_ai and settings.llm_provider == "off":
        out.append("Keys are set and external AI is allowed, but the language model "
                   "is set to 'off'. Choose a provider, or 'auto'.")
    if settings.sarvam_key_list and settings.stream_asr_provider == "off":
        out.append("Sarvam keys are set but dictation is switched off. "
                   "Set dictation to 'auto'.")
    if settings.sarvam_key_list and settings.tts_provider == "off":
        out.append("Sarvam keys are set but spoken replies are switched off. "
                   "Set spoken replies to 'auto'.")
    return out


def _providers_view(settings: Settings) -> dict[str, Any]:
    """The screen's whole model. Contains no credential, anywhere."""
    probe = provider_health.last_result()
    return {
        "settings": {
            "allow_external_ai": settings.allow_external_ai,
            "llm_provider": settings.llm_provider,
            "stream_asr_provider": settings.stream_asr_provider,
            "tts_provider": settings.tts_provider,
        },
        "counts": _counts(settings),
        "sources": provider_store.sources(settings),
        "health": probe,
        "advice": _configuration_advice(settings) + provider_health.advice(probe),
        # Said on the screen, because the safer path should be the obvious one.
        "note": (
            "Credentials belong in app.env on the host. Anything set here is "
            "kept in the data directory, applies immediately, and overrides "
            "app.env until the field is cleared. It is never shown again."
        ),
    }


@router.get("/providers")
async def providers(request: Request) -> dict[str, Any]:
    """Current provider configuration, by count and source. No values."""
    authorise(request)
    return _providers_view(get_settings())


@router.post("/providers")
async def set_providers(request: Request, body: ProviderSettings) -> dict[str, Any]:
    """Set or clear provider settings, and apply them without a restart.

    The values are written to the data directory, not to `app.env`: the
    container cannot write that file, it is passed in at start. Both are
    outside git, and the data directory is outside every backup — the backup
    script copies two databases by name rather than archiving the volume.
    """
    authorise(request)
    incoming = body.as_environment()
    if not incoming:
        raise HTTPException(422, "Nothing to change.")

    kept = provider_store.read()
    for name, value in incoming.items():
        if str(value).strip():
            kept[name] = value
        else:
            kept.pop(name, None)

    provider_store.write(kept)
    # Names only. A log line that carried the value would put credentials in
    # exactly the place this whole design keeps them out of.
    log.info("operator.providers_updated", extra={"names": sorted(incoming)})
    return _providers_view(get_settings())


@router.post("/providers/check")
async def check_providers(request: Request) -> dict[str, Any]:
    """Probe every configured key once and report by position.

    Costs one small request per key, so it runs when an operator asks rather
    than on every page load.
    """
    authorise(request)
    await provider_health.check(get_settings())
    return _providers_view(get_settings())
