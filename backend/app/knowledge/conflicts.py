"""When two government documents say different things about the same rule.

Government corpora are not consistent snapshots. A department's folder holds the
1998 Rules and the 2019 amendment; a G.O. is revised and both revisions are
circulated; a circular is withdrawn and the withdrawal notice is filed beside
it. Retrieval will happily return passages from two of these at once, and the
analyst will then produce one tidy answer assembled from both — which is the
worst possible outcome, because the seam is invisible. An officer reading "the
fee is fifty rupees" cannot tell it came from a document that stopped being
operative in 2019.

So conflicts are detected before the analyst reads anything, and handled in one
of exactly two ways:

    preferred_newer   One document is demonstrably current and the other is
                      not — it is superseded, or it is plainly older by date.
                      The older one is set aside as evidence and RECORDED, so
                      the version history survives and an officer can see what
                      the rule used to be.

    undetermined      Nothing establishes which is in force. Both are kept,
                      neither is treated as settled, and a warning is attached
                      that says so in as many words.

What is never done is the third thing: silently merging them.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from .schema import Chunk, Conflict

log = logging.getLogger(__name__)


def _parsed(value: str | None) -> date | None:
    """A date from the metadata, in any of the shapes ingestion records."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    match = re.match(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if match:
        day, month, year = (int(g) for g in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return date(int(match.group(0)), 1, 1) if match else None


def topic_of(chunk: Chunk) -> str | None:
    """What a passage is ABOUT, coarsely, for spotting two takes on one rule.

    Deliberately coarse. The purpose is to notice that two documents address the
    same instrument, not to classify them: an Act name, a Rule name or a G.O.
    number is enough, and a document carrying none of those is not compared at
    all — better to miss a conflict than to invent one between two unrelated
    circulars that happen to share a department.
    """
    for value in (chunk.act_name, chunk.rule_name):
        if value and value.strip():
            return _normalise(value)
    if chunk.government_order_number:
        return f"go:{_normalise(chunk.government_order_number)}"
    return None


# A year at the end of an instrument's name. "The Sample Licensing Rules,
# 1998" and "..., 2019" are two versions of ONE instrument, and that is the
# single most common way a conflict actually appears in a departmental
# folder. Left in the topic they were treated as unrelated documents and
# never compared at all, which made this whole module inert for the case it
# exists for.
_TRAILING_YEAR = re.compile(r"[\s,]+(?:19|20)\d{2}\s*$")


def _normalise(value: str) -> str:
    text = _TRAILING_YEAR.sub("", str(value).strip())
    return re.sub(r"[^a-z0-9஀-௿]+", " ", text.lower()).strip()


def _year_in(value: str | None) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    return int(match.group(0)) if match else None


def resolve(chunks: list[Chunk]) -> tuple[list[Chunk], list[Conflict]]:
    """Set aside superseded evidence, and flag what cannot be resolved.

    Returns the chunks the analyst may read, and every conflict found. A chunk
    that is set aside is not deleted from the world — it appears in the
    conflict's `older` source, which is what "preserve version history" means
    here.
    """
    by_topic: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        topic = topic_of(chunk)
        if topic:
            by_topic.setdefault(topic, []).append(chunk)

    conflicts: list[Conflict] = []
    set_aside: set[str] = set()

    for topic, group in by_topic.items():
        documents: dict[str, Chunk] = {}
        for chunk in group:
            # One representative per document: the best-scoring passage.
            current = documents.get(chunk.document_id)
            if current is None or chunk.score > current.score:
                documents[chunk.document_id] = chunk
        if len(documents) < 2:
            continue

        representatives = list(documents.values())
        for index, first in enumerate(representatives):
            for second in representatives[index + 1:]:
                conflict = _compare(topic, first, second)
                if conflict is None:
                    continue
                conflicts.append(conflict)
                if conflict.resolution == "preferred_newer" and conflict.superseded_id:
                    set_aside.add(conflict.superseded_id)

    if set_aside:
        log.info("knowledge.superseded_set_aside",
                 extra={"documents": len(set_aside), "conflicts": len(conflicts)})

    kept = [c for c in chunks if c.document_id not in set_aside]
    # Never hand back nothing. If every document on a topic was set aside — two
    # superseded revisions and no live one — the evidence is thin rather than
    # absent, and the conflict warning already says so.
    return (kept or chunks), conflicts


def _compare(topic: str, first: Chunk, second: Chunk) -> Conflict | None:
    """Two documents on one instrument. Which, if either, is in force?"""
    # 1. One is explicitly retired. This is the only signal a person actually
    #    asserted, so it outranks every inference from a date.
    if first.superseded != second.superseded:
        newer, older = (second, first) if first.superseded else (first, second)
        return Conflict(
            topic=topic,
            resolution="preferred_newer",
            superseded_id=older.document_id,
            newer=newer.to_source(),
            older=older.to_source(),
            message=(f"'{older.document_title}' is marked superseded. "
                     f"'{newer.document_title}' is used instead."),
        )

    # 2. Both live. Dates decide, when there are two of them to compare.
    first_date = _parsed(first.date) or _year_date(first)
    second_date = _parsed(second.date) or _year_date(second)
    if first_date and second_date and first_date != second_date:
        newer, older = ((first, second) if first_date > second_date
                        else (second, first))
        return Conflict(
            topic=topic,
            resolution="preferred_newer",
            superseded_id=older.document_id,
            newer=newer.to_source(),
            older=older.to_source(),
            message=(f"Two documents cover this. '{newer.document_title}' is the "
                     f"later one and is used; '{older.document_title}' is kept "
                     f"for reference."),
        )

    # 3. Nothing establishes which is in force. Both stay, neither is settled,
    #    and the officer is told that in as many words.
    return Conflict(
        topic=topic,
        resolution="undetermined",
        superseded_id=None,
        newer=first.to_source(),
        older=second.to_source(),
        message=(f"'{first.document_title}' and '{second.document_title}' both "
                 f"cover this, and neither carries a date or version that shows "
                 f"which is currently in force. Both are shown; neither should "
                 f"be relied on until the office confirms which applies."),
    )


def _year_date(chunk: Chunk) -> date | None:
    """A year read off the title or version, when there is no date field.

    "The Tamil Nadu ... Rules, 2019" carries its year in its name, and a corpus
    assembled from PDFs often has nothing else.
    """
    year = (_year_in(chunk.version) or _year_in(chunk.act_name)
            or _year_in(chunk.rule_name) or _year_in(chunk.document_title))
    return date(year, 1, 1) if year else None


def corpus_conflicts(documents: list[dict]) -> list[dict]:
    """Conflicts that exist in the corpus itself, before anybody searches it.

    `resolve` answers "are these retrieved passages in conflict?". This answers
    the operator's question instead: "does the corpus I have loaded contain two
    documents covering the same instrument?" — which is worth knowing at load
    time rather than the first time a citizen's grievance happens to retrieve
    both.

    Takes the document rows `KnowledgeStore.documents()` returns, so it reads no
    chunk text and costs nothing to call on a status page.
    """
    by_topic: dict[str, list[dict]] = {}
    for row in documents:
        name = (row.get("act_name") or row.get("rule_name") or "").strip()
        topic = _normalise(name) if name else (
            f"go:{_normalise(row['government_order_number'])}"
            if row.get("government_order_number") else None)
        if topic:
            by_topic.setdefault(topic, []).append(row)

    out: list[dict] = []
    for topic, group in by_topic.items():
        if len(group) < 2:
            continue
        live = [r for r in group if not r.get("superseded")]
        dated = [r for r in live if _parsed(r.get("date")) or _year_in(r.get("version"))
                 or _year_in(r.get("title"))]

        if len(live) < 2:
            # One live document and some retired ones: that is version history
            # working, not a conflict.
            continue

        resolvable = len(dated) == len(live) and len({
            (_parsed(r.get("date")) or date(_year_in(r.get("title")) or 1900, 1, 1))
            for r in live}) == len(live)
        out.append({
            "topic": topic,
            "documents": [{"document_id": r["document_id"], "title": r["title"],
                           "date": r.get("date"), "authority": r.get("authority")}
                          for r in live],
            "resolution": "preferred_newer" if resolvable else "undetermined",
            "message": (
                f"{len(live)} live documents cover the same instrument."
                + ("" if resolvable else
                   " None of them carries a date or version that establishes "
                   "which is in force — retrieval will show both and warn.")),
        })
    return out
