"""The agent: bounded retrieval, then a grounding check that drops inventions.

The loop is deliberately small. Plan queries, retrieve, and if the model says it
is missing something specific, retrieve once or twice more — `knowledge_max_steps`
caps it, and the whole thing sits inside a timeout on top of that. An agent that
can search until it finds something is an agent that will eventually find
something whether or not it is there.

Then the part that matters.

**Every Act, Rule, Government Order number, department and authority returned is
checked back against the text that was actually retrieved.** Not against the
model's confidence, not against a citation the model wrote — against the
characters in the chunks. Anything that does not appear there is deleted before
the result leaves this module, and a finding whose citations are all deleted is
deleted with it. When nothing survives, the answer is one sentence:

    Relevant official information could not be verified from the available
    knowledge base.

This is the same discipline as `_numbers_are_grounded` in `compose`, which
removes any drafted sentence containing a figure the citizen never gave. On a
government form, a plausible invention is worse than an absence: an officer can
act on a blank, but a fabricated G.O. number sends a citizen to a counter that
has never heard of it.

Prose findings — the steps of a procedure, the documents to attach — are checked
differently, by requiring most of their content words to come from the cited
passage. Demanding a verbatim substring there would reject every correct summary
and leave the panel permanently empty, which teaches an officer to ignore it.

Citizen text is masked before it reaches a model, and only the retrieved chunks
are sent — never a whole document.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

from ..config import Settings, get_settings
from ..services.llm import LLMUnavailable, chat_json
from ..services.mask import mask_pii
from .conflicts import resolve as resolve_conflicts
from .retrieve import _STOPWORDS, Retriever, keywords
from .schema import (
    UNVERIFIED,
    Chunk,
    Conflict,
    Finding,
    PetitionAnalysis,
    Source,
)

log = logging.getLogger(__name__)

# Fields whose values must appear verbatim in a retrieved passage. These are the
# things the brief says must never be invented.
_STRICT_FIELDS = frozenset({
    "applicable_acts", "applicable_rules", "government_orders",
    "responsible_authority", "department", "processing_hierarchy",
})
# Fields checked by content-word overlap instead.
_PROSE_FIELDS = frozenset({
    "required_documents", "processing_steps", "transfer_process",
    "closure_process", "petition_category",
})

_LIST_FIELDS = (
    "applicable_acts", "applicable_rules", "government_orders",
    "processing_hierarchy", "required_documents", "processing_steps",
)
_SINGLE_FIELDS = (
    "department", "petition_category", "responsible_authority",
    "transfer_process", "closure_process",
)

# Share of a prose finding's meaningful words that must come from its citation,
# after stopwords are removed. Measured against the alternative: at 0.6 with
# stopwords counted, "Appeal to the Tribunal within ninety days" scored 0.67
# against a passage that says the Revenue Divisional Officer and thirty days —
# the filler carried an invented authority and an invented deadline past the
# check. Both guards below exist because of that one case.
_OVERLAP_FLOOR = 0.75

# Spelled-out quantities. A deadline is the most damaging thing a summary can
# get wrong and "ninety" is not a digit, so the digit rule alone never saw it.
_NUMBER_WORDS = frozenset("""
zero one two three four five six seven eight nine ten eleven twelve thirteen
fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty
sixty seventy eighty ninety hundred thousand lakh lakhs crore crores
first second third fourth fifth sixth seventh eighth ninth tenth
""".split())

_SYSTEM = """You are a records analyst in a Tamil Nadu government office.

You are given numbered EXCERPTS from official documents and a summary of a
citizen's grievance. Report only what the excerpts say.

Rules, in order of importance:
1. Never state an Act, Rule, Government Order number, department, authority,
   deadline or procedure that does not appear in the excerpts. If the excerpts
   do not say it, leave the field out. An empty answer is correct and useful.
2. Every item you return must cite the excerpt numbers it came from. An item
   with no citation is discarded.
