"""Turning text into vectors, behind one interface.

Two providers, and the second one is the point. `gemini` does the real work
when a key is configured; `local` is a hashed bag-of-words that needs nothing
and never fails. The whole test suite of this service runs with no model
reachable, on purpose, and a knowledge layer that simply stopped existing in
that deployment would be a knowledge layer nobody could test.

The local embedder is not pretending to be a trained model. It is a cheap
lexical projection that puts documents sharing vocabulary near each other, and
it is honest about that: `EmbeddingProvider.semantic` says whether the vectors
mean anything beyond word overlap, and retrieval leans on the lexical index
instead when they do not.

Adding a provider is a class and a name in `build()`. Nothing else in the
knowledge layer knows which one is in use, and the stored dimension is recorded
with the corpus so a provider change is detected rather than silently mixing
vector spaces.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from typing import Protocol

from ..config import Settings, get_settings
from ..services.mask import mask_pii

log = logging.getLogger(__name__)

_WORD = re.compile(r"[^\W\d_]{2,}|\d+", re.UNICODE)


class EmbeddingProvider(Protocol):
    name: str
    dimension: int
    # False for anything that is really lexical wearing a vector costume.
    semantic: bool

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per input, in order. Must not raise for an empty list."""
        ...


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(str(text or ""))]


class LocalEmbeddings:
    """Hashed bag-of-words. No network, no model, no failure mode.

    Words are hashed into a fixed number of buckets and weighted by log term
    frequency, then the vector is L2-normalised so cosine distance behaves.
    Two documents about pawnbroker licensing land near each other because they
    use the same words — which is most of what is needed to keep the pipeline
    working when nothing is reachable, and is why `semantic` is False.
    """

    name = "local"
    semantic = False

    def __init__(self, dimension: int = 512) -> None:
        self.dimension = dimension

    def _vector(self, text: str) -> list[float]:
        counts: dict[int, float] = {}
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "big") % self.dimension
            counts[bucket] = counts.get(bucket, 0.0) + 1.0
        if not counts:
            return [0.0] * self.dimension
        vector = [0.0] * self.dimension
        for bucket, count in counts.items():
            vector[bucket] = 1.0 + math.log(count)
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


#: Statuses worth waiting out rather than failing on. 429 is the one that
#: matters for a bulk ingest; the 5xx family is ordinary transient trouble.
_RETRYABLE = frozenset({401, 402, 403, 429, 500, 502, 503, 504})
_RETRY_ATTEMPTS = 6
_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 60.0


class GeminiEmbeddings:
    """`gemini-embedding-001`, one request per text, with key rotation.

    Text is masked before it leaves. Documents in the corpus are government
    reference material and carry no citizen data, but a QUERY is built from a
    grievance, and a citizen who types their Aadhaar inside a complaint must
    not have it sent to an embedding endpoint any more than to a chat one.
    """

    name = "gemini"
    semantic = True

    def __init__(self, settings: Settings, dimension: int = 1536) -> None:
        self.s = settings
        self.dimension = dimension
        self.model = settings.knowledge_embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import httpx

        keys = self.s.gemini_key_list
        if not keys:
            raise RuntimeError("No Gemini key is configured for embeddings.")

        out: list[list[float]] = []
        active = 0
        url = (f"{self.s.gemini_base_url.rstrip('/')}/models/"
               f"{self.model}:embedContent")
        async with httpx.AsyncClient(timeout=self.s.knowledge_embed_timeout_ms / 1000) as client:
            for text in texts:
                payload = {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": mask_pii(text)[:8000]}]},
                    # Asking for a smaller vector keeps the index a quarter of
                    # the size at no measurable cost to recall on a corpus this
                    # shape, and the endpoint supports it directly.
                    "outputDimensionality": self.dimension,
                }
                vector = None
                # ROTATING KEYS IS NOT ENOUGH ON A BULK INGEST, and this cost
                # a real corpus. Indexing the Tamil Nadu Acts is ~8,000 chunks
                # and therefore ~8,000 requests; the per-minute quota is
                # reached within the first document, every key then answers
                # 429 together, and this gave up immediately. The result was
                # a corpus where 687 of 8,069 chunks had vectors and the rest
                # had none — lexical search still worked, so nothing looked
                # broken, and cross-language retrieval quietly did not.
                #
                # So when EVERY key is rate-limited, wait and try again rather
                # than failing the chunk. The delay doubles, and `Retry-After`
                # is honoured when the service sends one, because a server
                # saying how long to wait knows better than a formula.
                delay = _RETRY_BASE_SECONDS
                for attempt in range(_RETRY_ATTEMPTS):
                    retry_after = 0.0
                    exhausted = False
                    for offset in range(len(keys)):
                        key = keys[(active + offset) % len(keys)]
                        try:
                            response = await client.post(
                                url, headers={"x-goog-api-key": key},
                                json=payload)
                        except httpx.HTTPError as exc:
                            log.info("embed.transport_failed",
                                     extra={"error": str(exc)[:140]})
                            exhausted = True
                            continue
                        if response.status_code < 400:
                            vector = ((response.json() or {}).get("embedding")
                                      or {}).get("values")
                            active = (active + offset) % len(keys)
                            break
                        if response.status_code in _RETRYABLE:
                            exhausted = True
                            header = response.headers.get("retry-after", "")
                            if header.strip().isdigit():
                                retry_after = max(retry_after,
                                                  float(header.strip()))
                            continue
                        raise RuntimeError(
                            f"Embedding rejected: HTTP {response.status_code}")
                    if vector or not exhausted:
                        break
                    if attempt == _RETRY_ATTEMPTS - 1:
                        break
                    pause = retry_after or delay
                    log.info("embed.backing_off",
                             extra={"attempt": attempt + 1,
                                    "seconds": round(pause, 1)})
                    await asyncio.sleep(pause)
                    delay = min(delay * 2, _RETRY_MAX_SECONDS)
                if not vector:
                    raise RuntimeError(
                        "No embedding key answered after "
                        f"{_RETRY_ATTEMPTS} attempts.")
                # Normalise here so distance is comparable whatever the
                # provider returns.
                norm = math.sqrt(sum(v * v for v in vector)) or 1.0
                out.append([v / norm for v in vector])
        return out


def build(settings: Settings | None = None) -> EmbeddingProvider:
    """The configured provider, falling back rather than failing.

    A deployment that names a provider it cannot reach gets the local one and a
    warning in the log, because the alternative is an ingestion command that
    dies halfway through a department's document set.
    """
    s = settings or get_settings()
    choice = (s.knowledge_embedding_provider or "auto").lower()

    if choice in ("local", "off"):
        return LocalEmbeddings(dimension=s.knowledge_local_dimension)
    if choice in ("gemini", "auto"):
        if s.gemini_key_list and s.allow_external_ai:
            return GeminiEmbeddings(s, dimension=s.knowledge_embedding_dimension)
        if choice == "gemini":
            log.warning("embed.provider_unavailable",
                        extra={"asked": "gemini", "using": "local",
                               "reason": "no key, or external AI is disabled"})
        return LocalEmbeddings(dimension=s.knowledge_local_dimension)

    log.warning("embed.unknown_provider", extra={"asked": choice, "using": "local"})
    return LocalEmbeddings(dimension=s.knowledge_local_dimension)
