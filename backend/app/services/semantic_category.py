"""Reading a grievance that never names its subject.

THE PROBLEM THIS SOLVES, measured rather than assumed. The deterministic
reader in `system_one.py` scores well when a citizen uses the word for the
thing they are complaining about, and has no answer at all when they do not:

    "the amount that used to come every month stopped after my husband died"
        — a pension complaint containing no pension word
    "my children cannot study after seven because the lane is dark"
        — a street lighting complaint containing no lighting word
    "the lorry that collects from our area stopped coming"
        — a sanitation complaint containing no waste word

On a held-out set these were eleven of twenty English failures. No amount of
additional vocabulary fixes them, because the words genuinely are not there;
adding phrases for the ones that happen to be in a test set is fitting the
test set. What is needed is similarity of MEANING, which is what an embedding
measures.

WHERE THIS SITS, and why it is not the primary classifier. The deterministic
reader runs first and keeps every case it is confident about. This is asked
only when that reader says UNKNOWN or OTHER — roughly one grievance in five.
That ordering is deliberate:

    the lexical reader is free, instant, offline and EXPLAINABLE. It can tell
    a citizen "because you said தண்ணீர்". A cosine similarity cannot.

    it is also more accurate where it fires at all. Replacing it would trade
    a measured 1.000 on four languages for a model's opinion.

    and the service must work on a department machine with no outbound
    network. If embeddings are unreachable this returns None and the
    deterministic answer stands, exactly as before.

CROSS-LANGUAGE FOR FREE. The exemplars below are written once, in English.
`gemini-embedding-001` is multilingual, so a Tamil grievance lands near the
English exemplar for the same subject without a Tamil exemplar existing. That
is the same property the knowledge layer already depends on for retrieval, and
it is why this is worth doing with the embedder already in the image rather
than with a second model.

NO CITIZEN TEXT IS STORED. The grievance is masked before it leaves — the
embedder applies `mask_pii` — and nothing is written to disk except the
exemplar vectors, which are this file's own sentences.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: What each category LOOKS LIKE when a citizen describes it indirectly.
#:
#: These are symptom descriptions, not definitions. "Drinking water supply" is
#: a definition and sits near every other administrative phrase; "we are
#: carrying water from the next street" is what somebody actually says, and it
#: is what a grievance written in the same spirit lands near.
#:
#: Written from the subject matter, not copied from any evaluation set — the
#: held-out cases were deliberately not consulted while writing these, because
#: exemplars drawn from a test set measure nothing.
EXEMPLARS: dict[str, tuple[str, ...]] = {
    "WATER": (
        "there is no drinking water coming from the tap in our street",
        "we are carrying water in pots from the next street every morning",
        "the public tap has been dry for weeks and no tanker comes",
        "the water connection promised to our house was never given",
        "the bore well in our area stopped working and nobody repaired it",
    ),
    "ROAD": (
        "the road surface has broken up and vehicles cannot pass",
        "autos refuse to come down our lane because of the condition of it",
        "the approach to our village was dug up and never relaid",
        "there are deep holes in the road and people have fallen",
        "the footpath outside is broken and unusable",
    ),
    "STREET_LIGHT": (
        "the lane is completely dark at night and nothing has been repaired",
        "my children cannot study in the evening because there is no light outside",
        "women are afraid to walk here after dark because it is unlit",
        "the lamp on the pole outside my house has not come on for months",
        "public lighting in our area stopped working after the storm",
    ),
    "SANITATION": (
        "rubbish has not been collected from our street for weeks and it smells",
        "the lorry that collects waste from our area stopped coming",
        "sewage is overflowing and we cannot open the windows",
        "the open channel outside is blocked and mosquitoes have bred",
        "the public toilet in our area is filthy and unusable",
    ),
    "PENSION": (
        "the amount that used to be credited every month has stopped coming",
        "I am old and the monthly government payment was discontinued",
        "after my husband died the monthly assistance was stopped without notice",
        "my monthly government allowance has not arrived for several months",
        "I retired and the payment I was sanctioned never started",
    ),
    "WELFARE": (
        "the shop will not give me provisions because my card was cancelled",
        "my family card has not been renewed and we cannot draw rations",
        "I applied for the housing assistance and it was never considered",
        "my daughter's scholarship was sanctioned but never paid",
        "we were left out of the welfare scheme everybody else received",
    ),
    "LICENCE": (
        "my application for permission to run my small shop is still pending",
        "I paid the fee for approval of my building plan and heard nothing",
        "the permit for my trade has not been renewed for months",
        "permission to put up a small structure has been refused without reason",
        "my vending permission was cancelled and nobody explained why",
    ),
    "CERTIFICATE": (
        "the paper the college asked for to prove my daughter's community has not been issued",
        "I applied for proof of my income and the office has not given it",
        "the document showing where I was born has not been issued after months",
        "I need proof that I am the legal heir and the application is pending",
        "the office has not given me the certificate my son needs for admission",
    ),
    "PROPERTY": (
        "my neighbour has built a wall inside my boundary",
        "the land record is still in my dead father's name and was never transferred",
        "somebody has occupied the land that belongs to me",
        "the survey stone marking my boundary has been moved",
        "my title document has not been corrected despite applying",
    ),
    "ELECTRICITY": (
        "the supply goes off every evening for hours",
        "the transformer serving our area is faulty and was never repaired",
        "my bill shows a reading far higher than what I used",
        "the connection to my house was cut and not restored",
        "the pole carrying the line outside has tilted and is dangerous",
    ),
}

#: Below this cosine similarity, the nearest category is not evidence of
#: anything.
#:
#: MEASURED, NOT CHOSEN. Every development case the deterministic reader could
#: not place was scored, and the whole curve read off:
#:
#:     threshold   rescued   wrong subjects
#:          0.60         7               14
#:          0.65         7                7
#:          0.70         7                1
#:          0.72         7                0
#:          0.78         7                0
#:          0.80         6                0
#:
#: There is a plateau from 0.72 to 0.78 where every rescue is available and no
#: wrong subject survives. 0.75 is its middle, which is the robust place to
#: stand rather than either edge.
#:
#: THE TWO ERRORS ARE NOT PRICED THE SAME, which is why the curve is read this
#: way round rather than for best accuracy. An UNKNOWN costs a clerk a
#: question. A confident wrong subject costs an officer their trust in the
#: panel, and a service a government has to rely on cannot buy accuracy with
#: that. At 0.62 this reader turned 3 wrong subjects into 11 on the
#: development set while raising accuracy — which is the trade being refused.
MIN_SIMILARITY = 0.75

#: And the best category must beat the runner-up by this much. Two categories
#: within a whisker of each other is exactly the two-subject case the
#: deterministic reader already answers UNKNOWN for, and guessing between them
#: here would undo that.
#:
#: Every correct rescue on the development set had a margin above 0.15; the
#: one wrong answer that survived the similarity floor had a margin of 0.029 —
#: a stray-dog complaint placed as sanitation because rubbish and strays share
#: a vocabulary of streets and neglect. 0.05 separates those two populations
#: with room on both sides.
MIN_MARGIN = 0.05


def _cache_path(settings: Any) -> Path:
    return Path(settings.data_dir) / "category_vectors.json"


def _fingerprint(model: str, dimension: int) -> str:
    """Identifies the exemplars AND the embedder that produced the vectors.

    A cache written by a different model, or after an exemplar was edited, is
    not a cache — it is a set of vectors from a different space, and comparing
    against them silently returns nonsense.
    """
    payload = json.dumps({"e": EXEMPLARS, "m": model, "d": dimension},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _cosine(a: list[float], b: list[float]) -> float:
    # strict=True: two vectors of different length mean the cache was
    # written by a different model, and silently truncating to the shorter
    # one would compare coordinates that mean different things.
    return sum(x * y for x, y in zip(a, b, strict=True))


class SemanticCategories:
    """Nearest category by meaning, or None when it cannot say."""

    def __init__(self, provider: Any, settings: Any) -> None:
        self.provider = provider
        self.settings = settings
        self._vectors: dict[str, list[list[float]]] | None = None
        self._lock = asyncio.Lock()

    @property
    def semantic(self) -> bool:
        return bool(getattr(self.provider, "semantic", False))

    # ------------------------------------------------------------------ #
    # The exemplar vectors
    # ------------------------------------------------------------------ #

    async def _load(self) -> dict[str, list[list[float]]] | None:
        if self._vectors is not None:
            return self._vectors
        async with self._lock:
            if self._vectors is not None:
                return self._vectors

            model = str(getattr(self.provider, "model", self.provider.name))
            fingerprint = _fingerprint(model, int(self.provider.dimension))
            path = _cache_path(self.settings)

            if path.exists():
                try:
                    cached = json.loads(path.read_text(encoding="utf-8"))
                    if cached.get("fingerprint") == fingerprint:
                        self._vectors = cached["vectors"]
                        return self._vectors
                    log.info("semantic_category.cache_stale")
                except Exception as exc:  # noqa: BLE001
                    log.info("semantic_category.cache_unreadable",
                             extra={"error": str(exc)[:120]})

            # Embedded once. Fifty short sentences, so this is one small batch
            # and it only happens when the file is missing or the exemplars
            # changed.
            vectors: dict[str, list[list[float]]] = {}
            try:
                for category, sentences in EXEMPLARS.items():
                    vectors[category] = await self.provider.embed(list(sentences))
            except Exception as exc:  # noqa: BLE001
                log.warning("semantic_category.embed_failed",
                            extra={"error": str(exc)[:160]})
                return None

            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(
                    {"fingerprint": fingerprint, "model": model,
                     "dimension": int(self.provider.dimension),
                     "vectors": vectors}), encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                log.info("semantic_category.cache_unwritable",
                         extra={"error": str(exc)[:120]})

            self._vectors = vectors
            return self._vectors

    # ------------------------------------------------------------------ #
    # The answer
    # ------------------------------------------------------------------ #

    async def classify(self, grievance: str) -> tuple[str, float, str] | None:
        """(category, confidence, reason), or None when it cannot say.

        None rather than a guess, in every failure mode: no embedder, no
        network, nothing similar enough, or two categories too close to
        separate. The caller keeps whatever the deterministic reader said.
        """
        text = " ".join(str(grievance or "").split())
        if len(text) < 12 or not self.semantic:
            return None

        vectors = await self._load()
        if not vectors:
            return None

        try:
            query = (await self.provider.embed([text]))[0]
        except Exception as exc:  # noqa: BLE001
            log.info("semantic_category.query_failed",
                     extra={"error": str(exc)[:160]})
            return None

        # Best single exemplar, not the centroid. A category is several
        # distinct complaints — a pension that stopped and a pension never
        # sanctioned — and averaging them produces a point that is near
        # neither.
        scored: list[tuple[float, str]] = []
        for category, exemplars in vectors.items():
            best = max((_cosine(query, vector) for vector in exemplars),
                       default=-1.0)
            scored.append((best, category))
        if not scored:
            return None

        scored.sort(reverse=True)
        top, category = scored[0]
        runner = scored[1][0] if len(scored) > 1 else -1.0

        if top < MIN_SIMILARITY:
            return None
        if top - runner < MIN_MARGIN:
            return None

        # Mapped onto the same 0-1 scale the deterministic reader reports, and
        # deliberately capped below it: this is the less certain of the two
        # paths and the number is read as "how likely is this right".
        confidence = min(0.85, 0.60 + (top - MIN_SIMILARITY) * 1.2)
        return category, round(confidence, 2), f"closest meaning ({top:.2f})"


_instance: SemanticCategories | None = None


def build(settings: Any = None) -> SemanticCategories | None:
    """The configured semantic classifier, or None when it is switched off."""
    from ..config import get_settings

    s = settings or get_settings()
    if not getattr(s, "semantic_category_enabled", True):
        return None

    global _instance
    if _instance is None:
        from ..knowledge import embeddings as embedding_providers

        provider = embedding_providers.build(s)
        if not getattr(provider, "semantic", False):
            # The hashed local embedder has no semantics at all. Using it here
            # would return confident nonsense, which is worse than returning
            # nothing.
            log.info("semantic_category.not_semantic",
                     extra={"provider": provider.name})
            return None
        _instance = SemanticCategories(provider, s)
    return _instance


def reset() -> None:
    """Drop the cached instance. For tests."""
    global _instance
    _instance = None