3. Quote names, numbers and section references exactly as the excerpt writes
   them. Do not expand abbreviations, correct spellings or reformat numbers.
4. Do not infer. "Revenue Department handles land" is not in the excerpts unless
   an excerpt says it.
5. If the excerpts are about something else entirely, return nothing.

If you need a different search to answer, put up to three short search phrases
in "need_search" and return nothing else."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "department": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}},
        "petition_category": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}},
        "responsible_authority": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}},
        "transfer_process": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}},
        "closure_process": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}},
        "applicable_acts": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}}},
        "applicable_rules": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}}},
        "government_orders": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}}},
        "processing_hierarchy": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}}},
        "required_documents": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}}},
        "processing_steps": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string"}, "cites": {"type": "array",
                                                   "items": {"type": "integer"}}}}},
        "need_search": {"type": "array", "items": {"type": "string"}},
    },
}


# --------------------------------------------------------------------------- #
# Grounding
# --------------------------------------------------------------------------- #

_PUNCTUATION = re.compile(r"[\s.,;:()\[\]{}'\"“”‘’/\\|_\-–—]+")


def normalise(text: str) -> str:
    """Case-folded, punctuation-flattened, for containment tests.

    G.O. (Ms) No. 145 and GO Ms No 145 are the same order written twice. The
    check has to see through spacing and full stops without seeing through the
    number itself.
    """
    return _PUNCTUATION.sub(" ", str(text or "").lower()).strip()


def _content_words(text: str) -> set[str]:
    return {w for w in normalise(text).split() if len(w) > 2}


def _haystack(chunks: list[Chunk]) -> str:
    """Everything a citation may rest on: the passage and its own metadata."""
    parts = []
    for chunk in chunks:
        parts.append(chunk.text)
        for value in (chunk.document_title, chunk.act_name, chunk.rule_name,
                      chunk.department, chunk.government_order_number, chunk.section):
            if value:
                parts.append(str(value))
    return normalise(" \n ".join(parts))


def grounded(value: str, chunks: list[Chunk], strict: bool) -> bool:
    """Is this statement actually in the cited passages?"""
    candidate = normalise(value)
    if not candidate or not chunks:
        return False
    hay = _haystack(chunks)

    if strict:
        if candidate in hay:
            return True
        # A name may be cited with a trailing year or bracketed qualifier the
        # passage writes differently. Every content word of the claim must still
        # be present, and any digit in it must be present exactly — which is
        # what stops a fabricated order number from passing.
        words = _content_words(value)
        if not words:
            return False
        hay_words = set(hay.split())
        if not words <= hay_words:
            return False
        return all(number in hay for number in re.findall(r"\d+", candidate))

    hay_words = set(hay.split())

    # Two hard requirements before the overlap score is even looked at, because
    # a score computed over ordinary words cannot protect the words that matter.
    #
    # Every proper noun must be present. "Tribunal" is a body that either exists
    # in the passage or was invented, and a summary has no business naming one
    # the document does not. Over-rejection is the safe direction here: the cost
    # is a missing line in an advisory panel, and the cost of the other error is
    # a citizen sent to an authority that has no such jurisdiction.
    # Written without a regex on purpose. A word-boundary escape has twice
    # been mangled into a literal backspace on its way into this repository,
    # and a pattern that silently matches nothing turns this guard off
    # without failing anything. Splitting cannot be corrupted that way.
    #
    # The first token is skipped: it is capitalised because it begins the
    # sentence, not because it names anything. Scripts without case - Tamil
    # among them - are not checked here and rest on the overlap rule below.
    for token in str(value).replace("-", " ").split()[1:]:
        word = token.strip(".,;:()[]{}\"'")
        if len(word) > 2 and word[:1].isupper() \
                and normalise(word) not in hay_words:
            return False
    # Every quantity must be present, written out or in digits.
    for token in normalise(value).split():
        if token in _NUMBER_WORDS and token not in hay_words:
            return False
    if not all(number in hay for number in re.findall(r"\d+", candidate)):
        return False

    words = {w for w in _content_words(value) if w not in _STOPWORDS}
    if not words:
        return False
    return len(words & hay_words) / len(words) >= _OVERLAP_FLOOR


