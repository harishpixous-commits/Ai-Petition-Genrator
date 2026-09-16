"""Finding the right passages, twice, and agreeing on an order.

Two indexes answer every query. FTS5 matches words — it finds "G.O. (Ms) No.
145" and the exact spelling of an Act, which is what a citation needs and what
an embedding is worst at. The vector index matches meaning — it finds the
encroachment rule when the citizen wrote about a neighbour building on their
land, which is what a grievance needs and what a word index cannot do.

Their rankings are combined by reciprocal rank fusion: each result scores
`1/(k + rank)` in each list and the scores add. Rank rather than raw score,
because BM25 and cosine distance are not on the same scale and normalising them
against each other is guesswork that changes with the corpus. A passage both
halves like outranks one that only one half found, which is exactly the
behaviour wanted.

Then two government-specific rules:

* **Official outranks unofficial at equal relevance.** A gazette and somebody's
  summary of it are not interchangeable, and the fusion score alone cannot tell
  them apart.
* **A superseded document is excluded** — unless nothing live answers at all, in
  which case it is returned marked, because "this was the rule until 2019" is
  sometimes the true answer.

Retrieval never writes anything and never sees a session.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ..config import Settings, get_settings
from .schema import Chunk
from .store import KnowledgeStore

log = logging.getLogger(__name__)

# The constant in reciprocal rank fusion. 60 is the value from the original
# paper and it behaves well here: high enough that the top few ranks are not
# overwhelmingly dominant, low enough that agreement still matters.
RRF_K = 60

# How close a chunk must be to survive on vector evidence alone, on the
# `1/(1+distance)` scale the store returns. Unit-length vectors make this a
# cosine threshold of roughly 0.66 — near enough to be about the same subject,
# far enough out that "the least unrelated thing in the corpus" does not pass.
_VECTOR_FLOOR = 0.55

# Boost applied to a fused score by authority. Small on purpose — it decides
# ties and near-ties, it does not float an irrelevant official document above a
# relevant departmental one.
_AUTHORITY_WEIGHT = {
    "official": 1.15,
    "departmental": 1.10,
    "unknown": 1.0,
    "external": 0.85,
}

_STOPWORDS = frozenset("""
a an and are as at be but by for from has have i in is it its of on or that the
to was were will with my me our we you your this there their they them not no
please sir madam kindly request help problem issue
""".split())


@dataclass
class Retrieved:
    chunks: list[Chunk]
    query: str
    lexical_hits: int = 0
    vector_hits: int = 0
    used_superseded: bool = False

    @property
    def empty(self) -> bool:
        return not self.chunks

    @property
    def has_official(self) -> bool:
        return any(c.authority in ("official", "departmental") for c in self.chunks)


def keywords(text: str, limit: int = 24) -> list[str]:
    """The words worth searching for.

    Tamil is why this splits on separators instead of matching `\\w+`: Tamil
    combining marks are Mn/Mc and are not word characters, so `\\w+` cuts
    கோரிக்கை into fragments. Splitting on whitespace and punctuation keeps
    every script intact.
    """
    parts = re.split(r"[\s,.;:!?()\[\]{}\"'“”‘’/\\|<>+=*#@~`^&%$–—_-]+", str(text or ""))
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        word = part.strip()
        if len(word) < 2:
            continue
        lowered = word.lower()
        if lowered in _STOPWORDS or lowered in seen:
            continue
        seen.add(lowered)
        out.append(word)
        if len(out) >= limit:
            break
    return out


class Retriever:
    """Hybrid retrieval over the corpus."""

    def __init__(self, store: KnowledgeStore, provider=None,
                 settings: Settings | None = None) -> None:
        self.store = store
        self.provider = provider
        self.s = settings or get_settings()

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        candidates: int | None = None,
    ) -> Retrieved:
        limit = limit or self.s.knowledge_context_chunks
        candidates = candidates or self.s.knowledge_candidates
        text = " ".join(keywords(query))
        if not text:
            return Retrieved(chunks=[], query=query)

        lexical = self.store.lexical(text, limit=candidates)
        vector: list[Chunk] = []
        if self.provider is not None and getattr(self.provider, "semantic", False):
            vector = await self._vector(query, candidates)
        elif self.provider is not None and self.store._vector_search:
            # A non-semantic provider still helps a little — it clusters shared
            # vocabulary — but it is nearly the lexical index again, so it gets
            # a shorter list and contributes less to the fusion.
            vector = await self._vector(query, max(4, candidates // 3))

        semantic = bool(getattr(self.provider, "semantic", False))
        fused = self._fuse(lexical, vector, semantic=semantic)[:limit]
        used_superseded = False

        if not fused:
            # Nothing live matched. A retired document is better than silence,
            # provided it is labelled — `Chunk.superseded` travels into the
            # Source and the officer sees it.
            retired = self.store.lexical(text, limit=limit, include_superseded=True)
            if retired:
                fused = [c for c in retired if c.superseded][:limit]
                used_superseded = bool(fused)

        return Retrieved(
            chunks=fused,
            query=query,
            lexical_hits=len(lexical),
            vector_hits=len(vector),
            used_superseded=used_superseded,
        )

    async def _vector(self, query: str, limit: int) -> list[Chunk]:
        try:
            vectors = await self.provider.embed([query])
        except Exception as exc:  # noqa: BLE001
            # Half of hybrid retrieval going down is a quality loss, not an
            # outage. The lexical half answers on its own.
            log.info("retrieve.embed_failed", extra={"error": str(exc)[:160]})
            return []
        return self.store.vector(vectors[0], limit=limit) if vectors else []

    @staticmethod
    def _fuse(lexical: list[Chunk], vector: list[Chunk],
              semantic: bool = True) -> list[Chunk]:
        """Combine the two rankings, and throw away what neither really found.

        Nearest-neighbour search has no idea whether anything is near. Ask a
        vector index for eight results and it returns eight, so a pension
        grievance against a corpus of two land documents comes back holding both
        of them — and the analyst is then handed excerpts about encroachment to
        reason about a pension. Nothing downstream fabricates a citation from
        that, but it wastes the one model call and it is how the wrong Act ends
        up named beside the right grievance.

        So a chunk the word index did not match at all has to earn its place:
        it must be close, not merely closest. And when the embedder is the
        hashed local one, it cannot earn it at all — its "similarity" is word
        overlap measured worse than FTS5 already measured it.
        """
        lexical_ids = {c.chunk_id for c in lexical}
        scores: dict[str, float] = {}
        best: dict[str, Chunk] = {}

        for ranking in (lexical, vector):
            for rank, chunk in enumerate(ranking, start=1):
                if chunk.chunk_id not in lexical_ids:
                    if not semantic or chunk.score < _VECTOR_FLOOR:
                        continue
                scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
                best.setdefault(chunk.chunk_id, chunk)

        out = []
        for chunk_id, score in scores.items():
            chunk = best[chunk_id].model_copy()
            chunk.score = score * _AUTHORITY_WEIGHT.get(chunk.authority, 1.0)
            out.append(chunk)
        out.sort(key=lambda c: c.score, reverse=True)
        return out

    async def search_many(self, queries: list[str], *,
                          limit: int | None = None) -> Retrieved:
        """Several queries, one merged result, no duplicates.

        The analyst asks a few narrow questions rather than one broad one — the
        department, then the Act, then the procedure — and this keeps the best
        rank a chunk achieved under any of them.
        """
        limit = limit or self.s.knowledge_context_chunks
        merged: dict[str, Chunk] = {}
        lexical_hits = vector_hits = 0
        used_superseded = False
        for query in queries:
            result = await self.search(query, limit=limit)
            lexical_hits += result.lexical_hits
            vector_hits += result.vector_hits
            used_superseded = used_superseded or result.used_superseded
            for chunk in result.chunks:
                existing = merged.get(chunk.chunk_id)
                if existing is None or chunk.score > existing.score:
                    merged[chunk.chunk_id] = chunk
        chunks = sorted(merged.values(), key=lambda c: c.score, reverse=True)[:limit]
        return Retrieved(
            chunks=chunks,
            query=" | ".join(queries),
            lexical_hits=lexical_hits,
            vector_hits=vector_hits,
            used_superseded=used_superseded,
        )
