"""What the knowledge layer returns, and what a citation has to carry.

Everything here is typed on purpose. The alternative — a model writing prose
that something downstream parses for an Act name — is how a petition ends up
citing a statute nobody can find, and the officer who receives it has no way to
tell that from a real one.

A finding that cannot name where it came from is not returned. That is the
whole design in one sentence.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Said, word for word, when retrieval found nothing that clears the bar. The
# brief specifies this sentence; it is not paraphrased anywhere.
UNVERIFIED = ("Relevant official information could not be verified from the "
              "available knowledge base.")

UNVERIFIED_TA = ("கிடைக்கக்கூடிய அறிவுத் தளத்திலிருந்து தொடர்புடைய அதிகாரப்பூர்வத் "
                 "தகவலைச் சரிபார்க்க முடியவில்லை.")

DocumentType = Literal[
    "act", "rule", "government_order", "circular", "guideline",
    "procedure", "faq", "webpage", "other",
]

# Where something came from, and how much weight it carries. An official
# gazette and a blog post are not the same kind of thing and must never be
# ranked as though they were.
Authority = Literal["official", "departmental", "external", "unknown"]


class Source(BaseModel):
    """Where a finding came from. Enough for an officer to go and look."""

    # Which document, as an identity rather than a name. Two genuinely
    # different documents can carry the SAME title — a circular reissued, a
    # departmental template filled in twice — and keying anything on the title
    # silently merged them: a conflict between two versions of one rule showed
    # only one of the two passages, which is the one thing the conflict warning
    # exists to prevent.
    document_id: str | None = None
    document_title: str
    document_type: DocumentType = "other"
    authority: Authority = "unknown"
    department: str | None = None
    act_name: str | None = None
    rule_name: str | None = None
    government_order_number: str | None = None
    section: str | None = None
    page_number: int | None = None
    date: str | None = None
    source_url: str | None = None
    # The passage the finding actually rests on, so a reader can check the
    # claim against the words rather than against a document name.
    excerpt: str = ""
    # Reciprocal-rank-fusion score. Exposed because an officer deciding whether
    # to trust a thin result should be able to see that it was thin.
    relevance: float = 0.0

    @property
    def is_official(self) -> bool:
        return self.authority in ("official", "departmental")


class Finding(BaseModel):
    """One statement, with the sources that support it.

    `sources` is never empty for a finding that is returned. The grounding
    check drops anything that cannot point at a retrieved passage, and a
    finding left with no sources is dropped with it.
    """

    value: str
    sources: list[Source] = Field(default_factory=list)


class Conflict(BaseModel):
    """Two government documents covering the same instrument.

    Recorded rather than resolved away. `older` is kept even when it has been
    set aside, because "what the rule used to be" is a real question a citizen
    can be asking, and because an officer is entitled to see that the corpus
    held two answers.
    """

    topic: str
    # preferred_newer: one is demonstrably current, the other is not.
    # undetermined:    nothing establishes which is in force. Neither is settled.
    resolution: Literal["preferred_newer", "undetermined"] = "undetermined"
    # The document whose passages were set aside as evidence, if any.
    superseded_id: str | None = None
    newer: Source | None = None
    older: Source | None = None
    message: str = ""

    @property
    def needs_office_confirmation(self) -> bool:
        return self.resolution == "undetermined"


class PetitionAnalysis(BaseModel):
    """What the knowledge layer tells the petition assistant.

    Every field is optional because every field may genuinely be unknown, and
    an unknown that is left blank is honest where a guess is not.
    """

    department: Finding | None = None
    petition_category: Finding | None = None
    applicable_acts: list[Finding] = Field(default_factory=list)
    applicable_rules: list[Finding] = Field(default_factory=list)
    government_orders: list[Finding] = Field(default_factory=list)
    responsible_authority: Finding | None = None
    processing_hierarchy: list[Finding] = Field(default_factory=list)
    required_documents: list[Finding] = Field(default_factory=list)
    processing_steps: list[Finding] = Field(default_factory=list)
    transfer_process: Finding | None = None
    closure_process: Finding | None = None

    # True when nothing cleared the bar. The message below is then the only
    # thing worth showing.
    unverified: bool = True
    message: str = UNVERIFIED
    # Every distinct source behind any finding, for the officer's reference
    # list. Deduplicated, best first.
    sources: list[Source] = Field(default_factory=list)
    # How the answer was reached, for an operator reading the logs. Carries no
    # citizen text.
    queries_run: list[str] = Field(default_factory=list)
    retrieved_chunks: int = 0
    # Set when some of what is shown came from outside the indexed corpus.
    # Those findings are marked in the UI and are never treated as settled law.
    includes_external: bool = False
    # Documents that disagree, and what was done about it. Never empty-and-
    # ignored: an unresolved conflict is shown as a warning, because an answer
    # assembled from two versions of a rule is worse than no answer.
    conflicts: list[Conflict] = Field(default_factory=list)
    # Plain sentences for the officer's panel, from conflicts that could not be
    # resolved and anything else that qualifies what is shown.
    warnings: list[str] = Field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return bool(
            self.department or self.petition_category or self.applicable_acts
            or self.applicable_rules or self.government_orders
            or self.responsible_authority or self.processing_hierarchy
            or self.required_documents or self.processing_steps
            or self.transfer_process or self.closure_process
        )


class Chunk(BaseModel):
    """A passage of a government document, as stored and as retrieved."""

    chunk_id: str
    document_id: str
    text: str
    ordinal: int = 0
    # Everything below is metadata carried from the document it came from, so a
    # retrieved chunk can cite itself without a second lookup.
    document_title: str = ""
    document_type: DocumentType = "other"
    authority: Authority = "unknown"
    department: str | None = None
    act_name: str | None = None
    rule_name: str | None = None
    government_order_number: str | None = None
    section: str | None = None
    page_number: int | None = None
    date: str | None = None
    source_url: str | None = None
    version: str | None = None
    superseded: bool = False
    score: float = 0.0

    def to_source(self, excerpt_chars: int = 320) -> Source:
        excerpt = " ".join(self.text.split())
        if len(excerpt) > excerpt_chars:
            excerpt = excerpt[:excerpt_chars].rsplit(" ", 1)[0] + "…"
        return Source(
            document_id=self.document_id,
            document_title=self.document_title or self.document_id,
            document_type=self.document_type,
            authority=self.authority,
            department=self.department,
            act_name=self.act_name,
            rule_name=self.rule_name,
            government_order_number=self.government_order_number,
            section=self.section,
            page_number=self.page_number,
            date=self.date,
            source_url=self.source_url,
            excerpt=excerpt,
            relevance=round(self.score, 4),
        )