# --------------------------------------------------------------------------- #
# The analyst
# --------------------------------------------------------------------------- #

@dataclass
class _Draft:
    value: str
    cites: list[int]


class Analyst:
    """Grievance in, cited analysis out — or the refusal sentence."""

    def __init__(self, retriever: Retriever, settings: Settings | None = None) -> None:
        self.retriever = retriever
        self.s = settings or get_settings()

    async def analyse(self, grievance: str, *, subject: str = "",
                      names: list[str] | None = None) -> PetitionAnalysis:
        deadline = time.monotonic() + self.s.knowledge_timeout_ms / 1000
        queries = plan_queries(grievance, subject)
        retrieved = await self.retriever.search_many(queries)
        queries_run = list(queries)

        if retrieved.empty:
            return PetitionAnalysis(queries_run=queries_run, retrieved_chunks=0)

        # Two versions of the same Rule must never be read as one. Superseded
        # and plainly-older documents are set aside HERE, before the model sees
        # anything, so it cannot assemble a tidy answer across the seam; what
        # cannot be resolved becomes a warning instead of a silent merge.
        chunks, conflicts = resolve_conflicts(retrieved.chunks)

        drafts: dict[str, list[_Draft]] = {}
        steps = max(1, self.s.knowledge_max_steps)

        for step in range(steps):
            if time.monotonic() > deadline:
                log.info("knowledge.timed_out", extra={"step": step})
                break
            payload = await self._ask(grievance, subject, chunks, names or [],
                                      deadline=deadline)
            if payload is None:
                # No model: fall back to what the documents themselves assert.
                return _with_conflicts(
                    self._from_metadata(chunks, queries_run), conflicts)

            more = [str(q)[:120] for q in (payload.get("need_search") or [])][:3]
            drafts = _read_drafts(payload)
            if drafts or not more or step == steps - 1:
                break
            # One refinement, on the model's own terms, then we stop asking.
            queries_run.extend(more)
            extra = await self.retriever.search_many(more)
            chunks = _merge(chunks, extra.chunks, self.s.knowledge_context_chunks)

        analysis = self._build(drafts, chunks, queries_run, len(retrieved.chunks))
        if not analysis.has_findings:
            # The model found nothing it could cite. The documents still carry
            # their own metadata, and that is grounded by construction.
            analysis = self._from_metadata(chunks, queries_run)
        return _with_conflicts(analysis, conflicts)

    # -- model ---------------------------------------------------------- #

    async def _ask(self, grievance: str, subject: str, chunks: list[Chunk],
                   names: list[str], deadline: float) -> dict | None:
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms < 2500:
            return None

        excerpts = []
        for index, chunk in enumerate(chunks, start=1):
            head = chunk.document_title or chunk.document_id
            marks = [head]
            if chunk.section:
                marks.append(chunk.section)
            if chunk.page_number:
                marks.append(f"page {chunk.page_number}")
            if chunk.superseded:
                marks.append("SUPERSEDED")
            # Only the retrieved passage travels, never the document.
            excerpts.append(f"[{index}] ({' — '.join(marks)})\n{chunk.text.strip()}")

        # The grievance is masked here as well as inside `chat_json`. Belt and
        # braces, because this prompt is assembled by hand.
        summary = mask_pii(" ".join(str(grievance or "").split())[:1200], names)
        user = (
            f"GRIEVANCE (verbatim, for context only — do not rewrite it):\n{summary}\n"
            + (f"\nSUBJECT: {mask_pii(subject, names)}\n" if subject else "")
            + "\nEXCERPTS:\n" + "\n\n".join(excerpts)
        )
        try:
            return await chat_json(
                system=_SYSTEM, user=user, schema=_SCHEMA,
                max_tokens=1400,
                timeout_ms=min(self.s.compose_timeout_ms, remaining_ms),
                budget_ms=remaining_ms,
                names=names, settings=self.s, retry_pass=False,
            )
        except LLMUnavailable as exc:
            log.info("knowledge.no_model", extra={"reason": str(exc)[:160]})
            return None
        except Exception as exc:  # noqa: BLE001
            log.info("knowledge.analysis_failed", extra={"error": str(exc)[:200]})
            return None

    # -- assembly ------------------------------------------------------- #

    def _build(self, drafts: dict[str, list[_Draft]], chunks: list[Chunk],
               queries_run: list[str], retrieved_count: int) -> PetitionAnalysis:
        analysis = PetitionAnalysis(queries_run=queries_run,
                                    retrieved_chunks=retrieved_count)
        kept: list[Source] = []

        for field, items in drafts.items():
            strict = field in _STRICT_FIELDS
            findings: list[Finding] = []
            for draft in items:
                cited = [chunks[i - 1] for i in draft.cites
                         if 1 <= i <= len(chunks)]
                if not cited:
                    log.info("knowledge.dropped_uncited", extra={"field": field})
                    continue
                if not grounded(draft.value, cited, strict=strict):
                    log.info("knowledge.dropped_ungrounded",
                             extra={"field": field, "strict": strict,
                                    "value": draft.value[:80]})
                    continue
                sources = [c.to_source() for c in cited]
                findings.append(Finding(value=draft.value.strip(), sources=sources))
                kept.extend(sources)
            if not findings:
                continue
            if field in _LIST_FIELDS:
                setattr(analysis, field, findings)
            else:
                setattr(analysis, field, findings[0])

        analysis.sources = _dedupe(kept)
        analysis.unverified = not analysis.has_findings
        analysis.message = "" if analysis.has_findings else UNVERIFIED
        analysis.includes_external = any(s.authority == "external"
                                         for s in analysis.sources)
        return analysis

    @staticmethod
    def _from_metadata(chunks: list[Chunk], queries_run: list[str]) -> PetitionAnalysis:
        """What the corpus asserts about itself, with no model involved.

        A document indexed as the Tamil Nadu Land Encroachment Act carries that
        name in its own metadata, put there at ingestion by a person or read off
        the document's first page. Reporting it is retrieval, not generation,
        so it needs no grounding check — it *is* the ground.
        """
        analysis = PetitionAnalysis(queries_run=queries_run,
                                    retrieved_chunks=len(chunks))
        acts: dict[str, Finding] = {}
        rules: dict[str, Finding] = {}
        orders: dict[str, Finding] = {}
        department: Finding | None = None

        for chunk in chunks:
            source = chunk.to_source()
            if chunk.act_name and chunk.act_name not in acts:
                acts[chunk.act_name] = Finding(value=chunk.act_name, sources=[source])
            if chunk.rule_name and chunk.rule_name not in rules:
                rules[chunk.rule_name] = Finding(value=chunk.rule_name, sources=[source])
            if chunk.government_order_number and chunk.government_order_number not in orders:
                label = f"G.O. No. {chunk.government_order_number}"
                orders[label] = Finding(value=label, sources=[source])
            if chunk.department and department is None:
                department = Finding(value=chunk.department, sources=[source])

        analysis.applicable_acts = list(acts.values())
        analysis.applicable_rules = list(rules.values())
        analysis.government_orders = list(orders.values())
        analysis.department = department
        analysis.sources = _dedupe([c.to_source() for c in chunks])
        analysis.unverified = not analysis.has_findings
        analysis.message = "" if analysis.has_findings else UNVERIFIED
        return analysis



