"""The knowledge layer, wired into the service as one advisory capability.

`extensions/registry.py` already describes the seam this fills — *"maps a
grievance to the Act, Rules and the authority with jurisdiction; needs the legal
corpus and must cite"* — and already enforces the contract: advisory, optional,
bounded, and its output marked unverified. Nothing here re-invents that.

Two things this module adds on top.

**It runs once per grievance, not once per message.** Analysis is triggered when
the grievance is first recorded and the result is held against a hash of that
text, so the eight or ten turns that follow — corrections, the age, the mobile
number, the confirmation — cost nothing. A grievance that is edited hashes
differently and is analysed again, which is the one case where re-running is
the right answer.

**The cache holds no citizen text.** The key is a digest, the value is the
analysis, and an analysis is made of document titles and section numbers. It
lives in memory for the life of the process and is never written to disk.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Any

from ..config import Settings, get_settings
from .analyst import Analyst
from .retrieve import Retriever
from .schema import PetitionAnalysis
from .store import KnowledgeStore

log = logging.getLogger(__name__)

_CACHE_LIMIT = 256


class KnowledgeService:
    """One store, one retriever, one analyst, shared across sessions.

    Built lazily: a deployment with no corpus and no key should not pay for
    opening a database and probing a provider at import time.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self._store: KnowledgeStore | None = None
        self._analyst: Analyst | None = None
        self._cache: OrderedDict[str, PetitionAnalysis] = OrderedDict()
        self._lock = asyncio.Lock()

    # -- lazy construction ---------------------------------------------- #

    @property
    def store(self) -> KnowledgeStore:
        if self._store is None:
            from . import embeddings as embedding_providers

            provider = embedding_providers.build(self.s)
            self._store = KnowledgeStore(
                self.s.knowledge_path,
                dimension=provider.dimension,
                provider=provider.name,
            )
            self._analyst = Analyst(Retriever(self._store, provider, self.s), self.s)
        return self._store

    @property
    def analyst(self) -> Analyst:
        _ = self.store      # builds both
        assert self._analyst is not None
        return self._analyst

    @property
    def enabled(self) -> bool:
        return bool(self.s.knowledge_enabled)

    def status(self) -> dict[str, Any]:
        """For the health endpoint and the officer panel's empty state."""
        if not self.enabled:
            return {"enabled": False, "ready": False, "documents": 0, "chunks": 0}
        try:
            stats = self.store.stats()
        except Exception as exc:  # noqa: BLE001
            log.warning("knowledge.status_failed", extra={"error": str(exc)[:160]})
            return {"enabled": True, "ready": False, "error": "unavailable",
                    "documents": 0, "chunks": 0}
        return {"enabled": True, **stats}

    # -- analysis -------------------------------------------------------- #

    @staticmethod
    def _key(grievance: str, subject: str) -> str:
        return hashlib.sha256(f"{subject}\x00{grievance}".encode()).hexdigest()

    async def analyse(self, grievance: str, *, subject: str = "",
                      names: list[str] | None = None) -> PetitionAnalysis | None:
        """The analysis for this grievance, or None when there is nothing to say.

        None rather than an empty analysis when the layer is off or the corpus
        is empty, so the caller can leave the panel out entirely instead of
        showing a refusal for a question nobody could have answered.
        """
        text = " ".join(str(grievance or "").split())
        if not self.enabled or len(text) < 12:
            return None

        key = self._key(text, subject)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        async with self._lock:
            # Checked again: two turns can arrive together and analysing the
            # same grievance twice is a wasted model call, not a bug.
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            try:
                if not self.store.stats().get("ready"):
                    return None
                analysis = await asyncio.wait_for(
                    self.analyst.analyse(text, subject=subject, names=names),
                    timeout=self.s.knowledge_timeout_ms / 1000 + 2,
                )
            except TimeoutError:
                log.info("knowledge.timeout")
                return None
            except Exception as exc:  # noqa: BLE001
                # Advisory means advisory. A failure here is a missing panel,
                # never a petition that does not get produced.
                log.warning("knowledge.failed", extra={"error": str(exc)[:200]})
                return None

            self._cache[key] = analysis
            while len(self._cache) > _CACHE_LIMIT:
                self._cache.popitem(last=False)
            log.info("knowledge.analysed",
                     extra={"chunks": analysis.retrieved_chunks,
                            "queries": len(analysis.queries_run),
                            "findings": analysis.has_findings,
                            "sources": len(analysis.sources)})
            return analysis

    def register_capability(self) -> None:
        """Attach to `extensions.registry`, once."""
        register()

    def forget(self, grievance: str, subject: str = "") -> None:
        """Drop a cached analysis. Called when the grievance is corrected."""
        self._cache.pop(self._key(" ".join(str(grievance or "").split()), subject), None)


_service: KnowledgeService | None = None


def service(settings: Settings | None = None) -> KnowledgeService:
    global _service
    if _service is None:
        _service = KnowledgeService(settings)
    return _service


class ActIdentification:
    """The `act_identification` capability named in `extensions/registry.py`.

    The registry caps a capability at five seconds, which is less than a cold
    analysis needs. That is the right cap and it is left alone: by the time a
    petition is being enriched the analysis has usually been computed already
    and this returns the cached one immediately. If it has not, the capability
    returns nothing and the petition is produced without it — which is the
    contract, written in that file.
    """

    name = "act_identification"

    async def enrich(self, petition: dict[str, Any]) -> dict[str, Any] | None:
        grievance = str(petition.get("grievance") or "")
        subject = str(petition.get("subject") or "")
        analysis = await service().analyse(grievance, subject=subject)
        if analysis is None or not analysis.has_findings:
            return None
        return analysis.model_dump(exclude_none=True)


def register() -> None:
    """Attach the capability, once, if it is not already there."""
    from ..extensions.registry import registry

    if "act_identification" in registry.names:
        return
    registry.register(ActIdentification())