def _with_conflicts(analysis: PetitionAnalysis,
                    conflicts: list[Conflict]) -> PetitionAnalysis:
    """Attach the conflicts, and turn the unresolved ones into warnings.

    A resolved conflict is recorded but not warned about — setting aside a
    document that says on its face that it has been superseded is the system
    working, not a caveat. An UNRESOLVED one is warned about every time, because
    the honest answer there is "the corpus holds two of these and cannot tell
    you which is in force".
    """
    analysis.conflicts = conflicts
    analysis.warnings = [c.message for c in conflicts if c.needs_office_confirmation]
    return analysis


def plan_queries(grievance: str, subject: str = "") -> list[str]:
    """A few narrow searches, built without a model.

    Deterministic on purpose: query planning is the step most likely to be
    reached when nothing is configured, and it costs a round trip to ask a model
    for words that are already in the sentence.
    """
    words = keywords(f"{subject} {grievance}", limit=18)
    if not words:
        return []
    core = " ".join(words[:12])
    queries = [core]
    if len(words) > 4:
        # A second, tighter query over the most distinctive words, which pulls
        # the exact-name matches that the broad one buries.
        queries.append(" ".join(sorted(words[:10], key=len, reverse=True)[:5]))
    if subject.strip():
        queries.append(" ".join(keywords(subject, limit=8)))
    return [q for q in dict.fromkeys(queries) if q.strip()]


def _read_drafts(payload: dict) -> dict[str, list[_Draft]]:
    """Typed structure out of the model's answer, with nothing inferred."""
    out: dict[str, list[_Draft]] = {}

    def one(item) -> _Draft | None:
        if not isinstance(item, dict):
            return None
        value = str(item.get("value") or "").strip()
        if not value or len(value) > 400:
            return None
        cites = [int(c) for c in (item.get("cites") or [])
                 if isinstance(c, (int, float)) or str(c).isdigit()]
        return _Draft(value=value, cites=cites)

    for field in _SINGLE_FIELDS:
        draft = one(payload.get(field))
        if draft:
            out[field] = [draft]
    for field in _LIST_FIELDS:
        items = payload.get(field) or []
        if not isinstance(items, list):
            continue
        drafts = [d for d in (one(i) for i in items[:10]) if d]
        if drafts:
            out[field] = drafts
    return out


def _merge(first: list[Chunk], second: list[Chunk], limit: int) -> list[Chunk]:
    seen = {c.chunk_id for c in first}
    out = list(first)
    for chunk in second:
        if chunk.chunk_id not in seen:
            out.append(chunk)
            seen.add(chunk.chunk_id)
    out.sort(key=lambda c: c.score, reverse=True)
    return out[:limit]


def _dedupe(sources: list[Source]) -> list[Source]:
    seen: dict[tuple, Source] = {}
    for source in sources:
        key = (source.document_id or source.document_title,
               source.section, source.page_number)
        if key not in seen or source.relevance > seen[key].relevance:
            seen[key] = source
    ordered = sorted(seen.values(),
                     key=lambda s: (s.is_official, s.relevance), reverse=True)
    return ordered[:12]


async def analyse(grievance: str, *, subject: str = "", names: list[str] | None = None,
                  settings: Settings | None = None) -> PetitionAnalysis:
    """Convenience entry point, bounded by the configured timeout."""
    from . import embeddings as embedding_providers
    from .store import KnowledgeStore

    s = settings or get_settings()
    provider = embedding_providers.build(s)
    store = KnowledgeStore(s.knowledge_path, dimension=provider.dimension,
                           provider=provider.name)
    analyst = Analyst(Retriever(store, provider, s), s)
    try:
        return await asyncio.wait_for(
            analyst.analyse(grievance, subject=subject, names=names),
            timeout=s.knowledge_timeout_ms / 1000 + 2,
        )
    except TimeoutError:
        log.info("knowledge.hard_timeout")
        return PetitionAnalysis()
